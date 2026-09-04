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
from drf_spectacular.utils import OpenApiParameter, OpenApiTypes, extend_schema

from users.models import User
from .crypto import decrypt, decrypt_secret, encrypt, encrypt_secret, fingerprint
from .models import CRMConnection, DemoAccount, DemoLedgerEntry, ExternalIdentity, IntegrationAuditEvent, ServiceToken, UserImport, UserImportRow
from .permissions import HasScope, ScopedBearerAuthentication, organization_for_request
from .serializers import CRMConnectionSerializer, DemoAccountSerializer, ImportRowSerializer, ImportSerializer, ServiceTokenMetadataSerializer, UserCreateSerializer
from .tasks import process_user_import
from .throttles import CRMInboundThrottle, ImportActionThrottle, ImportThrottle, UserCreateThrottle
from .observability import IMPORT_ROWS_TOTAL, INVALID_SIGNATURE_TOTAL, USER_CREATE_TOTAL, count
from notifications.models import WebhookSubscription
from apps.foundation.models import ApplicationAuditEvent
from apps.foundation.services import IdempotencyConflict, begin_idempotent_request, complete_idempotent_request
from .services import emit_crm_event

ALLOWED_COLUMNS = {"external_user_id", "first_name", "last_name", "email", "phone", "organization_id", "locale", "country", "source", "tags", "terms_accepted", "marketing_allowed"}
FORBIDDEN_COLUMNS = {"password", "role", "admin", "permissions", "demo_balance", "real_balance", "account_type", "api_key", "authentication_secret"}
MAX_UPLOAD = 5 * 1024 * 1024
MAX_ROWS = 10000

COMMAND_PARAMETERS = [
    OpenApiParameter("Idempotency-Key", OpenApiTypes.STR, OpenApiParameter.HEADER, required=True),
    OpenApiParameter("X-Request-ID", OpenApiTypes.UUID, OpenApiParameter.HEADER, required=True),
    OpenApiParameter("X-Correlation-ID", OpenApiTypes.UUID, OpenApiParameter.HEADER, required=False),
]
VERSIONED_COMMAND_PARAMETERS = COMMAND_PARAMETERS + [
    OpenApiParameter("If-Match", OpenApiTypes.STR, OpenApiParameter.HEADER, required=True),
]


def _command_context(request, *, require_version=False):
    key = request.headers.get("Idempotency-Key", "").strip()
    request_id = request.headers.get("X-Request-ID", "").strip()
    expected_version = request.headers.get("If-Match", "").strip()
    if not key or len(key) > 255 or not request_id or len(request_id) > 128:
        return None, Response({"detail": "Idempotency-Key and X-Request-ID are required"}, status=400)
    if require_version and not expected_version:
        return None, Response({"detail": "If-Match is required"}, status=428)
    try:
        correlation_id = uuid.UUID(request.headers.get("X-Correlation-ID") or request_id)
    except (TypeError, ValueError):
        return None, Response({"detail": "correlation identifier must be a UUID"}, status=400)
    return (key, request_id, correlation_id, expected_version), None


def _actor_ref(request):
    token = getattr(request, "service_token", None)
    return f"service-token:{token.pk}" if token else str(request.user.pk)


def _begin_command(request, *, organization, key, payload):
    return begin_idempotent_request(
        key=key, tenant_ref=organization.pk, actor_ref=_actor_ref(request), endpoint=request.path,
        method=request.method, request_data={"api_version": "v1", **payload},
    )


def _replay(record):
    if record.response_status is None or record.response_body is None:
        return Response({"detail": "command result is not yet available"}, status=409)
    return Response(record.response_body, status=record.response_status)


def _complete_secret_result(record, *, status_code, body, raw_secret, resource_type, resource_id):
    ciphertext, nonce, version = encrypt(raw_secret)
    stored = {**body, "_secret_envelope": {"ciphertext": ciphertext, "nonce": nonce, "version": version}}
    complete_idempotent_request(record, status=status_code, body=stored, resource_type=resource_type, resource_id=resource_id)


