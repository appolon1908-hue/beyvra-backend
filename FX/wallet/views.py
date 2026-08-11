import json
from django.db import transaction as db_transaction
from drf_spectacular.utils import OpenApiParameter, OpenApiTypes, extend_schema, extend_schema_view
from rest_framework import generics, mixins, status, viewsets
from rest_framework.views import APIView
from rest_framework.decorators import api_view
from rest_framework.permissions import IsAuthenticated, IsAdminUser
from rest_framework.response import Response
from rest_framework.exceptions import ValidationError
from operations.services import assert_sensitive_mutation_allowed, tenant_for
from bank_account_app.models import WithdrawalRequest
from wallet.models import Currency, Transaction, Wallet, ManualBalanceUpdate
from wallet.permissions import IsOwner
from wallet.serializers import (
    CurrencySerializer,
    TransactionSerializer,
    WalletArchivedSerializer,
    WalletCreateSerializer,
    WalletDetailSerializer,
    WalletListSerializer,
    DepositSerializer,
    WithdrawSerializer,
    TransferSerializer,
    ManualBalanceUpdateSerializer,
)
from wallet.services import (
    BitPayService,
    AdyenService,
    PayRetailersService,
    BinanceService
)

from .constants import DEMO_BALANCE
from .pagination import PaginationMeta
from decimal import Decimal
import pycountry
import logging
from django.conf import settings
from notifications.services import emit_notification
from integrations.permissions import organization_for_request

# Set up logger
logger = logging.getLogger(__name__)


def simulation_wallet_mutations_enabled():
    return bool(
        settings.PAPER_TRADING_ONLY
        and settings.SIMULATED_TRADING_ENABLED
        and not settings.REAL_MONEY_ENABLED
    )


def _tenant_wallet_queryset(request, queryset):
    organization = organization_for_request(request)
    queryset.filter(user=request.user, organization__isnull=True).update(organization=organization)
    return queryset.filter(user=request.user, organization=organization)


def enforce_wallet_mutation_authority(user, action):
    try:
        assert_sensitive_mutation_allowed(
            tenant_id=tenant_for(user), account=user, action=action
        )
    except PermissionError as exc:
        raise ValidationError("ACCOUNT_FROZEN") from exc


class CurrencyList(generics.ListAPIView):
    queryset = Currency.objects.all().order_by("name")
    serializer_class = CurrencySerializer


class WalletListCreateView(generics.ListCreateAPIView):
    queryset = Wallet.objects.select_related("currency").filter(
        is_archived=False, is_real=False).order_by("-created_at")
    serializer_class = WalletListSerializer
    permission_classes = [IsAuthenticated, IsOwner]

    def get_serializer(self, *args, **kwargs):
        if self.request.method == "POST":
            self.serializer_class = WalletCreateSerializer
        return super().get_serializer(*args, **kwargs)

    def get_queryset(self):
        """Fiter queryset to authenticated user."""
        queryset = self.queryset
        queryset = _tenant_wallet_queryset(self.request, queryset)
        return queryset


