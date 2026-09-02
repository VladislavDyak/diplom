import json
import requests
from django.contrib.auth import authenticate
from django.contrib.auth.password_validation import validate_password
from django.db import IntegrityError
from django.db.models import Q, F, Sum
from django.http import JsonResponse
from rest_framework import status, permissions
from rest_framework.authentication import TokenAuthentication
from rest_framework.authtoken.models import Token
from rest_framework.exceptions import ValidationError
from rest_framework.generics import ListAPIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from ujson import loads
from setuptools._distutils.util import strtobool
from .models import ConfirmEmailToken, Category, Shop, Product, Order, OrderItem, ProductInfo, ProductParameter, \
    Contact, Parameter
from .serializer import UserSerializer, CategorySerializer, ShopSerializer, ProductInfoSerializer, \
    OrderSerializer, OrderItemSerializer, ContactSerializer
from .signals import new_order
from .tasks import import_shop_from_url


class RegisterAccount(APIView):

    permission_classes = (permissions.AllowAny,)

    def post(self, request):

        serializer = UserSerializer(data=request.data)
        print(request.data)
        print(serializer.is_valid())

        if not serializer.is_valid():
            return JsonResponse({'Status':'Failure', 'Reason': serializer.errors},
                                status=status.HTTP_400_BAD_REQUEST)

        try:
            user = serializer.save()
            token_obj = ConfirmEmailToken.objects.create(user=user)
            return JsonResponse({'Status': 'Success',
                                 'message': f'Успешно зарегистрирован пользователь с ID {user.pk} с токеном'
                                            f' {token_obj.key}'
                                 }, status=status.HTTP_201_CREATED)

        except Exception as e:
            import traceback
            return JsonResponse({'Status': 'Failure',
                                 'Message': str(e),
                                 'Trace': traceback.format_exc()},
                                status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class ConfirmAccount(APIView):

    permission_classes = (permissions.AllowAny,)

    def post(self, request)->JsonResponse:
        if {'email', 'token'}.issubset(request.data):
            token = ConfirmEmailToken.objects.filter(
                user__email=request.data['email'].strip().lower(),
                key=request.data['token']).first()


            if token:
                token.user.is_active = True
                token.user.save()
                token.delete()

                return JsonResponse({'Status': "Success"}, status=status.HTTP_200_OK)
            else:
                return JsonResponse({'Status': "Failure", 'Reason':'Неверный Email или Token'}, status=status.HTTP_403_FORBIDDEN)
        return JsonResponse({'Status': "Failure", 'reason':'Email и Token не могут быть Null'}, status=status.HTTP_403_FORBIDDEN)


class AccountDetails(APIView):

    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        serializer = UserSerializer(request.user).data
        return JsonResponse(serializer, status=status.HTTP_200_OK)

    def post(self, request):
        if 'password' in request.data:

            try:
                validate_password(request.data['password'])

            except ValidationError as e:
                errors_array = []
                for item in e.messages:
                    errors_array.append(item)
                return JsonResponse({'Status':'Failure', 'Errors': errors_array}, status=status.HTTP_403_FORBIDDEN)

            else:
                request.user.set_password(request.data['password'])

        user_serializer = UserSerializer(request.user, data=request.data, partial=True)

        if user_serializer.is_valid():
            user_serializer.save()
            return JsonResponse({'Status': "Success"}, status=status.HTTP_200_OK)
        else:
            return JsonResponse({'Status': "Failure", 'Reason':user_serializer.errors}, status=status.HTTP_401_UNAUTHORIZED)


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
        return JsonResponse({'Status': "Failure", 'reason':'Не введены учётные данные'}, status=status.HTTP_401_UNAUTHORIZED)


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

        queryset = (ProductInfo.objects.filter(query).
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
            'order_items__product_info__product__category',
            'order_items__product_info__product_parameters__parameter'
        ).annotate(
            total_sum=Sum(F('order_items__quantity') * F('order_items__product_info__price'))
        ).distinct()

        serializer = OrderSerializer(basket, many=True)
        return Response(serializer.data)

    def post(self, request):

        items_string = request.data.get('items')

        if items_string:
            try:
                items_dict = json.loads(items_string)

            except ValueError as e:
                return JsonResponse({'Status': "Failure", 'Reason':str(e)}, status=status.HTTP_400_BAD_REQUEST)

            else:
                basket, _ = Order.objects.get_or_create(user_id=request.user.id, state = 'basket')
                objects_created = 0
                for order_item in items_dict:
                    order_item.update({'order': basket.id})
                    serializer = OrderItemSerializer(data = order_item)
                    print(order_item)
                    if serializer.is_valid():
                        try:
                            serializer.save()
                        except IntegrityError as e:
                            return JsonResponse({'Status': "Failure", 'Причина': str(e)}, status=status.HTTP_400_BAD_REQUEST)
                        else:
                            objects_created += 1
                    else:
                        return JsonResponse({'Status': "Failure", 'Причина': serializer.errors}, status=status.HTTP_400_BAD_REQUEST)

            return JsonResponse({'Status': "Success", "Созданы объекты: " : objects_created}, status=status.HTTP_200_OK)

        return JsonResponse({
            "Status": 'Failure',
            "Reason": "Указаны не все необходимые аргументы"
        })


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
                    objects_deleted += 1

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
                        objects_updated += OrderItem.objects.filter(order_id = basket.id, id = order_item['id']).update(
                            quantity = order_item['quantity']
                        )

                return JsonResponse({'Status': "Success", "Updated Objects: " : objects_updated}, status=200)
        return JsonResponse({'Status': "Failure", 'reason': 'Not all required arguments were specified'}, status=400)


class PartnerUpdateView(APIView):

    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request):

        if request.user.type != 'shop':
            return JsonResponse({'Status': "Failure",
                                 'Reason': 'Доступно только для магазинов'},
                                status=status.HTTP_403_FORBIDDEN)

        url = request.data.get('url')
        if not url:

            return JsonResponse({
                'Status': 'Failure',
                'Reason': 'URL не указан!'
            })

        task = import_shop_from_url.delay(request.user.id, url)

        return JsonResponse({
            'Status': "Accepted",
            'Task ID': task.id,
            'Message': 'Импорт в фоновом режиме'

        }, status=status.HTTP_200_OK)





