from django.db.models import Q
from django.contrib.auth import get_user_model
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema, OpenApiParameter
from drf_spectacular.types import OpenApiTypes
from rest_framework import generics, status
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, IsAdminUser
from users.models import UserDeviceInfo
from security import models
from security import serializers
from security.commands import durable_security_command
from integrations.models import OrganizationMembership
from integrations.permissions import organization_for_request


def _managed_user(request, user_id):
    organization = organization_for_request(request)
    return get_user_model().objects.filter(
        id=user_id,
        id__in=OrganizationMembership.objects.filter(organization=organization).values("user_id"),
    ).first()


@extend_schema(
    parameters=[
        OpenApiParameter(name="date_from",
                         type=OpenApiTypes.DATE,
                         description="Start date for filtering activities (YYYY-MM-DD)."),
        OpenApiParameter(name="date_to",
                         type=OpenApiTypes.DATE,
                         description="End date for filtering activities (YYYY-MM-DD)."),
        OpenApiParameter(name="action_type",
                         type=OpenApiTypes.STR,
                         enum=['LOGIN', 'LOGOUT'],
                         description="Filter by action type."),
        OpenApiParameter(name="action_status",
                         enum=['SUCCESS', 'FAILED'],
                         type=OpenApiTypes.STR,
                         description="Filter by action status."),
        OpenApiParameter(name="q", type=OpenApiTypes.STR,
                         description="Search by user email, first_name and last_name."),
    ]
)
class UserActivityList(generics.ListAPIView):
    """
    List all user activities with search and filter capabilities.
    """
    serializer_class = serializers.UserActivitySerializer
    permission_classes = (IsAuthenticated, IsAdminUser)

    def get_queryset(self):
        # Get query parameters
        qry = self.request.query_params
        date_from = qry.get('date_from', None)
        date_to = qry.get('date_to', None)
        action_type = qry.get('action_type', None)
        action_status = qry.get('action_status', None)
        search_query = qry.get('q', None)

        queryset = models.UserActivity.objects.exclude(
            user=self.request.user)

        if date_from:
            queryset = queryset.filter(created_at__date__gte=date_from)

        if date_to:
            queryset = queryset.filter(created_at__date__lte=date_to)

        if action_type:
            queryset = queryset.filter(action_type=action_type)

        if action_status:
            queryset = queryset.filter(action_status=action_status)

        if search_query:
            queryset = queryset.filter(
                Q(user__email__icontains=search_query) |
                Q(user__first_name__icontains=search_query) |
                Q(user__last_name__icontains=search_query))

        queryset = queryset.order_by('-created_at')

        return queryset


class TrustedDeviceList(generics.ListAPIView):
    """
    List all trusted devices
    """
    serializer_class = serializers.UserDeviceInfoSerializer
    permission_classes = (IsAuthenticated,)

    def get_queryset(self):
        return UserDeviceInfo.objects.filter(user=self.request.user)

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)


class SetGlobalTwoFactorAuth(generics.CreateAPIView):
    """
    Set or update global 2FA settings for an admin.

    Only admin users can set global 2FA Auth Type for users.

    auth_type -- SMS or AUTHENTICATOR_APP
    """
    queryset = models.TwoFactorAuth.objects.all()
    serializer_class = serializers.TwoFactorAuthSerializer
    permission_classes = (IsAuthenticated, IsAdminUser)

    def get_command_object(self):
        return models.TwoFactorAuth.objects.select_for_update().filter(admin=self.request.user).first()

    @durable_security_command("security.global_2fa.update", versioned=True)
    def create(self, request, *args, **kwargs):
        existing = models.TwoFactorAuth.objects.select_for_update().filter(admin=request.user).first()
        serializer = self.get_serializer(existing, data=request.data)
        try:
            serializer.is_valid(raise_exception=True)
        except ValidationError as e:
            return Response(e.detail, status=status.HTTP_400_BAD_REQUEST)
        serializer.save(admin=request.user)
        status_code = status.HTTP_200_OK if existing else status.HTTP_201_CREATED

        return Response(serializer.data, status=status_code)


