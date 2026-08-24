from django.contrib.auth import authenticate
from django.contrib.auth.password_validation import validate_password
from django.core.validators import URLValidator
from django.db import IntegrityError
from django.db.models import Q, F, Sum
from django.http import JsonResponse
from requests.api import get
from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.exceptions import ValidationError
from rest_framework.generics import ListAPIView
from rest_framework.response import Response
from rest_framework.views import APIView
from ujson import loads
from yaml import load, Loader

from .models import ConfirmEmailToken, Category, Shop, Product, Order, OrderItem, ProductInfo, ProductParameter, \
    Contact
from .serializer import UserSerializer, CategorySerializer, ShopSerializer, ProductInfoSerializer, \
    OrderSerializer, OrderItemSerializer, ContactSerializer
from .signals import new_order



def strtobool(value: str) -> bool:
  value = value.lower()
  if value in ("y", "yes", "on", "1", "true", "t"):
    return True
  return False

class RegisterAccount(APIView):

    def post(self, request)->JsonResponse:
        required = {'first_name', 'last_name', 'email', 'password', 'company', 'position'}
        missing = set(required) - set(request.data.keys())

        if missing:
            return JsonResponse(
                {'Status':'Failure','message': f'Missing values {missing}'},
                status=status.HTTP_400_BAD_REQUEST)

        try:
            validate_password(request.data['password'])
        except ValidationError as e:
            return JsonResponse(
                {'Status':'Failure','message': f'Validation Error {str(e)}'},
                status=status.HTTP_400_BAD_REQUEST
            )

        serializer = UserSerializer(data=request.data)

        if not serializer.is_valid():
            return JsonResponse(
                {'Status':'Failure','message': f'Errors: {serializer.errors}'},
                status=status.HTTP_400_BAD_REQUEST
            )
        user = serializer.save()
        ConfirmEmailToken.objects.create(user=user)
        return JsonResponse(
            {'Status':'Success','message': f'Successfully registered! {user.pk}'},
            status=status.HTTP_201_CREATED
        )

        # if {'first_name', 'last_name', 'email', 'password', 'company', 'position'}.issubset(request.data):
        #
        #     try:
        #         validate_password(request.data['password'])
        #
        #     except ValidationError as pass_error:
        #         return JsonResponse({'error': f'Пароль не прошёл валидацию, ошибка {pass_error}'}, status=403)
        #
        #     else:
        #         user_serializer = UserSerializer(data=request.data)
        #
        #         if user_serializer.is_valid():
        #             user = user_serializer.save()
        #             user.set_password(request.data['password'])
        #             user.save()
        #             return JsonResponse({'Status': "Success"}, status=200)
        #
        #         else:
        #             return JsonResponse({'Status': 'Failure', 'errors': user_serializer.errors}, status=403)
        #
        # return JsonResponse({'Status': "Failure"}, status=403)


class ConfirmAccount(APIView):
    def post(self, request)->JsonResponse:
        if {'email', 'token'}.issubset(request.data):

            token = ConfirmEmailToken.objects.filter(
                user__email=request.data['email'],
                key=request.data['token']).first()
            if token:
                token.user.is_active = True
                token.user.save()
                token.delete()
                return JsonResponse({'Status': "Success"}, status=200)
            else:
                return JsonResponse({'Status': "Failure", 'reason':'Invalid Email or Token'}, status=403)
        return JsonResponse({'Status': "Failure", 'reason':'Email and Token can`t be Null'}, status=403)


class AccountDetails(APIView):
    def get(self, request):
        if not request.user.is_authenticated:
            return JsonResponse({'Status': "Failure", 'reason':'User not authenticated'}, status=401)
        serializer = UserSerializer(request.user).data
        return Response(serializer.data)

    def post(self, request):
        if not request.user.is_authenticated:
            return JsonResponse({'Status': "Failure", 'reason':'User not authenticated'}, status=401)
        if 'password' in request.data:
            errors = {}

            try:
                validate_password(request.data['password'])
            except Exception as e:
                errors_array = []
                for item in e:
                    errors_array.append(item)
                return JsonResponse({'Status':'Failure', 'errors': errors_array}, status=403)

            else:
                request.user.set_password(request.data['password'])

        user_serializer = UserSerializer(request.user, data=request.data, partial=True)

        if user_serializer.is_valid():
            user_serializer.save()
            return JsonResponse({'Status': "Success"}, status=200)
        else:
            return JsonResponse({'Status': "Failure", 'reason':user_serializer.errors}, status=401)


