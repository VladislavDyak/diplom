from django.contrib.auth.base_user import BaseUserManager, AbstractBaseUser
from django.db import models
from django.utils.translation import gettext_lazy
from django_rest_passwordreset.tokens import get_token_generator


STATE_CHOICES = (
    ('basket', 'Статус корзины'),
    ('new', 'Новый'),
    ('confirmed', 'Подтверждён'),
    ('assembled', 'Собран'),
    ('sent', 'Отправлен'),
    ('delivered', 'Доставлен'),
    ('canceled', 'Отменён'),
)

USER_TYPE_CHOICES = (
    ('shop', 'Магазин'),
    ('buyer', 'Покупатель'),
)


class UserManager(BaseUserManager):
    use_migrations = True


    def _create_user(self, email, password, **extra_fields):

        if not email:
            raise ValueError('The given email must be set')

        email = self.normalize_email(email).lower()
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, email, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', False)
        extra_fields.setdefault('is_superuser', False)
        return self._create_user(email, password, **extra_fields)

    def create_superuser(self, email, password, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        if extra_fields.get('is_staff') is not True:
            raise ValueError('Superuser must have is_staff=True.')
        if extra_fields.get('is_superuser') is not True:
            raise ValueError('Superuser must have is_superuser=True.')
        return self._create_user(email, password, **extra_fields)


class User(AbstractBaseUser):

    REQUIRED_FIELDS = []
    objects = UserManager()
    USERNAME_FIELD = 'email'
    first_name = models.CharField(verbose_name='Имя', max_length=40, blank=True)
    last_name = models.CharField(verbose_name='Фамилия', max_length=40, blank=True)
    email = models.EmailField(gettext_lazy('email address'), unique=True)
    company = models.CharField(verbose_name='Компания', max_length=40, blank=True)
    position = models.CharField(verbose_name='Должность', max_length=40, blank=True)
    is_active = models.BooleanField(gettext_lazy('active'),
                                    default=False,
                                    help_text='Designates whether this user should be treated as active. '
                                              'Unselect this instead of deleting accounts.',
                                    )
    type = models.CharField(verbose_name='Тип пользователя', choices=USER_TYPE_CHOICES, max_length=5, default='buyer')

    def __str__(self):
        return f'{self.first_name} {self.last_name}'

    class Meta:
        verbose_name = "Пользователь"
        verbose_name_plural = "Список пользователей"
        ordering = ['email']


class Shop(models.Model):
    name = models.CharField(max_length=100, verbose_name='Название')
    url = models.URLField(verbose_name='Ссылка', blank=True, null=True)
    user = models.OneToOneField(User,
                                on_delete=models.CASCADE,
                                verbose_name= 'Пользователь',
                                blank=True,
                                null=True,
                                )
    state = models.BooleanField(verbose_name='Статус получения заказов', default=True)

    class Meta:
        verbose_name = "Магазин"
        verbose_name_plural = "Список магазинов"
        ordering = ['-name']

    def __str__(self):
        return self.name


class Category(models.Model):
    name = models.CharField(max_length=100, verbose_name='Название')
    shops = models.ManyToManyField(Shop, verbose_name='Магазины', related_name='categories', blank=True)

    class Meta:
        verbose_name = "Категории"
        verbose_name_plural = "Список категории"
        ordering = ['-name']

    def __str__(self):
        return self.name


class Product(models.Model):
    name = models.CharField(max_length=100, verbose_name='Название')
    category = models.ForeignKey(Category, verbose_name='Категория', on_delete=models.CASCADE, blank=True)


    class Meta:
        verbose_name = "Продукт"
        verbose_name_plural = "Список продуктов"
        ordering = ['-name']

    def __str__(self):
        return self.name


class ProductInfo(models.Model):
    name = models.CharField(max_length=100, verbose_name='Имя')
    model = models.CharField(max_length=100, verbose_name='Модель', blank=True)
    external_id = models.PositiveIntegerField(verbose_name='Внешний ID')
    product = models.ForeignKey(Product,
                                verbose_name='Продукт',
                                on_delete=models.CASCADE,
                                related_name='product_infos',
                                blank=True,
                                )
    shop = models.ForeignKey(Shop,
                             verbose_name='Магазин',
                             on_delete=models.CASCADE,
                             related_name='shop_infos',
                             blank=True,
                             )

    price = models.PositiveIntegerField(verbose_name='Цена')
    quantity = models.PositiveIntegerField(verbose_name='Количество')
    price_rrc = models.PositiveIntegerField(verbose_name='Рекомендуемая розничная цена')

    class Meta:
        verbose_name = "Информация о продукте"
        verbose_name_plural = "Информационный список о продуктах"
        constraints = [
            models.UniqueConstraint(fields=['product', 'shop', 'external_id'], name='unique_product_id'), ]


class Parameter(models.Model):
    name = models.CharField(max_length=100, verbose_name='Название')

    class Meta:
        verbose_name = "Имя параметра"
        verbose_name_plural = "Список параметров"
        ordering = ['-name']

    def __str__(self):
        return self.name


class ProductParameter(models.Model):
    product_info = models.ForeignKey(ProductInfo,
                                     verbose_name='Информация о продукте',
                                     on_delete=models.CASCADE,
                                     blank=True,)

    parameter = models.ForeignKey(Parameter,
                                  verbose_name='Параметр',
                                  related_name='product_parameters',
                                  on_delete=models.CASCADE,
                                  blank=True,
                                  )
    value = models.CharField(max_length=100, verbose_name='Значение')

    class Meta:
        verbose_name = "Параметр"
        verbose_name_plural = "Список параметров"
        constraints = [
            models.UniqueConstraint(fields=['product_info', 'parameter'], name='unique_product_parameter_id'),
        ]


class Contact(models.Model):
    user = models.ForeignKey(User,
                             verbose_name='Пользователь',
                             on_delete=models.CASCADE,
                             related_name='contacts',
                             blank=True,)
    city = models.CharField(max_length=100, verbose_name='Город')
    street = models.CharField(max_length=100, verbose_name='Улица')
    house = models.CharField(max_length=100, verbose_name='Дом')
    structure = models.CharField(max_length=100, verbose_name='Корпус', blank=True)
    building = models.CharField(max_length=100, verbose_name='Строение', blank=True)
    apartment = models.CharField(max_length=100, verbose_name='Квартира', blank=True)
    phone = models.CharField(max_length=100, verbose_name='Телефон')

    class Meta:
        verbose_name = "Контакты пользователя"
        verbose_name_plural = "Список контактов"
    def __str__(self):
        return f'{self.city} {self.street} {self.house}'


class Order(models.Model):
    user = models.ForeignKey(User,
                             verbose_name='Пользователь',
                             on_delete=models.CASCADE,
                             related_name='orders',
                             blank=True,)
    dt = models.DateTimeField(auto_now_add=True)
    state = models.CharField(max_length=15, verbose_name='Статус', choices = STATE_CHOICES)
    contact = models.ForeignKey(Contact,
                                verbose_name='Контакт',
                                on_delete=models.CASCADE,
                                blank=True,
                                null=True)

    class Meta:
        verbose_name = "Заказ"
        verbose_name_plural = "Список заказов"
        ordering = ['-dt']

    def __str__(self):
        return f'{self.state} {self.user} {str(self.dt)}'


class OrderItem(models.Model):
    order = models.ForeignKey(Order,
                              verbose_name='Заказ',
                              on_delete=models.CASCADE,
                              related_name='order_items',
                              blank=True,)
    product_info = models.ForeignKey(ProductInfo,
                                     verbose_name='Информация о продукте',
                                     on_delete=models.CASCADE,
                                     blank=True,)
    quantity = models.PositiveIntegerField(verbose_name='Количество')

    class Meta:
        verbose_name = "Заказанная позиция"
        verbose_name_plural = "Список заказанных позиций"
        constraints = [
            models.UniqueConstraint(fields=['product_info', 'order_id'], name='unique_product_info'),
        ]


class ConfirmEmailToken(models.Model):
    objects = models.Manager()
    class Meta:
        verbose_name = "Токен подтверждения Email"
        verbose_name_plural = "Токены подтверждения Email"


    @staticmethod
    def generate_token(email):
        return get_token_generator().generate_token(email)

    user = models.ForeignKey(User,
                                related_name='confirmation_tokens',
                                on_delete=models.CASCADE,
                                verbose_name=gettext_lazy('The user which is associated with this token'),)

    created_at = models.DateTimeField(auto_now_add=True,
                                        verbose_name='When was this token created')


    key = models.CharField(
        gettext_lazy('Key'),
        max_length=255,
        db_index=True,
        unique=True,
    )


    def save(self, *args, **kwargs):
        if not self.key:
            self.key = self.generate_token(email=self.user.email)
        return super(ConfirmEmailToken, self).save(*args, **kwargs)

    def __str__(self):
        return f'Password reset token for user {self.user}'
