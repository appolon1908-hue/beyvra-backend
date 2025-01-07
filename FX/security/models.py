from django.db import models
from users.models import User


class TimeStampedModel(models.Model):
    """ Abstract model to store created and updated timestamps """

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class UserActivity(TimeStampedModel):
    """ Model to store user activities including login details """

    ACTION_STATUS = (
        ('', ''),
        ('SUCCESS', 'SUCCESS'),
        ('FAILED', 'FAILED'),
    )

    ACTION_TYPES = (
        ('', ''),
        ('CREATE', 'CREATE'),
        ('UPDATE', 'UPDATE'),
        ('DELETE', 'DELETE'),
        ('LOGIN', 'LOGIN'),
        ('LOGOUT', 'LOGOUT'),
        ('PASSWORD_RESET', 'PASSWORD_RESET'),
        ('FORGOT_PASSWORD', 'FORGOT_PASSWORD'),
        ('CHANGE_PASSWORD', 'CHANGE_PASSWORD'),
    )

    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="user_activity_logs")
    action_type = models.CharField(
        max_length=50, choices=ACTION_TYPES, default='')
    action_status = models.CharField(
        max_length=50, choices=ACTION_STATUS, default='')
    description = models.TextField(null=True, blank=True)
    ip_address = models.GenericIPAddressField()
    geolocation = models.CharField(
        max_length=255, null=True, blank=True)
    device_type = models.CharField(
        max_length=50, null=True, blank=True)
    device_model = models.CharField(
        max_length=100, null=True, blank=True)
    user_agent = models.TextField(
        null=True, blank=True)

    def __str__(self):
        return f'{self.user.email} - {self.action_type}'

    class Meta:
        verbose_name = "User Activity Log"
        verbose_name_plural = "User Activity Logs"
        ordering = ['-created_at']


class TwoFactorAuth(TimeStampedModel):
    """ Model to store 2FA configuration for users """

    AUTH_TYPES = (
        ('SMS', 'SMS'),
        ('AUTHENTICATOR_APP', 'AUTHENTICATOR APP'),
    )
    admin = models.OneToOneField(
        User, on_delete=models.CASCADE, related_name="two_factor_auth")
    auth_type = models.CharField(
        max_length=100, choices=AUTH_TYPES, default='SMS')
    is_enabled = models.BooleanField(default=True)

    def __str__(self):
        return f'{self.admin.email} - {self.auth_type}'


class PasswordPolicy(TimeStampedModel):
    """ Model to store password policy configuration """

    STRENGTH = (
        ('STRONG', 'STRONG'),
        ('MODERATE', 'MODERATE'),
        ('WEAK', 'WEAK'),
    )
    COMPLEXITY_CHOICES = (
        ('SPECIAL_CHARACTERS', 'Special Characters'),
        ('UPPERCASE_LOWERCASE', 'Uppercase and Lowercase'),
        ('NUMBERS_AND_SPECIAL_CHARACTERS', 'Numbers and Special Characters'),
        ('CUSTOM', 'Custom')
    )
    complexity = models.CharField(
        max_length=50, choices=COMPLEXITY_CHOICES, default='SPECIAL_CHARACTERS'
    )
    custom_characters = models.CharField(
        max_length=255, null=True, blank=True,
        help_text="Enter custom characters like @%^$ if 'Custom' is selected."
    )
    min_length = models.PositiveIntegerField(default=8)
    max_length = models.PositiveIntegerField(default=20)
    strength = models.CharField(
        max_length=50, choices=STRENGTH, default='MODERATE')
    admin = models.OneToOneField(
        User, on_delete=models.CASCADE, related_name="password_policy")

    def __str__(self):
        return f'{self.admin.email}'


class IPWhitelist(TimeStampedModel):
    """Model to store IP addresses to whitelist."""

    admin = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="ip_whitelists")
    ip_address = models.GenericIPAddressField(null=True, blank=True)

    def __str__(self):
        return f'{self.admin.email} - {self.ip_address}'


class CountryWhitelist(TimeStampedModel):
    """Model to store countries to whitelist."""

    admin = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="country_whitelists")
    country = models.CharField(max_length=100)

    def __str__(self):
        return f'{self.admin.email} - {self.country}'


class IPBlacklist(TimeStampedModel):
    """Model to store IP addresses to blacklist."""

    admin = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="ip_blacklists")
    ip_address = models.GenericIPAddressField()

    def __str__(self):
        return f'{self.admin.email} - {self.ip_address}'


class IPRestrictions(TimeStampedModel):
    """Model to store IP restriction configurations."""
    RESTRICTION_TYPES = (
        ('ALLOW_ALL', 'Allow All'),
        ('RESTRICT_BY_COUNTRY', 'Restrict by Country'),
        ('CUSTOM_IP_WHITELIST', 'Custom IP Whitelist'),
    )
    admin = models.OneToOneField(
        User, on_delete=models.CASCADE, related_name="ip_restrictions")
    restriction_type = models.CharField(
        max_length=50, choices=RESTRICTION_TYPES, default='ALLOW_ALL')
    ip_whitelist = models.ManyToManyField(
        IPWhitelist, blank=True, related_name="ip_restrictions")
    country_whitelist = models.ManyToManyField(
        CountryWhitelist, blank=True, related_name="ip_restrictions")
    ip_blacklist = models.ManyToManyField(
        IPBlacklist, blank=True, related_name="ip_restrictions")

    def __str__(self):
        return f'{self.admin.email} - Restriction: {self.restriction_type}'


class UserIPBlacklist(TimeStampedModel):
    """ Model to store blacklisted users IP address by admin """

    admin = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="blacklisted_users")
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    ip_address = models.GenericIPAddressField()


class AdminRoles(models.Model):
    """ Model to store roles assigned to admins """

    admin = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="admin_roles")
    role_name = models.CharField(max_length=50)
    permissions = models.JSONField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f'{self.role_name}'


class SecurityIncident(models.Model):
    """ Model to store security incidents reported by admins """

    INCIDENT_TYPES = (
        ('ACCOUNT_LOCKOUT', 'ACCOUNT LOCKOUT'),
        ('SUSPICIOUS_LOGIN', 'SUSPICIOUS LOGIN'),
    )

    INCIDENT_STATUS = (
        ('PENDING', 'PENDING'),
        ('OPEN', 'OPEN'),
        ('RESOLVED', 'RESOLVED'),
        ('IGNORED', 'IGNORED'),
    )
    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="security_incidents")
    admin = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="reported_incidents")
    incident_type = models.CharField(max_length=20, choices=INCIDENT_TYPES)
    details = models.TextField()
    status = models.CharField(max_length=20, choices=INCIDENT_STATUS)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f'{self.client.email} - {self.incident_type} - {self.status}'


class EncryptionKeys(models.Model):
    """ Model to store encryption keys used for encrypting sensitive data """

    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="encryption_keys")
    key_name = models.CharField(max_length=50)
    key_value = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f'{self.key_name}'