class LoginAccount(APIView):
    def post(self, request):
        if {'email', 'password'}.issubset(request.data):
            user = authenticate(request, email=request.data['email'], password=request.data['password'])

            if user:
                if user.is_active:
                    token, _ = Token.objects.get_or_create(user=user)
                    return JsonResponse({'Status': "Success", 'Token': token.key}, status=200)

            return JsonResponse({'Status': "Failure", 'reason':'User is not exist'}, status=403)

        return JsonResponse({'Status': "Failure", 'reason':'Email and Password can`t be Null'}, status=403)


class CategoryView(ListAPIView):
    queryset = Category.objects.all()
    serializer_class = CategorySerializer


class ShopView(ListAPIView):
    queryset = Shop.objects.all()
    serializer_class = ShopSerializer


class ProductInfoView(APIView):
    def get(self, request):
        query = Q(shop__state=True)
        shop_id = request.query_params.get('shop_id')
        category_id = request.query_params.get('category_id')
        if shop_id:
            query= query & Q(shop_id=shop_id)

        if category_id:
            query= query & Q(product__category_id=category_id)

        queryset = (Product.objects.filter(query).
                    select_related('shop', 'product__category').
                    prefetch_related('product_parameters__parameter')).distinct()

        serializer = ProductInfoSerializer(queryset, many=True)
        return Response(serializer.data)


class BasketView(APIView):

    def get(self, request):
        if not request.user.is_authenticated:
            return JsonResponse({'Status': "Failure", 'reason':'User not authenticated'}, status=403)

        basket = Order.objects.filter(
            user_id=request.user.id, state = 'basket').prefetch_related(
            'ordered_items__product_info__product__category',
            'ordered_items__product_info__product_parameters__parameter'
        ).annotate(
            total_sum=Sum(F('ordered_items__quantity') * F('ordered_items__product_info__price'))
        ).distinct()

        serializer = OrderSerializer(basket, many=True)
        return Response(serializer.data)

    def post(self, request):

        if not request.user.is_authenticated:
            return JsonResponse({'Status': "Failure", 'reason':'User not authenticated'}, status=403)
        items_string = request.data.get('items')

        if items_string:
            try:
                items_dict = loads(items_string)

            except ValueError:
                return JsonResponse({'Status': "Failure", 'reason':'Invalid JSON'}, status=400)

            else:
                basket, _ = Order.objects.get_or_create(user_id=request.user.id, state = 'basket')
                objects_created = 0
                for order_item in items_dict:
                    order_item.update({'order': basket.id})
                    serializer = OrderItemSerializer(data = order_item)
                    if serializer.is_valid():
                        try:
                            serializer.save()
                        except IntegrityError as e:
                            return JsonResponse({'Status': "Failure", 'reason': str(e)}, status=400)
                        else:
                            objects_created += 1
                else:
                    return JsonResponse({'Status': "Failure", 'reason': serializer.errors}, status=400)

            return JsonResponse({'Status': "Success", "Created Objects: " : objects_created}, status=200)


        def delete(self, request):
            if not request.user.is_authenticated:
                return JsonResponse({'Status': "Failure", 'reason':'User not authenticated'}, status=403)

            items_string = request.data.get('items')

            if items_string:
                items_list = items_string.split(',')

                basket, _ = Order.objects.get_or_create(user_id=request.user.id, state = 'basket')
                query = Q()
                objects_deleted = 0

                for order_item_id in items_list:
                    if order_item_id.is_digit():
                        query = query | Q(order_id = basket.id, id=order_item_id)
                        objects_deleted = True

                if objects_deleted:
                    deleted_count = OrderItem.objects.filter(query).delete()[0]

                    return JsonResponse({'Status': "Success", "Deleted Objects" : deleted_count}, status=200)

            return JsonResponse({'Status': "Failure", "Reason" : "Not all required arguments were specified"}, status=400)


        def put(self, request):
            if not request.user.is_authenticated:
                return JsonResponse({'Status': "Failure", 'reason':'User not authenticated'}, status=403)

            items_string = request.data.get('items')
            if items_string:
                try:
                    items_dict = loads(items_string)
                except ValueError:
                    return JsonResponse({'Status': "Failure", 'reason': 'Invalid JSON'}, status=400)
                else:
                    basket, _ = Order.objects.get_or_create(user_id=request.user.id, state = 'basket')
                    objects_updated = 0
                    for order_item in items_dict:
                        if type(order_item['id']) == int and type(order_item['quantity']) == int:
                            objects_updated += OrderItem.objects.fiter(order_id = basket.id, id = order_item['id']).update(
                                quantity = order_item['quantity']
                            )

                    return JsonResponse({'Status': "Success", "Updated Objects: " : objects_updated}, status=200)
            return JsonResponse({'Status': "Failure", 'reason': 'Not all required arguments were specified'}, status=400)


