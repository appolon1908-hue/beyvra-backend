"""Staging-only V2 realtime token and channel-registry contracts.

The middleware remains authoritative: clients receive short-lived tokens only
for channels derived from their authenticated session.  Centrifugo/NATS never
decide tenant or account permissions.
"""

import hashlib
import os
import re
import time
import uuid

import jwt
from django.core.cache import cache
from django.http import JsonResponse
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated

from integrations.models import OrganizationMembership


CHANNEL_REGISTRY = {
    "market.{symbol}.quote": {"visibility": "public", "required_permission": "market.read", "tenant_scope": True, "workspace_scope": False, "account_scope": False, "schema_version": 1, "history_size": 100, "history_ttl": 30, "resume_supported": True, "snapshot_provider": "/api/v1/market-data/snapshot", "rate_limit": 20},
    "market.{symbol}.candle.{timeframe}": {"visibility": "public", "required_permission": "market.read", "tenant_scope": True, "workspace_scope": False, "account_scope": False, "schema_version": 1, "history_size": 500, "history_ttl": 300, "resume_supported": True, "snapshot_provider": "/api/v1/market-data/snapshot", "rate_limit": 20},
    "news.{symbol}": {"visibility": "public", "required_permission": "news.read", "tenant_scope": True, "workspace_scope": False, "account_scope": False, "schema_version": 1, "history_size": 100, "history_ttl": 300, "resume_supported": True, "snapshot_provider": "/api/v1/news", "rate_limit": 10},
    "news.market": {"visibility": "public", "required_permission": "news.read", "tenant_scope": True, "workspace_scope": False, "account_scope": False, "schema_version": 1, "history_size": 100, "history_ttl": 300, "resume_supported": True, "snapshot_provider": "/api/v1/news", "rate_limit": 10},
    "news.economic": {"visibility": "public", "required_permission": "news.read", "tenant_scope": True, "workspace_scope": False, "account_scope": False, "schema_version": 1, "history_size": 100, "history_ttl": 300, "resume_supported": True, "snapshot_provider": "/api/v1/economic-calendar", "rate_limit": 10},
    "simulation.order.{account_id}": {"visibility": "private", "required_permission": "demo.trade.read", "tenant_scope": True, "workspace_scope": True, "account_scope": True, "schema_version": 1, "history_size": 100, "history_ttl": 300, "resume_supported": True, "snapshot_provider": "/api/v1/trading/orders", "rate_limit": 10},
    "simulation.execution.{account_id}": {"visibility": "private", "required_permission": "demo.trade.read", "tenant_scope": True, "workspace_scope": True, "account_scope": True, "schema_version": 1, "history_size": 100, "history_ttl": 300, "resume_supported": True, "snapshot_provider": "/api/v1/trading/trades", "rate_limit": 10},
    "simulation.position.{account_id}": {"visibility": "private", "required_permission": "demo.trade.read", "tenant_scope": True, "workspace_scope": True, "account_scope": True, "schema_version": 1, "history_size": 100, "history_ttl": 300, "resume_supported": True, "snapshot_provider": "/api/v1/trading/positions", "rate_limit": 10},
    "simulation.execution-quality.{account_id}": {"visibility": "private", "required_permission": "demo.trade.read", "tenant_scope": True, "workspace_scope": True, "account_scope": True, "schema_version": 1, "history_size": 100, "history_ttl": 300, "resume_supported": True, "snapshot_provider": "/api/v1/execution/reports", "rate_limit": 10},
    "notification.{user_id}": {"visibility": "private", "required_permission": "notification.read", "tenant_scope": True, "workspace_scope": False, "account_scope": False, "schema_version": 1, "history_size": 100, "history_ttl": 300, "resume_supported": True, "snapshot_provider": "/api/notification/inbox/", "rate_limit": 10},
    "account.security.{user_id}": {"visibility": "private", "required_permission": "account.security.read", "tenant_scope": True, "workspace_scope": False, "account_scope": False, "schema_version": 1, "history_size": 100, "history_ttl": 300, "resume_supported": True, "snapshot_provider": "/api/v1/session", "rate_limit": 5},
    "treasury.{tenant_id}": {"visibility": "private", "required_permission": "treasury.read", "tenant_scope": True, "workspace_scope": False, "account_scope": False, "schema_version": 1, "history_size": 100, "history_ttl": 300, "resume_supported": True, "snapshot_provider": "/api/v1/treasury/liquidity", "rate_limit": 10},
    "institutional.subaccount.updated.v1.{user_id}": {"visibility": "private", "required_permission": "institutional.read", "tenant_scope": True, "workspace_scope": False, "account_scope": False, "schema_version": 1, "history_size": 100, "history_ttl": 300, "resume_supported": True, "snapshot_provider": "/api/v1/institutional/account/hierarchy", "rate_limit": 10},
    "system.status": {"visibility": "public", "required_permission": "system.read", "tenant_scope": False, "workspace_scope": False, "account_scope": False, "schema_version": 1, "history_size": 50, "history_ttl": 60, "resume_supported": False, "snapshot_provider": "/api/v1/realtime/v2/health", "rate_limit": 10},
}

