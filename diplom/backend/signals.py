from django.db.models.signals import post_save
from django.dispatch import Signal, receiver
from django_rest_passwordreset.signals import reset_password_token_created

from .models import User, ConfirmEmailToken
from .tasks import send_confirmation_email,send_password_reset_email,send_new_order_notification

new_user_registered = Signal()

new_order = Signal()

@receiver(reset_password_token_created)
def password_reset_token_created(reset_password_token):
    send_password_reset_email.apply_async(
        user_id = reset_password_token.user.id,
        token = reset_password_token.key
    )

@receiver(post_save, sender=User)
def new_user_registered_signal(instance, created):
    if created and not instance.is_active:
        token, _ = ConfirmEmailToken.objects.get_or_create(user_id=instance.pk)

        send_confirmation_email.delay(
            user_id = instance.pk,
            token = token.key,
        )


@receiver(new_order)
def new_order_signal(user_id):
    send_new_order_notification.delay(
        user_id = user_id,
        message = 'Заказ создан!',
    )