class PartnerUpdateView(APIView):


    def post(self, request):

        if not request.user.is_authenticated:
            return JsonResponse({'Status': "Failure", 'reason':'User not authenticated'}, status=403)

        if request.user.type != 'shop':
            return JsonResponse({'Status': "Failure", 'reason': 'Not a shop'}, status=403)

        url = request.data.get('url')
        if url:
            validate_url = URLValidator()

            try:
                validate_url(url)
            except ValidationError as e:
                return JsonResponse({'Status': "Failure", 'reason': str(e)}, status=400)
            else:

                stream = get(url).content

                data = load(stream, loader=Loader)

                shop, _ = Shop.objects.get_or_create(name=data['shop'], user_id=request.user.id)

                for category in data['categories']:
                    category_object, _ = Category.objects.get_or_create(id = category['id'],name=category['name'])
                    category_object.shops.add(shop.id)
                    category_object.save()

                ProductInfo.objects.filter(shop_id=shop.id).delete()

                for item in data['goods']:

                    product, _ = Product.objects.get_or_create(name = item['name'], category_id = item['category'])

                    product_info = ProductInfo.objects.create(
                        product_id = product.id,
                        external_id = item['id'],
                        model=item['model'],
                        price = item['price'],
                        quantity = item['quantity'],
                        shop_id = shop.id,
                    )

                    for name, value in item['parameters'].items():
                        parameter_object, _ = ProductParameter.objects.get_or_create(name=name)
                        ProductParameter.objects.create(
                            product_info = product_info.id,
                            parameter_id = parameter_object.id,
                            value = value,
                        )
                return JsonResponse({'Status': "Success", "Partner URL: " : url}, status=200)
        return JsonResponse({'Status': "Failure", 'reason': 'Not all required arguments were specified'}, status=400)


class PartnerStateView(APIView):


    def get(self, request):

        if not request.user.is_authenticated:
            return JsonResponse({'Status': "Failure", 'reason':'User not authenticated'}, status=403)

        if request.user.type != 'shop':
            return JsonResponse({'Status': "Failure", 'reason': 'Not a shop'}, status=403)

        shop = request.user.shop

        serializer = ShopSerializer(shop)

        return Response(serializer.data)

    def post(self, request):
        if not request.user.is_authenticated:
            return JsonResponse({'Status': "Failure", 'reason':'User not authenticated'}, status=403)

        if request.user.type != 'shop':
            return JsonResponse({'Status': "Failure", 'reason': 'Not a shop'}, status=403)

        state = request.data.get('state')
        if state:
            try:
                Shop.objects.filter(user_id = request.user.id).update(state = strtobool(state))
                return JsonResponse({'Status': "Success"}, status=200)
            except ValueError as e:
                return JsonResponse({'Status': "Failure", 'reason': str(e)}, status=400)

        return JsonResponse({'Status': "Failure", 'reason': 'Not all required arguments were specified'}, status=400)


class PartnerOrdersView(APIView):
    def get(self, request):
        if not request.user.is_authenticated:
            return JsonResponse({'Status': "Failure", 'reason':'User not authenticated'}, status=403)

        if request.user.type != 'shop':
            return JsonResponse({'Status': "Failure", 'reason': 'Not a shop'}, status=403)

        order =Order.objects.filter(
            ordered_items__product_info__shop__user_id=request.user.id).exclude(state='basket').prefetch_related(
            'ordered_items__product_info__product__category',
            'ordered_items__product_info__product_parameters__parameter').select_related('contact').annotate(
            total_sum=Sum(F('ordered_items__quantity') * F('ordered_items__product_info__price'))).distinct()

        serializer = OrderSerializer(order)
        return Response(serializer.data)


