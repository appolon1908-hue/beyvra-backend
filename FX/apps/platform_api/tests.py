import hashlib
import hmac
import json
import time
from concurrent.futures import ThreadPoolExecutor

from django.db import close_old_connections
from django.core.cache import cache
from django.test import TestCase, TransactionTestCase, override_settings
from rest_framework.test import APIClient

from integrations.models import Organization, OrganizationMembership
from users.models import User

from .models import OperatorAction, PlatformAuditEvent, PlatformOutboxEvent, SupportCase, WebhookDeadLetter, WebhookInboxEvent


def user(email, phone):
    return User.objects.create_user(email=email, phone_number=phone, first_name="Synthetic", last_name="Tester", password="A-valid-test-password-42")


class CanonicalPlatformApiTests(TestCase):
    def setUp(self):
        self.organization = Organization.objects.create(name="Synthetic API Tenant")
        self.user = user("api-user@example.test", "+15555551001")
        OrganizationMembership.objects.create(user=self.user, organization=self.organization, role="member")
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def test_authentication_and_safe_error_contract(self):
        anonymous = APIClient().get("/api/v1/account")
        self.assertEqual(anonymous.status_code, 401)
        self.assertEqual(anonymous.json()["error"]["code"], "AUTHENTICATION_REQUIRED")
        self.assertNotIn("request", json.dumps(anonymous.json()).lower())
        failed = APIClient().post("/api/v1/auth/login", {"email": self.user.email, "password": "wrong"}, format="json")
        self.assertEqual(failed.status_code, 401)
        self.assertEqual(failed.json()["error"]["code"], "AUTHENTICATION_REQUIRED")

    def test_account_rejects_mass_assignment(self):
        response = self.client.patch("/api/v1/account", {"is_staff": True}, format="json")
        self.assertEqual(response.status_code, 400)
        self.user.refresh_from_db()
        self.assertFalse(self.user.is_staff)

    def test_real_value_surface_is_fail_closed(self):
        routes = [
            ("get", "/api/v1/wallets"),
            ("post", "/api/v1/deposits"),
            ("post", "/api/v1/withdrawals"),
            ("post", "/api/v1/withdrawals/preview"),
            ("post", "/api/v1/transfers"),
            ("post", "/api/v1/transfers/preview"),
        ]
        for method, route in routes:
            response = getattr(self.client, method)(route, {}, format="json")
            self.assertEqual(response.status_code, 503, route)
            self.assertEqual(response.json()["error"]["code"], "FEATURE_DISABLED")

    def test_features_never_advertise_real_value(self):
        body = APIClient().get("/api/v1/features").json()["features"]
        for name in ("real_wallet_read", "real_deposits", "real_withdrawals", "real_internal_transfers", "real_trading", "external_execution", "real_money"):
            self.assertIs(body[name], False)
        self.assertIs(body["five_second_market_data"], False)

    @override_settings(GUEST_DEMO_ENABLED=True, PAPER_TRADING_ONLY=True)
    def test_guest_demo_wallet_has_canonical_tenant_context(self):
        cache.delete("guest-demo-session:tenant-linked-guest-fixture")
        guest = APIClient().post(
            "/api/user/guest-demo/",
            {},
            format="json",
            HTTP_IDEMPOTENCY_KEY="tenant-linked-guest-fixture",
        )
        self.assertEqual(guest.status_code, 201)
        authenticated = APIClient()
        authenticated.credentials(HTTP_AUTHORIZATION=f"Bearer {guest.json()['access']}")
        account = authenticated.get("/api/v1/demo/account")
        self.assertEqual(account.status_code, 200)
        self.assertEqual(account.json()["kind"], "DEMO")
        self.assertIs(account.json()["real_money"], False)

    def test_support_idempotency_outbox_and_tenant_isolation(self):
        headers = {"HTTP_IDEMPOTENCY_KEY": "support-fixture-key"}
        payload = {"subject": "Synthetic support request", "message": "Fixture-only customer message"}
        first = self.client.post("/api/v1/support/cases", payload, format="json", **headers)
        second = self.client.post("/api/v1/support/cases", payload, format="json", **headers)
        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 201)
        self.assertEqual(first.json()["id"], second.json()["id"])
        self.assertEqual(SupportCase.objects.count(), 1)
        self.assertEqual(PlatformOutboxEvent.objects.filter(event_type="support.case.created.v1").count(), 1)
        conflict = self.client.post("/api/v1/support/cases", {**payload, "message": "different"}, format="json", **headers)
        self.assertEqual(conflict.status_code, 409)
        other_org = Organization.objects.create(name="Other API Tenant")
        other = user("other-api@example.test", "+15555551002")
        OrganizationMembership.objects.create(user=other, organization=other_org)
        foreign = APIClient(); foreign.force_authenticate(other)
        self.assertEqual(foreign.get(f"/api/v1/support/cases/{first.json()['id']}").status_code, 404)

    def test_report_and_privacy_jobs_are_idempotent_and_audited(self):
        report_headers = {"HTTP_IDEMPOTENCY_KEY": "report-fixture-key"}
        first = self.client.post("/api/v1/reports/exports", {"type": "activity", "filters": {}}, format="json", **report_headers)
        second = self.client.post("/api/v1/reports/exports", {"type": "activity", "filters": {}}, format="json", **report_headers)
        self.assertEqual(first.json()["id"], second.json()["id"])
        privacy_headers = {"HTTP_IDEMPOTENCY_KEY": "privacy-fixture-key"}
        privacy = self.client.post("/api/v1/privacy/deletion-requests", {}, format="json", **privacy_headers)
        self.assertEqual(privacy.status_code, 202)
        self.assertEqual(privacy.json()["status"], "PENDING_REVIEW")
        self.assertEqual(PlatformAuditEvent.objects.filter(event_type="PRIVACY_REQUEST_CREATED").count(), 1)

    def test_notification_and_support_idor_are_not_distinguishable(self):
        unknown = "00000000-0000-0000-0000-000000000001"
        self.assertEqual(self.client.post(f"/api/v1/notifications/{unknown}/read").status_code, 404)
        self.assertEqual(self.client.get(f"/api/v1/support/cases/{unknown}").status_code, 404)

    def test_operator_least_privilege_and_maker_checker(self):
        denied = self.client.post("/api/v1/operator/actions", {"action_type": "ACCOUNT_RESTRICTION", "target_ref": "fixture", "reason": "Synthetic fixture reason"}, format="json")
        self.assertEqual(denied.status_code, 403)
        requester = user("operator@example.test", "+15555551003")
        OrganizationMembership.objects.create(user=requester, organization=self.organization, role="platform_admin")
        operator = APIClient(); operator.force_authenticate(requester)
        created = operator.post("/api/v1/operator/actions", {"action_type": "ACCOUNT_RESTRICTION", "target_ref": "fixture", "reason": "Synthetic fixture reason"}, format="json", HTTP_IDEMPOTENCY_KEY="operator-fixture-key")
        self.assertEqual(created.status_code, 201)
        self.assertEqual(operator.post(f"/api/v1/operator/actions/{created.json()['id']}/approve").status_code, 403)
        checker = user("checker@example.test", "+15555551004")
        OrganizationMembership.objects.create(user=checker, organization=self.organization, role="platform_admin")
        checker_client = APIClient(); checker_client.force_authenticate(checker)
        approved = checker_client.post(f"/api/v1/operator/actions/{created.json()['id']}/approve")
        self.assertEqual(approved.json()["status"], "APPROVED")


