import os
from datetime import datetime
from random import randint

import pycountry
import requests
from django import template
from django.conf import settings
from django.contrib.auth.tokens import default_token_generator
from django.core.mail import EmailMultiAlternatives
from django.core.validators import RegexValidator
from django.http import JsonResponse
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from rest_framework import status
from rest_framework.response import Response
from twilio.rest import Client
from user_agents import parse

PHONE_REGEX_VALIDATOR = RegexValidator(
    regex=r"^\+\d{9,15}$",
    message="Phone number must be entered in the format: '+999999999'. Up to 15 digits allowed.",
)

ALPHABETS_REGEX_VALIDATOR = RegexValidator(
    regex=r"^[a-zA-Z ]+$",
    message="Only alphabets and spaces are allowed.",
)


def send_welcome_email(user_email, first_name, temp_password=None):
    subject = "Welcome | Tradx.io"
    email_template = template.loader.get_template("welcome_email.html")

    context = {
        "email": user_email,
        "first_name": first_name,
        "frontend_url": os.getenv("FRONTEND_URL"),
        "temp_password": temp_password,
    }

    html_content = email_template.render(context)
    text_content = " "

    msg = EmailMultiAlternatives(subject, text_content, settings.EMAIL_HOST_USER, [user_email])
    msg.attach_alternative(html_content, "text/html")
    msg.send(fail_silently=False)


def send_email_verification_email(user):
    subject = "Email Verification required | Tradx.io"
    email_template = template.loader.get_template("email_verify_email.html")

    context = {
        "email": user.email,
        "uid": urlsafe_base64_encode(force_bytes(user.pk)),
        "user": user,
        "token": default_token_generator.make_token(user),
        "frontend_url": os.getenv("FRONTEND_URL"),
    }

    html_content = email_template.render(context)
    text_content = " "

    msg = EmailMultiAlternatives(subject, text_content, settings.EMAIL_HOST_USER, [user.email])
    msg.attach_alternative(html_content, "text/html")
    msg.send(fail_silently=False)


def send_password_reset_link_email(user):
    subject = "Password Reset Requested | Tradx.io"
    email_template = template.loader.get_template("password_reset_email.html")

    context = {
        "email": user.email,
        "uid": urlsafe_base64_encode(force_bytes(user.pk)),
        "user": user,
        "token": default_token_generator.make_token(user),
        "frontend_url": os.getenv("FRONTEND_URL"),
    }

    html_content = email_template.render(context)
    text_content = " "

    msg = EmailMultiAlternatives(subject, text_content, settings.EMAIL_HOST_USER, [user.email])
    msg.attach_alternative(html_content, "text/html")
    msg.send(fail_silently=False)


def generate_verification_code():
    n = 6
    code = "".join(["{}".format(randint(0, 9)) for num in range(0, n)])
    return code


def send_mobile_verification_code(user):
    client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
    code = generate_verification_code()
    message_text = f"Your verification code for tradx.io is {code}."

    client.messages.create(
        from_=settings.TWILIO_SEND_FROM_NUMBER,
        body=message_text,
        to=user.phone_number,
    )
    return code


def blur_email(email):
    if email:
        blured_email = email[:4] + "*" * (len(email) - 8) + email[-4:]
    else:
        blured_email = ""
    return blured_email


def blur_phone_number(phone_number):
    if phone_number:
        blured_phone_number = phone_number[0] + "*" * (len(phone_number) - 5) + phone_number[-4:]
    else:
        blured_phone_number = ""

    return blured_phone_number


def get_local_currency(country_name):
    try:
        country = pycountry.countries.get(name=country_name)

        if not country:
            return JsonResponse({"error": "Country not found"}, status=404)

        currency = pycountry.currencies.get(numeric=country.numeric)

        if not currency:
            return JsonResponse({"error": "Currency not found"}, status=404)

        return currency.alpha_3
    except Exception:
        return JsonResponse(
            {"code": "REQUEST_FAILED", "message": "The request could not be completed."},
            status=500,
        )