def _compile_pattern(pattern):
    escaped = re.escape(pattern)
    for name, expression in {
        "symbol": r"[A-Za-z0-9_.-]+",
        "timeframe": r"[A-Za-z0-9_-]+",
        "account_id": r"[A-Za-z0-9:_-]+",
        "user_id": r"[A-Za-z0-9:_-]+",
        "tenant_id": r"[A-Fa-f0-9-]+",
    }.items():
        escaped = escaped.replace(re.escape("{" + name + "}"), expression)
    return re.compile("^" + escaped + "$")


_PATTERN_RE = {pattern: _compile_pattern(pattern) for pattern in CHANNEL_REGISTRY}


def _secret():
    return os.getenv("CENTRIFUGO_TOKEN_HMAC_SECRET", "")


def _enabled():
    return all(os.getenv(name, "false").lower() == "true" for name in (
        "REALTIME_V2_ENABLED", "REALTIME_V2_STAGING_ENABLED", "CENTRIFUGO_ENABLED", "NATS_JETSTREAM_ENABLED"
    ))


def _channel_entry(channel):
    if channel in CHANNEL_REGISTRY:
        return channel, CHANNEL_REGISTRY[channel]
    for pattern, entry in CHANNEL_REGISTRY.items():
        if _PATTERN_RE[pattern].match(channel):
            return pattern, entry
    return None, None


def _tenant(user):
    membership = OrganizationMembership.objects.filter(user_id=user.id).order_by("id").values_list("organization_id", flat=True).first()
    return str(membership) if membership else "default"


def _owns_demo_account(user_id, channel):
    if channel.startswith(("simulation.order.", "simulation.execution.", "simulation.position.", "simulation.execution-quality.")):
        return channel.rsplit(".", 1)[-1] == f"sim-{user_id}"
    return False


def _claims(request, audience, extra=None):
    secret = _secret()
    if not secret:
        return None
    now = int(time.time())
    tenant_id = _tenant(request.user)
    claims = {
        "sub": str(request.user.id),
        "user_id": str(request.user.id),
        "tenant_id": tenant_id,
        "workspace_id": "default",
        "account_scope": [f"demo:{request.user.id}"],
        "allowed_channel_patterns": list(CHANNEL_REGISTRY),
        "iat": now,
        "exp": now + 60,
        "nonce": uuid.uuid4().hex,
        "session_id": hashlib.sha256(f"{request.user.id}:{now}".encode()).hexdigest()[:32],
        "aud": audience,
        "token_version": int(cache.get(f"realtime:v2:token-version:{request.user.id}", 1)),
    }
    if extra:
        claims.update(extra)
    return jwt.encode(claims, secret, algorithm="HS256")


from .realtime_views import RealtimeTicketView, RealtimeSnapshotView, RealtimeResumeView

