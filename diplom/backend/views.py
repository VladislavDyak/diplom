from django.contrib.auth import authenticate, get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.validators import URLValidator
from django.db import IntegrityError
from django.db.models import Q, F, Sum
from django.http import JsonResponse
from requests.api import get
from rest_framework import status, permissions
from rest_framework.authentication import TokenAuthentication
from rest_framework.authtoken.models import Token
from rest_framework.exceptions import ValidationError
from rest_framework.generics import ListAPIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from ujson import loads
from yaml import load, Loader, safe_load

from .models import ConfirmEmailToken, Category, Shop, Product, Order, OrderItem, ProductInfo, ProductParameter, \
    Contact, Parameter
from .serializer import UserSerializer, CategorySerializer, ShopSerializer, ProductInfoSerializer, \
    OrderSerializer, OrderItemSerializer, ContactSerializer
from .signals import new_order


def strtobool(value: str) -> bool:
  value = value.lower()
  if value in ("y", "yes", "on", "1", "true", "t"):
    return True
  return False



class RegisterAccount(APIView):

    permission_classes = (permissions.AllowAny,)

    def post(self, request):

        serializer = UserSerializer(data=request.data)

        if not serializer.is_valid():
            return JsonResponse("Несоответствие предоставляемых данных", status=status.HTTP_400_BAD_REQUEST)

        try:
            user = serializer.save()
            print(f"User created with email: {user.email} (pk={user.pk})")  # или logger
            ConfirmEmailToken.objects.create(user=user)
            return JsonResponse({'Status': 'Success', 'message': f'Successfully registered! {user.pk}'}, status=status.HTTP_201_CREATED)
        except Exception as e:
            import traceback
            return JsonResponse({'Status': 'Failure', 'message': str(e), 'trace': traceback.format_exc()}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class ConfirmAccount(APIView):

    permission_classes = (permissions.AllowAny,)

    def post(self, request)->JsonResponse:
        if {'email', 'token'}.issubset(request.data):
            token = ConfirmEmailToken.objects.filter(
                user__email=request.data['email'].strip().lower(),
                key=request.data['token']).first()
            print(token)
            if token:
                print(f"Before save: is_active = {token.user.is_active}")
                token.user.is_active = True
                token.user.save()
                token.user.refresh_from_db()
                print(f"After save: is_active = {token.user.is_active}")
                token.delete()

                return JsonResponse({'Status': "Success"}, status=200)
            else:
                return JsonResponse({'Status': "Failure", 'reason':'Invalid Email or Token'}, status=403)
        return JsonResponse({'Status': "Failure", 'reason':'Email and Token can`t be Null'}, status=403)


class AccountDetails(APIView):

    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        serializer = UserSerializer(request.user).data
        return Response(serializer.data)

    def post(self, request):
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

    permission_classes = (permissions.AllowAny,)

    def post(self, request):

        if {'email', 'password'}.issubset(request.data):

            email = request.data['email'].strip().lower()
            password = request.data['password']

            if not email or not password:
                return JsonResponse({
                    'Status': "Failure", 'reason':'Почта и пароль не должны быть пустыми'
                }, status=status.HTTP_400_BAD_REQUEST)

            user = authenticate(request=request, email=email, password=password)

            if not user:
                return JsonResponse({
                    'Status': "Failure",
                    'reason':'Неверные почта или пароль'
                }, status=status.HTTP_403_FORBIDDEN)

            if not user.is_active:
                return JsonResponse({
                    'Status': "Failure",
                    'reason':'Аккаунт не подтверждён'
                }, status=status.HTTP_403_FORBIDDEN)

            token, created = Token.objects.get_or_create(user=user)

            return JsonResponse({
                'Status': "Success",
                'token': token.key,
                'user': UserSerializer(user).data,
            }, status=status.HTTP_200_OK)


class CategoryView(ListAPIView):

    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]

    queryset = Category.objects.all()
    serializer_class = CategorySerializer


class ShopView(ListAPIView):

    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]

    queryset = Shop.objects.all()
    serializer_class = ShopSerializer


class ProductInfoView(APIView):

    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]

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

    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):

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

    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request):


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

                data = safe_load(stream)

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
                        price_rrc = item['price_rrc'],
                    )

                    for name, value in item['parameters'].items():
                        parameter_object, _ = Parameter.objects.get_or_create(name=name)
                        ProductParameter.objects.create(
                            product_info = product_info,
                            parameter_id = parameter_object.id,
                            value = value,
                        )
                return JsonResponse({'Status': "Success", "Partner URL: " : url}, status=200)
        return JsonResponse({'Status': "Failure", 'reason': 'Not all required arguments were specified'}, status=400)


class PartnerStateView(APIView):

    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):

        if request.user.type != 'shop':
            return JsonResponse({'Status': "Failure", 'reason': 'Not a shop'}, status=403)

        shop = request.user.shop

        serializer = ShopSerializer(shop)

        return Response(serializer.data)

    def post(self, request):

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

    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):

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

    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):

        contact = Contact.objects.filter(user_id = request.user.id)
        serializer = ContactSerializer(contact, many=True)
        return Response(serializer.data)

    def post(self, request):

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

    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):

        order = Order.objects.filter(user_id=request.user.id).exclude(state='basket').prefetch_related(
            'ordered_items__product_info__product__category',
            'ordered_items__product_info__product_parameters__parameter').select_related('contact').annotate(
            total_sum=Sum(F('ordered_items__quantity') * F('ordered_items__product_info__price'))).distinct()
        serializer = OrderSerializer(order, many=True)
        return Response(serializer.data)

    def post(self, request):

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