class GetGlobalTwoFactorAuth(generics.RetrieveAPIView):
    """
    Retrieve the global 2FA settings for the current admin.
    """
    queryset = models.TwoFactorAuth.objects.all()
    serializer_class = serializers.TwoFactorAuthSerializer
    permission_classes = (IsAuthenticated, IsAdminUser)

    def get_object(self):
        try:
            return models.TwoFactorAuth.objects.get(admin=self.request.user)
        except models.TwoFactorAuth.DoesNotExist:
            raise NotFound("TwoFactorAuth settings not found for this admin.")


class SetGlobalPasswordPolicy(generics.CreateAPIView):
    """
    Set or update global password policy settings.

    Only admin users can set global password policy settings for users.

    complexity -- SPECIAL_CHARACTERS, UPPERCASE_LOWERCASE, NUMBERS_AND_SPECIAL_CHARACTERS, CUSTOM

    custom_characters -- Custom characters to be used in password

    min_length -- Minimum length of password

    max_length -- Maximum length of password

    strength -- Password strength (WEAK, MODERATE, STRONG)
    """
    queryset = models.PasswordPolicy.objects.all()
    serializer_class = serializers.PasswordPolicySerializer
    permission_classes = (IsAuthenticated, IsAdminUser)

    def get_command_object(self):
        return models.PasswordPolicy.objects.select_for_update().filter(admin=self.request.user).first()

    @durable_security_command("security.password_policy.update", versioned=True)
    def create(self, request, *args, **kwargs):
        existing = models.PasswordPolicy.objects.select_for_update().filter(admin=request.user).first()
        serializer = self.get_serializer(existing, data=request.data)
        try:
            serializer.is_valid(raise_exception=True)
        except ValidationError as e:
            return Response(e.detail, status=status.HTTP_400_BAD_REQUEST)
        serializer.save(admin=request.user)
        status_code = status.HTTP_200_OK if existing else status.HTTP_201_CREATED

        return Response(serializer.data, status=status_code)


class GetGlobalPasswordPolicy(generics.RetrieveAPIView):
    """
    Retrieve the global password policy settings for the current admin.
    """
    queryset = models.PasswordPolicy.objects.all()
    serializer_class = serializers.PasswordPolicySerializer
    permission_classes = (IsAuthenticated, IsAdminUser)

    def get_object(self):
        try:
            return models.PasswordPolicy.objects.get(admin=self.request.user)
        except models.PasswordPolicy.DoesNotExist:
            raise NotFound("PasswordPolicy settings not found for this admin.")


class IPWhitelist(generics.ListCreateAPIView):
    """
    List or add IP addresses to whitelist.

    Only admin users can view or add IP addresses to whitelist.
    """
    serializer_class = serializers.IPWhitelistSerializer
    permission_classes = (IsAuthenticated, IsAdminUser)

    def get_queryset(self):
        return models.IPWhitelist.objects.filter(admin=self.request.user)

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    @durable_security_command("security.ip_whitelist.create")
    def create(self, request, *args, **kwargs):
        ip_address = request.data.get('ip_address', None)

        if not ip_address:
            return Response({'ip_address': ['This field is required.']}, status=status.HTTP_400_BAD_REQUEST)

        # Check if the IP address already exists
        if models.IPWhitelist.objects.filter(
                admin=request.user, ip_address=ip_address).exists():
            return Response({'ip_address': ['This IP address is already whitelisted.']}, status=status.HTTP_400_BAD_REQUEST)

        serializer = self.get_serializer(data=request.data)

        # Validate the serializer
        try:
            serializer.is_valid(raise_exception=True)
        except ValidationError as e:
            return Response(e.detail, status=status.HTTP_400_BAD_REQUEST)

        serializer.save(admin=self.request.user)

        return Response(serializer.data, status=status.HTTP_201_CREATED)


class IPWhitelistDeleteView(generics.DestroyAPIView):
    queryset = models.IPWhitelist.objects.all()
    serializer_class = serializers.IPWhitelistSerializer
    permission_classes = [IsAuthenticated, IsAdminUser]

    def get_queryset(self):
        return models.IPWhitelist.objects.filter(admin=self.request.user)

    @durable_security_command("security.ip_whitelist.delete", versioned=True)
    def delete(self, request, *args, **kwargs):
        instance = self.get_object()
        self.perform_destroy(instance)
        return Response(status=status.HTTP_204_NO_CONTENT)