@override_settings(
    PLATFORM_WEBHOOK_SECRETS={"fixture": ["old-fixture-secret", "current-fixture-secret"]},
    PLATFORM_WEBHOOK_EVENT_TYPES={"fixture:notification": ["delivery.updated"]},
)
class ProviderWebhookContractTests(TestCase):
    route = "/api/v1/webhooks/fixture/notification"

    def signed(self, body, event_id="fixture-event-1", timestamp=None, secret="current-fixture-secret"):
        timestamp = timestamp or int(time.time())
        signed = f"fixture.notification.{timestamp}.{event_id}.".encode() + body
        signature = hmac.new(secret.encode(), signed, hashlib.sha256).hexdigest()
        return {
            "HTTP_X_BEYVRA_TIMESTAMP": str(timestamp),
            "HTTP_X_BEYVRA_EVENT_ID": event_id,
            "HTTP_X_BEYVRA_SIGNATURE": signature,
        }

    def test_signature_rotation_replay_and_conflict(self):
        body = json.dumps({"type": "delivery.updated"}).encode()
        headers = self.signed(body, secret="old-fixture-secret")
        first = APIClient().post(self.route, body, content_type="application/json", **headers)
        duplicate = APIClient().post(self.route, body, content_type="application/json", **headers)
        self.assertEqual(first.status_code, 202)
        self.assertEqual(duplicate.json()["status"], "duplicate")
        self.assertEqual(WebhookInboxEvent.objects.count(), 1)
        changed = json.dumps({"type": "delivery.updated", "changed": True}).encode()
        conflict = APIClient().post(self.route, changed, content_type="application/json", **self.signed(changed, secret="old-fixture-secret"))
        self.assertEqual(conflict.status_code, 409)

    def test_one_hundred_duplicate_deliveries_have_one_inbox_effect(self):
        body = json.dumps({"type": "delivery.updated"}).encode()
        headers = self.signed(body, event_id="fixture-event-100")
        statuses = [APIClient().post(self.route, body, content_type="application/json", **headers).status_code for _ in range(100)]
        self.assertEqual(statuses[0], 202)
        self.assertTrue(all(code == 200 for code in statuses[1:]))
        self.assertEqual(WebhookInboxEvent.objects.filter(provider_event_id="fixture-event-100").count(), 1)

    def test_bad_missing_stale_and_future_signatures_are_rejected(self):
        body = json.dumps({"type": "delivery.updated"}).encode()
        self.assertEqual(APIClient().post(self.route, body, content_type="application/json").status_code, 401)
        self.assertEqual(APIClient().post(self.route, body, content_type="application/json", **self.signed(body, timestamp=int(time.time()) - 301)).status_code, 401)
        self.assertEqual(APIClient().post(self.route, body, content_type="application/json", **self.signed(body, timestamp=int(time.time()) + 31)).status_code, 401)
        bad = self.signed(body); bad["HTTP_X_BEYVRA_SIGNATURE"] = "bad"
        self.assertEqual(APIClient().post(self.route, body, content_type="application/json", **bad).status_code, 401)
        self.assertEqual(WebhookInboxEvent.objects.count(), 0)

    def test_malformed_oversized_and_unknown_events(self):
        malformed = b"not-json"
        self.assertEqual(APIClient().post(self.route, malformed, content_type="application/json", **self.signed(malformed)).status_code, 400)
        oversized = b"{" + (b" " * 262145) + b"}"
        self.assertEqual(APIClient().post(self.route, oversized, content_type="application/json", **self.signed(oversized, event_id="oversized")).status_code, 413)
        unknown = json.dumps({"type": "unknown.event"}).encode()
        response = APIClient().post(self.route, unknown, content_type="application/json", **self.signed(unknown, event_id="unknown"))
        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.json()["status"], "ignored")
        self.assertEqual(WebhookDeadLetter.objects.count(), 1)

    def test_unconfigured_provider_fails_closed(self):
        body = json.dumps({"type": "delivery.updated"}).encode()
        self.assertEqual(APIClient().post("/api/v1/webhooks/unconfigured/notification", body, content_type="application/json").status_code, 503)


class ApiConcurrencyTests(TransactionTestCase):
    reset_sequences = True

    def setUp(self):
        self.organization = Organization.objects.create(name="Concurrent API Tenant")
        self.user = user("concurrent-api@example.test", "+15555551009")
        OrganizationMembership.objects.create(user=self.user, organization=self.organization)

    def submit(self):
        close_old_connections()
        client = APIClient(); client.force_authenticate(User.objects.get(pk=self.user.pk))
        response = client.post(
            "/api/v1/support/cases",
            {"subject": "Concurrent synthetic request", "message": "Same bounded fixture payload"},
            format="json",
            HTTP_IDEMPOTENCY_KEY="concurrent-support-fixture",
        )
        close_old_connections()
        return response.status_code, response.json()

    def test_concurrent_duplicate_support_submit_has_one_business_effect(self):
        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(lambda _index: self.submit(), range(16)))
        self.assertTrue(all(status == 201 for status, _body in results))
        self.assertEqual(len({body["id"] for _status, body in results}), 1)
        self.assertEqual(SupportCase.objects.count(), 1)
        self.assertEqual(PlatformOutboxEvent.objects.filter(event_type="support.case.created.v1").count(), 1)
