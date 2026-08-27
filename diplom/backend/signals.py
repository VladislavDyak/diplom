from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.db.models.signals import post_save
from django.dispatch import Signal, receiver
from django_rest_passwordreset.signals import reset_password_token_created

from .models import User, ConfirmEmailToken

new_user_registered = Signal()

new_order = Signal()

@receiver(reset_password_token_created)
def password_reset_token_created(sender, instance, reset_password_token,**kwargs):
    msg = EmailMultiAlternatives(
        f"Password Reset Token for {reset_password_token.user}",
        reset_password_token.key,
        settings.DEFAULT_FROM_EMAIL,
        [reset_password_token.user.email]
    )
    msg.send()

@receiver(post_save, sender=User)
def new_user_registered_signal(sender, instance, created, **kwargs):
    if created and not instance.is_active:
        token, _ = ConfirmEmailToken.objects.get_or_create(user_id=instance.pk)

        msg = EmailMultiAlternatives(
            f"Password Reset Token for {instance.email}",
            token.key,
            settings.DEFAULT_FROM_EMAIL,
            [instance.email]
        )
        msg.send()


@receiver(new_order)
def new_order_signal(user_id, **kwargs):
    user = User.objects.get(id=user_id)

    msg = EmailMultiAlternatives(
        "Update order\'s state",
        "Order created",
        settings.DEFAULT_FROM_EMAIL,
        [user.email]
    )
    msg.send()