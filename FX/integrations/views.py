import csv
import hashlib
import hmac
import io
import uuid

from django.core.cache import cache
from django.db import IntegrityError, transaction
from django.http import HttpResponse
from django.utils import timezone
from rest_framework import permissions, status, throttling
from rest_framework.parsers import JSONParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from users.models import User
from .crypto import decrypt_secret, encrypt_secret, fingerprint
from .models import CRMConnection, DemoAccount, DemoLedgerEntry, ExternalIdentity, IntegrationAuditEvent, Organization, ServiceToken, UserImport, UserImportRow
from .permissions import HasScope, ScopedBearerAuthentication, organization_for_request
from .serializers import CRMConnectionSerializer, DemoAccountSerializer, ImportRowSerializer, ImportSerializer, PublicIntakeSerializer, ServiceTokenMetadataSerializer, UserCreateSerializer
from .tasks import process_user_import
from .throttles import CRMInboundThrottle, ImportActionThrottle, ImportThrottle, UserCreateThrottle
from .observability import IMPORT_ROWS_TOTAL, INVALID_SIGNATURE_TOTAL, USER_CREATE_TOTAL, count
from notifications.models import WebhookSubscription
from .services import emit_crm_event
from .control_plane import build_control_plane_context

ALLOWED_COLUMNS = {"external_user_id", "first_name", "last_name", "email", "phone", "organization_id", "locale", "country", "source", "tags", "terms_accepted", "marketing_allowed"}
FORBIDDEN_COLUMNS = {"password", "role", "admin", "permissions", "demo_balance", "real_balance", "account_type", "api_key", "authentication_secret"}
MAX_UPLOAD = 5 * 1024 * 1024
MAX_ROWS = 10000


class TenantContextView(APIView):
    """Returns the caller's authorized tenant context without exposing secrets."""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        context = build_control_plane_context(request)
        tenant = context["tenant"]
        result = Response({
            "tenantId": tenant["tenant_id"],
            "name": tenant["name"],
            "active": tenant["active"],
            "role": tenant["role"],
            "environment": "staging" if getattr(request, "service_token", None) is None else getattr(request.service_token, "environment", "staging"),
        })
        result["Deprecation"] = "true"
        result["Sunset"] = "Fri, 27 Feb 2027 00:00:00 GMT"
        result["Link"] = '</api/v1/control-plane/context>; rel="successor-version"'
        return result


class ControlPlaneContextView(APIView):
    """Compose the caller's canonical account, tenant and policy decisions."""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        result = Response(build_control_plane_context(request))
        result["Cache-Control"] = "private, no-store"
        result["Vary"] = "Cookie, Authorization, X-Organization-ID"
        return result


class PublicIntakeView(APIView):
    authentication_classes = []
    permission_classes = [permissions.AllowAny]
    throttle_scope = "public_intake"

    def post(self, request):
        serializer = PublicIntakeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        organization, _ = Organization.objects.get_or_create(
            name="Beyvra public intake",
            defaults={"is_active": True},
        )
        key = request.headers.get("Idempotency-Key") or request.headers.get("X-Request-ID") or str(uuid.uuid4())
        prior = IntegrationAuditEvent.objects.filter(
            organization=organization,
            action="public.intake",
            metadata__idempotency_key=key,
        ).first()
        if prior:
            return Response(prior.metadata["result"], status=status.HTTP_200_OK)
        result = {
            "intake_id": str(uuid.uuid5(uuid.NAMESPACE_URL, f"beyvra-public-intake:{key}")),
            "status": "submitted",
            "source": data["source"],
        }
        IntegrationAuditEvent.objects.create(
            organization=organization,
            action="public.intake",
            metadata={
                "idempotency_key": key,
                "result": result,
                "source": data["source"],
                "interest": data["interest"],
                "email": data["email"],
                "name": data["name"],
                "goal_preview": data["goal"][:160],
                "contact_consent": data["consent"],
            },
        )
        return Response(result, status=status.HTTP_202_ACCEPTED)


