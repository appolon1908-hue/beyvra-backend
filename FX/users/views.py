import base64
import io
from uuid import uuid4
import pandas as pd
import pyotp
import qrcode
import re
from django.db import transaction
from datetime import datetime
from users.signals import update_user_upon_creation
from django.db.models.signals import post_save
from django.utils.crypto import get_random_string
from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.core.cache import cache
from django.utils.encoding import force_str
from django.utils.http import urlsafe_base64_decode
from django.views.decorators.csrf import csrf_exempt
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import generics, permissions, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated,IsAdminUser
from rest_framework.response import Response
from rest_framework.serializers import ValidationError
from rest_framework.views import APIView
from rest_framework.pagination import PageNumberPagination
from users import messages
from users.models import User
from users.tasks import async_send_welcome_email
from users.serializers import (
    AuthSerializer,
    AuthTokenObtainPairSerializer,
    KYCFileSerializer,
    KYCSerializer,
    LoginSerializer,
    PasswordChangeSerializer,
    PasswordResetConfirmSerializer,
    PasswordResetRequestSerializer,
    ResendEmailVerfySerializer,
    UserSerializer,
    UserUpdateSerializer,
    VerifyPhoneCodeSerializer,
    WalkthroughSerializer,
    UserVerificationStatusSerializer,
    User2FAMethodSerializer,
    AdminUserStatusSerializer,
)
from wallet.serializers import WalletDetailSerializer
from trade.serializers import TradeDetailSerializer,TransactionSerializer
from trade.models import Transaction


from .models import KYC, KYCFile, PhoneVerificationCode
from .tasks import (
    async_send_email_verification_email,
    async_send_mobile_verification_code,
    async_send_password_reset_link_email,
    async_send_user_ban_email,
)
from trade.models import Trade
from django.db.models import Sum, Q, Case, When, Value, CharField
from django.db import connection
from wallet.models import Wallet, Currency
from wallet.constants import DEMO_BALANCE, DEMO_WALLET_NAME
from django.http import HttpResponse


User = get_user_model()


class CreateUserView(generics.CreateAPIView):
    """Create a new user in the system."""

    serializer_class = UserSerializer
    permission_classes = [permissions.AllowAny]


class GetUserView(APIView):
    """Get a user from the system."""

    def get(self, request, id):
        user = request.user

        try:
            user = User.objects.get(id=id)
        except User.DoesNotExist:
            return Response({"detail": messages.USER_NOT_FOUND}, status=status.HTTP_404_NOT_FOUND)

        return Response(UserSerializer(user).data, status=status.HTTP_200_OK)


class SendEmailVerificationView(generics.CreateAPIView):
    """Send Email for user email address verification."""

    serializer_class = ResendEmailVerfySerializer
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        serializer = self.serializer_class(data=request.data)
        if serializer.is_valid(raise_exception=True):
            user = serializer.validated_data["user"]

            async_send_email_verification_email.delay(user.id)
            return Response({"detail": "Verification Email sent."}, status=status.HTTP_201_CREATED)
        return Response(
            {"detail": "Invalid data."},
            status=status.HTTP_400_BAD_REQUEST,
        )
    


@extend_schema(
    description="Request email verification link for authenticated user.",
    responses={200: {"description": messages.VERIFICATION_EMAIL_SENT}},
)
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def request_email_verification(request):
    """Request email verification link for authenticated user."""
    user = request.user

    # Send verification email asynchronously
    async_send_email_verification_email.delay(user.id)

    return Response({"detail": messages.VERIFICATION_EMAIL_SENT}, status=status.HTTP_200_OK)


    





@api_view(["GET"])
@permission_classes([AllowAny])
def verify_email(request, uidb64, token):
    """Verify the email verification link is correct."""
    try:
        uid = force_str(urlsafe_base64_decode(uidb64))
        user = User.objects.get(pk=uid)
    except (TypeError, ValueError, OverflowError, User.DoesNotExist):
        user = None

    if (user is not None) and default_token_generator.check_token(user, token):
        user.email_verified = True
        user.save()

        return Response(
            {"detail": "Email Verification completed successfully"},
            status=status.HTTP_200_OK,
        )
    else:
        return Response(
            {"detail": "Email verification link is not valid."},
            status=status.HTTP_400_BAD_REQUEST,
        )


class SendPhoneVerificationView(APIView):
    """Send SMS code to user phone number for verification."""

    def post(self, request):
        async_send_mobile_verification_code.delay(request.user.id)

        return Response({"detail": "Verification Message sent."}, status=status.HTTP_200_OK)