class CountryWhitelist(generics.ListCreateAPIView):
    """
    List or add countries to whitelist.

    Only admin users can view or add countries to whitelist.
    """
    serializer_class = serializers.CountryWhitelistSerializer
    permission_classes = (IsAuthenticated, IsAdminUser)

    def get_queryset(self):
        return models.CountryWhitelist.objects.filter(
            admin=self.request.user)

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    @durable_security_command("security.country_whitelist.create")
    def create(self, request, *args, **kwargs):
        country = request.data.get('country', None)

        if not country:
            return Response({'country': ['This field is required.']}, status=status.HTTP_400_BAD_REQUEST)

        # Check if the country already exists
        if models.CountryWhitelist.objects.filter(
                admin=request.user, country=country).exists():
            return Response({'country': ['This country is already whitelisted.']}, status=status.HTTP_400_BAD_REQUEST)

        serializer = self.get_serializer(data=request.data)

        # Validate the serializer
        try:
            serializer.is_valid(raise_exception=True)
        except ValidationError as e:
            return Response(e.detail, status=status.HTTP_400_BAD_REQUEST)

        serializer.save(admin=self.request.user)

        return Response(serializer.data, status=status.HTTP_201_CREATED)


class CountryWhitelistDeleteView(generics.DestroyAPIView):
    queryset = models.CountryWhitelist.objects.all()
    serializer_class = serializers.CountryWhitelistSerializer
    permission_classes = [IsAuthenticated, IsAdminUser]

    def get_queryset(self):
        return models.CountryWhitelist.objects.filter(admin=self.request.user)

    @durable_security_command("security.country_whitelist.delete", versioned=True)
    def delete(self, request, *args, **kwargs):
        instance = self.get_object()
        self.perform_destroy(instance)
        return Response(status=status.HTTP_204_NO_CONTENT)


class IPBlacklistView(generics.ListCreateAPIView):
    """
    List or add IP addresses to blacklist.

    Only admin users can view or add IP addresses to blacklist.
    """
    serializer_class = serializers.IPBlacklistSerializer
    permission_classes = (IsAuthenticated, IsAdminUser)

    def get_queryset(self):
        return models.IPBlacklist.objects.filter(admin=self.request.user)

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    @durable_security_command("security.ip_blacklist.create")
    def create(self, request, *args, **kwargs):
        ip_address = request.data.get('ip_address', None)

        if not ip_address:
            return Response({'ip_address': ['This field is required.']}, status=status.HTTP_400_BAD_REQUEST)

        # Check if the IP address already exists
        if models.IPBlacklist.objects.filter(
                admin=request.user, ip_address=ip_address).exists():
            return Response({'ip_address': ['This IP address is already blacklisted.']}, status=status.HTTP_400_BAD_REQUEST)

        serializer = self.get_serializer(data=request.data)

        # Validate the serializer
        try:
            serializer.is_valid(raise_exception=True)
        except ValidationError as e:
            return Response(e.detail, status=status.HTTP_400_BAD_REQUEST)

        serializer.save(admin=self.request.user)

        return Response(serializer.data, status=status.HTTP_201_CREATED)


class IPBlacklistDeleteView(generics.DestroyAPIView):

    queryset = models.IPBlacklist.objects.all()
    serializer_class = serializers.IPBlacklistSerializer
    permission_classes = [IsAuthenticated, IsAdminUser]

    def get_queryset(self):
        return models.IPBlacklist.objects.filter(admin=self.request.user)

    @durable_security_command("security.ip_blacklist.delete", versioned=True)
    def delete(self, request, *args, **kwargs):
        instance = self.get_object()
        self.perform_destroy(instance)
        return Response(status=status.HTTP_204_NO_CONTENT)