def _create_user(attrs, organization, reference):
    if str(attrs["organization_id"]) != str(organization.id):
        raise PermissionError("organization mismatch")
    if ExternalIdentity.objects.filter(organization=organization, external_user_id=attrs["external_user_id"]).exists():
        raise ValueError("duplicate external_user_id")
    with transaction.atomic():
        user = User.objects.create_user(email=attrs["email"], password=None, first_name=attrs["first_name"], last_name=attrs["last_name"], phone_number=attrs["phone"], preferred_language=attrs.get("locale", "en"), country_iso_code=attrs.get("country", ""), verification_status="CHANGE_PASSWORD", email_verified=False)
        user.set_unusable_password(); user.save(update_fields=["password", "verification_status", "email_verified", "updated_at"])
        ExternalIdentity.objects.create(organization=organization, user=user, external_user_id=attrs["external_user_id"], source=attrs.get("source", "third_party_crm"))
        account = DemoAccount.objects.create(user=user, organization=organization)
        DemoLedgerEntry.objects.create(account=account, reference=reference)
    return user, account


def _result(user, account, created=True):
    return {"user_id": str(user.id), "status": "pending_activation", "demo_account": {**DemoAccountSerializer(account).data, "account_id": str(account.id)}, "created": created}


class UserCreateView(APIView):
    authentication_classes = [ScopedBearerAuthentication]
    permission_classes = [HasScope]
    required_scope = "users:write"
    throttle_classes = [UserCreateThrottle]

    def post(self, request):
        serializer = UserCreateSerializer(data=request.data); serializer.is_valid(raise_exception=True)
        org = organization_for_request(request); key = request.headers.get("Idempotency-Key")
        if not key or len(key) > 255: return Response({"detail": "Idempotency-Key is required"}, status=400)
        prior = IntegrationAuditEvent.objects.filter(organization=org, action="user.create", metadata__idempotency_key=key).first()
        if prior: return Response(prior.metadata["result"], status=200)
        try: user, account = _create_user(serializer.validated_data, org, key)
        except PermissionError as exc: return Response({"detail": str(exc)}, status=403)
        except (ValueError, IntegrityError) as exc: return Response({"detail": str(exc)}, status=409)
        result = _result(user, account)
        count(USER_CREATE_TOTAL)
        emit_crm_event(organization=org, event_type="user.created", data={"user_id": str(user.id), "demo_account_id": str(account.id)}, correlation_id=user.id)
        IntegrationAuditEvent.objects.create(organization=org, action="user.create", metadata={"idempotency_key": key, "result": result})
        return Response(result, status=201)


class CRMInboundUserView(APIView):
    authentication_classes = []
    permission_classes = [permissions.AllowAny]
    parser_classes = [JSONParser]
    throttle_classes = [CRMInboundThrottle]

    def post(self, request, connection_id):
        if int(request.META.get("CONTENT_LENGTH") or 0) > 1024 * 1024:
            return Response({"detail": "payload too large"}, status=413)
        connection = CRMConnection.objects.filter(id=connection_id, is_active=True).first()
        if not connection: return Response({"detail": "connection not found"}, status=404)
        timestamp = request.headers.get("X-Codestra-Timestamp", ""); event_id = request.headers.get("X-Codestra-Event-Id") or request.headers.get("Idempotency-Key"); signature = request.headers.get("X-Codestra-Signature-256", "")
        try: signed_at = int(timestamp)
        except ValueError: return Response({"detail": "invalid timestamp"}, status=401)
        if abs(int(timezone.now().timestamp()) - signed_at) > 300 or not event_id: return Response({"detail": "expired or missing event"}, status=401)
        connection_secret = decrypt_secret(connection.secret_ciphertext, connection.secret_nonce, connection.secret_key_version) if connection.secret_ciphertext else decrypt_secret(connection.secret_encrypted)
        expected = hmac.new(connection_secret.encode(), f"{timestamp}.".encode() + request.body, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature.removeprefix("sha256="), expected):
            count(INVALID_SIGNATURE_TOTAL, "crm")
            return Response({"detail": "invalid signature"}, status=401)
        replay_key = f"crm-replay:{connection.id}:{event_id}"
        if not cache.add(replay_key, "seen", timeout=900): return Response({"detail": "replay"}, status=409)
        if IntegrationAuditEvent.objects.filter(organization=connection.organization, action="crm.inbound", metadata__event_id=event_id).exists(): return Response({"detail": "replay"}, status=409)
        serializer = UserCreateSerializer(data=request.data); serializer.is_valid(raise_exception=True); data = serializer.validated_data; data["organization_id"] = connection.organization.id
        try: user, account = _create_user(data, connection.organization, f"crm:{connection.id}:{event_id}")
        except (ValueError, IntegrityError): return Response({"detail": "duplicate identity"}, status=409)
        IntegrationAuditEvent.objects.create(organization=connection.organization, action="crm.inbound", metadata={"event_id": event_id, "user_id": str(user.id)})
        return Response(_result(user, account), status=201)