class ContactView(APIView):

    def get(self, request):

        if not request.user.is_authenticated:
            return JsonResponse({'Status': "Failure", 'reason':'User not authenticated'}, status=403)

        contact = Contact.objects.filter(user_id = request.user.id)
        serializer = ContactSerializer(contact, many=True)
        return Response(serializer.data)

    def post(self, request):
        if not request.user.is_authenticated:
            return JsonResponse({'Status': "Failure", 'reason':'User not authenticated'}, status=403)

        if {'city', 'street', 'phone'}.issubset(request.data):
            request.data._mutable = True
            request.data.update({'user': request.user.id})

            serializer = ContactSerializer(data=request.data)

            if serializer.is_valid():
                serializer.save()
                return JsonResponse({'Status': "Success"}, status=200)
            else:
                return JsonResponse({'Status': "Failure", 'reason': serializer.errors}, status=400)

        return JsonResponse({'Status': "Failure", 'reason': 'Not all required arguments were specified'}, status=400)


    def delete(self, request):

        if not request.user.is_authenticated:
            return JsonResponse({'Status': "Failure", 'reason':'User not authenticated'}, status=403)

        items_string = request.data.get('items')

        if items_string:

            items_list = items_string.split(',')
            query = Q()
            object_deleted = False

            for contact_id in items_list:
                if contact_id.isdigit():
                    query = query | Q(user_id = request.user.id, id = contact_id)
                    object_deleted = True

                if object_deleted:
                    deleted_count = Contact.objects.filter(query).delete()[0]
                    return JsonResponse({'Status': "Success", "Deleted Items":deleted_count}, status=200)

        return JsonResponse({'Status': "Failure", 'reason': 'Not all required arguments were specified'}, status=400)

    def put(self, request):
        if not request.user.is_authenticated:
            return JsonResponse({'Status': "Failure", 'reason':'User not authenticated'}, status=403)

        if 'id' in request.data:
            if request.data['id'].isdigit():
                contact = Contact.objects.filter(id = request.data['id'], user_id=request.user.id).first()
                if contact:
                    serializer = ContactSerializer(contact, data=request.data, partial=True)
                    if serializer.is_valid():
                        serializer.save()
                        return JsonResponse({'Status': "Success"}, status=200)
                    else:
                        return JsonResponse({'Status': "Failure", 'reason': serializer.errors}, status=400)

        return JsonResponse({'Status': "Failure", 'reason': 'Not all required arguments were specified'}, status=400)


class OrderView(APIView):

    def get(self, request):
        if not request.user.is_authenticated:
            return JsonResponse({'Status': "Failure", 'reason':'User not authenticated'}, status=403)

        order = Order.objects.filter(user_id=request.user.id).exclude(state='basket').prefetch_related(
            'ordered_items__product_info__product__category',
            'ordered_items__product_info__product_parameters__parameter').select_related('contact').annotate(
            total_sum=Sum(F('ordered_items__quantity') * F('ordered_items__product_info__price'))).distinct()
        serializer = OrderSerializer(order, many=True)
        return Response(serializer.data)

    def post(self, request):
        if not request.user.is_authenticated:

            return JsonResponse({'Status': "Failure", 'reason':'User not authenticated'}, status=403)

        if {'id', 'contact'}.issubset(request.data):
            if request.data['id'].isdigit():
                try:
                    is_updated = Order.objects.filter(
                        user_id=request.user.id,
                        id = request.data['id'],
                    ).update(
                        contact_id = request.data['contact'],
                        state = 'new'
                    )
                except IntegrityError as e:
                    return JsonResponse({'Status': "Failure", 'reason': e}, status=400)

                else:
                    if is_updated:
                        new_order.send(sender=self.__class__, user_id=request.user.id)
                        return JsonResponse({'Status': "Success"}, status=200)

        return JsonResponse({'Status': "Failure", 'reason': 'Not all required arguments were specified'}, status=400)