class IPRestrictionsView(generics.RetrieveUpdateAPIView):
    """
    Retrieve, update or create IPRestrictions for the current admin user.

    restriction_type -- ALLOW_ALL, RESTRICT_BY_COUNTRY, CUSTOM_IP_WHITELIST
    """
    serializer_class = serializers.IPRestrictionsSerializer
    permission_classes = [IsAuthenticated, IsAdminUser]

    def get_command_object(self):
        return models.IPRestrictions.objects.select_for_update().filter(admin=self.request.user).first()

    def get_object(self):

        obj, created = models.IPRestrictions.objects.get_or_create(
            admin=self.request.user)

        # Set newly added IPWhitelist and CountryWhitelist entries to the IPRestrictions object
        obj.ip_whitelist.set(
            models.IPWhitelist.objects.filter(admin=self.request.user))
        obj.country_whitelist.set(
            models.CountryWhitelist.objects.filter(admin=self.request.user))
        obj.ip_blacklist.set(
            models.IPBlacklist.objects.filter(admin=self.request.user))
        return obj

    @durable_security_command("security.ip_restrictions.update", versioned=True)
    def update(self, request, *args, **kwargs):
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        serializer = self.get_serializer(
            instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)
        return Response(serializer.data)

    def create(self, request, *args, **kwargs):
        return self.update(request, *args, **kwargs)


# User Setting Views

