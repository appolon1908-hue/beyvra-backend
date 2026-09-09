"""Regressions for missing-row preconditions and fail-closed transactions."""
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.contrib.auth import get_user_model
from django.db import DatabaseError, close_old_connections
from django.test import TestCase, TransactionTestCase, skipUnlessDBFeature
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from rest_framework.test import APIClient

from apps.foundation.models import ApplicationAuditEvent, IdempotencyRecord
from integrations.models import Organization, OrganizationMembership
from security.commands import durable_security_command
from security.models import IPRestrictions, IPWhitelist, TwoFactorAuth


class SecurityPreconditionTests(TestCase):
    def setUp(self):
        self.organization = Organization.objects.create(name="Precondition tenant")
        self.admin = get_user_model().objects.create_user(
            email="security-preconditions@example.test", password="test-only", is_staff=True,
        )
        OrganizationMembership.objects.create(
            organization=self.organization, user=self.admin, role="owner",
        )
        self.client = APIClient()
        self.client.force_authenticate(self.admin)
        self.headers = {
            "HTTP_X_ORGANIZATION_ID": str(self.organization.pk),
            "HTTP_IDEMPOTENCY_KEY": "precondition-command",
            "HTTP_X_REQUEST_ID": "467dc5f9-0274-43de-ab92-f48d907a9011",
            "HTTP_IF_MATCH": "stale-version",
        }

    def assert_no_command_evidence(self):
        self.assertFalse(IdempotencyRecord.objects.filter(actor_ref=str(self.admin.pk)).exists())
        self.assertFalse(ApplicationAuditEvent.objects.filter(action="security.global_2fa.update").exists())

    def test_missing_global_policy_rejects_stale_version_without_creation(self):
        response = self.client.post(
            "/api/security/set-2fa/", {"auth_type": "AUTHENTICATOR_APP"},
            format="json", **self.headers,
        )
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.data["detail"], "VERSION_CONFLICT")
        self.assertFalse(TwoFactorAuth.objects.filter(admin=self.admin).exists())
        self.assert_no_command_evidence()

    def test_missing_restrictions_reject_stale_version_without_creation(self):
        response = self.client.patch(
            "/api/security/ip-restrictions/", {"restriction_type": "ALLOW_ALL"},
            format="json", **self.headers,
        )
        self.assertEqual(response.status_code, 409)
        self.assertFalse(IPRestrictions.objects.filter(admin=self.admin).exists())
        self.assert_no_command_evidence()

    def test_none_precondition_creates_once_and_replays_original_result(self):
        headers = {**self.headers, "HTTP_IF_MATCH": "NONE"}
        first = self.client.post(
            "/api/security/set-2fa/", {"auth_type": "AUTHENTICATOR_APP"}, format="json", **headers,
        )
        replay = self.client.post(
            "/api/security/set-2fa/", {"auth_type": "AUTHENTICATOR_APP"}, format="json", **headers,
        )
        self.assertEqual(first.status_code, 201)
        self.assertEqual(replay.status_code, 201)
        self.assertEqual(first.data, replay.data)
        self.assertIn("version", first.data)
        self.assertEqual(TwoFactorAuth.objects.filter(admin=self.admin).count(), 1)
        self.assertEqual(ApplicationAuditEvent.objects.filter(action="security.global_2fa.update").count(), 1)

    def test_valid_correlation_does_not_hide_invalid_request_uuid(self):
        response = self.client.post(
            "/api/security/set-2fa/", {"auth_type": "AUTHENTICATOR_APP"}, format="json",
            **{**self.headers, "HTTP_IF_MATCH": "NONE", "HTTP_X_REQUEST_ID": "not-a-uuid",
               "HTTP_X_CORRELATION_ID": "467dc5f9-0274-43de-ab92-f48d907a9011"},
        )
        self.assertEqual(response.status_code, 400)
        self.assertFalse(TwoFactorAuth.objects.filter(admin=self.admin).exists())
        self.assert_no_command_evidence()

    def command_request(self):
        return SimpleNamespace(
            headers={"Idempotency-Key": "wrapper-regression", "If-Match": "NONE",
                     "X-Request-ID": "467dc5f9-0274-43de-ab92-f48d907a9011"},
            user=self.admin, data={}, path="/security-wrapper-regression", method="POST",
        )

    def test_lookup_failures_are_not_treated_as_missing_objects(self):
        for error in (PermissionDenied("denied"), DatabaseError("database unavailable")):
            with self.subTest(error=type(error).__name__):
                handler = Mock(return_value=Response({}, status=200))
                view = SimpleNamespace(get_object=Mock(side_effect=error))
                command = durable_security_command("security.test", versioned=True)(handler)
                with patch("security.commands.organization_for_request", return_value=self.organization):
                    with self.assertRaises(type(error)):
                        command(view, self.command_request())
                handler.assert_not_called()
                self.assert_no_command_evidence()

    def test_rejected_handler_rolls_back_business_writes_and_idempotency(self):
        def rejected_handler(view, request):
            IPWhitelist.objects.create(admin=self.admin, ip_address="198.51.100.50")
            return Response({"detail": "invalid command"}, status=400)
        command = durable_security_command("security.test.rejected")(rejected_handler)
        with patch("security.commands.organization_for_request", return_value=self.organization):
            response = command(SimpleNamespace(), self.command_request())
        self.assertEqual(response.status_code, 400)
        self.assertFalse(IPWhitelist.objects.filter(admin=self.admin).exists())
        self.assert_no_command_evidence()


@skipUnlessDBFeature("has_select_for_update")
class SecuritySingletonConcurrencyTests(TransactionTestCase):
    def test_only_one_first_writer_can_satisfy_none_precondition(self):
        organization = Organization.objects.create(name="Concurrent security tenant")
        admin = get_user_model().objects.create_user(
            email="security-concurrent@example.test", password="test-only", is_staff=True,
        )
        OrganizationMembership.objects.create(organization=organization, user=admin, role="owner")
        barrier = Barrier(2)

        def submit(index):
            close_old_connections()
            try:
                user = get_user_model().objects.get(pk=admin.pk)
                client = APIClient()
                client.force_authenticate(user)
                barrier.wait(timeout=10)
                return client.post(
                    "/api/security/set-2fa/", {"auth_type": "AUTHENTICATOR_APP"}, format="json",
                    HTTP_X_ORGANIZATION_ID=str(organization.pk),
                    HTTP_IDEMPOTENCY_KEY=f"concurrent-security-{index}",
                    HTTP_X_REQUEST_ID="467dc5f9-0274-43de-ab92-f48d907a9011",
                    HTTP_IF_MATCH="NONE",
                ).status_code
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(submit, index) for index in range(2)]
            statuses = [future.result(timeout=30) for future in futures]
        self.assertEqual(sorted(statuses), [201, 409])
        self.assertEqual(TwoFactorAuth.objects.filter(admin=admin).count(), 1)
        self.assertEqual(ApplicationAuditEvent.objects.filter(action="security.global_2fa.update").count(), 1)
        self.assertEqual(IdempotencyRecord.objects.filter(actor_ref=str(admin.pk)).count(), 1)
