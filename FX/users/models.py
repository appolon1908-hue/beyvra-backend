from enum import Enum
import uuid

from django.contrib.auth.models import AbstractUser
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from fx_utils.generators import generate_trader_id
from users.managers import UserManager
from users.utils import blur_email, blur_phone_number

from .constants import KYC_FILE_STATUS, KYC_ID_CH, KYC_STATUS_CH
from .utils import ALPHABETS_REGEX_VALIDATOR, PHONE_REGEX_VALIDATOR


class TwoFactorAuthType(Enum):
    NOT_SET = ""
    SMS = "SMS"
    AUTHENTICATOR_APP = "AUTHENTICATOR APP"

    @classmethod
    def choices(cls):
        return [(tag.name, tag.value) for tag in cls]


def validate_file_size(file_obj):
    filesize = file_obj.size
    megabyte_limit = 5.0
    if filesize > megabyte_limit * 1024 * 1024:
        raise ValidationError("Max file size is %s MB" % str(megabyte_limit))


class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class UserRoles(Enum):
    User = "User"
    Admin = "Admin"
    Super_Admin = "Super Admin"

    @classmethod
    def choices(cls):
        return [(tag.name, tag.value) for tag in cls]


class User(AbstractUser, TimeStampedModel):
    GENDER_CHOICES = (
        ("M", "Male"),
        ("F", "Female"),
    )

    PASSWORD_STRENGTH = (
        ("", ""),
        ("STRONG", "STRONG"),
        ("MODERATE", "MODERATE"),
        ("WEAK", "WEAK"),
    )
    PASSWORD_COMPLEXITY_CHOICES = (
        ("", ""),
        ("SPECIAL_CHARACTERS", "Special Characters"),
        ("UPPERCASE_LOWERCASE", "Uppercase and Lowercase"),
        ("NUMBERS_AND_SPECIAL_CHARACTERS", "Numbers and Special Characters"),
        ("CUSTOM", "Custom"),
    )
    VERIFICATION_STATUS = (
        ("", ""),
        ("PENDING", "Pending"),
        ("APPROVED", "Approved"),
        ("REJECTED", "Rejected"),
        ("VERIFIED", "Verified"),
        ("CHANGE_PASSWORD", "Change Password"),  # For bulk created users first login
    )
    preferred_language = models.CharField(
        max_length=10,
        choices=[
            ("en", "English"),
            ("fr", "French"),
            ("es", "Spanish"),
            ("de", "German"),
        ],
        default="en",
        verbose_name="Preferred Language",
    )
    username = None
    email = models.EmailField(_("email address"), unique=True)
    # Human credentials remain in Keycloak. These fields bind the local read model
    # to one immutable OIDC identity without storing passwords or provider tokens.
    identity_issuer = models.URLField(max_length=255, blank=True, default="")
    identity_subject = models.CharField(max_length=255, blank=True, default="")
    first_name = models.CharField(max_length=20, validators=[ALPHABETS_REGEX_VALIDATOR])
    last_name = models.CharField(max_length=20, validators=[ALPHABETS_REGEX_VALIDATOR])
    phone_number = models.CharField(
        max_length=16,
        validators=[PHONE_REGEX_VALIDATOR],
        unique=True,
        blank=True,
        null=True,
    )
    profile_picture = models.ImageField(
        upload_to="user_profile_pictures",
        blank=True,
        null=True,
        validators=[validate_file_size],
    )
    address = models.TextField(blank=True, null=True)
    gender = models.CharField(choices=GENDER_CHOICES, blank=True, null=True)
    dob = models.DateField(blank=True, null=True)
    two_factor_authentication_enabled = models.BooleanField(default=False)
    hidden_account_balances_toggle_enabled = models.BooleanField(default=False)
    one_click_trade_toggle_enabled = models.BooleanField(default=False)
    one_click_trade_closing_toggle_enabled = models.BooleanField(default=False)
    date_joined = models.DateTimeField(default=timezone.now)
    is_staff = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    country_name = models.CharField(max_length=100, blank=True, null=True)
    country_iso_code = models.CharField(max_length=5, blank=True, null=True)
    mfa_secret = models.CharField(max_length=100, blank=True, null=True)
    is_mfa_enabled = models.BooleanField(default=False)
    email_verified = models.BooleanField(default=False)
    email_verified_at = models.DateTimeField(null=True, blank=True)
    # Retained for compatibility with the staging schema's verification flow.
    email_verification_source = models.CharField(max_length=32, blank=True, default="")
    # Short-lived server-issued paper-trading identity. These users never
    # represent a customer or a real-money account.
    is_guest_demo = models.BooleanField(default=False)
    guest_demo_expires_at = models.DateTimeField(null=True, blank=True)
    phone_verified = models.BooleanField(default=False)
    trader_id = models.BigIntegerField(null=True, blank=True, unique=True, default=generate_trader_id, editable=False)
    is_walkthrough = models.BooleanField(default=False)
    is_online = models.BooleanField(default=False)
    role = models.CharField(max_length=11, choices=UserRoles.choices(), default=UserRoles.User.value)
    ip_restricted = models.BooleanField(default=False)
    two_fa_type = models.CharField(
        max_length=100, choices=TwoFactorAuthType.choices(), default=TwoFactorAuthType.NOT_SET.value
    )
    password_complexity = models.CharField(max_length=100, choices=PASSWORD_COMPLEXITY_CHOICES, default="")
    custom_characters = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        help_text="Enter password custom characters like @%^$ if 'Custom' is selected.",
    )
    password_strength = models.CharField(max_length=64, choices=PASSWORD_STRENGTH, default="")
    password_min_length = models.PositiveIntegerField(default=8)
    password_max_length = models.PositiveIntegerField(default=20)
    document_verification = models.CharField(max_length=100, choices=VERIFICATION_STATUS, default="")
    face_verification = models.CharField(max_length=100, choices=VERIFICATION_STATUS, default="")
    verification_status = models.CharField(max_length=100, choices=VERIFICATION_STATUS, default="")
    brand = models.CharField(max_length=120, null=True, blank=True, help_text="Where we got the contact from.")

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    objects = UserManager()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("identity_issuer", "identity_subject"),
                condition=~models.Q(identity_subject=""),
                name="user_identity_issuer_subject_unique",
            )
        ]

    def __str__(self):
        return self.email

    def save(self, *args, **kwargs):
        self.blured_email = blur_email(self.email)
        self.blured_phone_number = blur_phone_number(self.phone_number)

        super(User, self).save(*args, **kwargs)


