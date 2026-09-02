from unittest.mock import patch

from django.test import SimpleTestCase

from apps.foundation.publisher import publish_batch


class PublisherHeartbeatTests(SimpleTestCase):
    @patch("apps.foundation.publisher.worker_success")
    @patch("apps.foundation.publisher.OUTBOX_LAST_SUCCESS")
    @patch("apps.foundation.publisher.claim_outbox_batch", return_value=[])
    def test_empty_poll_refreshes_worker_heartbeat(
        self, claim_outbox_batch, last_success, worker_success
    ):
        with patch("apps.foundation.publisher.time.time", return_value=1234.5):
            self.assertEqual(publish_batch(), 0)

        claim_outbox_batch.assert_called_once_with(limit=100)
        last_success.set.assert_called_once_with(1234.5)
        worker_success.assert_called_once_with("outbox_publisher")
