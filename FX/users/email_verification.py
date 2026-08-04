import hashlib
import hmac
import secrets
import uuid
import base64
from cryptography.fernet import Fernet
from datetime import timedelta

from django.conf import settings
from django.contrib.auth.hashers import make_password, check_password
from django.core.cache import cache
from django.core.mail import send_mail
from django.db import transaction
from django.utils import timezone
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from wallet.constants import DEMO_BALANCE, DEMO_WALLET_NAME
from wallet.models import Currency, Wallet

from .models import DemoLegalAcceptance, EmailVerificationChallenge, PendingRegistration, TransactionalEmailOutbox, User


def _active_legal_versions():
    return {
        "service-agreement": getattr(settings, "LEGAL_SERVICE_AGREEMENT_VERSION", "demo-v1"),
        "privacy-policy": getattr(settings, "LEGAL_PRIVACY_POLICY_VERSION", "demo-v1"),
        "risk-disclosure": getattr(settings, "LEGAL_RISK_DISCLOSURE_VERSION", "demo-v1"),
    }


def _audit(event_type, **kwargs):
    # The legacy branch has no audit model; retain an application log event
    # until the shared security-event model is migrated.
    import logging
    logging.getLogger("codestra.auth").info("%s %s", event_type, {k: v for k, v in kwargs.items() if k not in {"request"}})


def mask_email(email: str) -> str:
    local, _, domain = email.partition("@")
    if len(local) <= 2:
        masked = local[:1] + "*"
    else:
        masked = local[:1] + "*" * max(1, len(local) - 2) + local[-1:]
    return f"{masked}@{domain}"


def generate_otp() -> str:
    return "".join(str(secrets.randbelow(10)) for _ in range(settings.EMAIL_OTP_LENGTH))


def hash_otp(code: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", code.encode(), f"{settings.EMAIL_OTP_PEPPER}:{salt}".encode(), 120_000)
    return f"pbkdf2$120000${salt}${digest.hex()}"


def verify_otp(code: str, encoded: str) -> bool:
    try:
        _, iterations, salt, expected = encoded.split("$", 3)
        actual = hashlib.pbkdf2_hmac("sha256", code.encode(), f"{settings.EMAIL_OTP_PEPPER}:{salt}".encode(), int(iterations)).hex()
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError):
        return False


def _encrypted_code(code: str) -> str:
    key = base64.urlsafe_b64encode(hashlib.sha256(settings.SECRET_KEY.encode()).digest())
    return Fernet(key).encrypt(code.encode()).decode("ascii")


def queue_email(*, event_type, email, template_key, payload, idempotency_key, locale="en"):
    return TransactionalEmailOutbox.objects.create(event_type=event_type, recipient_email=email, template_key=template_key, locale=locale, payload=payload, idempotency_key=idempotency_key, next_attempt_at=timezone.now())


def _wallet(user):
    currency, _ = Currency.objects.get_or_create(name="Đ", defaults={"symbol": "DEMO", "longer_name": "Demo Dollar"})
    Wallet.objects.get_or_create(name=DEMO_WALLET_NAME, user=user, is_real=False, defaults={"currency": currency, "balance": DEMO_BALANCE})


def _activate_registration(pending, request):
    now = timezone.now()
    first, _, last = pending.display_name.partition(" ")
    with transaction.atomic():
        pending = PendingRegistration.objects.select_for_update().get(pk=pending.pk)
        user = User(email=pending.email_normalized, first_name=(first or "Customer")[:20], last_name=(last or "User")[:20], phone_number=f"+999{uuid.uuid4().int % 10**12:012d}", password=pending.password_hash, email_verified=True, email_verified_at=now, email_verification_source="otp", is_walkthrough=True, is_active=True)
        user.save()
        for doc_type, version in pending.legal_document_versions.items():
            DemoLegalAcceptance.objects.create(user=user, document_type=doc_type, document_version=version, accepted_at=now, acceptance_source="email-registration", registration_id=pending.id, locale=pending.locale, ip_address=request.META.get("REMOTE_ADDR"), user_agent=request.META.get("HTTP_USER_AGENT", "")[:1000])
        _wallet(user)
        pending.status = "completed"
        pending.verified_at = now
        pending.activated_user = user
        pending.save(update_fields=["status", "verified_at", "activated_user"])
        queue_email(event_type="user.registration.completed", email=user.email, template_key="welcome_email", payload={"display_name": user.first_name, "frontend_url": settings.FRONTEND_URL if hasattr(settings, "FRONTEND_URL") else "/"}, idempotency_key=f"welcome:{user.pk}:registration")
        _audit("email_otp_verification_succeeded", user=user, result="success", request=request)
    return user


