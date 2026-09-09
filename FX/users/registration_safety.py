"""Concurrency-safe local email registration.

This module keeps the legacy local-registration endpoint available only while
that capability is explicitly enabled. Database constraints remain the final
authority; the view converts an expected concurrent uniqueness race into an
idempotent 202 response instead of a 500.
"""

from __future__ import annotations

from datetime import timedelta
import hashlib
import hmac
import uuid

from django.conf import settings
from django.contrib.auth.hashers import make_password
from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework import permissions
from rest_framework.response import Response
from rest_framework.views import APIView

from .email_verification import (
    _active_legal_versions,
    _audit,
    _encrypted_code,
    generate_otp,
    hash_otp,
    mask_email,
    queue_email,
)
from .models import EmailVerificationChallenge, PendingRegistration, User


def _pending_registration_response(
    pending: PendingRegistration, email: str, now
) -> Response:
    challenge = (
        pending.challenges.filter(status="active", expires_at__gt=now)
        .only("expires_at")
        .order_by("-created_at", "-id")
        .first()
    )
    challenge_expires_in = (
        max(0, int((challenge.expires_at - now).total_seconds()))
        if challenge
        else 0
    )
    registration_expires_in = max(
        0, int((pending.expires_at - now).total_seconds())
    )
    return Response(
        {
            "registrationId": f"reg_{pending.pk}",
            "status": pending.status,
            "maskedEmail": mask_email(email),
            # Keep expiresIn aligned with resend/verification semantics: it is
            # the OTP challenge lifetime, not the longer registration lifetime.
            "expiresIn": challenge_expires_in,
            "registrationExpiresIn": registration_expires_in,
            "resendAvailableIn": settings.EMAIL_OTP_RESEND_COOLDOWN_SECONDS,
        },
        status=202,
    )


def _decoy_registration_id(email: str) -> uuid.UUID:
    """Stable, unguessable identifier for an address that cannot be registered.

    Derived from SECRET_KEY so repeating the request returns the same value,
    the way a real pending registration does. A random identifier per call
    would itself distinguish registered addresses from new ones.
    """
    digest = hmac.new(
        settings.SECRET_KEY.encode("utf-8"),
        f"registration-decoy:{email}".encode("utf-8"),
        hashlib.sha256,
    ).digest()
    return uuid.UUID(bytes=digest[:16])


def _unavailable_registration_response(email: str) -> Response:
    """Mirror the accepted-registration body exactly.

    An address that is already registered must not be distinguishable from a
    new one. The identifier resolves to no PendingRegistration, so verify and
    resend already treat it exactly like an expired registration.
    """
    return Response(
        {
            "registrationId": f"reg_{_decoy_registration_id(email)}",
            "status": "pending_email_verification",
            "maskedEmail": mask_email(email),
            "expiresIn": settings.EMAIL_OTP_TTL_SECONDS,
            "registrationExpiresIn": settings.PENDING_REGISTRATION_TTL_SECONDS,
            "resendAvailableIn": settings.EMAIL_OTP_RESEND_COOLDOWN_SECONDS,
        },
        status=202,
    )


class EmailRegistrationView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        if (
            not settings.EMAIL_REGISTRATION_ENABLED
            or not settings.EMAIL_OTP_VERIFICATION_ENABLED
        ):
            return Response(
                {
                    "code": "EMAIL_REGISTRATION_DISABLED",
                    "message": "Registration is temporarily unavailable.",
                },
                status=503,
            )

        email = str(request.data.get("email", "")).strip().lower()
        password = str(request.data.get("password", ""))
        display_name = str(request.data.get("displayName", "")).strip()[:120]
        if (
            not email
            or "@" not in email
            or len(password) < 8
            or not request.data.get("legalAccepted")
        ):
            return Response(
                {
                    "code": "REGISTRATION_INVALID",
                    "message": "Please provide valid registration details and accept the required agreement.",
                },
                status=400,
            )

        # Registered addresses get a body identical to an accepted
        # registration. Returning a different shape here was an enumeration
        # oracle: callers could tell registered from unregistered addresses.
        if User.objects.filter(email__iexact=email).exists():
            return _unavailable_registration_response(email)

        now = timezone.now()
        versions = {
            key: value or "current"
            for key, value in _active_legal_versions().items()
        }
        created = False

        with transaction.atomic():
            expired = PendingRegistration.objects.filter(
                email_normalized=email,
                status="pending_email_verification",
                expires_at__lte=now,
            )
            expired_ids = list(expired.values_list("pk", flat=True))
            if expired_ids:
                expired.update(status="expired")
                EmailVerificationChallenge.objects.filter(
                    registration_id__in=expired_ids,
                    status="active",
                ).update(status="invalidated", invalidated_at=now)

            pending = (
                PendingRegistration.objects.filter(
                    email_normalized=email,
                    status="pending_email_verification",
                )
                .order_by("-created_at", "-id")
                .first()
            )

            if pending is None:
                try:
                    # The inner savepoint can roll back an expected unique-index
                    # race without poisoning the outer transaction.
                    with transaction.atomic():
                        pending = PendingRegistration.objects.create(
                            email_normalized=email,
                            display_name=display_name,
                            password_hash=make_password(password),
                            locale=str(request.data.get("locale", "en"))[:16],
                            legal_confirmation=True,
                            legal_document_versions=versions,
                            expires_at=now
                            + timedelta(
                                seconds=settings.PENDING_REGISTRATION_TTL_SECONDS
                            ),
                            request_ip=request.META.get("REMOTE_ADDR"),
                            request_user_agent=request.META.get(
                                "HTTP_USER_AGENT", ""
                            )[:1000],
                        )
                        code = generate_otp()
                        EmailVerificationChallenge.objects.create(
                            registration=pending,
                            email_normalized=email,
                            otp_hash=hash_otp(code),
                            expires_at=now
                            + timedelta(seconds=settings.EMAIL_OTP_TTL_SECONDS),
                            max_attempts=settings.EMAIL_OTP_MAX_ATTEMPTS,
                            send_count=1,
                        )
                        queue_email(
                            event_type="email_otp_created",
                            email=email,
                            template_key="email_otp",
                            payload={
                                "code_encrypted": _encrypted_code(code),
                                "expires_minutes": settings.EMAIL_OTP_TTL_SECONDS
                                // 60,
                                "purpose": "registration",
                            },
                            idempotency_key=f"otp:{pending.pk}:1",
                            locale=pending.locale,
                        )
                        created = True
                except IntegrityError:
                    pending = (
                        PendingRegistration.objects.filter(
                            email_normalized=email,
                            status="pending_email_verification",
                        )
                        .order_by("-created_at", "-id")
                        .first()
                    )
                    if pending is None:
                        raise

            if created:
                _audit(
                    "registration_pending_email_verification",
                    transaction_id=pending.id,
                    result="accepted",
                    request=request,
                )

        return _pending_registration_response(pending, email, now)
