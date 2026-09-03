import os

import pytest
import requests


BASE_URL =  os.getenv('API_URL', 'http://localhost:80')

PARTNER_IMPORT_URL = (
    'https://raw.githubusercontent.com/netology-code/python-final-diplom/master/data/shop1.yaml'
)


class TestApi:

    def setup_method(self):
        self.session = requests.Session()

        # Подставь данные тестового пользователя.
        self.email = 'test@test.ru'
        self.password = 'testpassword'

    def test_login(self):
        response = self.session.post(
            f'{BASE_URL}/api/v1/user/login',
            json={
                'email': self.email,
                'password': self.password,
            },
        )

        assert response.status_code == 200
        assert response.json()['status'] == 'success'
        assert 'token' in response.json()['data']

        self.session.headers.update({
            'Authorization': f"Token {response.json()['data']['token']}"
        })

    def test_account_details(self):
        self.test_login()

        response = self.session.get(
            f'{BASE_URL}/api/v1/user/details'
        )

        assert response.status_code == 200
        assert response.json()['email'] == self.email

    def test_categories(self):
        self.test_login()

        response = self.session.get(
            f'{BASE_URL}/api/v1/categories'
        )

        assert response.status_code == 200

    def test_shops(self):
        self.test_login()

        response = self.session.get(
            f'{BASE_URL}/api/v1/shops'
        )

        assert response.status_code == 200

    def test_products(self):
        self.test_login()

        response = self.session.get(
            f'{BASE_URL}/api/v1/products'
        )

        assert response.status_code == 200

    def test_basket(self):
        self.test_login()

        response = self.session.get(
            f'{BASE_URL}/api/v1/basket'
        )

        assert response.status_code == 200

    def test_contacts(self):
        self.test_login()

        response = self.session.get(
            f'{BASE_URL}/api/v1/user/contact'
        )

        assert response.status_code == 200

    def test_orders(self):
        self.test_login()

        response = self.session.get(
            f'{BASE_URL}/api/v1/order'
        )

        assert response.status_code == 200

    @pytest.mark.xfail(reason='Возвращает 404 если к тестовому пользователю не приязан магазин')
    def test_partner_update(self):
        self.test_login()

        response = self.session.post(
            f'{BASE_URL}/api/v1/partner/update',
            json={
                'url': PARTNER_IMPORT_URL,
            },
        )
        print('URL:', response.request.url)
        print('STATUS:', response.status_code)
        print('RESPONSE:', response.text)

        assert response.status_code == 200
        assert response.json()['status'] == 'Accepted'
        assert 'Task ID' in response.json()['data']

    def test_unauthorized_basket(self):
        response = self.session.get(
            f'{BASE_URL}/api/v1/basket'
        )

        assert response.status_code == 401