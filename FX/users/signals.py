from django.contrib.auth import get_user_model
from django.db.models.signals import post_save
from django.dispatch import receiver
from users.tasks import async_send_welcome_email

User = get_user_model()


@receiver(post_save, sender=User, dispatch_uid="update_user_upon_creation")
def update_user_upon_creation(sender, instance, created, **kwargs):
    if created:
        # Send welcome email to user:
        async_send_welcome_email.delay(instance.email, instance.first_name)
