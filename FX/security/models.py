from enum import Enum

from django.db import models
from users.models import User


class UserActivityActionStatus(Enum):
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"

    @classmethod
    def choices(cls):
        return [(tag.name, tag.value) for tag in cls]


class UserActivityActionTypes(Enum):
    CREATE = "CREATE"
    UPDATE = "UPDATE"
    DELETE = "DELETE"
    LOGIN = "LOGIN"
    LOGOUT = "LOGOUT"
    PASSWORD_RESET = "PASSWORD_RESET"
    FORGOT_PASSWORD = "FORGOT_PASSWORD"
    CHANGE_PASSWORD = "CHANGE_PASSWORD"
    WHITELISTED_IP = "WHITELISTED_IP"
    WHITELISTED_COUNTRY = "WHITELISTED_COUNTRY"
    WHITELISTED_USER = "WHITELISTED_USER"
    BLACKLISTED_IP = "BLACKLISTED_IP"
    INVALID_IP = "INVALID_IP"
    BLACKLISTED_COUNTRY = "BLACKLISTED_COUNTRY"
    BLACKLISTED_USER = "BLACKLISTED_USER"
    USER_ANOMALY_ALERT = "USER_ANOMALY_ALERT"
    ADMIN_GLOBAL_SET_2FA = "ADMIN_GLOBAL_SET_2FA"
    OTHER_ADMIN_ACTION = "OTHER_ADMIN_ACTION"

    @classmethod
    def choices(cls):
        return [(tag.name, tag.value) for tag in cls]


class TimeStampedModel(models.Model):
    """Abstract model to store created and updated timestamps"""

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class UserActivity(TimeStampedModel):
    """Model to store user activities including login details"""

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="user_activity_logs",
        null=True,
        blank=True,
    )
    anonymous_user = models.CharField(max_length=50, null=True, blank=True)
    action_type = models.CharField(max_length=100, choices=UserActivityActionTypes.choices(), default="")
    action_status = models.CharField(max_length=50, choices=UserActivityActionStatus.choices(), default="")
    description = models.TextField(null=True, blank=True)
    ip_address = models.GenericIPAddressField()
    geolocation = models.CharField(max_length=255, null=True, blank=True)
    device_type = models.CharField(max_length=50, null=True, blank=True)
    device_model = models.CharField(max_length=100, null=True, blank=True)
    user_agent = models.TextField(null=True, blank=True)

    @property
    def custom_action_type(self):
        if UserActivityActionTypes.OTHER_ADMIN_ACTION.value in self.action_type:
            return self.action_type
        return self.action_type

    def save(self, *args, **kwargs):
        if not isinstance(self.user, User):
            self.user = self.user
        if self.action_type.startswith(UserActivityActionTypes.OTHER_ADMIN_ACTION.value):
            self.action_type = self.action_type
        super(UserActivity, self).save(*args, **kwargs)

    def __str__(self):
        return f"{self.user.email if self.user else self.anonymous_user} - {self.action_type}"

    class Meta:
        verbose_name = "User Activity Log"
        verbose_name_plural = "User Activity Logs"
        ordering = ["-created_at"]


class TwoFactorAuth(TimeStampedModel):
    """Model to store 2FA configuration for users"""

    AUTH_TYPES = (
        ("SMS", "SMS"),
        ("AUTHENTICATOR_APP", "AUTHENTICATOR APP"),
    )
    admin = models.OneToOneField(User, on_delete=models.CASCADE, related_name="two_factor_auth")
    auth_type = models.CharField(max_length=100, choices=AUTH_TYPES, default="SMS")
    is_enabled = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.admin.email} - {self.auth_type}"


class PasswordPolicy(TimeStampedModel):
    """Model to store password policy configuration"""

    STRENGTH = (
        ("STRONG", "STRONG"),
        ("MODERATE", "MODERATE"),
        ("WEAK", "WEAK"),
    )
    COMPLEXITY_CHOICES = (
        ("SPECIAL_CHARACTERS", "Special Characters"),
        ("UPPERCASE_LOWERCASE", "Uppercase and Lowercase"),
        ("NUMBERS_AND_SPECIAL_CHARACTERS", "Numbers and Special Characters"),
        ("CUSTOM", "Custom"),
    )
    complexity = models.CharField(max_length=50, choices=COMPLEXITY_CHOICES, default="SPECIAL_CHARACTERS")
    custom_characters = models.CharField(
        max_length=255, null=True, blank=True, help_text="Enter custom characters like @%^$ if 'Custom' is selected."
    )
    min_length = models.PositiveIntegerField(default=8)
    max_length = models.PositiveIntegerField(default=20)
    strength = models.CharField(max_length=50, choices=STRENGTH, default="MODERATE")
    admin = models.OneToOneField(User, on_delete=models.CASCADE, related_name="password_policy")

    def __str__(self):
        return f"{self.admin.email}"


