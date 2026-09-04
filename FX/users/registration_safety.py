"""Concurrency-safe local email registration.

This module keeps the legacy local-registration endpoint available only while
that capability is explicitly enabled.  Database constraints remain the final
authority; the view converts an expected concurrent uniqueness race into an
idempotent 202 response instead of a 500.
"""

from __future__ import annotations

from datetime import timedelta

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


def _pending_registration_response(pending: PendingRegistration, email: str, now) -> Response:
    return Response(
        {
            "registrationId": f"reg_{pending.pk}",
            "status": pending.status,
            "maskedEmail": mask_email(email),
            "expiresIn": max(0, int((pending.expires_at - now).total_seconds())),
            "resendAvailableIn": settings.EMAIL_OTP_RESEND_COOLDOWN_SECONDS,
        },
        status=202,
    )


class EmailRegistrationView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        if not settings.EMAIL_REGISTRATION_ENABLED or not settings.EMAIL_OTP_VERIFICATION_ENABLED:
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
        if not email or "@" not in email or len(password) < 8 or not request.data.get("legalAccepted"):
            return Response(
                {
                    "code": "REGISTRATION_INVALID",
                    "message": "Please provide valid registration details and accept the required agreement.",
                },
                status=400,
            )

        # Preserve the existing non-enumerating response for registered users.
        if User.objects.filter(email__iexact=email).exists():
            return Response(
                {
                    "status": "pending_email_verification",
                    "message": "If this address can be registered, a verification code will be sent.",
                },
                status=202,
            )

        now = timezone.now()
        versions = {key: value or "current" for key, value in _active_legal_versions().items()}
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
                            + timedelta(seconds=settings.PENDING_REGISTRATION_TTL_SECONDS),
                            request_ip=request.META.get("REMOTE_ADDR"),
                            request_user_agent=request.META.get("HTTP_USER_AGENT", "")[:1000],
                        )
                        code = generate_otp()
                        EmailVerificationChallenge.objects.create(
                            registration=pending,
                            email_normalized=email,
                            otp_hash=hash_otp(code),
                            expires_at=now + timedelta(seconds=settings.EMAIL_OTP_TTL_SECONDS),
                            max_attempts=settings.EMAIL_OTP_MAX_ATTEMPTS,
                            send_count=1,
                        )
                        queue_email(
                            event_type="email_otp_created",
                            email=email,
                            template_key="email_otp",
                            payload={
                                "code_encrypted": _encrypted_code(code),
                                "expires_minutes": settings.EMAIL_OTP_TTL_SECONDS // 60,
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