def _replay_secret(record):
    if record.response_status is None or record.response_body is None:
        return Response({"detail": "command result is not yet available"}, status=409)
    if record.expires_at <= timezone.now():
        return Response({"detail": "one-time secret replay window has expired"}, status=410)
    stored = dict(record.response_body)
    envelope = stored.pop("_secret_envelope", None)
    if not envelope:
        return Response({"detail": "one-time secret is unavailable"}, status=409)
    stored["token"] = decrypt(envelope["ciphertext"], envelope["nonce"], key_version=envelope["version"])
    return Response(stored, status=record.response_status)


def _command_audit(*, organization, request, action, correlation_id, metadata=None):
    actor = request.user if isinstance(request.user, User) else None
    metadata = metadata or {}
    event = IntegrationAuditEvent.objects.create(
        organization=organization, actor=actor, action=action, correlation_id=correlation_id, metadata=metadata or {},
    )
    ApplicationAuditEvent.objects.create(
        actor_ref=_actor_ref(request), action=action, resource_type="integration",
        resource_id=str(metadata.get("user_id") or metadata.get("import_id") or metadata.get("connection_id") or metadata.get("token_id") or event.pk),
        request_id=str(metadata.get("request_id", ""))[:128], correlation_id=correlation_id,
        context={"tenant_ref": str(organization.pk)}, reason="integration command", occurred_at=timezone.now(),
    )
    return event


class TenantContextView(APIView):
    """Returns the caller's authorized tenant context without exposing secrets."""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        organization = organization_for_request(request)
        membership = organization.memberships.filter(user=request.user).values("role").first()
        return Response({
            "tenantId": str(organization.id),
            "name": organization.name,
            "active": organization.is_active,
            "role": membership["role"] if membership else "service",
            "environment": "staging" if getattr(request, "service_token", None) is None else getattr(request.service_token, "environment", "staging"),
        })


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

    @extend_schema(parameters=COMMAND_PARAMETERS)
    @transaction.atomic
    def post(self, request):
        serializer = UserCreateSerializer(data=request.data); serializer.is_valid(raise_exception=True)
        org = organization_for_request(request); command, error = _command_context(request)
        if error: return error
        key, request_id, correlation_id, _ = command
        try: record, created = _begin_command(request, organization=org, key=key, payload=serializer.validated_data)
        except IdempotencyConflict: return Response({"detail": "IDEMPOTENCY_CONFLICT"}, status=409)
        if not created: return _replay(record)
        try: user, account = _create_user(serializer.validated_data, org, key)
        except PermissionError as exc: record.delete(); return Response({"detail": str(exc)}, status=403)
        except (ValueError, IntegrityError) as exc: record.delete(); return Response({"detail": str(exc)}, status=409)
        result = _result(user, account)
        count(USER_CREATE_TOTAL)
        emit_crm_event(organization=org, event_type="user.created", data={"user_id": str(user.id), "demo_account_id": str(account.id)}, correlation_id=user.id)
        _command_audit(organization=org, request=request, action="user.create", correlation_id=correlation_id, metadata={"request_id": request_id, "user_id": str(user.pk)})
        complete_idempotent_request(record, status=201, body=result, resource_type="user", resource_id=user.pk)
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
    @extend_schema(parameters=COMMAND_PARAMETERS)
    @transaction.atomic
    def post(self, request):
        if not request.user.is_staff: return Response({"detail": "organization administrator required"}, status=403)
        upload = request.FILES.get("file")
        if not upload or upload.size > MAX_UPLOAD or not upload.name.lower().endswith(".csv"): return Response({"detail": "UTF-8 CSV under 5MB required"}, status=400)
        org = organization_for_request(request); command, error = _command_context(request)
        if error: return error
        key, request_id, correlation_id, _ = command
        digest = hashlib.sha256()
        for chunk in upload.chunks(): digest.update(chunk)
        upload.seek(0)
        try: record, command_created = _begin_command(request, organization=org, key=key, payload={"file_name": upload.name, "size": upload.size, "sha256": digest.hexdigest()})
        except IdempotencyConflict: return Response({"detail": "IDEMPOTENCY_CONFLICT"}, status=409)
        if not command_created: return _replay(record)
        job, created = UserImport.objects.get_or_create(organization=org, idempotency_key=key, defaults={"created_by": request.user, "file_name": upload.name})
        if not created:
            record.delete(); return Response({"detail": "IDEMPOTENCY_CONFLICT"}, status=409)
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
            job.status = "FAILED"; job.save(update_fields=["status", "updated_at"])
            body = {"detail": str(exc)}
            complete_idempotent_request(record, status=400, body=body, resource_type="user_import", resource_id=job.pk)
            return Response(body, status=400)
        body = ImportSerializer(job).data
        _command_audit(organization=org, request=request, action="user_import.upload", correlation_id=correlation_id, metadata={"request_id": request_id, "import_id": str(job.pk), "file_sha256": digest.hexdigest()})
        complete_idempotent_request(record, status=201, body=body, resource_type="user_import", resource_id=job.pk)
        return Response(body, status=201)