class WalletDetailView(generics.RetrieveUpdateAPIView):
    queryset = Wallet.objects.filter(is_archived=False, is_real=False)
    serializer_class = WalletDetailSerializer
    lookup_field = "pk"
    permission_classes = [IsAuthenticated, IsOwner]

    def get_queryset(self):
        return _tenant_wallet_queryset(self.request, self.queryset)

    def put(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(
            instance, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response({"wallet": serializer.data}, status=status.HTTP_200_OK)
        else:
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class WalletRefillView(generics.RetrieveAPIView):
    queryset = Wallet.objects.filter(is_archived=False, is_real=False)
    serializer_class = WalletDetailSerializer
    lookup_field = "pk"
    permission_classes = [IsAuthenticated, IsOwner]

    def get_queryset(self):
        return _tenant_wallet_queryset(self.request, self.queryset)

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        # check if account is not real and update price to initial
        if not instance.is_real:
            instance.balance = DEMO_BALANCE
            instance.save()
        serializer = self.get_serializer(instance)
        return Response(serializer.data)


class WalletArchiveView(generics.GenericAPIView):
    queryset = Wallet.objects.filter(is_real=False)
    serializer_class = WalletArchivedSerializer
    lookup_field = "pk"
    permission_classes = [IsAuthenticated, IsOwner]

    def get_queryset(self):
        return _tenant_wallet_queryset(self.request, self.queryset)

    def put(self, request, *args, **kwargs):
        instance = self.get_object()
        if instance.user != request.user:
            return Response(
                {"detail": "You do not have permission to archive this wallet."},
                status=status.HTTP_403_FORBIDDEN,
            )
        serializer = self.get_serializer(
            instance, data=request.data, partial=True)
        serializer.context["request"] = request
        if serializer.is_valid():
            serializer.save()
            return Response({"wallet": serializer.data}, status=status.HTTP_200_OK)
        else:
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@extend_schema_view(
    list=extend_schema(
        parameters=[
            OpenApiParameter(
                "date_from",
                OpenApiTypes.DATE,
                description="Date from in 'yyyy-mm-dd' format.",
            ),
            OpenApiParameter(
                "date_to",
                OpenApiTypes.DATE,
                description="Date to in 'yyyy-mm-dd' format.",
            ),
            OpenApiParameter(
                "type",
                OpenApiTypes.STR,
                enum=["D", "W", "TD", "TN"],
                description="DEPOSIT, WITHDRAWAL, TRADE, or TRANSFER",
            ),
            OpenApiParameter(
                "status",
                OpenApiTypes.STR,
                enum=["P", "S", "F", "R"],
                description="PENDING, SUCCESSFUL, FAILED or REFUNDED",
            ),
            OpenApiParameter(
                "currency",
                OpenApiTypes.STR,
                description="Transaction currency. ex: USD",
            ),
            OpenApiParameter(
                "sort_by",
                OpenApiTypes.STR,
                description="Sort by field name",
            ),
            OpenApiParameter(
                "sort_desc",
                OpenApiTypes.STR,
                description="if 'true', records will be sorted in descending order",
            ),
        ]
    )
)
class TransactionViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    queryset = Transaction.objects.all()
    serializer_class = TransactionSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = PaginationMeta

    def get_queryset(self):
        """Fiter queryset to authenticated user."""

        date_from = self.request.query_params.get("date_from")
        date_to = self.request.query_params.get("date_to")
        type = self.request.query_params.get("type")
        status = self.request.query_params.get("status")
        currency = self.request.query_params.get("currency")
        sort_by = self.request.query_params.get("sort_by")
        sort_desc = self.request.query_params.get("sort_desc")
        wallet_id = self.request.query_params.get("wallet_id")

        queryset = self.queryset
        organization = organization_for_request(self.request)
        Wallet.objects.filter(user=self.request.user, organization__isnull=True).update(organization=organization)
        queryset = queryset.filter(
            wallet__user=self.request.user,
            wallet__organization=organization,
            wallet__is_real=False,
        )

        if date_from:
            queryset = queryset.filter(created_at__date__gte=date_from)
        if date_to:
            queryset = queryset.filter(created_at__date__lte=date_to)
        if type:
            queryset = queryset.filter(type=type)
        if status:
            queryset = queryset.filter(status=status)
        if currency:
            queryset = queryset.filter(currency=currency)
        if wallet_id:
            queryset = queryset.filter(wallet=wallet_id)

        if sort_by:
            sort_term = sort_by
            if sort_desc == "true":
                sort_term = f"-{sort_term}"

            queryset = queryset.order_by(sort_term)
        else:
            queryset = queryset.order_by("-created_at")

        return queryset


class DepositToWalletView(APIView):
    """ Deposit to wallet view. """

    permission_classes = [IsAuthenticated]
    serializer_class = DepositSerializer

    def post(self, request, wallet_id):
        enforce_wallet_mutation_authority(request.user, "deposit")
        if not simulation_wallet_mutations_enabled():
            raise ValidationError("Real-money trading is disabled in this environment.")
        # Input Validations:
        try:
            wallet = Wallet.objects.get(id=wallet_id)
        except Wallet.DoesNotExist:
            response = {"detail": f"Wallet with ID {wallet_id} does not exist."}
            return Response(response, status=status.HTTP_404_NOT_FOUND)

        # Ensure wallet ID belongs to the authenticated user.
        if wallet.user.id != request.user.id:
            response = {
                "detail": "You do not have permission to perform this action."}
            return Response(response, status=status.HTTP_403_FORBIDDEN)
        if wallet.is_real:
            return Response({"code": "FEATURE_DISABLED", "detail": "Real balances are Financial Service authoritative."}, status=503)

        # Validate input using the serializer
        serializer = DepositSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        validated_data = serializer.validated_data
        amount = validated_data['amount']
        currency = validated_data['currency']
        gateway = validated_data['gateway']
        payment_method = validated_data.get('payment_method', '')
        paymentMethodTagName = validated_data.get('paymentMethodTagName', '')
        token = validated_data.get('token', '')

        if settings.PAPER_TRADING_ONLY:
            if wallet.is_real:
                emit_notification(
                    user_id=request.user.id, title="Deposit rejected",
                    message="Real-money deposits are disabled in staging.", category="DEPOSIT",
                    payload={"wallet_id": wallet.id, "status": "rejected"},
                )
                return Response(
                    {"detail": "Real-money deposits are disabled in staging."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            with db_transaction.atomic():
                locked_wallet = Wallet.objects.select_for_update().get(pk=wallet.pk)
                simulated = Transaction.objects.create(
                    amount=amount, type="D", status="S", wallet=locked_wallet,
                    gateway="demo", description="Staging demo deposit",
                )
                locked_wallet.balance += amount
                locked_wallet.save(update_fields=["balance", "updated_at"])
            return Response(
                {"detail": "Demo deposit completed.", "transaction_id": simulated.transaction_id},
                status=status.HTTP_200_OK,
            )

        try:
            # Create a pending transaction
            transaction = Transaction.objects.create(
                # user=request.user,
                amount=amount,
                type="D",
                status="P",
                wallet=wallet,
            )

            # Payment Gateway Integration:
            if gateway == "Adyen":
                adyen_service = AdyenService()
                result = adyen_service.deposit_to_wallet(
                    amount, currency, payment_method, transaction.transaction_id)

            elif gateway == "PayRetailers":
                pay_service = PayRetailersService()
                transfer_details = {
                    "paymentMethodTagName": paymentMethodTagName}
                result = pay_service.deposit_to_wallet(
                    amount, currency, transfer_details, transaction.transaction_id)

            elif gateway == "Bitpay":
                bitpay_service = BitPayService()
                result = bitpay_service.deposit_to_wallet(
                    amount, currency, transaction.transaction_id, token)

            elif gateway == "Binance":
                binance_service = BinanceService()
                result = binance_service.get_deposit_address(currency, amount)

            else:
                transaction.status = "F"
                transaction.save(update_fields=["status", "updated_at"])
                return Response({
                    "detail": f"Unsupported payment gateway: {gateway}"},
                    status=status.HTTP_400_BAD_REQUEST)

            if "error" in result:
                logger.error(f"Payment gateway error: {result['error']}")
                transaction.status = "F"
                transaction.save(update_fields=["status", "updated_at"])
                return Response({
                    "detail": result["error"]}, status=status.HTTP_400_BAD_REQUEST)

            # Success
            return Response({
                "detail": "Wallet deposit successful.",
                "result": result
                }, status=status.HTTP_200_OK)

        except Exception as e:
            logger.error("Deposit to wallet failed")
            return Response({
                "detail": "An unexpected error occurred during the deposit process."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class WithdrawFromWalletView(APIView):
    """ Withdraw from wallet view. """

    permission_classes = [IsAuthenticated]
    serializer_class = WithdrawSerializer

    def post(self, request, wallet_id):
        enforce_wallet_mutation_authority(request.user, "withdrawal")
        if not simulation_wallet_mutations_enabled():
            raise ValidationError("Real-money trading is disabled in this environment.")
        # Validate the incoming data using the serializer
        serializer = WithdrawSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        try:
            wallet = Wallet.objects.get(id=wallet_id)
        except Wallet.DoesNotExist:
            return Response({
                "detail": f"Wallet with ID {wallet_id} does not exist."},
                status=status.HTTP_404_NOT_FOUND)

        if wallet.user.id != request.user.id:
            return Response({
                "detail": "You do not have permission to perform this action."},
                status=status.HTTP_403_FORBIDDEN)
        if wallet.is_real:
            return Response({"code": "FEATURE_DISABLED", "detail": "Real balances are Financial Service authoritative."}, status=503)

        if settings.PAPER_TRADING_ONLY:
            if wallet.is_real:
                emit_notification(
                    user_id=request.user.id, title="Withdrawal rejected",
                    message="Real-money withdrawals are disabled in staging.", category="WITHDRAWAL",
                    payload={"wallet_id": wallet.id, "status": "rejected"},
                )
                return Response(
                    {"detail": "Real-money withdrawals are disabled in staging."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            amount = Decimal(str(serializer.validated_data['amount']))
            with db_transaction.atomic():
                locked_wallet = Wallet.objects.select_for_update().get(pk=wallet.pk)
                if locked_wallet.balance < amount:
                    emit_notification(
                        user_id=request.user.id, title="Withdrawal rejected",
                        message="Your withdrawal was rejected because the balance is insufficient.",
                        category="WITHDRAWAL", payload={"wallet_id": wallet.id, "status": "rejected"},
                    )
                    return Response({"detail": "Insufficient balance."}, status=status.HTTP_400_BAD_REQUEST)
                simulated = Transaction.objects.create(
                    amount=amount, type="W", status="S", wallet=locked_wallet,
                    gateway="demo", description="Staging demo withdrawal",
                )
                locked_wallet.balance -= amount
                locked_wallet.save(update_fields=["balance", "updated_at"])
            return Response(
                {"detail": "Demo withdrawal completed.", "transaction_id": simulated.transaction_id},
                status=status.HTTP_200_OK,
            )

        amount = serializer.validated_data['amount']
        gateway = serializer.validated_data['gateway']
        address = serializer.validated_data.get('address')

        # Check for sufficient balance
        if wallet.balance < amount:
            return Response({
                "detail": "Insufficient balance."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            # Create withdrawal request
            withdrawal_request = WithdrawalRequest.objects.create(
                user=request.user,
                wallet=wallet,
                amount=amount,
                status='Pending',
                currency=wallet.currency,
            )
            transaction = Transaction.objects.create(
                reference=withdrawal_request.withdrawal_id,
                wallet=wallet,
                amount=amount,
                type="W",
                status="P"
            )

            # Handle payment gateway integration
            if gateway == "Adyen":
                adyen_service = AdyenService()
                transfer_details = {}
                result = adyen_service.withdraw_from_wallet(
                    amount, wallet.currency, transfer_details, transaction.transaction_id)

            elif gateway == "PayRetailers":
                pay_service = PayRetailersService()
                transfer_details = {}
                result = pay_service.withdraw_from_wallet(
                    transfer_details, transaction.transaction_id)

            elif gateway == "Bitpay":
                if not address:
                    return Response({"detail": "Address is required for Bitpay withdrawals."}, status=status.HTTP_400_BAD_REQUEST)
                bitpay_service = BitPayService()
                result = bitpay_service.withdraw_from_wallet(
                    address, amount, wallet.currency, transaction.transaction_id)

            elif gateway == "Binance":
                if not address:
                    return Response({"detail": "Address is required for Binance withdrawals."}, status=status.HTTP_400_BAD_REQUEST)
                binance_service = BinanceService()
                result = binance_service.withdraw_crypto(
                    wallet.currency, amount, address)

            else:
                transaction.status = "F"
                transaction.save(update_fields=["status", "updated_at"])
                return Response({"detail": f"Unsupported payment gateway: {gateway}"}, status=status.HTTP_400_BAD_REQUEST)

            if "error" in result:
                logger.error(f"Withdrawal error: {result['error']}")
                transaction.status = "F"
                transaction.save(update_fields=["status", "updated_at"])
                return Response({"detail": result["error"]}, status=status.HTTP_400_BAD_REQUEST)

            # Success
            return Response({"detail": "Withdrawal request successfully processed."}, status=status.HTTP_200_OK)

        except Exception as e:
            logger.error("Withdrawal from wallet failed")
            return Response({"detail": "An unexpected error occurred during the withdrawal process."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class TransferFromWalletView(APIView):
    """ Transfer from wallet view. """

    permission_classes = [IsAuthenticated]
    serializer_class = TransferSerializer

    def post(self, request, wallet_id):
        enforce_wallet_mutation_authority(request.user, "transfer")
        if not simulation_wallet_mutations_enabled():
            raise ValidationError("Real-money trading is disabled in this environment.")
        # Validate the incoming data using the serializer
        serializer = TransferSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        recipient_id = serializer.validated_data['recipient_id']
        amount = serializer.validated_data['amount']

        if wallet_id == recipient_id:
            return Response({"detail": "Source and recipient wallets must be different."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            # Lock both rows in a stable order so concurrent transfers cannot
            # spend the same balance. The source wallet must belong to the
            # authenticated user; returning 404 avoids disclosing its owner.
            with db_transaction.atomic():
                wallets = {
                    wallet.id: wallet
                    for wallet in Wallet.objects.select_for_update()
                    .filter(id__in=sorted([wallet_id, recipient_id]), is_active=True, is_archived=False)
                    .order_by("id")
                }
                wallet = wallets.get(wallet_id)
                recipient_wallet = wallets.get(recipient_id)
                if wallet is None or wallet.user_id != request.user.id:
                    return Response({"detail": "Wallet not found."}, status=status.HTTP_404_NOT_FOUND)
                if recipient_wallet is None:
                    return Response({"detail": "Recipient wallet not found."}, status=status.HTTP_404_NOT_FOUND)
                if wallet.is_real or recipient_wallet.is_real:
                    return Response({"code": "FEATURE_DISABLED", "detail": "Real balances are Financial Service authoritative."}, status=503)
                if wallet.balance < amount:
                    return Response({"detail": "Insufficient balance."}, status=status.HTTP_400_BAD_REQUEST)

                recipient_wallet.credit(amount, wallet.currency)
                wallet.debit(amount, wallet.currency)

            # Success response
            return Response({"detail": "Transfer successful."}, status=status.HTTP_200_OK)

        except Exception as e:
            logger.error("Transfer from wallet failed")
            return Response({"detail": "An unexpected error occurred during the transfer process."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(["GET"])
def get_currency(request, country):
    country = pycountry.countries.get(name=country)
    currency = pycountry.currencies.get(numeric=country.numeric)
    response = {'detail': json.dumps(currency)}
    return Response(response, status=status.HTTP_200_OK)


class ManualBalanceUpdateListCreateView(generics.ListCreateAPIView):
    """ 
    List and create view for ManualBalanceUpdate.
    
    Only admin users can access this view.

    Reason for manual balance update:
    - CORRECTION: Correcting a balance that was previously incorrect.
    - FEE: Deducting a fee from a user's wallet.
    - BONUS: Adding a bonus to a user's wallet.
    - OTHER: Any other reason not covered
    """
    
    permission_classes = [IsAdminUser]
    queryset = ManualBalanceUpdate.objects.filter(wallet__is_real=False)
    serializer_class = ManualBalanceUpdateSerializer


class ManualBalanceUpdateDetailView(generics.RetrieveUpdateDestroyAPIView):
    """
    Retrieve, update, and delete view for ManualBalanceUpdate.
    
    Only admin users can access this view.
    """
    
    permission_classes = [IsAdminUser]
    queryset = ManualBalanceUpdate.objects.filter(wallet__is_real=False)
    serializer_class = ManualBalanceUpdateSerializer
