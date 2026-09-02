import requests
import yaml
from celery import shared_task
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.mail import send_mail, EmailMultiAlternatives
import logging

from django.core.validators import URLValidator

from .services.import_service import import_shop_data
from .models import User

logger = logging.getLogger(__name__)

@shared_task(bind=True, max_retries=3)
def import_shop_from_url(self, user_id, url):
    try:
        if not User.objects.filter(id=user_id).exists():
            error_msg = f'Пользователь с ID {user_id} не найден'
            logger.error(error_msg)
            return {'Status': 'Failure', 'Message': error_msg}


        validate_url = URLValidator()

        try:
            validate_url(url)

        except ValidationError as e:
            return {'Status': 'Failure', 'Message': str(e)}

        response = requests.get(url, timeout=60)
        response.raise_for_status()
        data = yaml.safe_load(response.content)

        result = import_shop_data(data, user_id)


        return result

    except Exception as e:
        logger.exception('Ошибка при импорте URL')
        self.retry(exc=e, countdown=60)


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def send_password_reset_email(self, user_id, token):

    try:
        user = User.objects.get(id=user_id)
        msg = EmailMultiAlternatives(
            f'Токен для сброса пароля для {user.email}',
            token,
            settings.DEFAULT_FROM_EMAIL,
            [user.email],
        )
        msg.send()

        return {'Status': 'Success'}

    except Exception as e:
        self.retry(exc=e, countdown=60)


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def send_confirmation_email(self, user_id, token):
    try:
        user = User.objects.get(id=user_id)
        msg = EmailMultiAlternatives(
            f'Подтверждение почты для {user.email}',
            token,
            settings.DEFAULT_FROM_EMAIL,
            [user.email],
        )
        msg.send()
        return {'Status': 'Success'}
    except Exception as e:
        self.retry(exc=e, countdown=60)


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def send_new_order_notification(self, user_id, message="Заказ создан"):
    try:
        user = User.objects.get(id=user_id)
        msg = EmailMultiAlternatives(
            'Обновлён статус заказа',
            message,
            settings.DEFAULT_FROM_EMAIL,
            [user.email],
        )
        msg.send()
        return {'Status': 'Success'}
    except Exception as e:
        self.retry(exc=e, countdown=60)