class ImportDetailView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    def get_job(self, request, import_id): return UserImport.objects.get(id=import_id, created_by=request.user)
    def get(self, request, import_id): return Response(ImportSerializer(self.get_job(request, import_id)).data)


class ImportRowsView(ImportDetailView):
    def get(self, request, import_id): return Response(ImportRowSerializer(self.get_job(request, import_id).rows.order_by("row_number"), many=True).data)


class ImportActionView(ImportDetailView):
    action = None
    throttle_classes = [ImportActionThrottle]
    @extend_schema(parameters=COMMAND_PARAMETERS)
    @transaction.atomic
    def post(self, request, import_id):
        command, error = _command_context(request)
        if error: return error
        key, request_id, correlation_id, _ = command
        job = UserImport.objects.select_for_update().get(id=import_id, created_by=request.user)
        try: record, created = _begin_command(request, organization=job.organization, key=key, payload={"import_id": str(import_id), "action": self.action})
        except IdempotencyConflict: return Response({"detail": "IDEMPOTENCY_CONFLICT"}, status=409)
        if not created: return _replay(record)
        if self.action == "commit" and job.status == "UPLOADED":
            if UserImport.objects.filter(organization=job.organization, status__in=["COMMITTED", "PROCESSING"]).exclude(id=job.id).exists():
                record.delete(); return Response({"detail": "organization import concurrency limit reached"}, status=429)
            lock_key = f"import-commit:{job.id}"
            if not cache.add(lock_key, "queued", timeout=3600): record.delete(); return Response({"detail": "import already queued"}, status=409)
            job.status = "COMMITTED"; job.save(update_fields=["status", "updated_at"]); transaction.on_commit(lambda: process_user_import.delay(str(job.id)))
        elif self.action == "cancel" and job.status in {"UPLOADED", "COMMITTED"}: job.status = "CANCELLED"; job.save(update_fields=["status", "updated_at"])
        else: record.delete(); return Response({"detail": "invalid import state"}, status=409)
        body = ImportSerializer(job).data
        _command_audit(organization=job.organization, request=request, action=f"user_import.{self.action}", correlation_id=correlation_id, metadata={"request_id": request_id, "import_id": str(job.pk), "status": job.status})
        complete_idempotent_request(record, status=200, body=body, resource_type="user_import", resource_id=job.pk)
        return Response(body)


class ImportCommitView(ImportActionView): action = "commit"
class ImportCancelView(ImportActionView): action = "cancel"


