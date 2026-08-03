from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from notifications.models import NotificationEvent


class NotificationInboxTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            email="inbox@example.com", password="test-pass", phone_number="+12025550133"
        )
        self.other = get_user_model().objects.create_user(
            email="other-inbox@example.com", password="test-pass", phone_number="+12025550134"
        )
        self.event = NotificationEvent.objects.create(
            user=self.user, title="Trade placed", message="Your demo trade is open", category="TRADE"
        )
        NotificationEvent.objects.create(
            user=self.other, title="Private", message="Not visible to first user"
        )
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def test_inbox_is_user_scoped_and_can_mark_read(self):
        response = self.client.get("/api/notification/inbox/", secure=True)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.data.get("results", response.data)
        self.assertEqual(len(results), 1)

        read = self.client.post(
            f"/api/notification/inbox/{self.event.id}/read/", secure=True
        )
        self.assertEqual(read.status_code, status.HTTP_200_OK)
        self.event.refresh_from_db()
        self.assertTrue(self.event.is_read)

    def test_mark_all_read(self):
        NotificationEvent.objects.create(user=self.user, title="Second", message="Another event")
        response = self.client.post("/api/notification/inbox/read-all/", secure=True)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["updated"], 2)