class PendingRegistration(models.Model):
    STATUS_CHOICES = (("pending_email_verification", "Pending email verification"), ("completed", "Completed"), ("expired", "Expired"))
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email_normalized = models.EmailField()
    display_name = models.CharField(max_length=120, blank=True)
    password_hash = models.CharField(max_length=128)
    status = models.CharField(max_length=32, choices=STATUS_CHOICES, default="pending_email_verification")
    locale = models.CharField(max_length=16, default="en")
    legal_confirmation = models.BooleanField(default=False)
    legal_document_versions = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    verified_at = models.DateTimeField(null=True, blank=True)
    activated_user = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="pending_registrations")
    request_ip = models.GenericIPAddressField(null=True, blank=True)
    request_user_agent = models.TextField(blank=True)


class EmailVerificationChallenge(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    registration = models.ForeignKey(PendingRegistration, null=True, blank=True, on_delete=models.CASCADE, related_name="challenges")
    email_normalized = models.EmailField()
    purpose = models.CharField(max_length=32, default="registration")
    otp_hash = models.CharField(max_length=255)
    status = models.CharField(max_length=16, default="active")
    attempt_count = models.PositiveSmallIntegerField(default=0)
    max_attempts = models.PositiveSmallIntegerField(default=5)
    send_count = models.PositiveSmallIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    consumed_at = models.DateTimeField(null=True, blank=True)
    invalidated_at = models.DateTimeField(null=True, blank=True)
    last_attempt_at = models.DateTimeField(null=True, blank=True)
    last_sent_at = models.DateTimeField(auto_now_add=True)


class TransactionalEmailOutbox(models.Model):
    STATUS_CHOICES = (("pending", "Pending"), ("processing", "Processing"), ("sent", "Sent"), ("failed", "Failed"), ("dead_letter", "Dead letter"))
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    notification_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    event_id = models.CharField(max_length=255, db_index=True)
    correlation_id = models.UUIDField(default=uuid.uuid4, db_index=True, editable=False)
    user_id_ref = models.CharField(max_length=255)
    account_id_ref = models.CharField(max_length=255)
    tenant_id = models.CharField(max_length=255, default="beyvra", db_index=True)
    event_type = models.CharField(max_length=64)
    recipient_email = models.EmailField()
    template_key = models.CharField(max_length=64)
    template_version = models.CharField(max_length=32, default="1")
    locale = models.CharField(max_length=16, default="en")
    payload = models.JSONField(default=dict)
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default="pending")
    attempt_count = models.PositiveSmallIntegerField(default=0)
    next_attempt_at = models.DateTimeField(null=True, blank=True)
    lease_expires_at = models.DateTimeField(null=True, blank=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    provider_message_id = models.CharField(max_length=255, blank=True)
    provider_status = models.CharField(max_length=32, blank=True)
    last_error_code = models.CharField(max_length=64, blank=True)
    idempotency_key = models.CharField(max_length=255, unique=True)

    class Meta:
        indexes = [
            models.Index(fields=["status", "next_attempt_at", "lease_expires_at"], name="email_outbox_claim_idx"),
            models.Index(fields=["tenant_id", "created_at"], name="email_outbox_tenant_idx"),
        ]


class DemoLegalAcceptance(models.Model):
    """Immutable record of the demo agreements accepted at activation."""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="demo_legal_acceptances")
    document_type = models.CharField(max_length=64)
    document_version = models.CharField(max_length=64)
    locale = models.CharField(max_length=16, default="en")
    accepted_at = models.DateTimeField()
    acceptance_source = models.CharField(max_length=64)
    registration_id = models.UUIDField(null=True, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)