class CRMConnectionListView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    def get(self, request): return Response(CRMConnectionSerializer(organization_for_request(request).crm_connections.all(), many=True).data)
    @extend_schema(parameters=COMMAND_PARAMETERS)
    @transaction.atomic
    def post(self, request):
        if not request.user.is_staff: return Response({"detail": "organization administrator required"}, status=403)
        serializer = CRMConnectionSerializer(data=request.data); serializer.is_valid(raise_exception=True)
        org = organization_for_request(request); command, error = _command_context(request)
        if error: return error
        key, request_id, correlation_id, _ = command
        try: record, created = _begin_command(request, organization=org, key=key, payload=serializer.validated_data)
        except IdempotencyConflict: return Response({"detail": "IDEMPOTENCY_CONFLICT"}, status=409)
        if not created: return _replay(record)
        data = serializer.validated_data; secret = data.pop("secret"); ciphertext, nonce, version = encrypt_secret(secret); connection = CRMConnection.objects.create(organization=org, owner=request.user, secret_encrypted="", secret_ciphertext=ciphertext, secret_nonce=nonce, secret_key_version=version, secret_fingerprint=fingerprint(secret), secret_created_at=timezone.now(), **data)
        WebhookSubscription.objects.create(user=request.user, url=connection.endpoint, categories=connection.event_categories, is_active=connection.is_active, **__import__("notifications.services", fromlist=["encrypted_webhook_fields"]).encrypted_webhook_fields(secret))
        body = CRMConnectionSerializer(connection).data
        _command_audit(organization=org, request=request, action="crm.connection.create", correlation_id=correlation_id, metadata={"request_id": request_id, "connection_id": str(connection.pk)})
        complete_idempotent_request(record, status=201, body=body, resource_type="crm_connection", resource_id=connection.pk)
        return Response(body, status=201)


class CRMConnectionDetailView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    def get_object(self, request, connection_id): return CRMConnection.objects.get(id=connection_id, organization=organization_for_request(request))
    def get(self, request, connection_id): return Response(CRMConnectionSerializer(self.get_object(request, connection_id)).data)
    @extend_schema(parameters=VERSIONED_COMMAND_PARAMETERS)
    @transaction.atomic
    def patch(self, request, connection_id):
        command, error = _command_context(request, require_version=True)
        if error: return error
        key, request_id, correlation_id, expected_version = command
        org = organization_for_request(request)
        obj = CRMConnection.objects.select_for_update().get(id=connection_id, organization=org)
        old_endpoint = obj.endpoint
        data = request.data.copy(); secret = data.pop("secret", None); serializer = CRMConnectionSerializer(obj, data=data, partial=True); serializer.is_valid(raise_exception=True)
        try: record, created = _begin_command(request, organization=org, key=key, payload={"connection_id": str(connection_id), "expected_version": expected_version, **request.data})
        except IdempotencyConflict: return Response({"detail": "IDEMPOTENCY_CONFLICT"}, status=409)
        if not created: return _replay(record)
        current_version = obj.updated_at.isoformat().replace("+00:00", "Z")
        if expected_version != current_version:
            record.delete(); return Response({"detail": "VERSION_CONFLICT"}, status=409)
        obj = serializer.save()
        subscription_updates = {"url": obj.endpoint, "categories": obj.event_categories, "is_active": obj.is_active}
        if secret:
            ciphertext, nonce, version = encrypt_secret(secret); obj.secret_encrypted = ""; obj.secret_ciphertext = ciphertext; obj.secret_nonce = nonce; obj.secret_key_version = version; obj.secret_fingerprint = fingerprint(secret); obj.secret_rotated_at = timezone.now(); obj.save(update_fields=["secret_encrypted", "secret_ciphertext", "secret_nonce", "secret_key_version", "secret_fingerprint", "secret_rotated_at", "updated_at"])
            from notifications.services import encrypted_webhook_fields
            subscription_updates.update(encrypted_webhook_fields(secret))
        WebhookSubscription.objects.filter(user=obj.owner, url=old_endpoint).update(**subscription_updates)
        body = CRMConnectionSerializer(obj).data
        _command_audit(organization=org, request=request, action="crm.connection.update", correlation_id=correlation_id, metadata={"request_id": request_id, "connection_id": str(obj.pk), "secret_rotated": bool(secret)})
        complete_idempotent_request(record, status=200, body=body, resource_type="crm_connection", resource_id=obj.pk)
        return Response(body)


