from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import check_password
from django.core.validators import MinLengthValidator
from django.utils import timezone
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from users import messages
from users.models import UserDeviceInfo
from users.tasks import async_send_device_verification_email, async_send_email_verification_email
from users.utils import ALPHABETS_REGEX_VALIDATOR, PHONE_REGEX_VALIDATOR, get_user_location, mask_email, mask_phone
from wallet.constants import DEMO_BALANCE, DEMO_WALLET_NAME
from wallet.models import Currency, Wallet
from .models import KYC, KYCFile
from security.login_anomaly_detection import AnomalyDetector

USER_READ_ONLY = (
    "is_active",
    "is_staff",
    "is_superuser",
    "date_joined",
    "last_login",
    "email_verified",
    "is_walkthrough",
    "is_mfa_enabled",
    "country_name",
    "country_iso_code",
    "phone_verified",
    "phone_verified",
    "trader_id",
    "is_online",
)


class BaseUserSerializer(serializers.ModelSerializer):
    phone_number = serializers.CharField(validators=[PHONE_REGEX_VALIDATOR])
    first_name = serializers.CharField(validators=[ALPHABETS_REGEX_VALIDATOR])
    last_name = serializers.CharField(validators=[ALPHABETS_REGEX_VALIDATOR])

    class Meta:
        model = get_user_model()

    def to_representation(self, instance):
        representation = super().to_representation(instance)
        # mask email and phone_number while serializing instance
        # representation["email"] = mask_email(instance.email)
        # representation["phone_number"] = mask_phone(instance.phone_number)

        return representation


class UserSerializer(BaseUserSerializer):
    """Serializer for the user object."""

    class Meta:
        model = get_user_model()
        exclude = ("groups", "user_permissions", "mfa_secret", "password_complexity",
                    "custom_characters", "ip_restricted", "two_fa_type", "password_strength",
                    "password_min_length", "password_max_length")
        extra_kwargs = {"password": {"write_only": True, "min_length": 5, "max_length": 20}}
        read_only_fields = USER_READ_ONLY

    def create(self, validated_data):
        user = get_user_model().objects.create_user(**validated_data)
        
        # Set the is_walkthrough to True on new user register
        user.is_walkthrough = True
        user.save()

        # send verification email on register
        # async_send_email_verification_email.delay(user.id)
        # create a demo account with DEMO_BALANCE as initial balance
        demo_currency = Currency.objects.get(name="Đ")
        Wallet.objects.create(
            name=DEMO_WALLET_NAME,
            currency=demo_currency,
            user=user,
            balance=DEMO_BALANCE,
            is_real=False,
        )
        return user


class UserUpdateSerializer(BaseUserSerializer):
    first_name = serializers.CharField(validators=[ALPHABETS_REGEX_VALIDATOR])
    last_name = serializers.CharField(validators=[ALPHABETS_REGEX_VALIDATOR])

    class Meta:
        model = get_user_model()
        exclude = ("groups", "user_permissions", "password")
        read_only_fields = USER_READ_ONLY

    def update(self, instance, validated_data):
        instance = super().update(instance, validated_data)
        # if phone was updated set verfied_phone to False
        phone_number = validated_data.get("phone_number", None)
        if phone_number is not None:
            instance.phone_verified = False
            instance.save()
        return instance


class WalkthroughSerializer(serializers.ModelSerializer):
    class Meta:
        model = get_user_model()
        fields = ["is_walkthrough"]


class AuthSerializer(serializers.Serializer):
    otp = serializers.CharField()


class VerifyPhoneCodeSerializer(serializers.Serializer):
    code = serializers.CharField(max_length=6)


class PasswordResetRequestSerializer(serializers.Serializer):
    email = serializers.EmailField()


class PasswordResetConfirmSerializer(serializers.Serializer):
    new_password = serializers.CharField(max_length=20, validators=[MinLengthValidator(5)])
    new_password_confirm = serializers.CharField(max_length=20, validators=[MinLengthValidator(5)])

    def validate(self, data):
        if data["new_password"] != data["new_password_confirm"]:
            raise serializers.ValidationError("Passwords must match.")

        return data


class PasswordChangeSerializer(serializers.Serializer):
    old_password = serializers.CharField(max_length=20)
    new_password = serializers.CharField(max_length=20, validators=[MinLengthValidator(5)])
    new_password_confirm = serializers.CharField(max_length=20, validators=[MinLengthValidator(5)])

    def validate(self, data):
        if data["new_password"] != data["new_password_confirm"]:
            raise serializers.ValidationError("Passwords must match.")

        if data["old_password"] == data["new_password"]:
            raise serializers.ValidationError("Old password and new password should be different.")

        return data