class CSVTemplateView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    def get(self, request):
        response = HttpResponse(",".join(sorted(ALLOWED_COLUMNS)) + "\n", content_type="text/csv"); response["Content-Disposition"] = 'attachment; filename="codestra-users-template.csv"'; return response


class UserImportView(APIView):
    parser_classes = [MultiPartParser]
    permission_classes = [permissions.IsAuthenticated]
    throttle_classes = [ImportThrottle]
    def post(self, request):
        if not request.user.is_staff: return Response({"detail": "organization administrator required"}, status=403)
        upload = request.FILES.get("file")
        if not upload or upload.size > MAX_UPLOAD or not upload.name.lower().endswith(".csv"): return Response({"detail": "UTF-8 CSV under 5MB required"}, status=400)
        org = organization_for_request(request); key = request.headers.get("Idempotency-Key") or str(uuid.uuid4())
        job, created = UserImport.objects.get_or_create(organization=org, idempotency_key=key, defaults={"created_by": request.user, "file_name": upload.name})
        if not created: return Response(ImportSerializer(job).data, status=200)
        try:
            reader = csv.DictReader(io.StringIO(upload.read().decode("utf-8-sig"))); columns = set(reader.fieldnames or [])
            if not columns or columns - ALLOWED_COLUMNS or columns & FORBIDDEN_COLUMNS: raise ValueError("unsupported CSV columns")
            for number, row in enumerate(reader, 2):
                if number - 1 > MAX_ROWS: raise ValueError("row limit exceeded")
                errors = []
                for field in ("external_user_id", "first_name", "last_name", "email", "phone", "organization_id"):
                    if not row.get(field): errors.append(f"missing {field}")
                if any(str(v).lstrip().startswith(("=", "+", "-", "@")) for v in row.values() if v): errors.append("formula-like value")
                try:
                    UserCreateSerializer(data={**row, "consent": {"terms_accepted": str(row.get("terms_accepted", "")).lower() == "true"}}).is_valid(raise_exception=True)
                except Exception: errors.append("invalid field")
                row_status = "INVALID" if errors else "VALID"
                UserImportRow.objects.create(import_job=job, row_number=number, data=row, errors=errors, status=row_status)
                count(IMPORT_ROWS_TOTAL, row_status.lower())
            job.row_count = job.rows.count(); job.valid_count = job.rows.filter(status="VALID").count(); job.invalid_count = job.rows.filter(status="INVALID").count(); job.save()
        except (UnicodeDecodeError, csv.Error, ValueError) as exc:
            job.status = "FAILED"; job.save(update_fields=["status", "updated_at"]); return Response({"detail": str(exc)}, status=400)
        return Response(ImportSerializer(job).data, status=201)


class ImportDetailView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    def get_job(self, request, import_id): return UserImport.objects.get(id=import_id, created_by=request.user)
    def get(self, request, import_id): return Response(ImportSerializer(self.get_job(request, import_id)).data)


class ImportRowsView(ImportDetailView):
    def get(self, request, import_id): return Response(ImportRowSerializer(self.get_job(request, import_id).rows.order_by("row_number"), many=True).data)


class ImportActionView(ImportDetailView):
    action = None
    throttle_classes = [ImportActionThrottle]
    def post(self, request, import_id):
        job = self.get_job(request, import_id)
        if self.action == "commit" and job.status == "UPLOADED":
            if UserImport.objects.filter(organization=job.organization, status__in=["COMMITTED", "PROCESSING"]).exclude(id=job.id).exists():
                return Response({"detail": "organization import concurrency limit reached"}, status=429)
            lock_key = f"import-commit:{job.id}"
            if not cache.add(lock_key, "queued", timeout=3600): return Response({"detail": "import already queued"}, status=409)
            job.status = "COMMITTED"; job.save(update_fields=["status", "updated_at"]); process_user_import.delay(str(job.id))
        elif self.action == "cancel" and job.status in {"UPLOADED", "COMMITTED"}: job.status = "CANCELLED"; job.save(update_fields=["status", "updated_at"])
        else: return Response({"detail": "invalid import state"}, status=409)
        return Response(ImportSerializer(job).data)


class ImportCommitView(ImportActionView): action = "commit"
class ImportCancelView(ImportActionView): action = "cancel"


