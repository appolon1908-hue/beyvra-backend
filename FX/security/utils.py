import os
from django import template
from django.conf import settings
from django.core.mail import EmailMultiAlternatives


def send_user_anomaly_alert_to_admin(user, details, dynamic_msg):
    """ Send an email alert to the admin about a detected anomaly activity """

    subject = "User Suspicious Activity Detected | Tradx.io"
    email_template = template.loader.get_template(
        "user_anomaly_info.html")

    context = {
        "user": user,
        "details": details,
        "dynamic_msg": dynamic_msg,
        "frontend_url": os.getenv("FRONTEND_URL"),
        "twitter_url": os.getenv("TWITTER_URL"),
        "facebook_url": os.getenv("FACEBOOK_URL"),
        "linkedin_url": os.getenv("LINKEDIN_URL"),
    }

    html_content = email_template.render(context)
    text_content = " "

    if not settings.ADMINS:
        return

    if not all(isinstance(a, (list, tuple)) and len(a) == 2 for a in settings.ADMINS):
        raise ValueError("The ADMINS setting must be a list of 2-tuples.")

    msg = EmailMultiAlternatives(subject, text_content,
                                 settings.EMAIL_HOST_USER,
                                 [a[1] for a in settings.ADMINS])

    msg.attach_alternative(html_content, "text/html")
    msg.send(fail_silently=False)
