# security/login_anomaly_detection.py

from django.utils import timezone
from security.models import UserActivity
from .tasks import async_send_user_anomaly_alert_to_admin


class AnomalyDetector:
    """Detect anomalies in user login activities."""

    def __init__(self, user, time_window=5):
        self.user = user
        self.time_window = time_window
        self.time_threshold = timezone.now() - timezone.timedelta(minutes=time_window)

    def detect_multiple_failed_logins(self, max_attempts=5):
        """Detect multiple failed login attempts within a certain time window (minutes)."""

        failed_attempts = UserActivity.objects.filter(
            user=self.user,
            action_type='LOGIN',
            action_status='FAILED',
            created_at__gte=self.time_threshold,
        ).count()
        return failed_attempts >= max_attempts

    def detect_rapid_logins_from_different_locations(self, max_locations=3):
        """Detect logins from different locations in a short time window."""

        distinct_ips = UserActivity.objects.filter(
            user=self.user,
            action_type='LOGIN',
            action_status='SUCCESS',
            created_at__gte=self.time_threshold,
        ).values('ip_address').distinct().count()

        return distinct_ips >= max_locations

    def detect_simultaneous_logins_from_different_devices(self):
        """Detect simultaneous logins from different devices."""

        distinct_devices = UserActivity.objects.filter(
            user=self.user,
            action_type='LOGIN',
            action_status='SUCCESS',
            created_at__gte=self.time_threshold,
        ).values('user_agent').distinct().count()

        return distinct_devices > 3

    def check_for_anomalies(self):
        if self.detect_multiple_failed_logins():
            # Multiple Failed Logins Detection:
            email_msg = f"Multiple failed login attempts detected for user {self.user.email}."
            async_send_user_anomaly_alert_to_admin(self.user.id, email_msg)
            return False

        if self.detect_rapid_logins_from_different_locations():
            # Rapid Logins from Different Locations:
            email_msg = f"Rapid logins from different locations detected for user {self.user.email}."
            async_send_user_anomaly_alert_to_admin(self.user.id, email_msg)
            return False
        if self.detect_simultaneous_logins_from_different_devices():
            # Simultaneous Logins from Different Devices:
            email_msg = f"Simultaneous logins from different devices detected for user {self.user.email}."
            async_send_user_anomaly_alert_to_admin(self.user.id, email_msg)
            return False

        return True