class UserIPRestrictionView(generics.GenericAPIView):
    """ 
    IP restrictions status update for a user.

    action: allow or block
    """

    serializer_class = serializers.UserIPRestrictionSerializer
    permission_classes = [IsAdminUser]

    def get_object(self):
        user_id = self.kwargs.get("user_id")
        return _managed_user(self.request, user_id)

    @durable_security_command("security.user_ip_restriction.update", versioned=True)
    def patch(self, request, *args, **kwargs):
        user = self.get_object()
        if not user:
            return Response({"error": "User not found."}, status=status.HTTP_404_NOT_FOUND)

        serializer = self.get_serializer(
            data=request.data, context={'view': self})
        if serializer.is_valid():
            return Response(serializer.data, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class SetUser2FATypeView(generics.GenericAPIView):
    """
    Set user 2FA authentication type.

    two_factor_auth_type: SMS or AUTHENTICATOR_APP

    """

    serializer_class = serializers.User2FATypeSerializer
    permission_classes = [IsAdminUser]

    def get_object(self):
        user_id = self.kwargs.get("user_id")
        return _managed_user(self.request, user_id)

    @durable_security_command("security.user_2fa_type.update", versioned=True)
    def patch(self, request, *args, **kwargs):
        user = self.get_object()
        if not user:
            return Response({"error": "User not found."}, status=status.HTTP_404_NOT_FOUND)
        serializer = self.get_serializer(
            data=request.data, context={'view': self})
        if serializer.is_valid():
            return Response(serializer.data, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class SetUserPasswordStrengthView(generics.GenericAPIView):
    """
    Password strength configuration for a user.

    password_strength: MODERATE, STRONG, WEAK

    """

    serializer_class = serializers.UserPasswordStrengthSerializer
    permission_classes = [IsAdminUser]

    def get_object(self):
        user_id = self.kwargs.get("user_id")
        return _managed_user(self.request, user_id)

    @durable_security_command("security.user_password_strength.update", versioned=True)
    def patch(self, request, *args, **kwargs):
        user = self.get_object()
        if not user:
            return Response({"error": "User not found."}, status=status.HTTP_404_NOT_FOUND)
        serializer = self.get_serializer(
            data=request.data, context={'view': self})
        if serializer.is_valid():
            return Response(serializer.data, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class SetUserPasswordLengthView(generics.GenericAPIView):
    """
    Password length configuration for a user.
    """

    serializer_class = serializers.UserPasswordLengthSerializer
    permission_classes = [IsAdminUser]

    def get_object(self):
        user_id = self.kwargs.get("user_id")
        return _managed_user(self.request, user_id)

    @durable_security_command("security.user_password_length.update", versioned=True)
    def patch(self, request, *args, **kwargs):
        user = self.get_object()
        if not user:
            return Response({"error": "User not found."}, status=status.HTTP_404_NOT_FOUND)
        serializer = self.get_serializer(
            data=request.data, context={'view': self})
        if serializer.is_valid():
            return Response(serializer.data, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class SetUserPasswordComplexityView(generics.GenericAPIView):
    """
    Password complexity configuration for a user.

    password_complexity: 
        SPECIAL_CHARACTERS, UPPERCASE_LOWERCASE, 
        NUMBERS_AND_SPECIAL_CHARACTERS or CUSTOM

    custom_characters: Custom characters for password complexity.

    """

    serializer_class = serializers.UserPasswordComplexitySerializer
    permission_classes = [IsAdminUser]

    def get_object(self):
        user_id = self.kwargs.get("user_id")
        return _managed_user(self.request, user_id)

    @durable_security_command("security.user_password_complexity.update", versioned=True)
    def patch(self, request, *args, **kwargs):
        user = self.get_object()
        if not user:
            return Response({"error": "User not found."}, status=status.HTTP_404_NOT_FOUND)
        serializer = self.get_serializer(
            data=request.data, context={'view': self})
        if serializer.is_valid():
            return Response(serializer.data, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class ResetUserSettingsView(generics.GenericAPIView):
    """
    Reset user settings to default.
    """
    serializer_class = serializers.ResetUserSettingsSerializer
    permission_classes = [IsAdminUser]

    def get_object(self):
        user_id = self.kwargs.get("user_id")
        return _managed_user(self.request, user_id)

    @durable_security_command("security.user_settings.reset", versioned=True)
    def post(self, request, *args, **kwargs):
        user = self.get_object()
        if not user:
            return Response({"error": "User not found."}, status=status.HTTP_404_NOT_FOUND)
        serializer = self.get_serializer(
            data=request.data, context={'view': self})
        if serializer.is_valid():
            return Response(serializer.data, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class UserIPBlacklistView(generics.ListCreateAPIView):
    """ 
    List and create user IP blacklist.

    Only accessible by admins.
    """

    serializer_class = serializers.UserIPBlacklistSerializer
    permission_classes = [IsAdminUser]

    def get_queryset(self):
        organization = organization_for_request(self.request)
        return models.UserIPBlacklist.objects.filter(
            user_id=self.kwargs.get("user_id"), admin=self.request.user,
            user_id__in=OrganizationMembership.objects.filter(organization=organization).values("user_id"),
        )

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    @durable_security_command("security.user_ip_blacklist.create")
    def create(self, request, *args, **kwargs):
        ip_address = request.data.get('ip_address', None)
        user_id = self.kwargs.get("user_id")
        if not _managed_user(request, user_id):
            return Response({"error": "User not found."}, status=status.HTTP_404_NOT_FOUND)

        if not ip_address:
            return Response({'ip_address': ['This field is required.']},
                            status=status.HTTP_400_BAD_REQUEST)

        # Check if the IP address already exists
        if models.UserIPBlacklist.objects.filter(
                admin=request.user, user_id=user_id, ip_address=ip_address).exists():
            return Response({'ip_address': ['This IP address is already blacklisted.']},
                            status=status.HTTP_400_BAD_REQUEST)
        
        serializer = self.get_serializer(data=request.data)

        # Validate the serializer
        try:
            serializer.is_valid(raise_exception=True)
        except ValidationError as e:
            return Response(e.detail, status=status.HTTP_400_BAD_REQUEST)

        serializer.save(admin=self.request.user, user_id=user_id)

        return Response(serializer.data, status=status.HTTP_201_CREATED)


class UserIPBlacklistUpdateDeleteView(generics.RetrieveUpdateDestroyAPIView):
    """ 
    Get, Update and delete user IP blacklist by ID.

    Only accessible by admins.
    """

    serializer_class = serializers.UserIPBlacklistSerializer
    permission_classes = [IsAdminUser]

    def get_queryset(self):
        organization = organization_for_request(self.request)
        return models.UserIPBlacklist.objects.filter(
            admin=self.request.user,
            user_id__in=OrganizationMembership.objects.filter(organization=organization).values("user_id"),
        )

    def get_object(self):
        return get_object_or_404(
            self.get_queryset(), id=self.kwargs.get("pk"))

    @durable_security_command("security.user_ip_blacklist.update", versioned=True)
    def update(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(
            instance, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @durable_security_command("security.user_ip_blacklist.delete", versioned=True)
    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        instance.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
