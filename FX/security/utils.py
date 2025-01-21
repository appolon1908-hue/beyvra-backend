import os
import re

from django import template
from django.conf import settings
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.mail import EmailMultiAlternatives
from rest_framework import serializers
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.authentication import JWTAuthentication


class PasswordPolicyValidator:
    def validate(self, password, user=None):
        # Check for minimum length
        min_length = 8
        if len(password) < min_length:
            raise ValidationError(f"Password must be at least {min_length} characters long.")
        # Check for at least one uppercase letter
        if not re.search(r"[A-Z]", password):
            raise ValidationError("Password must contain at least one uppercase letter.")
        # Check for at least one lowercase letter
        if not re.search(r"[a-z]", password):
            raise ValidationError("Password must contain at least one lowercase letter.")
        # Check for at least one digit
        if not re.search(r"\d", password):
            raise ValidationError("Password must contain at least one digit.")
        # Check for at least one special character
        if not re.search(r'[!@#$%^&*(),.?":{}|<>]', password):
            raise ValidationError("Password must contain at least one special character (e.g., !@#$%^&*).")
        return password


def send_user_anomaly_alert_to_admin(user, details, dynamic_msg):
    """Send an email alert to the admin about a detected anomaly activity"""

    subject = "User Suspicious Activity Detected | Tradx.io"
    email_template = template.loader.get_template("user_anomaly_info.html")

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

    msg = EmailMultiAlternatives(subject, text_content, settings.EMAIL_HOST_USER, [a[1] for a in settings.ADMINS])

    msg.attach_alternative(html_content, "text/html")
    msg.send(fail_silently=False)


def get_logged_user(request):
    try:
        user, _ = JWTAuthentication().authenticate(request)
    except AuthenticationFailed as e:
        return None
    except Exception as e:
        return None
    return user


def password_check_policy(password: str):
    """
    enforce password policy check on user creation with django's
    builtin validator, can be extended as required"""
    try:
        validate_password(password)
    except ValidationError as e:
        raise serializers.ValidationError({"password": str(e)})
    return password
