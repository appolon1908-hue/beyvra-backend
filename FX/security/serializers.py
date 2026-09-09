from .models import PasswordPolicy
from django.contrib.auth import get_user_model
from rest_framework import serializers
from security import models
from users.models import UserDeviceInfo


User = get_user_model()


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'email', 'first_name', 'last_name', 'updated_at']
        read_only_fields = ['updated_at']


class UserActivitySerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)

    class Meta:
        model = models.UserActivity
        fields = '__all__'


class UserDeviceInfoSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserDeviceInfo
        fields = '__all__'


class TwoFactorAuthSerializer(serializers.ModelSerializer):
    """ User Global 2FA Settings Serializer """
    class Meta:
        model = models.TwoFactorAuth
        fields = ['auth_type', 'updated_at']
        read_only_fields = ['updated_at']


class PasswordPolicySerializer(serializers.ModelSerializer):
    """Serializer for PasswordPolicy"""

    class Meta:
        model = PasswordPolicy
        fields = ['complexity', 'custom_characters',
                  'min_length', 'max_length', 'strength', 'updated_at']
        read_only_fields = ['updated_at']


class IPWhitelistSerializer(serializers.ModelSerializer):
    """Serializer for IP Whitelist"""

    class Meta:
        model = models.IPWhitelist
        fields = ['id', 'ip_address', 'updated_at']
        read_only_fields = ['updated_at']


class CountryWhitelistSerializer(serializers.ModelSerializer):
    """Serializer for Country Whitelist"""

    class Meta:
        model = models.CountryWhitelist
        fields = ['id', 'country', 'updated_at']
        read_only_fields = ['updated_at']


class IPBlacklistSerializer(serializers.ModelSerializer):
    """Serializer for IP Blacklist"""

    class Meta:
        model = models.IPBlacklist
        fields = ['id', 'ip_address', 'updated_at']
        read_only_fields = ['updated_at']


class IPRestrictionsSerializer(serializers.ModelSerializer):
    ip_whitelist = IPWhitelistSerializer(many=True, read_only=True)
    country_whitelist = CountryWhitelistSerializer(many=True, read_only=True)
    ip_blacklist = IPBlacklistSerializer(many=True, read_only=True)

    class Meta:
        model = models.IPRestrictions
        fields = ['restriction_type', 'ip_whitelist',
                  'country_whitelist', 'ip_blacklist', 'updated_at']
        read_only_fields = ['updated_at']

    def create(self, validated_data):

        admin = self.context['request'].user

        # Fetch all IPWhitelist and CountryWhitelist entries for the admin
        ip_whitelists = models.IPWhitelist.objects.filter(admin=admin)
        country_whitelists = models.CountryWhitelist.objects.filter(
            admin=admin)
        ip_blacklists = models.IPBlacklist.objects.filter(admin=admin)

        ip_restrictions = models.IPRestrictions.objects.create(
            admin=admin,
            restriction_type=validated_data.get(
                'restriction_type', 'ALLOW_ALL')
        )

        # Link the whitelists to the IPRestrictions instance
        ip_restrictions.ip_whitelist.set(ip_whitelists)
        ip_restrictions.country_whitelist.set(country_whitelists)
        ip_restrictions.ip_blacklist.set(ip_blacklists)

        return ip_restrictions

    def update(self, instance, validated_data):
        instance.restriction_type = validated_data.get(
            'restriction_type', instance.restriction_type)

        admin = self.context['request'].user

        ip_whitelists = models.IPWhitelist.objects.filter(admin=admin)
        country_whitelists = models.CountryWhitelist.objects.filter(
            admin=admin)
        ip_blacklists = models.IPBlacklist.objects.filter(admin=admin)

        instance.ip_whitelist.set(ip_whitelists)
        instance.country_whitelist.set(country_whitelists)
        instance.ip_blacklist.set(ip_blacklists)

        instance.save()
        return instance


# User Settings Serializers

class UserIPRestrictionSerializer(serializers.Serializer):
    action = serializers.ChoiceField(choices=["block", "allow"])

    def validate(self, data):
        action = data.get("action")
        user_id = self.context["view"].kwargs.get("user_id")
        user = get_user_model().objects.filter(id=user_id).first()

        if not user:
            raise serializers.ValidationError("User not found.")
        if user.is_superuser:
            raise serializers.ValidationError("Cannot block a superuser.")
        if user.is_staff:
            raise serializers.ValidationError("Cannot block a staff user.")
        if not user.is_active:
            raise serializers.ValidationError("User is already banned.")

        # Handle the action logic
        if action == "block":
            user.ip_restricted = True
        elif action == "allow":
            user.ip_restricted = False

        user.save()
        return data


