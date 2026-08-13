import uuid
from django.test import override_settings
from rest_framework.test import APITestCase, APIClient
from users.models import User

class AuthorizationBoundaryTests(APITestCase):
    def setUp(self):
        self.owner=User.objects.create_user(email=f"owner-{uuid.uuid4()}@example.invalid",phone_number=f"+1202{uuid.uuid4().int%10000000:07d}",password="StrongPass!234")
        self.other=User.objects.create_user(email=f"other-{uuid.uuid4()}@example.invalid",phone_number=f"+1312{uuid.uuid4().int%10000000:07d}",password="StrongPass!234")
    def test_user_cannot_read_another_user_record(self):
        self.client.force_authenticate(self.owner)
        self.assertEqual(self.client.get(f"/api/v1/auth/get-user/{self.other.pk}/",secure=True).status_code,404)
    def test_user_can_read_own_record(self):
        self.client.force_authenticate(self.owner)
        self.assertEqual(self.client.get(f"/api/v1/auth/get-user/{self.owner.pk}/",secure=True).status_code,200)
    def test_non_admin_cannot_mutate_trading_controls(self):
        self.client.force_authenticate(self.owner)
        response=self.client.post("/api/v1/admin/trading/halt",{"reason":"unauthorized"},format="json",HTTP_IDEMPOTENCY_KEY="no",HTTP_X_REQUEST_ID="no",secure=True)
        self.assertEqual(response.status_code,403)
    def test_anonymous_cannot_access_admin_surface(self):
        client=APIClient(); self.assertIn(client.get("/admin/",secure=True).status_code,{302,403})

class SafeTradingErrorTests(APITestCase):
    def setUp(self):
        self.user=User.objects.create_user(email=f"safe-{uuid.uuid4()}@example.invalid",phone_number=f"+1415{uuid.uuid4().int%10000000:07d}",password="StrongPass!234")
        self.client.force_authenticate(self.user)
    @override_settings(DEPLOYMENT_ENV="test",SIMULATED_TRADING_ENABLED=True,REAL_TRADING_ENABLED=False,EXTERNAL_EXECUTION_ENABLED=False,REAL_MONEY_ENABLED=False)
    def test_error_never_exposes_request_or_correlation_identifiers(self):
        response=self.client.post("/api/v1/trading/orders",{},format="json",HTTP_X_BEYVRA_SIMULATION_MODE="true",HTTP_X_REQUEST_ID="secret-internal",HTTP_X_CORRELATION_ID="secret-correlation",secure=True)
        text=response.content.decode().lower()
        self.assertNotIn("request_id",text); self.assertNotIn("correlation_id",text); self.assertNotIn("secret-internal",text); self.assertNotIn("secret-correlation",text)