class PhoneVerificationCode(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    code = models.CharField(max_length=6)
    failed_checks = models.IntegerField(default=0)


class KYC(TimeStampedModel):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    full_name = models.CharField(max_length=255)
    dob = models.DateField(verbose_name="Date of Birth")
    address = models.CharField(max_length=100)
    id_type = models.CharField(
        max_length=50,
        choices=KYC_ID_CH,
        null=False,
        blank=False,
    )
    id_number = models.CharField(max_length=100, unique=True)
    verified = models.BooleanField(default=False)
    status = models.CharField(max_length=2, null=False, blank=False, choices=KYC_STATUS_CH, default="P")

    def __str__(self):
        return f"KYC for {self.full_name}"


class KYCFile(TimeStampedModel):
    kyc = models.ForeignKey(KYC, related_name="files", on_delete=models.CASCADE)
    file = models.FileField(upload_to="kyc", validators=[validate_file_size], null=False, blank=False)
    desc = models.CharField(max_length=50, null=False, blank=False)
    status = models.CharField(max_length=2, null=False, blank=False, choices=KYC_FILE_STATUS, default="P")

    def __str__(self):
        return f"KYC {self.desc} file for {self.kyc.full_name}"


class UserDeviceInfo(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    ip_address = models.GenericIPAddressField()
    user_agent = models.CharField(max_length=255)
    location = models.CharField(max_length=255)
    device = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Device info for {self.user.id}"