class AuthTokenObtainPairSerializer(TokenObtainPairSerializer):
    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        return token


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(max_length=100)

    def validate(self, data):
        email = data.get("email")
        password = data.get("password")
        if email and password:
            user = get_user_model().objects.filter(email=email).first()
            if user is not None:
                # check for user anomalies
                detector = AnomalyDetector(user)
                if not detector.check_for_anomalies():
                    raise serializers.ValidationError(
                        messages.ANOMALY_DETECTED,
                        code="anomaly_detected",
                    )
                if not check_password(password, user.password):
                    raise serializers.ValidationError(
                        "Invalid credentials.",
                        code="authorization",
                    )
                if not user.is_active:
                    raise serializers.ValidationError(messages.USER_BANNED_CONTACT_SUPPORT)
            else:
                raise serializers.ValidationError("User doesn't exist.", code="authorization")
        else:
            raise serializers.ValidationError(
                'Must include "email" and "password".',
                code="authorization",
            )
        data["user"] = user
        return data

    def save(self, request):
        user = self.validated_data["user"]

        # device info
        user_agent = request.META.get("HTTP_USER_AGENT")[0:255]
        ip_address = request.META.get("REMOTE_ADDR")
        location = get_user_location(ip_address)
        device = f"{user_agent.split('/')[0]} {user_agent.split('/')[1].split(' ')[0]}"

        self._handle_user_device_info(user, ip_address, user_agent, location, device)

    def _handle_user_device_info(self, user, ip_address, user_agent, location, device):
        device_info, created = UserDeviceInfo.objects.get_or_create(
            user=user,
            defaults={"ip_address": ip_address, "user_agent": user_agent, "location": location, "device": device},
        )
        if not created and device_info.ip_address != ip_address:
            device_info.ip_address = ip_address
            device_info.user_agent = user_agent
            device_info.location = location
            device_info.device = device
            device_info.created_at = timezone.now()
            device_info.save()

            async_send_device_verification_email.delay(user.id)


class ResendEmailVerfySerializer(serializers.Serializer):
    email = serializers.EmailField(required=True)

    def validate(self, data):
        email = data.get("email")
        if email:
            user = get_user_model().objects.filter(email=email).first()
            if user is None:
                raise serializers.ValidationError({"detail": "User with that email has not registered yet."})
        else:
            raise serializers.ValidationError(
                {"detail": 'Must include "email" field'},
            )
        data["user"] = user
        return data


class KYCFileSerializer(serializers.ModelSerializer):
    class Meta:
        model = KYCFile
        fields = "__all__"
        read_only_fields = ["created_at", "updated_at"]

    def create(self, validated_data):
        # if kyc status is verified do not allow editing
        if validated_data["kyc"].verified:
            raise serializers.ValidationError("Can not update already verified document.")
        return super().create(validated_data)

    def update(self, instance, validated_data):
        # if kyc status is verified do not allow editing
        if instance.kyc.verified:
            raise serializers.ValidationError("Can not update already verified document.")
        return super().update(instance, validated_data)


class KYCSerializer(serializers.ModelSerializer):
    user = UserSerializer(
        default=serializers.CreateOnlyDefault(serializers.CurrentUserDefault()),
        read_only=True,
    )

    class Meta:
        model = KYC
        fields = "__all__"
        read_only_fields = ["status", "verified", "created_at", "updated_at"]
        # depth = 2

    def create(self, validated_data):
        user = self.context["request"].user
        validated_data["user"] = user
        return super().create(validated_data)

    def update(self, instance, validated_data):
        # if kyc status is verified do not allow editing
        if instance.verified:
            raise serializers.ValidationError("Can not update already verified document.")
        # status should always be pending when kyc updated
        instance.status = "P"
        return super().update(instance, validated_data)

class UserVerificationStatusSerializer(serializers.Serializer):
    status = serializers.ChoiceField(
        choices=["PENDING", "APPROVED", "REJECTED", "VERIFIED"])

    def validate(self, data):
        user_id = self.context["view"].kwargs.get("user_id")
        user = get_user_model().objects.filter(id=user_id).first()

        if not user:
            raise serializers.ValidationError("User not found.")
        if user.is_superuser:
            raise serializers.ValidationError(
                "Cannot perform this action for a superuser.")
        if user.is_staff:
            raise serializers.ValidationError(
                "Cannot perform this action for a staff user.")
        return data


class User2FAMethodSerializer(serializers.Serializer):
    method = serializers.ChoiceField(choices=["SMS", "AUTHENTICATOR_APP"])

    def validate(self, data):
        # Accessing the user from the request
        user = self.context["view"].request.user
        user.two_fa_type = data["method"]
        user.save()
        return data
