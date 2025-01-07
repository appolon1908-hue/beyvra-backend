from django.conf import settings
from django.utils.log import AdminEmailHandler
from fx_utils.tasks import send_mail_async


def custom_mail_admins(subject=str, message=str, fail_silently=False, connection=None, html_message=None):
    """Send a message to the admins, as defined by the ADMINS setting."""
    if not settings.ADMINS:
        return
    if not all(isinstance(a, (list, tuple)) and len(a) == 2 for a in settings.ADMINS):
        raise ValueError("The ADMINS setting must be a list of 2-tuples.")
    send_mail_async.delay(
        subject=subject,
        message=message,
        from_email=settings.EMAIL_HOST_USER,
        recipient_list=[a[1] for a in settings.ADMINS],
        fail_silently=fail_silently,
        html_message=html_message,
    )


class CustomAdminEmailHandler(AdminEmailHandler):
    def send_mail(self, subject, message, *args, **kwargs) -> None:
        custom_mail_admins(subject, message, *args, connection=self.connection(), **kwargs)