class PartnerStateView(APIView):

    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):

        if request.user.type != 'shop':
            return JsonResponse({'Status': "Failure", 'Reason': 'Доступно только для магазинов'}, status=status.HTTP_403_FORBIDDEN)

        shop = request.user.shop

        serializer = ShopSerializer(shop)

        return Response(serializer.data)

    def post(self, request):

        if request.user.type != 'shop':
            return JsonResponse({'Status': "Failure", 'Reason': 'Доступно только для магазинов'}, status=status.HTTP_403_FORBIDDEN)

        state = request.data.get('state')
        if state:
            try:
                Shop.objects.filter(user_id = request.user.id).update(state = strtobool(state))
                return JsonResponse({'Status': "Success"}, status=200)
            except ValueError as e:
                return JsonResponse({'Status': "Failure", 'Reason': str(e)}, status=status.HTTP_400_BAD_REQUEST)

        return JsonResponse({'Status': "Failure",
                             'Reason': 'Не все требуемые аргументы переданы'
                             }, status=status.HTTP_400_BAD_REQUEST)


class PartnerOrdersView(APIView):

    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):

        if request.user.type != 'shop':
            return JsonResponse({'Status': "Failure",
                                 'Reason': 'Доступно только для магазинов'
                                 }, status=status.HTTP_403_FORBIDDEN)

        order =Order.objects.filter(
            order_items__product_info__shop__user_id=request.user.id).exclude(state='basket').prefetch_related(
            'order_items__product_info__product__category',
            'order_items__product_info__product_parameters__parameter').select_related('contact').annotate(
            total_sum=Sum(F('order_items__quantity') * F('order_items__product_info__price'))).distinct()

        serializer = OrderSerializer(order, many=True)
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
            print(request.user)
            serializer = ContactSerializer(data=request.data, context={'user': request.user})

            if serializer.is_valid():
                serializer.save()
                return JsonResponse({'Status': "Success"}, status=status.HTTP_201_CREATED)
            else:
                return JsonResponse({'Status': "Failure", 'Reason': serializer.errors}, status=status.HTTP_400_BAD_REQUEST)

        return JsonResponse({'Status': "Failure", 'Reason': 'Не все требуемые аргументы переданы'}, status=status.HTTP_400_BAD_REQUEST)


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
                    return JsonResponse({'Status': "Success", "Deleted Items":deleted_count}, status=status.HTTP_200_OK)

        return JsonResponse({'Status': "Failure", 'Reason': 'Не все требуемые аргументы переданы'}, status=status.HTTP_400_BAD_REQUEST)

    def put(self, request):

        if 'id' in request.data:
            if request.data['id'].isdigit():
                contact = Contact.objects.filter(id = request.data['id'], user_id=request.user.id).first()
                if contact:
                    serializer = ContactSerializer(contact, data=request.data, partial=True)
                    if serializer.is_valid():
                        serializer.save()
                        return JsonResponse({'Status': "Success"}, status=status.HTTP_201_CREATED)
                    else:
                        return JsonResponse({'Status': "Failure",
                                             'Reason': serializer.errors},
                                            status=status.HTTP_400_BAD_REQUEST)

        return JsonResponse({'Status': "Failure",
                             'Reason': 'Не все требуемые аргументы переданы'
                             }, status=status.HTTP_400_BAD_REQUEST)


class OrderView(APIView):

    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):

        order = Order.objects.filter(user_id=request.user.id).exclude(state='basket').prefetch_related(
            'order_items__product_info__product__category',
            'order_items__product_info__product_parameters__parameter').select_related('contact').annotate(
            total_sum=Sum(F('order_items__quantity') * F('order_items__product_info__price'))).distinct()
        serializer = OrderSerializer(order, many=True)
        return Response(serializer.data)

    def post(self, request):

        if not {'id', 'contact'}.issubset(request.data):
            return JsonResponse({
                                    'Status': "Failure",
                                    'Reason': 'Не указаны в переданных данных ID или Contact'
            }, status=status.HTTP_400_BAD_REQUEST)


        if not request.data['id'].isdigit():

            return JsonResponse({'Status': "Failure", 'Reason': 'ID должен быть числом'}, status=status.HTTP_400_BAD_REQUEST)

        try:

            order = Order.objects.filter(user_id=request.user.id, id = request.data['id'], state = 'basket',).first()

            if not order:
                return JsonResponse({'Status': 'Failure', 'Reason': 'Заказ не найден'}, status=status.HTTP_404_NOT_FOUND)

            order.contact_id = request.data['contact']
            order.state = 'new'
            order.save(update_fields=['contact_id', 'state'])

            new_order.send(sender=self.__class__, user_id=request.user.id)

            return JsonResponse({'Status': "Success"}, status=status.HTTP_200_OK)

        except IntegrityError as e:

            return JsonResponse({'Status': "Failure", 'Reason': str(e)}, status=status.HTTP_400_BAD_REQUEST)