class IPWhitelist(TimeStampedModel):
    """Model to store IP addresses to whitelist."""

    admin = models.ForeignKey(User, on_delete=models.CASCADE, related_name="ip_whitelists")
    ip_address = models.GenericIPAddressField(null=True, blank=True)

    def __str__(self):
        return f"{self.admin.email} - {self.ip_address}"


class CountryWhitelist(TimeStampedModel):
    """Model to store countries to whitelist."""

    admin = models.ForeignKey(User, on_delete=models.CASCADE, related_name="country_whitelists")
    country = models.CharField(max_length=100)

    def __str__(self):
        return f"{self.admin.email} - {self.country}"


class CountryBlacklist(TimeStampedModel):
    """Model to store countries to blacklist."""

    admin = models.ForeignKey(User, on_delete=models.CASCADE, related_name="country_blacklists")
    country = models.CharField(max_length=100)

    def __str__(self):
        return f"{self.admin.email} - {self.country}"


class IPBlacklist(TimeStampedModel):
    """Model to store IP addresses to blacklist."""

    admin = models.ForeignKey(User, on_delete=models.CASCADE, related_name="ip_blacklists")
    ip_address = models.GenericIPAddressField()

    def __str__(self):
        return f"{self.admin.email} - {self.ip_address}"


class UserIPBlacklist(TimeStampedModel):
    """Model to store blacklisted users IP address by admin"""

    admin = models.ForeignKey(User, on_delete=models.CASCADE, related_name="blacklisted_users")
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    ip_address = models.GenericIPAddressField()

    def __str__(self):
        return f"{self.admin.email} - {self.user}"


class IPRestrictions(TimeStampedModel):
    """Model to store IP restriction configurations."""

    RESTRICTION_TYPES = (
        ("ALLOW_ALL", "Allow All"),
        ("RESTRICT_BY_COUNTRY", "Restrict by Country"),
        ("CUSTOM_IP_WHITELIST", "Custom IP Whitelist"),
    )
    admin = models.OneToOneField(User, on_delete=models.CASCADE, related_name="ip_restrictions")
    restriction_type = models.CharField(max_length=50, choices=RESTRICTION_TYPES, default="ALLOW_ALL")
    ip_whitelist = models.ManyToManyField(IPWhitelist, blank=True, related_name="ip_restrictions")
    country_whitelist = models.ManyToManyField(CountryWhitelist, blank=True, related_name="ip_restrictions")
    country_blacklist = models.ManyToManyField(CountryBlacklist, blank=True, related_name="ip_restrictions")
    ip_blacklist = models.ManyToManyField(IPBlacklist, blank=True, related_name="ip_restrictions")
    user_ip_blacklist = models.ManyToManyField(UserIPBlacklist, blank=True, related_name="ip_restrictions")

    def __str__(self):
        return f"{self.admin.email} - Restriction: {self.restriction_type}"


class AdminRoles(models.Model):
    """Model to store roles assigned to admins"""

    admin = models.ForeignKey(User, on_delete=models.CASCADE, related_name="admin_roles")
    role_name = models.CharField(max_length=50)
    permissions = models.JSONField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.role_name}"


class SecurityIncident(models.Model):
    """Model to store security incidents reported by admins"""

    INCIDENT_TYPES = (
        ("ACCOUNT_LOCKOUT", "ACCOUNT LOCKOUT"),
        ("SUSPICIOUS_LOGIN", "SUSPICIOUS LOGIN"),
    )

    INCIDENT_STATUS = (
        ("PENDING", "PENDING"),
        ("OPEN", "OPEN"),
        ("RESOLVED", "RESOLVED"),
        ("IGNORED", "IGNORED"),
    )
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="security_incidents")
    admin = models.ForeignKey(User, on_delete=models.CASCADE, related_name="reported_incidents")
    incident_type = models.CharField(max_length=20, choices=INCIDENT_TYPES)
    details = models.TextField()
    status = models.CharField(max_length=20, choices=INCIDENT_STATUS)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.client.email} - {self.incident_type} - {self.status}"


class EncryptionKeys(models.Model):
    """Model to store encryption keys used for encrypting sensitive data"""

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="encryption_keys")
    key_name = models.CharField(max_length=50)
    key_value = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.key_name}"


class AnomalyCheckSchedule(models.Model):
    last_checked_time = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Anomaly Check Status"
        verbose_name_plural = "Anomaly Check Statuses"

    @classmethod
    def get_last_checked_time(cls):
        obj, created = cls.objects.get_or_create(id=1)
        return obj.last_checked_time

    @classmethod
    def update_last_checked_time(cls, timestamp):
        obj, created = cls.objects.get_or_create(id=1)
        obj.last_checked_time = timestamp
        obj.save()