def mask_email(email: str) -> str:
    """Mask email by turning some of the characters to *
    Args:
        email (str): _description_
    Returns:
        str: _description_
    """

    username, host = email.split("@")
    username_chars = list(username)
    size = len(username_chars)
    if size <= 2:
        username_chars[-1] = "*"
    else:
        username_chars[2:] = ["*"] * (size - 2)
    masked_email = "".join(username_chars) + "@" + host
    return masked_email


def mask_phone(phone: str) -> str:
    """Mask phone by turning some of the characters to *
    Args:
        phone (str): _description_
    Returns:
        str: _description_
    """

    phone_chars = list(phone)
    size = len(phone_chars)
    if size <= 4:
        pass
    else:
        mask_length = int(size / 2)
        ending_rev = -2 - (mask_length)
        phone_chars[ending_rev:-2] = ["*"] * mask_length
    masked_phone = "".join(phone_chars)
    return masked_phone


def get_user_location(ip_address: str) -> str:
    try:
        response = requests.get(f"http://ip-api.com/json/{ip_address}")

        if response.status_code != 200:
            return "Location lookup failed"

        data = response.json()

        city = data.get("city")
        country = data.get("country")

        if not city or not country:
            return "Unknown location"

        return f"{city}, {country}"

    except requests.exceptions.RequestException:
        return "Location lookup unavailable"

    except Exception:
        return "Location lookup unavailable"


def get_user_location_mod(ip_address: str) -> [dict, str]:
    try:
        response = requests.get(f"http://ip-api.com/json/{ip_address}")
        if response.status_code != 200:
            return {"city": None, "country": None}
        data = response.json()
        city = data.get("city")
        country = data.get("country")
        return {"city": city, "country": country}
    except requests.exceptions.RequestException:
        return {"city": None, "country": None}
    except Exception:
        return {"city": None, "country": None}


def get_ip_address(request):
    # Get the currently authenticated user
    ip_address = request.META.get("HTTPX_FORWARDED_FOR")
    if ip_address:
        ip_address = ip_address.split(",")[-1]
    else:
        ip_address = request.META.get("REMOTE_ADDR")
    return ip_address


def get_user_agent(request) -> dict:
    user_agent = request.META.get("HTTP_USER_AGENT", "")
    parsed_user_agent = parse(user_agent)
    device_type = parsed_user_agent.device.family if parsed_user_agent.device.family else "Unknown"
    device_model = parsed_user_agent.device.model if parsed_user_agent.device.model else "Unknown"
    user_agent_data = {
        "device_type": device_type,
        "device_model": device_model,
        "user_agent": user_agent,
    }
    return user_agent_data


def send_user_device_info_alert(user, details):
    subject = "New device detected | Tradx.io"
    email_template = template.loader.get_template("device_info_alert_email.html")

    context = {
        "user": user,
        "details": details,
        "frontend_url": os.getenv("FRONTEND_URL"),
        "twitter_url": os.getenv("TWITTER_URL"),
        "facebook_url": os.getenv("FACEBOOK_URL"),
        "linkedin_url": os.getenv("LINKEDIN_URL"),
    }

    html_content = email_template.render(context)
    text_content = " "

    msg = EmailMultiAlternatives(subject, text_content, settings.EMAIL_HOST_USER, [user.email])
    msg.attach_alternative(html_content, "text/html")
    msg.send(fail_silently=False)


def send_user_ban_email(user):
    subject = "Account Banned | Tradx.io"
    email_template = template.loader.get_template("user_ban_email.html")

    context = {
        "user": user,
        "ban_date": datetime.now(),
    }

    html_content = email_template.render(context)
    text_content = " "

    msg = EmailMultiAlternatives(subject, text_content, settings.EMAIL_HOST_USER, [user.email])
    msg.attach_alternative(html_content, "text/html")
    print("Sending user ban email")
    msg.send(fail_silently=False)


def confirm_action(request) -> bool | Response:
    """ensures a double check on the action to be performed"""
    confirm = request.data.get("confirm", False)
    if isinstance(confirm, bool) and confirm is True:
        return True

    return Response(
        {
            "error": "Please confirm action by adding 'confirm: true' in the request body.",
        },
        status=status.HTTP_400_BAD_REQUEST,
    )
