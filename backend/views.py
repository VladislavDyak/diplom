from django.contrib.auth import authenticate
from django.contrib.auth.password_validation import validate_password
from django.db.models import Q
from django.http import JsonResponse
from rest_framework.authtoken.models import Token
from rest_framework.exceptions import ValidationError
from rest_framework.generics import ListAPIView
from rest_framework.response import Response
from rest_framework.views import APIView

from backend.models import ConfirmEmailToken, Category, Shop, Product
from backend.serializer import UserSerializer, CategorySerializer, ShopSerializer, ProductInfoSerializer


class RegisterAccount(APIView):

    def post(self, request)->JsonResponse:


        if {'first_name', 'last_name', 'email', 'password', 'company', 'position'}.issubset(request.data):

            try:
                validate_password(request.data['password'])

            except ValidationError as pass_error:
                return JsonResponse({'error': f'Пароль не прошёл валидацию, ошибка {pass_error}'}, status=403)

            else:
                user_serializer = UserSerializer(data=request.data)

                if user_serializer.is_valid():
                    user = user_serializer.save()
                    user.set_password(request.data['password'])
                    user.save()
                    return JsonResponse({'Status': "Success"}, status=200)

                else:
                    return JsonResponse({'Status': 'Failure'}, status=403)

        return JsonResponse({'Status': "Failure"}, status=403)




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

            return JsonResponse({'Status': "Failure", 'reason':'User was not authorized'}, status=403)

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



