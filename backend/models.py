from django.db import models

# Create your models here.


class User(models.Model):

    email  = models.EmailField()
    company = models.CharField(max_length=100)
    position = models.CharField(max_length=100)
    username = models.CharField(max_length=100)
    type = models.CharField(max_length=100)

    class Meta:
        verbose_name = 'User'
        verbose_name_plural = 'Users'
        ordering = ['email']

class Shop(models.Model):

    name = models.CharField(max_length=100, unique=True)
    url = models.URLField()

    class Meta:
        verbose_name = 'Shop'
        verbose_name_plural = 'Shops'
        ordering = ['name']

    @property
    def dict(self):
        return {'id': self.id, 'name': self.name, 'url': self.url}


class Category(models.Model):

    shop = models.ManyToManyField(Shop)
    name = models.CharField(max_length=100, unique=True)

    class Meta:
        verbose_name = 'Category'
        verbose_name_plural = 'Categories'
        ordering = ['name']

    @property
    def dict(self):
        return {'id': self.id, 'name': self.name, 'shop': self.shop}

class Product(models.Model):

    category = models.ManyToManyField(Category)
    name = models.CharField(max_length=100, unique=True)

    class Meta:
        verbose_name = 'Product'
        verbose_name_plural = 'Products'
        ordering = ['name']

    @property
    def dict(self):
        return {'id': self.id, 'name': self.name, 'category': self.category, 'shop': self.shop}


class ProductInfo(models.Model):

    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    name = models.CharField(max_length=100, unique=True)
    quantity = models.IntegerField()
    price = models.FloatField()
    price_rcc = models.FloatField()

    class Meta:
        verbose_name = 'ProductInfo'
        verbose_name_plural = 'ProductInfos'
        ordering = ['name']


    @property
    def dict(self):
        return {'id': self.id, 'product': self.product, 'name': self.name, 'quantity': self.quantity, 'price': self.price, 'price_rcc': self.price_rcc}


class Parameter(models.Model):
    id = models.AutoField(primary_key=True)
    name = models.CharField(max_length=100, unique=True)

    class Meta:
        verbose_name = 'Parameter'
        verbose_name_plural = 'Parameters'
        ordering = ['name']

class ProductParameter(models.Model):
    product_info = models.ForeignKey(ProductInfo, on_delete=models.CASCADE)
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    value = models.FloatField()


    class Meta:
        verbose_name = 'ProductParameter'
        verbose_name_plural = 'ProductParameters'
        ordering = ['value']


class Order(models.Model):
    user = models.CharField(max_length=100)
    dt = models.DateTimeField(auto_now_add=True)
    status = models.BooleanField(default=False)


    class Meta:
        verbose_name = 'Order'
        verbose_name_plural = 'Orders'
        ordering = ['-dt']

class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE)
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    shop = models.ForeignKey(Shop, on_delete=models.CASCADE)
    quantity = models.IntegerField()

    class Meta:
        verbose_name = 'OrderItem'
        verbose_name_plural = 'OrderItems'
        ordering = ['-quantity']


class Contact(models.Model): #Модель заглушка дальше нужно будет доработать
    type = models.CharField(max_length=100)
    user = models.CharField(max_length=100)
    value = models.CharField(max_length=100)

    class Meta:
        verbose_name = 'Contact'
        verbose_name_plural = 'Contacts'
        ordering = ['-type']