class ServiceTokenListView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    def get(self, request):
        org = organization_for_request(request)
        return Response(ServiceTokenMetadataSerializer(org.service_tokens.order_by("-created_at"), many=True).data)
    @extend_schema(parameters=COMMAND_PARAMETERS)
    @transaction.atomic
    def post(self, request):
        if not request.user.is_staff:
            return Response({"detail": "organization administrator required"}, status=403)
        scopes = request.data.get("scopes", [])
        allowed = {"users:read", "users:write", "users:import", "demo_accounts:read", "crm_connections:read", "crm_connections:write", "crm_deliveries:read", "crm_deliveries:retry", "webhooks:read", "webhooks:write"}
        if not isinstance(scopes, list) or not set(scopes).issubset(allowed):
            return Response({"detail": "invalid scopes"}, status=400)
        org = organization_for_request(request); command, error = _command_context(request)
        if error: return error
        key, request_id, correlation_id, _ = command
        payload = {"name": request.data.get("name", "integration"), "scopes": sorted(scopes)}
        try: record, created = _begin_command(request, organization=org, key=key, payload=payload)
        except IdempotencyConflict: return Response({"detail": "IDEMPOTENCY_CONFLICT"}, status=409)
        if not created: return _replay_secret(record)
        token, raw = ServiceToken.issue(org, payload["name"], scopes); token.owner = request.user; token.save(update_fields=["owner"])
        _command_audit(organization=org, request=request, action="service_token.issue", correlation_id=correlation_id, metadata={"request_id": request_id, "token_id": str(token.id), "fingerprint": token.fingerprint})
        response = ServiceTokenMetadataSerializer(token).data
        _complete_secret_result(record, status_code=201, body=response, raw_secret=raw, resource_type="service_token", resource_id=token.pk)
        return Response({**response, "token": raw}, status=201)


class ServiceTokenActionView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    @extend_schema(parameters=VERSIONED_COMMAND_PARAMETERS)
    @transaction.atomic
    def post(self, request, token_id):
        command, error = _command_context(request, require_version=True)
        if error: return error
        key, request_id, correlation_id, expected_version = command
        org = organization_for_request(request)
        token = ServiceToken.objects.select_for_update().get(id=token_id, organization=org)
        if not request.user.is_staff: return Response({"detail": "organization administrator required"}, status=403)
        action = request.data.get("action", "revoke")
        if action not in {"revoke", "rotate"}: return Response({"detail": "unsupported action"}, status=400)
        try: record, created = _begin_command(request, organization=org, key=key, payload={"token_id": str(token_id), "action": action, "expected_version": expected_version})
        except IdempotencyConflict: return Response({"detail": "IDEMPOTENCY_CONFLICT"}, status=409)
        if not created: return _replay_secret(record) if action == "rotate" else _replay(record)
        current_version = "ACTIVE" if token.is_active and token.revoked_at is None else "REVOKED"
        if expected_version != current_version:
            record.delete(); return Response({"detail": "VERSION_CONFLICT"}, status=409)
        if action == "revoke":
            token.is_active = False; token.revoked_at = timezone.now(); token.save(update_fields=["is_active", "revoked_at"]); body = ServiceTokenMetadataSerializer(token).data
            _command_audit(organization=org, request=request, action="service_token.revoke", correlation_id=correlation_id, metadata={"request_id": request_id, "token_id": str(token.pk)})
            complete_idempotent_request(record, status=200, body=body, resource_type="service_token", resource_id=token.pk)
            return Response(body)
        if action == "rotate":
            replacement, raw = ServiceToken.issue(token.organization, token.name, token.scopes); replacement.owner = request.user; replacement.save(update_fields=["owner"]); token.is_active = False; token.revoked_at = timezone.now(); token.save(update_fields=["is_active", "revoked_at"]); response = ServiceTokenMetadataSerializer(replacement).data
            _command_audit(organization=org, request=request, action="service_token.rotate", correlation_id=correlation_id, metadata={"request_id": request_id, "token_id": str(token.pk), "replacement_id": str(replacement.pk)})
            _complete_secret_result(record, status_code=201, body=response, raw_secret=raw, resource_type="service_token", resource_id=replacement.pk)
            return Response({**response, "token": raw}, status=201)
