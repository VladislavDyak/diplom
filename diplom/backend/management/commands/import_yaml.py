import yaml

from django.core.management import BaseCommand
from django.db import transaction

from ...models import ProductInfo, Parameter, User, Shop, Category, Product, ProductParameter


class Command(BaseCommand):
    help = 'Импортирует данные из файла YAML'

    def add_arguments(self, parser):
        parser.add_argument(
            'file_path',
            type=str,
            help='Путь до файла YAML',
        )

        parser.add_argument(
            '--user-id',
            type=int,
            required=True,
            help='ID пользователя, которому нужно обновить данные по магазину',
        )

    @transaction.atomic
    def handle(self, *args, **options):

        user_id = options['user_id']
        file_path = options['file_path']

        try:

            if not User.objects.filter(id=user_id).exists():
                self.stderr.write(self.style.ERROR(f'Пользователя с ID {user_id} не найден'))
                return

            with open(file_path, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f)

        except FileNotFoundError:
            self.stderr.write(self.style.ERROR(f'Файл не найден: {file_path}'))
            return

        except yaml.YAMLError as e:
            self.stderr.write(self.style.ERROR(f'Ошибка парсинга YAML файла: {e}'))
            return

        if 'shop' not in data or 'categories' not in data or 'goods' not in data:
            self.stderr.write(self.style.ERROR(
                'Неверный формат файла YAML: отсутствуют поля shop, categories или goods')
            )

            return

        shop, _ = Shop.objects.get_or_create(
            name=data['shop'],
        )

        self.stdout.write(f'Магазин {shop.name} импортирован')

        for category in data['categories']:
            category,_ = Category.objects.get_or_create(
                id=category['id'],
                name=category['name'],
            )
            category.shops.add(shop)

        ProductInfo.objects.filter(shop_id=shop.id).delete()


        for item in data['goods']:

            category_id = int(item.get('category'))

            category, _ = Category.objects.get_or_create(id=category_id)

            product, _ = Product.objects.get_or_create(
                name = item['name'],
                category = category,
            )

            product_info = ProductInfo.objects.create(
                product = product,
                external_id = item['id'],
                name = item['name'],
                model = item['model'],
                price = item['price'],
                quantity = item['quantity'],
                shop = shop,
                price_rrc = item.get('price_rrc', 0),
            )

            for param_name, param_value in item.get('parameters', {}).items():
                parameter, _ = Parameter.objects.get_or_create(
                    name = param_name,
                )
                ProductParameter.objects.create(
                    product_info = product_info,
                    parameter = parameter,
                    value = str(param_value),
                )

        self.stdout.write(self.style.SUCCESS(f'Импорт завершён. Загружено {len(data['goods'])} товаров'))