class CRMConnectionListView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    def get(self, request): return Response(CRMConnectionSerializer(organization_for_request(request).crm_connections.all(), many=True).data)
    def post(self, request):
        if not request.user.is_staff: return Response({"detail": "organization administrator required"}, status=403)
        serializer = CRMConnectionSerializer(data=request.data); serializer.is_valid(raise_exception=True); data = serializer.validated_data; secret = data.pop("secret"); ciphertext, nonce, version = encrypt_secret(secret); connection = CRMConnection.objects.create(organization=organization_for_request(request), owner=request.user, secret_encrypted="", secret_ciphertext=ciphertext, secret_nonce=nonce, secret_key_version=version, secret_fingerprint=fingerprint(secret), secret_created_at=timezone.now(), **data)
        WebhookSubscription.objects.create(user=request.user, url=connection.endpoint, categories=connection.event_categories, is_active=connection.is_active, **__import__("notifications.services", fromlist=["encrypted_webhook_fields"]).encrypted_webhook_fields(secret))
        return Response(CRMConnectionSerializer(connection).data, status=201)


class CRMConnectionDetailView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    def get_object(self, request, connection_id): return CRMConnection.objects.get(id=connection_id, organization=organization_for_request(request))
    def get(self, request, connection_id): return Response(CRMConnectionSerializer(self.get_object(request, connection_id)).data)
    def patch(self, request, connection_id):
        obj = self.get_object(request, connection_id); data = request.data.copy(); secret = data.pop("secret", None); serializer = CRMConnectionSerializer(obj, data=data, partial=True); serializer.is_valid(raise_exception=True); obj = serializer.save()
        if secret:
            ciphertext, nonce, version = encrypt_secret(secret); obj.secret_encrypted = ""; obj.secret_ciphertext = ciphertext; obj.secret_nonce = nonce; obj.secret_key_version = version; obj.secret_fingerprint = fingerprint(secret); obj.secret_rotated_at = timezone.now(); obj.save(update_fields=["secret_encrypted", "secret_ciphertext", "secret_nonce", "secret_key_version", "secret_fingerprint", "secret_rotated_at", "updated_at"])
            from notifications.services import encrypted_webhook_fields
            WebhookSubscription.objects.filter(user=obj.owner, url=obj.endpoint).update(**encrypted_webhook_fields(secret))
        WebhookSubscription.objects.filter(user=obj.owner, url=obj.endpoint).update(categories=obj.event_categories, is_active=obj.is_active)
        return Response(CRMConnectionSerializer(obj).data)


class ServiceTokenListView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    def get(self, request):
        org = organization_for_request(request)
        return Response(ServiceTokenMetadataSerializer(org.service_tokens.order_by("-created_at"), many=True).data)
    def post(self, request):
        if not request.user.is_staff:
            return Response({"detail": "organization administrator required"}, status=403)
        scopes = request.data.get("scopes", [])
        allowed = {"users:read", "users:write", "users:import", "demo_accounts:read", "crm_connections:read", "crm_connections:write", "crm_deliveries:read", "crm_deliveries:retry", "webhooks:read", "webhooks:write"}
        if not isinstance(scopes, list) or not set(scopes).issubset(allowed):
            return Response({"detail": "invalid scopes"}, status=400)
        org = organization_for_request(request); token, raw = ServiceToken.issue(org, request.data.get("name", "integration"), scopes); token.owner = request.user; token.save(update_fields=["owner"])
        IntegrationAuditEvent.objects.create(organization=org, actor=request.user, action="service_token.issue", metadata={"token_id": str(token.id), "fingerprint": token.fingerprint})
        response = ServiceTokenMetadataSerializer(token).data; response["token"] = raw
        return Response(response, status=201)


class ServiceTokenActionView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    def post(self, request, token_id):
        token = ServiceToken.objects.get(id=token_id, organization=organization_for_request(request))
        if not request.user.is_staff: return Response({"detail": "organization administrator required"}, status=403)
        action = request.data.get("action", "revoke")
        if action == "revoke":
            token.is_active = False; token.revoked_at = timezone.now(); token.save(update_fields=["is_active", "revoked_at"]); return Response(ServiceTokenMetadataSerializer(token).data)
        if action == "rotate":
            replacement, raw = ServiceToken.issue(token.organization, token.name, token.scopes); replacement.owner = request.user; replacement.save(update_fields=["owner"]); token.is_active = False; token.revoked_at = timezone.now(); token.save(update_fields=["is_active", "revoked_at"]); response = ServiceTokenMetadataSerializer(replacement).data; response["token"] = raw; return Response(response, status=201)
        return Response({"detail": "unsupported action"}, status=400)
