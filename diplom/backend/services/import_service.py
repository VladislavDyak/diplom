
from django.db import transaction
from ..models import Shop, Category, ProductInfo, Parameter, ProductParameter, Product
from ..serializer import ImportDataSerializer


def import_shop_data(data, user_id):
    serializer = ImportDataSerializer(data=data)
    if not serializer.is_valid():
        return {
            'Status': False,
            'Message': f'Ошибка валидации данных {serializer.errors}',
        }

    validated_data = serializer.validated_data
    try:

        with transaction.atomic():
            shop,_ = Shop.objects.get_or_create(name=validated_data['shop'],
                                                user_id=user_id)

            for category in validated_data['categories']:
                category_obj, _ = Category.objects.get_or_create(
                    external_id=category['external_id'],
                    defaults={'name': category['name']},
                )
                category_obj.shops.add(shop)

            ProductInfo.objects.filter(shop_id=shop.id).delete()

            goods_count = 0

            for item in validated_data['goods']:

                category_id = int(item.get('category'))

                category, _ = Category.objects.get_or_create(external_id=category_id)

                product, _ = Product.objects.get_or_create(
                    name=item['name'],
                    category=category,
                )

                product_info = ProductInfo.objects.create(
                    product=product,
                    external_id=item['id'],
                    name=item['name'],
                    model=item['model'],
                    price=item['price'],
                    quantity=item['quantity'],
                    shop = shop,
                    price_rrc = item.get('price_rrc', 0),
                )

                for parameter_name, parameter_value in item.get('parameters', {}).items():
                    parameter_obj, _ = Parameter.objects.get_or_create(name=parameter_name,)

                    ProductParameter.objects.create(
                        product_info=product_info,
                        parameter=parameter_obj,
                        value=parameter_value,
                    )

                goods_count += 1

            return {
                'Status': True,
                'Message': f'Импорт YAML завершён. Загружено {goods_count} товаров.',
                'Shop_name': shop.name,
            }
    except Exception as e:
        return {
            'Status': False,
            'Message': f'Ошибка сохранения {str(e)}',
        }