class User2FATypeSerializer(serializers.Serializer):
    two_factor_auth_type = serializers.ChoiceField(
        choices=["SMS", "AUTHENTICATOR_APP"])

    def validate(self, data):
        user_id = self.context["view"].kwargs.get("user_id")
        user = get_user_model().objects.filter(id=user_id).first()

        if not user:
            raise serializers.ValidationError("User not found.")
        if user.is_superuser:
            raise serializers.ValidationError(
                "Cannot set 2FA for a superuser.")
        if user.is_staff:
            raise serializers.ValidationError(
                "Cannot set 2FA for a staff user.")

        user.two_fa_type = data["two_factor_auth_type"]
        user.save()
        return data


class UserPasswordStrengthSerializer(serializers.Serializer):
    password_strength = serializers.ChoiceField(
        choices=["MODERATE", "STRONG",  "WEAK"])

    def validate(self, data):
        user_id = self.context["view"].kwargs.get("user_id")
        user = get_user_model().objects.filter(id=user_id).first()

        if not user:
            raise serializers.ValidationError("User not found.")
        if user.is_superuser:
            raise serializers.ValidationError(
                "Cannot set password strength for a superuser.")
        if user.is_staff:
            raise serializers.ValidationError(
                "Cannot set password strength for a staff user.")

        user.password_strength = data["password_strength"]
        user.save()
        return data


class UserPasswordLengthSerializer(serializers.Serializer):
    password_min_length = serializers.IntegerField(default=8)
    password_max_length = serializers.IntegerField(default=20)

    def validate(self, data):
        user_id = self.context["view"].kwargs.get("user_id")
        user = get_user_model().objects.filter(id=user_id).first()

        if not user:
            raise serializers.ValidationError("User not found.")
        if user.is_superuser:
            raise serializers.ValidationError(
                "Cannot set password length for a superuser.")
        if user.is_staff:
            raise serializers.ValidationError(
                "Cannot set password length for a staff user.")

        length_check = data["password_min_length"] <= data["password_max_length"]
        if not length_check:
            raise serializers.ValidationError(
                "Minimum password length should be less than maximum password length.")

        # should not less then or equal to 0
        if data["password_min_length"] <= 0 or data["password_max_length"] <= 0:
            raise serializers.ValidationError(
                "Password length should be greater than 0.")

        user.password_min_length = data["password_min_length"]
        user.password_max_length = data["password_max_length"]
        user.save()

        return data


class UserPasswordComplexitySerializer(serializers.Serializer):
    password_complexity = serializers.ChoiceField(choices=[
        "SPECIAL_CHARACTERS", "UPPERCASE_LOWERCASE",
        "NUMBERS_AND_SPECIAL_CHARACTERS", "CUSTOM"])

    # incase of custom complexity
    custom_characters = serializers.CharField(max_length=255, required=False)

    def validate(self, data):
        user_id = self.context["view"].kwargs.get("user_id")
        user = get_user_model().objects.filter(id=user_id).first()

        if not user:
            raise serializers.ValidationError("User not found.")
        if user.is_superuser:
            raise serializers.ValidationError(
                "Cannot set password complexity for a superuser.")
        if user.is_staff:
            raise serializers.ValidationError(
                "Cannot set password complexity for a staff user.")

        if data.get("password_complexity") == "CUSTOM":
            custom_characters = data.get("custom_characters", "").strip()

            # Check if custom_characters is missing or empty
            if not custom_characters or custom_characters == "string":
                raise serializers.ValidationError(
                    "Custom characters required for custom complexity.")

        user.password_complexity = data["password_complexity"]
        user.custom_characters = data.get("custom_characters", None)
        user.save()

        return data


class ResetUserSettingsSerializer(serializers.Serializer):
    def validate(self, data):
        user_id = self.context["view"].kwargs.get("user_id")
        user = get_user_model().objects.filter(id=user_id).first()

        if not user:
            raise serializers.ValidationError("User not found.")
        if user.is_superuser:
            raise serializers.ValidationError(
                "Cannot reset settings for a superuser.")
        if user.is_staff:
            raise serializers.ValidationError(
                "Cannot reset settings for a staff user.")

        user.two_fa_type = "SMS"
        user.ip_restricted = False
        user.password_complexity = "SPECIAL_CHARACTERS"
        user.custom_characters = None
        user.password_strength = "STRONG"
        user.password_min_length = 8
        user.password_max_length = 20
        user.save()

        # update data to return
        data['two_fa_type'] = user.two_fa_type
        data['ip_restricted'] = user.ip_restricted
        data['password_complexity'] = user.password_complexity
        data['custom_characters'] = user.custom_characters
        data['password_strength'] = user.password_strength
        data['password_min_length'] = user.password_min_length
        data['password_max_length'] = user.password_max_length
        return data


class UserIPBlacklistSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.UserIPBlacklist
        fields = ['ip_address', 'id', 'updated_at']
        read_only_fields = ["created_at", "updated_at"]
