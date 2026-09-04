from unittest.mock import patch

from django.test import SimpleTestCase

from apps.foundation.publisher import publish_batch


class PublisherHeartbeatTests(SimpleTestCase):
    @patch("apps.foundation.publisher.worker_success")
    @patch("apps.foundation.publisher.OUTBOX_LAST_SUCCESS")
    @patch("apps.foundation.publisher.OutboxEvent.objects.filter")
    @patch("apps.foundation.publisher.claim_outbox_batch", return_value=[])
    def test_empty_poll_refreshes_worker_heartbeat(
        self,
        claim_outbox_batch,
        outbox_filter,
        last_success,
        worker_success,
    ):
        outbox_filter.return_value.exists.return_value = False
        with patch("apps.foundation.publisher.time.time", return_value=1234.5):
            self.assertEqual(publish_batch(), 0)

        claim_outbox_batch.assert_called_once_with(limit=100)
        last_success.set.assert_called_once_with(1234.5)
        worker_success.assert_called_once_with("outbox_publisher")

    @patch("apps.foundation.publisher.worker_success")
    @patch("apps.foundation.publisher.OUTBOX_LAST_SUCCESS")
    @patch("apps.foundation.publisher.OutboxEvent.objects.filter")
    @patch("apps.foundation.publisher.claim_outbox_batch", return_value=[])
    def test_dead_letter_prevents_healthy_idle_heartbeat(
        self,
        _claim_outbox_batch,
        outbox_filter,
        last_success,
        worker_success,
    ):
        outbox_filter.return_value.exists.return_value = True

        self.assertEqual(publish_batch(), 0)

        last_success.set.assert_not_called()
        worker_success.assert_not_called()