@extend_schema(request=VerifyPhoneCodeSerializer)
class VerifyPhoneCodeView(APIView):
    """Verify code sent to users phone number."""

    serializer_class = VerifyPhoneCodeSerializer

    @extend_schema(
        request=VerifyPhoneCodeSerializer,
        responses={201: VerifyPhoneCodeSerializer, 400: 'Bad Request'},
    )
    def post(self, request):
        serializer = self.serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)

        code = request.data["code"]
        try:
            verification_code = PhoneVerificationCode.objects.get(user=request.user)
            if verification_code.failed_checks >= 3:
                verification_code.delete()
                return Response(
                    {"detail": "Verification failed checks limit exceeded. Please request new code."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            elif code == verification_code.code:
                user_instance = get_user_model().objects.get(id=request.user.id)
                user_instance.phone_verified = True
                user_instance.save()
                verification_code.delete()
                return Response({"detail": "Phone verified successfully."})

            elif code != verification_code.code:
                verification_code.failed_checks = verification_code.failed_checks + 1
                verification_code.save()

                return Response(
                    {"detail": "Invalid code."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
        except PhoneVerificationCode.DoesNotExist:
            return Response(
                {"detail": "Please request code first before verificaion."},
                status=status.HTTP_400_BAD_REQUEST,
            )


@extend_schema(request=PasswordResetRequestSerializer)
class PasswordResetRequestView(APIView):
    """Send password reset link to user's email ID."""

    serializer_class = PasswordResetRequestSerializer
    permission_classes = [permissions.AllowAny]

    @extend_schema(
        request=PasswordResetRequestSerializer,
        responses={201: PasswordResetRequestSerializer, 400: 'Bad Request'},
    )
    def post(self, request):
        serializer = self.serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)

        email = request.data["email"]

        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            return Response(
                {"detail": "This email is not associated with any account. Please try again with valid email."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        async_send_password_reset_link_email.delay(user.id)
        return Response(
            {"detail": "Password reset instructions sent on email."},
            status=status.HTTP_200_OK,
        )


@extend_schema(request=PasswordResetConfirmSerializer)
@api_view(["POST"])
@permission_classes([AllowAny])
def password_reset_confirm(request, uidb64, token):
    """Set new password for user"""

    serializer = PasswordResetConfirmSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    new_password = serializer.data["new_password"]

    try:
        uid = force_str(urlsafe_base64_decode(uidb64))
        user = User.objects.get(pk=uid)
    except (TypeError, ValueError, OverflowError, User.DoesNotExist):
        user = None

    if (user is not None) and default_token_generator.check_token(user, token):
        user.set_password(new_password)
        user.save()

        return Response({"detail": "Password updated successfully"}, status=status.HTTP_200_OK)
    else:
        return Response(
            {"detail": "Password reset link is not valid."},
            status=status.HTTP_400_BAD_REQUEST,
        )


@extend_schema(request=PasswordChangeSerializer)
@api_view(["POST"])
def password_change(request):
    """Change password for loggedin user."""

    serializer = PasswordChangeSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    old_password = serializer.data["old_password"]
    new_password = serializer.data["new_password"]

    user = request.user

    if not user.check_password(old_password):
        return Response({"detail": "Incorrect old password"}, status=status.HTTP_400_BAD_REQUEST)

    user.set_password(new_password)
    # Reset verification status if user is in change password status
    if user.verification_status == "CHANGE_PASSWORD":
        user.verification_status = ""
    user.save()

    return Response({"detail": "Password updated successfully"}, status=status.HTTP_200_OK)


class ManageUserView(generics.RetrieveUpdateAPIView):
    """Manage the authenticated user."""

    serializer_class = UserUpdateSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self):
        """Retrive and return the authenticated user."""
        return self.request.user


class DisableWalkthroughView(generics.UpdateAPIView):
    serializer_class = WalkthroughSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self):
        return self.request.user

    def put(self, request, *args, **kwargs):
        user = self.get_object()
        serializer = self.get_serializer(user, data={"is_walkthrough": True}, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class EnableMFAView(generics.GenericAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = AuthSerializer

    def get(self, request, *args, **kwargs):
        user = request.user
        if not user.mfa_secret:
            user.mfa_secret = pyotp.random_base32()
            user.save()

        # Generate the provisioning URI
        otp_uri = pyotp.totp.TOTP(user.mfa_secret).provisioning_uri(
            name=user.email,
            issuer_name="Tradx.io"
        )

        # Create the QR code
        qr = qrcode.make(otp_uri)
        buffer = io.BytesIO()
        qr.save(buffer, format="PNG")
        
        # Get the value from buffer
        buffer.seek(0)  # Move to the start of the buffer
        qr_code = base64.b64encode(buffer.getvalue()).decode("utf-8")

        # Ensure to prefix the base64 string with the appropriate data URL scheme
        qr_code_data_uri = f"data:image/png;base64,{qr_code}"

        return Response({"qrcode": qr_code_data_uri}, status=status.HTTP_200_OK)


class VerifyMFAView(generics.GenericAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = AuthSerializer

    def post(self, request, *args, **kwargs):
        user = request.user
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        otp_code = serializer.validated_data["otp"]
        totp = pyotp.TOTP(user.mfa_secret)
        if totp.verify(otp_code):
            if not user.is_mfa_enabled:  # to validate mfa is enabled
                user.is_mfa_enabled = True
            if not user.two_factor_authentication_enabled:
                user.two_factor_authentication_enabled = True
            user.save()
            return Response({"message": "OTP verified successfully"}, status=status.HTTP_200_OK)
        return Response({"error": "Invalid OTP code"}, status=status.HTTP_400_BAD_REQUEST)


@api_view(["GET"])
# @permission_classes([permissions.AllowAny])
def websocket_ticket(request):
    """Generate and return unique ticket for websocket connections"""
    ticket_uuid = str(uuid4())
    cache.set(ticket_uuid, request.user.id, 60 * 2)
    return Response({"ws_ticket": ticket_uuid})


class LoginView(generics.CreateAPIView):
    serializer_class = LoginSerializer
    permission_classes = [permissions.AllowAny]

    @extend_schema(
        request=LoginSerializer,
        responses={201: LoginSerializer, 400: 'Bad Request'},
    )
    @csrf_exempt
    def post(self, request, *args, **kwargs):
        serializer = self.serializer_class(data=request.data)
        if serializer.is_valid(raise_exception=True):
            user = serializer.validated_data["user"]

            # check if user is not active
            if not user.is_active:
                return Response(
                    {"detail": messages.USER_BANNED_CONTACT_SUPPORT},
                    status=status.HTTP_401_UNAUTHORIZED,
                )

            serializer.save(request)

            # TODO: blacklist existing user refresh_tokens first
            refresh = AuthTokenObtainPairSerializer.get_token(user)

            return Response(
                {
                    "refresh": str(refresh),
                    "access": str(refresh.access_token),
                    "user": UserSerializer(user).data,
                },
                status=status.HTTP_201_CREATED,
            )
        return Response(
            {"detail": "Invalid credentials"},
            status=status.HTTP_401_UNAUTHORIZED,
        )



class KYCFileListCreateView(generics.ListCreateAPIView):
    serializer_class = KYCFileSerializer
    permission_classes = [IsAuthenticated]
    queryset = KYCFile.objects.all().order_by("-id")

    def get_queryset(self):
        # allowing access to only the authenticated user kyc data
        self.queryset = self.queryset.filter(kyc__user=self.request.user)
        return super().get_queryset()


class KYCFileDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = KYCFileSerializer
    permission_classes = [IsAuthenticated]
    queryset = KYCFile.objects.select_related("kyc").all()

    def get_queryset(self):
        # allowing access to only the authenticated user kyc data
        self.queryset = self.queryset.filter(kyc__user=self.request.user)
        return super().get_queryset()

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        # if kyc status is verified do not allow editing
        if instance.kyc.verified:
            raise ValidationError("Can not delete already verified document.")
        self.perform_destroy(instance)
        return Response(status=status.HTTP_204_NO_CONTENT)


class KYCListCreateView(generics.ListCreateAPIView):
    serializer_class = KYCSerializer
    permission_classes = [IsAuthenticated]
    queryset = KYC.objects.all().order_by("-id")

    def get_queryset(self):
        # allowing access to only the authenticated user kyc data
        self.queryset = self.queryset.filter(user=self.request.user)
        return super().get_queryset()


class KYCUpdateView(generics.UpdateAPIView):
    serializer_class = KYCSerializer
    permission_classes = [IsAuthenticated]
    queryset = KYC.objects.all()

    def get_queryset(self):
        # allowing access to only the authenticated user kyc data
        self.queryset = self.queryset.filter(user=self.request.user)
        return super().get_queryset()


@extend_schema(
    description="Fetch users based on active status, and username. Only accessible by admins.",
    parameters=[
        OpenApiParameter(
            "is_active", description="Filter by active status. Pass 'true' or 'false'.", required=False, type=bool
        ),
        OpenApiParameter(
            "email", description="Filter by email (partial, case-insensitive match).", required=False, type=str
        ),
        OpenApiParameter(
            "role", description="Filter by user role. Pass 'admin' or 'user'.", required=False, type=str
        ),
        OpenApiParameter(
            "trader_id", description="Filter by trading id.", required=False, type=int
            ),
        OpenApiParameter(
            "first_name", description="Filter by first name.", required=False, type=str
        ),
        OpenApiParameter(
            "last_name", description="Filter by last name.", required=False, type=str
        ),
        OpenApiParameter(
            "phone", description="Filter by phone number.", required=False, type=str
        ),

        

    ],
    responses={
        200: UserSerializer(many=True),
        403: {"description": messages.UNAUTHORIZED_ACTION},
    },
)
class FetchUserView(generics.ListAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = UserSerializer

    def get_queryset(self):
        # Start with a base queryset of all users
        queryset = User.objects.all()

        # Filtering by active status
        is_active = self.request.query_params.get("is_active", None)
        if is_active is not None:
            is_active = is_active.lower() == "true"
            queryset = queryset.filter(is_active=is_active)

        # Filtering by email (case-insensitive, partial match)=
        email = self.request.query_params.get("email", None)
        if email:
            queryset = queryset.filter(email__icontains=email)

        # Filtering by role (admin or user)
        role = self.request.query_params.get("role", None)
        if role:
            if role.lower() == "admin":
                queryset = queryset.filter(is_staff=True)
            elif role.lower() == "user":
                queryset = queryset.filter(is_staff=False,role="User")

        trader_id = self.request.query_params.get("trader_id", None)
        if trader_id:
            queryset = queryset.filter(trader_id=trader_id)


        first_name = self.request.query_params.get("first_name", None)
        if first_name:
            queryset = queryset.filter(first_name__icontains=first_name)

        last_name = self.request.query_params.get("last_name", None)
        if last_name:
            queryset = queryset.filter(last_name__icontains=last_name)

        phone = self.request.query_params.get("phone", None)
        if phone:
            queryset = queryset.filter(phone__icontains=phone)
        


        return queryset

    def list(self, request):
        user = request.user
        if not user.is_staff:
            return Response({"detail": messages.UNAUTHORIZED_ACTION}, status=status.HTTP_403_FORBIDDEN)

        queryset = self.get_queryset()
        serializer = UserSerializer(queryset, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)


class FetchUserDetailView(generics.GenericAPIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, user_id):
        if not request.user.is_staff:
            return Response({"detail": messages.UNAUTHORIZED_ACTION}, status=status.HTTP_403_FORBIDDEN)

        try:
            # Retrieve the user by ID
            user = User.objects.get(id=user_id)
        except User.DoesNotExist:
            return Response({"detail": messages.USER_NOT_FOUND}, status=status.HTTP_404_NOT_FOUND)

        # Attempt to retrieve the user's KYC data
        kyc = KYC.objects.filter(user=user).first()
        kyc_data = KYCSerializer(kyc).data if kyc else None

        if kyc_data:
            kyc_data.pop('user', None)

        # Retrieve the user's KYC files based on the KYC instance
        kyc_files = KYCFile.objects.filter(kyc=kyc) if kyc else []
        kyc_file_data = KYCFileSerializer(kyc_files, many=True).data if kyc_files else []

        # Retrieve the user's wallets
        wallets = Wallet.objects.filter(user=user, is_active=True, is_archived=False)
        wallet_data = WalletDetailSerializer(wallets, many=True).data

        # Retrieve trades related to the user's wallets
        trades = Trade.objects.filter(wallet__in=wallets).select_related('wallet', 'asset', 'transaction', 'category')
        trade_data = TradeDetailSerializer(trades, many=True).data

        # Return the user data, KYC data, KYC files, wallets, and trades
        return Response(
            {
                "user": UserSerializer(user).data,
                "kyc": kyc_data,
                "kyc_files": kyc_file_data,
                "wallets": wallet_data,
                "trades": trade_data
            },
            status=status.HTTP_200_OK,
        )

    def delete(self, request, user_id):
        user = request.user
        if not user.is_staff:
            return Response({"detail": messages.UNAUTHORIZED_ACTION}, status=status.HTTP_403_FORBIDDEN)

        try:
            user_to_delete = User.objects.get(id=user_id)
        except User.DoesNotExist:
            return Response({"detail": messages.USER_NOT_FOUND}, status=status.HTTP_404_NOT_FOUND)

        user_to_delete.delete()
        return Response({"detail": messages.USER_DELETED_SUCCESS}, status=status.HTTP_200_OK)
    

    @extend_schema(
        request=UserUpdateSerializer,
        responses={200: {"description": messages.USER_UPDATED_SUCCESS}},
    )
    def patch(self, request, user_id):
        user = request.user
        if not user.is_staff:
            return Response({"detail": messages.UNAUTHORIZED_ACTION}, status=status.HTTP_403_FORBIDDEN)
        
        try:
            user_to_update = User.objects.get(id=user_id)
        except User.DoesNotExist:
            return Response({"detail": messages.USER_NOT_FOUND}, status=status.HTTP_404_NOT_FOUND)
        
        serializer = UserUpdateSerializer(user_to_update, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        
        return Response({"detail": messages.USER_UPDATED_SUCCESS}, status=status.HTTP_200_OK)


class BulkCreateUserView(APIView):
    """
    Bulk create users using a CSV file.
    
    To test this endpoint use Postman with File upload option.

    The CSV file should contain the following columns:
    
    - first_name
    - last_name
    - email
    - phone_number
    - country_name
    - brand
    """

    permission_classes = [IsAdminUser]
    
    def post(self, request):
        file = request.FILES.get("file")
        if not file:
            return Response({"detail": "No file uploaded."}, status=status.HTTP_400_BAD_REQUEST)
        
        if not file.name.endswith('.csv'):
            return Response({"detail": "Only CSV files are allowed."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            df = pd.read_csv(file, dtype={"phone_number": str})
        except pd.errors.EmptyDataError:
            return Response({"detail": "Empty file uploaded."}, status=status.HTTP_400_BAD_REQUEST)
        except pd.errors.ParserError:
            return Response({"detail": "Invalid file format."}, status=status.HTTP_400_BAD_REQUEST)

        errors = []
        created_users = []
        user_objs = []
        wallet_objs = []
        demo_currency = Currency.objects.filter(name="Đ").first()

        # Temporarily disable the post_save signal
        post_save.disconnect(update_user_upon_creation, sender=User, dispatch_uid="update_user_upon_creation")

        for index, row in df.iterrows():
            # Values
            fname = row.get("first_name", "")
            lname = row.get("last_name", "")
            email = row.get("email", "")
            phone = row.get("phone_number", "")
            country = row.get("country_name", "")
            brand = row.get("brand", "")
            
            # Validations
            NAME_REGEX = re.compile(r"^[a-zA-Z]+$")
            EMAIL_REGEX = re.compile(r"[^@]+@[^@]+\.[^@]+")
            PHONE_REGEX = re.compile(r"^\+\d{1,3}\d+$")
            
            if not email or not fname or not lname or not phone:
                errors.append({
                    "row": index + 1,
                    "email": email,
                    "reason": "Email, first name, last name and phone are required fields."
                })
                continue

            if User.objects.filter(email=email).exists():
                errors.append({
                    "row": index + 1,
                    "email": email,
                    "reason": f"User with email {email} already exists."
                })
                continue

            if User.objects.filter(phone_number=phone).exists():
                errors.append({
                    "row": index + 1,
                    "phone": phone,
                    "reason": f"User with phone {phone} already exists."
                })
                continue
            
            if not NAME_REGEX.match(fname) or not NAME_REGEX.match(lname):
                errors.append({
                    "row": index + 1,
                    "email": email,
                    "reason": "First name and last name should only contain alphabets."
                })
                continue

            if not PHONE_REGEX.match(phone):
                errors.append({
                    "row": index + 1,
                    "email": email,
                    "reason": "Invalid phone number."
                })
                continue

            if len(fname) > 20 or len(lname) > 20:
                errors.append({
                    "row": index + 1,
                    "email": email,
                    "reason": "First name and last name should be less than 20 characters."
                })
                continue

            if not EMAIL_REGEX.match(email):
                errors.append({
                    "row": index + 1,
                    "email": email,
                    "reason": "Invalid email."
                })
                continue

            # Generate random password for user
            temp_password = get_random_string(8)

            # Create user object (without saving it to the DB yet)
            user = User(
                email=email,
                first_name=fname,
                last_name=lname,
                phone_number=phone,
                country_name=country,
                brand=brand,
                is_walkthrough=True,
                verification_status="CHANGE_PASSWORD", # User Need to Change Password On First Login
            )
            user.set_password(temp_password)
            user_objs.append((user, temp_password))

        # Bulk create users
        try:
            with transaction.atomic():
                users = User.objects.bulk_create([user for user, _ in user_objs])

            # Prepare wallets and send welcome emails after users have been created
            for user, temp_password in zip(users, [temp_password for _, temp_password in user_objs]):
                wallet_objs.append(Wallet(
                    name=DEMO_WALLET_NAME,
                    currency=demo_currency,
                    user=user,
                    balance=DEMO_BALANCE,
                    is_real=False
                ))

                # Send welcome email with temporary password
                async_send_welcome_email.delay(user.email, user.first_name, temp_password)

                created_users.append(user.email)

            # Bulk create wallets
            Wallet.objects.bulk_create(wallet_objs)

        except Exception as e:
            errors.append({
                "row": index + 1,
                "email": email,
                "reason": f"Error creating user: {str(e)}"
            })

        # Reconnect the post_save signal
        post_save.connect(update_user_upon_creation, sender=User, dispatch_uid="update_user_upon_creation")

        success_message = f"Users created successfully: {', '.join(created_users)}." if created_users else "No users were created."

        if errors:
            # Log the errors to a file for debugging
            with open("users/users_bulk.log", 'w') as f:
                f.write(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"Errors: {errors}\n")
                f.write(f"Success: {success_message}\n")

        return Response({
            "detail": success_message,
            "errors": errors
        })


@extend_schema(
    description="Ban a user",
    responses={
        200: {"description": "User banned successfully."},
        403: {"description": "Unauthorized action."},
        404: {"description": "User not found."},
    },
)
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def ban_user(request, user_id):
    # Ensure the requesting user has administrative privileges
    if not request.user.is_staff:
        return Response(
            {"detail": messages.UNAUTHORIZED_ACTION},
            status=status.HTTP_403_FORBIDDEN
        )

    try:
        user_to_ban = User.objects.get(id=user_id)
    except User.DoesNotExist:
        return Response(
            {"detail": messages.USER_NOT_FOUND},
            status=status.HTTP_404_NOT_FOUND
        )

    # Prevent banning of other staff members
    if user_to_ban.is_staff:
        return Response(
            {"detail": messages.UNAUTHORIZED_ACTION},
            status=status.HTTP_403_FORBIDDEN
        )

    # Check if the user is already banned
    if not user_to_ban.is_active:
        return Response(
            {"detail": messages.USER_ALREADY_BANNED},
            status=status.HTTP_200_OK
        )

    # Deactivate the user
    user_to_ban.is_active = False
    user_to_ban.save()

    # Trigger the ban notification asynchronously
    async_send_user_ban_email.delay(user_to_ban.id)

    return Response(
        {"detail": messages.USER_BANNED_SUCCESS},
        status=status.HTTP_200_OK
    )



@extend_schema(
        summary="Unban a user",
        description="Unban a user",
        responses={
            200: {"description": "User unbanned successfully."},
            403: {"description": "Unauthorized action."},
            404: {"description": "User not found."},
        },
)
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def unban_user(request, user_id):
    # Ensure the requesting user has administrative privileges
    if not request.user.is_staff:
        return Response(
            {"detail": messages.UNAUTHORIZED_ACTION},
            status=status.HTTP_403_FORBIDDEN
        )

    try:
        user_to_unban = User.objects.get(id=user_id)
    except User.DoesNotExist:
        return Response(
            {"detail": messages.USER_NOT_FOUND},
            status=status.HTTP_404_NOT_FOUND
        )

    # Check if the user is already active
    if user_to_unban.is_active:
        return Response(
            {"detail": messages.USER_ALREADY_UNBANNED},
            status=status.HTTP_200_OK
        )

    # Activate the user
    user_to_unban.is_active = True
    user_to_unban.save()

    return Response(
        {"detail": messages.USER_UNBANNED_SUCCESS},
        status=status.HTTP_200_OK
    )


@extend_schema(
    summary="Admin Dashboard Overview",
    description="Provides an overview of the admin dashboard including user statistics, trade data, and system health.",
    responses={200: dict, 403: dict},
)
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def admin_dashboard_overview(request):
    user = request.user

    # Check if the user is a staff/admin
    if not user.is_staff:
        return Response({"detail": messages.UNAUTHORIZED_ACTION}, status=status.HTTP_403_FORBIDDEN)

    # User statistics
    total_users = User.objects.filter(is_staff=False).count()
    total_active_users = User.objects.filter(is_active=True, is_staff=False).count()
    total_inactive_users = User.objects.filter(is_active=False, is_staff=False).count()

    # Trade statistics
    total_trades = Trade.objects.count()

    # Revenue calculation
    # revenue = Trade.objects.aggregate(Sum('amount'))['amount__sum'] or 0  # Handle null values
    revenue = 0

    # System health check (you can add more checks as needed)
    system_health = {"database": False}
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1;")
            system_health["database"] = True
    except Exception:
        system_health["database"] = False

    # Create the response with all the data
    return Response(
        {
            "total_users": total_users,
            "total_active_users": total_active_users,
            "total_inactive_users": total_inactive_users,
            "total_trades": total_trades,
            "system_health": system_health,
            "revenue": revenue,
        },
        status=status.HTTP_200_OK,
    )




@extend_schema(
    description="get user trading activity",
    responses={
        200: TradeDetailSerializer(many=True),
        403: {"description": "Unauthorized action."},
    },
)
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def get_user_trading_activity(request, user_id):
    user = request.user
    if not user.is_staff:
        return Response({"detail": messages.UNAUTHORIZED_ACTION}, status=status.HTTP_403_FORBIDDEN)

    try:
        user = User.objects.get(id=user_id)
    except User.DoesNotExist:
        return Response({"detail": messages.USER_NOT_FOUND}, status=status.HTTP_404_NOT_FOUND)
    
    trades = Trade.objects.filter(wallet__user=user)

    return Response(TradeDetailSerializer(trades, many=True).data, status=status.HTTP_200_OK)

    

@extend_schema(
    description="Get user trading statistics",
    responses={
        200: dict,
        403: {"description": "Unauthorized action."},
        404: {"description": "User not found."}
    },
)
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def get_user_trading_statistics(request, user_id):
    user = request.user
    
    # Check if the requesting user is staff
    if not user.is_staff:
        return Response({"detail": "Unauthorized action."}, status=status.HTTP_403_FORBIDDEN)

    # Fetch the user for whom to retrieve statistics
    try:
        target_user = User.objects.get(id=user_id)
    except User.DoesNotExist:
        return Response({"detail": "User not found."}, status=status.HTTP_404_NOT_FOUND)
    
    # Fetch all trades related to the user's wallets
    user_wallets = Wallet.objects.filter(user=target_user)
    trades = Trade.objects.filter(wallet__in=user_wallets)
    transactions = Transaction.objects.filter(wallet__in=user_wallets)
    
    # If no trades or wallets, return a zeroed response
    if not user_wallets.exists() or not trades.exists():
        return Response(
            {
                "total_trades": 0,
                "total_transactions": 0,
                "total_deposit_amount": 0.00,
                "total_withdrawal_amount": 0.00,
                "total_traded_amount": 0.00,
                "total_transfer_amount": 0.00,
                "balance": 0.00,
                "pending_transactions": []
            },
            status=status.HTTP_200_OK,
        )

    # Total trades
    total_trades = trades.count()

    # Total transactions
    total_transactions = transactions.count()

    # Aggregate amounts for different transaction types
    total_deposit_amount = transactions.filter(type="D").aggregate(Sum('amount'))['amount__sum'] or 0.00
    total_withdrawal_amount = transactions.filter(type="W").aggregate(Sum('amount'))['amount__sum'] or 0.00
    total_traded_amount = transactions.filter(type="TD").aggregate(Sum('amount'))['amount__sum'] or 0.00
    total_transfer_amount = transactions.filter(type="TN").aggregate(Sum('amount'))['amount__sum'] or 0.00


    balance = user_wallets.aggregate(Sum('balance'))['balance__sum'] or 0.00

    pending_transactions = transactions.filter(status="P").all()

    # Constructing the response data
    return Response(
        {
            "total_trades": total_trades,
            "total_transactions": total_transactions,
            "total_deposit_amount": total_deposit_amount,
            "total_withdrawal_amount": total_withdrawal_amount,
            "total_traded_amount": total_traded_amount,
            "total_transfer_amount": total_transfer_amount,
            "balance": balance - total_withdrawal_amount,
            "pending_transactions": TransactionSerializer(pending_transactions, many=True).data
        },
        status=status.HTTP_200_OK,
    )


@extend_schema(
    description="Verify user KYC",
    responses={
        200: {"description": "User KYC verified successfully."},
        403: {"description": "Unauthorized action."},
        404: {"description": "User not found."},
    },
)
@api_view(["PATCH"])
@permission_classes([IsAuthenticated])
def verify_user_kyc(request, user_id):
    user = request.user
    if not user.is_staff:
        return Response({"detail": messages.UNAUTHORIZED_ACTION}, status=status.HTTP_403_FORBIDDEN)

    try:
        user = User.objects.get(id=user_id)
    except User.DoesNotExist:
        return Response({"detail": messages.USER_NOT_FOUND}, status=status.HTTP_404_NOT_FOUND)

    kyc = KYC.objects.filter(user=user).first()
    if not kyc:
        return Response({"detail": "User KYC not found."}, status=status.HTTP_404_NOT_FOUND)
    
    if kyc.verified:
        return Response({"detail": "User KYC already verified."}, status=status.HTTP_200_OK)

    kyc.verified = True
    kyc.status = "S"
    kyc.save()

    return Response({"detail": "User KYC verified successfully."}, status=status.HTTP_200_OK)

@extend_schema(
    description="get user trading activity",
    responses={
        200: dict,
        403: {"description": "Unauthorized action."},
    },

)
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def user_trading_statistics(request):
    user = request.user
    try:
        target_user = User.objects.get(id=user.id)
    except User.DoesNotExist:
        return Response({"detail": messages.USER_NOT_FOUND}, status=status.HTTP_404_NOT_FOUND)
    
    # Fetch all trades related to the user's wallets
    user_wallets = Wallet.objects.filter(user=target_user)
    trades = Trade.objects.filter(wallet__in=user_wallets)
    transactions = Transaction.objects.filter(wallet__in=user_wallets)
    
    # If no trades or wallets, return a zeroed response
    if not user_wallets.exists() or not trades.exists():
        return Response(
            {
                "total_trades": 0,
                "total_transactions": 0,
                "total_deposit_amount": 0.00,
                "total_withdrawal_amount": 0.00,
                "total_traded_amount": 0.00,
                "total_transfer_amount": 0.00,
                "balance": 0.00,
                "pending_transactions": []
            },
            status=status.HTTP_200_OK,
        )

    # Total trades
    total_trades = trades.count()

    # Total transactions
    total_transactions = transactions.count()

    # Aggregate amounts for different transaction types
    total_deposit_amount = transactions.filter(type="D").aggregate(Sum('amount'))['amount__sum'] or 0.00
    total_withdrawal_amount = transactions.filter(type="W").aggregate(Sum('amount'))['amount__sum'] or 0.00
    total_traded_amount = transactions.filter(type="TD").aggregate(Sum('amount'))['amount__sum'] or 0.00
    total_transfer_amount = transactions.filter(type="TN").aggregate(Sum('amount'))['amount__sum'] or 0.00


    balance = user_wallets.aggregate(Sum('balance'))['balance__sum'] or 0.00

    pending_transactions = transactions.filter(status="P").all()

    # Constructing the response data
    return Response(
        {
            "total_trades": total_trades,
            "total_transactions": total_transactions,
            "total_deposit_amount": total_deposit_amount,
            "total_withdrawal_amount": total_withdrawal_amount,
            "total_traded_amount": total_traded_amount,
            "total_transfer_amount": total_transfer_amount,
            "balance": balance - total_withdrawal_amount,
            "pending_transactions": TransactionSerializer(pending_transactions, many=True).data
        },
        status=status.HTTP_200_OK,
    )

@extend_schema(
    description="Accept KYC file",
    responses={
        200: {"description": "KYC File accepted successfully."},
        404: {"description": "KYC File not found."},
        409: {"description": "KYC File already accepted."}
    }
)
@api_view(['PATCH'])
@permission_classes([IsAdminUser])
def accept_kyc_file(request, file_id):
    try:
        kyc_file = KYCFile.objects.get(id=file_id)
    except KYCFile.DoesNotExist:
        return Response({"detail": "KYC File not found."}, status=status.HTTP_404_NOT_FOUND)
    
    if kyc_file.status == "A":
        return Response({"detail": "KYC File already accepted."}, status=status.HTTP_409_CONFLICT)
    
    kyc_file.status = "A"
    kyc_file.save()
    return Response({"detail": "KYC File accepted successfully."}, status=status.HTTP_200_OK)


@extend_schema(
    description="Reject KYC file",
    responses={
        200: {"description": "KYC File rejected successfully."},
        404: {"description": "KYC File not found."},
        409: {"description": "KYC File already rejected."},
        400: {"description": "KYC File already accepted. Cannot reject."}
    }
)
@api_view(['PATCH'])
@permission_classes([IsAdminUser])
def reject_kyc_file(request, file_id):
    try:
        kyc_file = KYCFile.objects.get(id=file_id)
    except KYCFile.DoesNotExist:
        return Response({"detail": "KYC File not found."}, status=status.HTTP_404_NOT_FOUND)
    
    if kyc_file.status == "R":
        return Response({"detail": "KYC File already rejected."}, status=status.HTTP_409_CONFLICT)
    
    if kyc_file.status == "A":
        return Response({"detail": "KYC File already accepted. Cannot reject."}, status=status.HTTP_400_BAD_REQUEST)
    
    kyc_file.status = "R"
    kyc_file.save()
    return Response({"detail": "KYC File rejected successfully."}, status=status.HTTP_200_OK)


class UserDocumentVerificationStatus(generics.GenericAPIView):
    """
    Update user document verification status.

    status: PENDING, APPROVED, REJECTED, VERIFIED
    """

    serializer_class = UserVerificationStatusSerializer
    permission_classes = [IsAdminUser]

    def get_object(self):
        user_id = self.kwargs.get("user_id")
        return get_user_model().objects.get(id=user_id)

    def patch(self, request, *args, **kwargs):
        user = self.get_object()
        serializer = self.get_serializer(
            data=request.data, context={'view': self})
        if serializer.is_valid():
            user.document_verification = serializer.validated_data.get(
                'status')
            user.save()
            return Response(serializer.data, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class UserFaceVerificationStatus(generics.GenericAPIView):
    """
    Update user face verification status.

    status: PENDING, APPROVED, REJECTED, VERIFIED
    """

    serializer_class = UserVerificationStatusSerializer
    permission_classes = [IsAdminUser]

    def get_object(self):
        user_id = self.kwargs.get("user_id")
        return get_user_model().objects.get(id=user_id)

    def patch(self, request, *args, **kwargs):
        user = self.get_object()
        serializer = self.get_serializer(
            data=request.data, context={'view': self})
        if serializer.is_valid():
            user.face_verification = serializer.validated_data.get('status')
            user.save()
            return Response(serializer.data, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class UserVerificationStatus(generics.GenericAPIView):
    """
    Update user verification status.

    status: PENDING, APPROVED, REJECTED, VERIFIED
    """

    serializer_class = UserVerificationStatusSerializer
    permission_classes = [IsAdminUser]

    def get_object(self):
        user_id = self.kwargs.get("user_id")
        return get_user_model().objects.get(id=user_id)

    def patch(self, request, *args, **kwargs):
        user = self.get_object()
        serializer = self.get_serializer(
            data=request.data, context={'view': self})
        if serializer.is_valid():
            user.verification_status = serializer.validated_data.get('status')
            user.save()
            return Response(serializer.data, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    

class UserSearchPagination(PageNumberPagination):
    page_size = 10


class UserSearchView(generics.ListAPIView):
    permission_classes = [IsAdminUser]
    serializer_class = UserSerializer
    pagination_class = UserSearchPagination

    def get_queryset(self):
        """
        Search for users based on query parameters. If query is empty or not provided, return all users.
        If no results are found, it will return an empty list.
        """
        queryset = User.objects.all()
        query = self.request.query_params.get("query", "").strip()  # Strip any leading/trailing spaces

        if query:
            queryset = queryset.filter(
                Q(email__icontains=query) |
                Q(first_name__icontains=query) |
                Q(last_name__icontains=query) |
                Q(phone_number__icontains=query)
            )

        return queryset

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        if not queryset.exists():  # If no results
            return Response([], status=200)  # Return empty list with a 200 OK status

        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)
    

class UserStatusPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 100


class UserStatusView(generics.ListAPIView):
    permission_classes = [IsAdminUser]
    serializer_class = AdminUserStatusSerializer
    pagination_class = UserStatusPagination

    def get_queryset(self):
        return get_user_model().objects.all()


class UserSet2FAMethodView(generics.GenericAPIView):
    """
    User 2FA method setup.
    
    Any logged-in user can set up their 2FA method preference.

    method: SMS, AUTHENTICATOR_APP
    """

    serializer_class = User2FAMethodSerializer
    permission_classes = [IsAuthenticated]

    def get_object(self):
        return get_user_model().objects.get(id=self.request.user.id)

    def patch(self, request, *args, **kwargs):
        user = self.get_object()
        serializer = self.get_serializer(
            data=request.data, context={'view': self})  # Pass request context properly
        if serializer.is_valid():
            return Response(serializer.data, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['POST'])
def import_users(request):
    file = request.FILES.get('file')
    if not file:
        return Response({"error": "No file provided"}, status=400)

    if file.name.endswith('.csv'):
        df = pd.read_csv(file)
    elif file.name.endswith('.xlsx'):
        df = pd.read_excel(file)
    else:
        return Response({"error": "Unsupported file format. Please upload a CSV or Excel file."}, status=400)

    users = []
    for index, row in df.iterrows():
        user_data = {
            "first_name": row.get('first_name'),
            "last_name": row.get('last_name'),
            "email": row.get('email'),
            "phone_number": row.get('phone_number', ''),
        }
        try:
            user = User.objects.create(**user_data)
            users.append(user)
        except ValidationError as e:
            return Response({"error": f"Error creating user at row {index}: {e}"}, status=400)

    return Response({"message": f"{len(users)} users imported successfully."})


@api_view(['GET'])
def export_users(request):
    filters = {}
    if 'is_active' in request.GET:
        filters['is_active'] = request.GET['is_active'] == 'true'
    if 'role' in request.GET:
        filters['role'] = request.GET['role']
    
    users = User.objects.filter(**filters)

    user_data = [{
        'first_name': user.first_name,
        'last_name': user.last_name,
        'email': user.email,
        'phone_number': user.phone_number,
        'role': user.role,
        'is_active': user.is_active,
    } for user in users]

    df = pd.DataFrame(user_data)

    if 'csv' in request.GET:
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="users.csv"'
        df.to_csv(path_or_buffer=response, index=False)
        return response

    elif 'excel' in request.GET:
        response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        response['Content-Disposition'] = 'attachment; filename="users.xlsx"'
        df.to_excel(path_or_buffer=response, index=False, engine='openpyxl')
        return response

    return Response({"error": "Invalid file type requested. Please specify 'csv' or 'excel'."}, status=400)