class EmailRegistrationView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        if not settings.EMAIL_REGISTRATION_ENABLED or not settings.EMAIL_OTP_VERIFICATION_ENABLED:
            return Response({"code": "EMAIL_REGISTRATION_DISABLED", "message": "Registration is temporarily unavailable."}, status=503)
        email = str(request.data.get("email", "")).strip().lower()
        password = str(request.data.get("password", ""))
        display_name = str(request.data.get("displayName", "")).strip()[:120]
        if not email or "@" not in email or len(password) < 8 or not request.data.get("legalAccepted"):
            return Response({"code": "REGISTRATION_INVALID", "message": "Please provide valid registration details and accept the required agreement."}, status=400)
        if User.objects.filter(email__iexact=email).exists():
            return Response({"status": "pending_email_verification", "message": "If this address can be registered, a verification code will be sent."}, status=202)
        existing = PendingRegistration.objects.filter(email_normalized=email, status="pending_email_verification", expires_at__gt=timezone.now()).first()
        if existing:
            return Response({"registrationId": f"reg_{existing.pk}", "status": existing.status, "maskedEmail": mask_email(email), "expiresIn": max(0, int((existing.expires_at - timezone.now()).total_seconds())), "resendAvailableIn": settings.EMAIL_OTP_RESEND_COOLDOWN_SECONDS}, status=202)
        now = timezone.now()
        code = generate_otp()
        versions = _active_legal_versions()
        versions = {key: value or "current" for key, value in versions.items()}
        with transaction.atomic():
            pending = PendingRegistration.objects.create(email_normalized=email, display_name=display_name, password_hash=make_password(password), locale=request.data.get("locale", "en")[:16], legal_confirmation=True, legal_document_versions=versions, expires_at=now + timedelta(seconds=settings.PENDING_REGISTRATION_TTL_SECONDS), request_ip=request.META.get("REMOTE_ADDR"), request_user_agent=request.META.get("HTTP_USER_AGENT", "")[:1000])
            EmailVerificationChallenge.objects.create(registration=pending, email_normalized=email, otp_hash=hash_otp(code), expires_at=now + timedelta(seconds=settings.EMAIL_OTP_TTL_SECONDS), max_attempts=settings.EMAIL_OTP_MAX_ATTEMPTS)
            queue_email(event_type="email_otp_created", email=email, template_key="email_otp", payload={"code_encrypted": _encrypted_code(code), "expires_minutes": settings.EMAIL_OTP_TTL_SECONDS // 60, "purpose": "registration"}, idempotency_key=f"otp:{pending.pk}:1", locale=pending.locale)
            _audit("registration_pending_email_verification", transaction_id=pending.id, result="accepted", request=request)
        return Response({"registrationId": f"reg_{pending.pk}", "status": pending.status, "maskedEmail": mask_email(email), "expiresIn": settings.EMAIL_OTP_TTL_SECONDS, "resendAvailableIn": settings.EMAIL_OTP_RESEND_COOLDOWN_SECONDS}, status=202)


def _pending_id(value):
    try:
        return uuid.UUID(str(value).removeprefix("reg_"))
    except (ValueError, AttributeError, TypeError):
        return None


class EmailVerificationVerifyView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        pending_id = _pending_id(request.data.get("registrationId"))
        code = str(request.data.get("code", ""))
        if not pending_id or len(code) != settings.EMAIL_OTP_LENGTH or not code.isdigit():
            return Response({"code": "OTP_INVALID", "message": "The verification code is invalid or expired."}, status=400)
        try:
            with transaction.atomic():
                pending = PendingRegistration.objects.select_for_update().get(pk=pending_id)
                challenge = EmailVerificationChallenge.objects.select_for_update().filter(registration=pending, status="active").order_by("-created_at").first()
                if pending.status != "pending_email_verification" or pending.expires_at <= timezone.now() or not challenge or challenge.expires_at <= timezone.now():
                    return Response({"code": "OTP_EXPIRED", "message": "The verification code is invalid or expired."}, status=400)
                if challenge.attempt_count >= challenge.max_attempts:
                    challenge.status = "locked"; challenge.save(update_fields=["status"])
                    return Response({"code": "OTP_LOCKED", "message": "The verification code is invalid or expired."}, status=400)
                challenge.attempt_count += 1; challenge.last_attempt_at = timezone.now()
                if not verify_otp(code, challenge.otp_hash):
                    challenge.save(update_fields=["attempt_count", "last_attempt_at"])
                    _audit("email_otp_verification_failed", transaction_id=pending.id, result="denied", reason_code="OTP_INVALID", request=request)
                    return Response({"code": "OTP_INVALID", "message": "The verification code is invalid or expired."}, status=400)
                challenge.status = "consumed"; challenge.consumed_at = timezone.now(); challenge.save(update_fields=["status", "consumed_at", "attempt_count", "last_attempt_at"])
                user = _activate_registration(pending, request)
            refresh = TokenObtainPairSerializer.get_token(user)
            response = Response({"status": "verified", "accountStatus": "active", "welcomeEmailQueued": True, "nextPath": "/platform", "user": {"id": user.pk, "email": user.email, "is_walkthrough": user.is_walkthrough}})
            response.set_cookie("access_token", str(refresh.access_token), max_age=3600, secure=True, httponly=True, samesite="Lax", path="/")
            response.set_cookie("refresh_token", str(refresh), max_age=604800, secure=True, httponly=True, samesite="Lax", path="/")
            return response
        except PendingRegistration.DoesNotExist:
            return Response({"code": "OTP_INVALID", "message": "The verification code is invalid or expired."}, status=400)


class EmailVerificationResendView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        pending_id = _pending_id(request.data.get("registrationId"))
        if not pending_id:
            return Response({"status": "sent", "expiresIn": settings.EMAIL_OTP_TTL_SECONDS, "resendAvailableIn": settings.EMAIL_OTP_RESEND_COOLDOWN_SECONDS})
        with transaction.atomic():
            pending = PendingRegistration.objects.select_for_update().filter(pk=pending_id, status="pending_email_verification").first()
            if not pending or pending.expires_at <= timezone.now():
                return Response({"status": "sent", "expiresIn": settings.EMAIL_OTP_TTL_SECONDS, "resendAvailableIn": settings.EMAIL_OTP_RESEND_COOLDOWN_SECONDS})
            previous = EmailVerificationChallenge.objects.filter(registration=pending, status="active").order_by("-created_at").first()
            if previous and previous.last_sent_at and (timezone.now() - previous.last_sent_at).total_seconds() < settings.EMAIL_OTP_RESEND_COOLDOWN_SECONDS:
                return Response({"status": "sent", "expiresIn": settings.EMAIL_OTP_TTL_SECONDS, "resendAvailableIn": settings.EMAIL_OTP_RESEND_COOLDOWN_SECONDS})
            sends = EmailVerificationChallenge.objects.filter(email_normalized=pending.email_normalized, created_at__gte=timezone.now() - timedelta(hours=1)).count()
            if sends >= settings.EMAIL_OTP_MAX_SENDS_PER_HOUR:
                return Response({"status": "sent", "expiresIn": settings.EMAIL_OTP_TTL_SECONDS, "resendAvailableIn": settings.EMAIL_OTP_RESEND_COOLDOWN_SECONDS})
            EmailVerificationChallenge.objects.filter(registration=pending, status="active").update(status="invalidated", invalidated_at=timezone.now())
            code = generate_otp(); ordinal = sends + 1
            EmailVerificationChallenge.objects.create(registration=pending, email_normalized=pending.email_normalized, otp_hash=hash_otp(code), expires_at=timezone.now() + timedelta(seconds=settings.EMAIL_OTP_TTL_SECONDS), max_attempts=settings.EMAIL_OTP_MAX_ATTEMPTS, send_count=ordinal)
            queue_email(event_type="email_otp_resent", email=pending.email_normalized, template_key="email_otp", payload={"code_encrypted": _encrypted_code(code), "expires_minutes": settings.EMAIL_OTP_TTL_SECONDS // 60, "purpose": "registration"}, idempotency_key=f"otp:{pending.pk}:{ordinal}", locale=pending.locale)
        return Response({"status": "sent", "expiresIn": settings.EMAIL_OTP_TTL_SECONDS, "resendAvailableIn": settings.EMAIL_OTP_RESEND_COOLDOWN_SECONDS})


class EmailVerificationStatusView(APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        pending_id = _pending_id(request.query_params.get("registrationId"))
        if not pending_id:
            return Response({"status": "unknown"})
        pending = PendingRegistration.objects.filter(pk=pending_id).first()
        if not pending:
            return Response({"status": "unknown"})
        challenge = pending.challenges.filter(status="active").order_by("-created_at").first()
        return Response({"status": pending.status, "maskedEmail": mask_email(pending.email_normalized), "expiresIn": max(0, int((pending.expires_at - timezone.now()).total_seconds())), "challengeExpiresIn": max(0, int((challenge.expires_at - timezone.now()).total_seconds())) if challenge else 0})


def send_outbox_message(item):
    payload = item.payload or {}
    if item.template_key == "email_otp":
        key = base64.urlsafe_b64encode(hashlib.sha256(settings.SECRET_KEY.encode()).digest())
        code = Fernet(key).decrypt(payload["code_encrypted"].encode()).decode()
        subject = "Your Codestra verification code"
        body = f"Your verification code is {code}.\n\nThis code expires in {payload.get('expires_minutes', 10)} minutes. Do not share it. Codestra support will never ask for it.\n\nIgnore this message if you did not start registration."
    else:
        subject = "Welcome to Codestra"
        body = f"Your Codestra account was created successfully, {payload.get('display_name', 'Customer')}.\n\nSign in at {payload.get('frontend_url', '/')}.\n\nIf you did not create this account, contact support immediately."
    if not settings.TRANSACTIONAL_EMAIL_ENABLED:
        return "disabled"
    send_mail(subject, body, settings.EMAIL_FROM_ADDRESS or settings.EMAIL_HOST_USER, [item.recipient_email], fail_silently=False)
    return "sent"
