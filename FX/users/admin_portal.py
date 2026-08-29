from django.conf import settings
from django.db.models import Count, Q
from django.utils import timezone
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.compliance.models import ComplianceCase, ComplianceProfile
from financial_boundary.models import ProviderWebhookInbox
from operations.models import AuditEvent, SecurityEvent
from platform_ops.health.services import HealthAuthority
from users.models import User, UserRoles


def _is_admin(user):
    return bool(
        user
        and user.is_authenticated
        and (
            user.is_staff
            or user.is_superuser
            or user.role in {UserRoles.Admin.value, UserRoles.Super_Admin.value}
        )
    )


def _limit(value, default=10, maximum=50):
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return min(max(parsed, 1), maximum)


def _user_payload(user):
    return {
        "id": user.id,
        "email": user.email,
        "firstName": user.first_name,
        "lastName": user.last_name,
        "role": user.role,
        "isStaff": user.is_staff,
        "isSuperuser": user.is_superuser,
        "isActive": user.is_active,
        "emailVerified": user.email_verified,
        "createdAt": user.created_at,
        "dateJoined": user.date_joined,
    }


def _audit_payload(event):
    return {
        "auditId": str(event.audit_id),
        "action": event.action,
        "target": event.target,
        "role": event.role,
        "actorEmail": event.actor.email if event.actor_id else "",
        "timestamp": event.timestamp,
    }


def _webhook_payload(event):
    return {
        "id": str(event.id),
        "provider": event.provider,
        "externalEventId": event.external_event_id,
        "tenantId": str(event.tenant_id),
        "status": event.status,
        "attempts": event.attempts,
        "receivedAt": event.received_at,
        "processedAt": event.processed_at,
        "failureCode": event.failure_code,
    }


class AdminPortalPermissionMixin:
    permission_classes = [IsAuthenticated]

    def check_permissions(self, request):
        super().check_permissions(request)
        if not _is_admin(request.user):
            self.permission_denied(request, message="Admin portal access is required.")


class AdminPortalSummaryView(AdminPortalPermissionMixin, APIView):
    def get(self, request):
        today = timezone.localdate()
        users = User.objects.aggregate(
            total=Count("id"),
            active=Count("id", filter=Q(is_active=True)),
            staff=Count("id", filter=Q(is_staff=True) | Q(is_superuser=True)),
            admins=Count(
                "id",
                filter=Q(role__in=[UserRoles.Admin.value, UserRoles.Super_Admin.value]),
            ),
            contractors=Count("id", filter=Q(role=UserRoles.Contractor.value)),
            newToday=Count("id", filter=Q(created_at__date=today)),
        )
        compliance = {
            "profiles": ComplianceProfile.objects.count(),
            "pendingProfiles": ComplianceProfile.objects.filter(account_state="PENDING").count(),
            "activeProfiles": ComplianceProfile.objects.filter(account_state="ACTIVE").count(),
            "openCases": ComplianceCase.objects.filter(
                status__in=("OPEN", "IN_REVIEW", "ESCALATED"),
            ).count(),
        }
        webhook_status_keys = {
            ProviderWebhookInbox.Status.PENDING: "pending",
            ProviderWebhookInbox.Status.PROCESSING: "processing",
            ProviderWebhookInbox.Status.PROCESSED: "processed",
            ProviderWebhookInbox.Status.DEAD_LETTER: "deadLetter",
        }
        webhooks = dict.fromkeys(webhook_status_keys.values(), 0)
        for row in ProviderWebhookInbox.objects.values("status").annotate(total=Count("id")):
            key = webhook_status_keys.get(row["status"])
            if key:
                webhooks[key] = row["total"]
        security = {
            "openHighRiskEvents": SecurityEvent.objects.filter(
                risk_level__in=("HIGH", "CRITICAL"),
                resolved=False,
            ).count(),
        }
        system = {
            "state": HealthAuthority.system_state(),
            "realtimeV2Enabled": bool(getattr(settings, "REALTIME_V2_ENABLED", False)),
            "environment": getattr(settings, "DEPLOYMENT_ENV", ""),
        }
        recent_audit = AuditEvent.objects.select_related("actor").order_by(
            "-timestamp",
        )[:5]
        return Response(
            {
                "users": users,
                "compliance": compliance,
                "webhooks": webhooks,
                "security": security,
                "system": system,
                "audit": {"recent": [_audit_payload(event) for event in recent_audit]},
            }
        )


class AdminPortalUsersView(AdminPortalPermissionMixin, APIView):
    def get(self, request):
        limit = _limit(request.query_params.get("limit"), default=20)
        users = User.objects.order_by("-created_at", "-id")[:limit]
        return Response({"results": [_user_payload(user) for user in users]})


class AdminPortalEventsView(AdminPortalPermissionMixin, APIView):
    def get(self, request):
        limit = _limit(request.query_params.get("limit"), default=20)
        audit_events = AuditEvent.objects.select_related("actor").order_by("-timestamp")[
            :limit
        ]
        webhook_events = ProviderWebhookInbox.objects.order_by("-received_at")[:limit]
        return Response(
            {
                "audit": [_audit_payload(event) for event in audit_events],
                "webhooks": [_webhook_payload(event) for event in webhook_events],
            }
        )