realtime_ticket_v1 = RealtimeTicketView.as_view()
realtime_snapshot_v1 = RealtimeSnapshotView.as_view()
realtime_resume_v1 = RealtimeResumeView.as_view()


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def connection_token(request):
    if not _enabled():
        return JsonResponse({"code": "REALTIME_V2_DISABLED"}, status=404)
    token = _claims(request, audience="centrifugo")
    if token is None:
        return JsonResponse({"code": "REALTIME_V2_NOT_CONFIGURED"}, status=503)
    return JsonResponse({"token": token, "expires_in": 60, "gateway": "/ws/v2/"})


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def subscription_token(request):
    if not _enabled():
        return JsonResponse({"code": "REALTIME_V2_DISABLED"}, status=404)
    channel = request.data.get("channel")
    if not isinstance(channel, str) or not channel or len(channel) > 200:
        return JsonResponse({"code": "INVALID_CHANNEL"}, status=400)
    pattern, entry = _channel_entry(channel)
    if not entry:
        return JsonResponse({"code": "UNSUPPORTED_CHANNEL"}, status=403)
    user_id = str(request.user.id)
    if entry["visibility"] == "private":
        if pattern and pattern.startswith("simulation.") and not _owns_demo_account(request.user.id, channel):
            return JsonResponse({"code": "FORBIDDEN_CHANNEL"}, status=403)
        if pattern in {"notification.{user_id}", "account.security.{user_id}"} and not channel.endswith(user_id):
            return JsonResponse({"code": "FORBIDDEN_CHANNEL"}, status=403)
        if pattern == "treasury.{tenant_id}" and channel != f"treasury.{_tenant(request.user)}":
            return JsonResponse({"code": "FORBIDDEN_CHANNEL"}, status=403)
        if entry["account_scope"] and not (user_id in channel or _owns_demo_account(request.user.id, channel)):
            return JsonResponse({"code": "FORBIDDEN_CHANNEL"}, status=403)
    if entry["required_permission"].startswith("demo.") and not request.user.is_active:
        return JsonResponse({"code": "FORBIDDEN_CHANNEL"}, status=403)
    token = _claims(request, audience="centrifugo-subscription", extra={"channel": channel, "channel_pattern": pattern})
    if token is None:
        return JsonResponse({"code": "REALTIME_V2_NOT_CONFIGURED"}, status=503)
    return JsonResponse({"token": token, "channel": channel, "expires_in": 60})


@api_view(["POST"])
@permission_classes([AllowAny])
def authorize_subscription(request):
    """Centrifugo subscribe-proxy contract; reachable only on the private network."""
    supplied_secret = request.headers.get("X-Beyvra-Proxy-Secret") or request.headers.get("X-Codestra-Proxy-Secret")
    if supplied_secret != os.getenv("CENTRIFUGO_PROXY_SECRET", ""):
        return JsonResponse({"error": {"code": 403, "message": "forbidden"}})
    channel = request.data.get("channel")
    user_id = str(request.data.get("user", ""))
    pattern, entry = _channel_entry(channel) if isinstance(channel, str) else (None, None)
    if not entry:
        return JsonResponse({"error": {"code": 403, "message": "forbidden"}})
    if entry["visibility"] == "private" and pattern and pattern.startswith("simulation.") and not _owns_demo_account(user_id, channel):
        return JsonResponse({"error": {"code": 403, "message": "forbidden"}})
    if entry["visibility"] == "private" and pattern == "treasury.{tenant_id}" and channel != f"treasury.{_tenant(type('UserRef', (), {'id': user_id})())}":
        return JsonResponse({"error": {"code": 403, "message": "forbidden"}})
    user_scoped = pattern in {
        "notification.{user_id}",
        "account.security.{user_id}",
        "institutional.subaccount.updated.v1.{user_id}",
    } and channel.rsplit(".", 1)[-1] == user_id
    if entry["visibility"] == "private" and pattern != "treasury.{tenant_id}" and not (user_scoped or (entry["account_scope"] and _owns_demo_account(user_id, channel))):
        return JsonResponse({"error": {"code": 403, "message": "forbidden"}})
    return JsonResponse({"result": {}})


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def revoke(request):
    key = f"realtime:v2:token-version:{request.user.id}"
    cache.add(key, 1, timeout=None)
    cache.incr(key)
    return JsonResponse({"revoked": True})


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def channel_registry(request):
    if not _enabled():
        return JsonResponse({"code": "REALTIME_V2_DISABLED"}, status=404)
    return JsonResponse({"version": 1, "channels": CHANNEL_REGISTRY})


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def health(request):
    return JsonResponse({"status": "ok", "gateway": "/ws/v2/", "centrifugo": bool(os.getenv("CENTRIFUGO_ENABLED", "false").lower() == "true"), "nats_jetstream": bool(os.getenv("NATS_JETSTREAM_ENABLED", "false").lower() == "true")})
