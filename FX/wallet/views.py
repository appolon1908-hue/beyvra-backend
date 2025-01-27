import json
from drf_spectacular.utils import OpenApiParameter, OpenApiTypes, extend_schema, extend_schema_view
from rest_framework import generics, mixins, status, viewsets
from rest_framework.views import APIView
from rest_framework.decorators import api_view
from rest_framework.permissions import IsAuthenticated, IsAdminUser
from rest_framework.response import Response
from bank_account_app.models import WithdrawalRequest
from wallet.models import Currency, Transaction, Wallet, ManualBalanceUpdate, LinkedAccount
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
    WithdrawFundsSerializer,
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

# Set up logger
logger = logging.getLogger(__name__)


class CurrencyList(generics.ListAPIView):
    queryset = Currency.objects.all().order_by("name")
    serializer_class = CurrencySerializer


class WalletListCreateView(generics.ListCreateAPIView):
    queryset = Wallet.objects.select_related("currency").filter(
        is_archived=False).order_by("-created_at")
    serializer_class = WalletListSerializer
    permission_classes = [IsAuthenticated, IsOwner]

    def get_serializer(self, *args, **kwargs):
        if self.request.method == "POST":
            self.serializer_class = WalletCreateSerializer
        return super().get_serializer(*args, **kwargs)

    def get_queryset(self):
        """Fiter queryset to authenticated user."""
        queryset = self.queryset
        queryset = queryset.filter(user=self.request.user)
        return queryset


class WalletDetailView(generics.RetrieveUpdateAPIView):
    queryset = Wallet.objects.filter(is_archived=False)
    serializer_class = WalletDetailSerializer
    lookup_field = "pk"
    permission_classes = [IsAuthenticated, IsOwner]

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
    queryset = Wallet.objects.filter(is_archived=False)
    serializer_class = WalletDetailSerializer
    lookup_field = "pk"
    permission_classes = [IsAuthenticated, IsOwner]

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        # check if account is not real and update price to initial
        if not instance.is_real:
            instance.balance = DEMO_BALANCE
            instance.save()
        serializer = self.get_serializer(instance)
        return Response(serializer.data)


class WalletArchiveView(generics.GenericAPIView):
    queryset = Wallet.objects.all()
    serializer_class = WalletArchivedSerializer
    lookup_field = "pk"
    permission_classes = [IsAuthenticated, IsOwner]

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
        queryset = queryset.filter(wallet__user=self.request.user)

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
                return Response({
                    "detail": f"Unsupported payment gateway: {gateway}"},
                    status=status.HTTP_400_BAD_REQUEST)

            if "error" in result:
                logger.error(f"Payment gateway error: {result['error']}")
                return Response({
                    "detail": result["error"]}, status=status.HTTP_400_BAD_REQUEST)

            # Success
            return Response({
                "detail": "Wallet deposit successful.",
                "result": result
                }, status=status.HTTP_200_OK)

        except Exception as e:
            logger.error(f"Deposit to wallet failed: {str(e)}", exc_info=True)
            return Response({
                "detail": "An unexpected error occurred during the deposit process."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class WithdrawFromWalletView(APIView):
    """ Withdraw from wallet view. """

    permission_classes = [IsAuthenticated]
    serializer_class = WithdrawSerializer

    def post(self, request, wallet_id):
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
                user=request.user,
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
                return Response({"detail": f"Unsupported payment gateway: {gateway}"}, status=status.HTTP_400_BAD_REQUEST)

            if "error" in result:
                logger.error(f"Withdrawal error: {result['error']}")
                return Response({"detail": result["error"]}, status=status.HTTP_400_BAD_REQUEST)

            # Success
            return Response({"detail": "Withdrawal request successfully processed."}, status=status.HTTP_200_OK)

        except Exception as e:
            logger.error(f"Withdrawal from wallet failed: {str(e)}", exc_info=True)
            return Response({"detail": "An unexpected error occurred during the withdrawal process."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class TransferFromWalletView(APIView):
    """ Transfer from wallet view. """

    permission_classes = [IsAuthenticated]
    serializer_class = TransferSerializer

    def post(self, request, wallet_id):
        # Validate the incoming data using the serializer
        serializer = TransferSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        try:
            wallet = Wallet.objects.get(id=wallet_id)
        except Wallet.DoesNotExist:
            return Response({"detail": f"Wallet with ID {wallet_id} does not exist."}, status=status.HTTP_404_NOT_FOUND)

        recipient_id = serializer.validated_data['recipient_id']
        try:
            recipient_wallet = Wallet.objects.get(id=recipient_id)
        except Wallet.DoesNotExist:
            return Response({"detail": f"Recipient wallet with ID {recipient_id} does not exist."}, status=status.HTTP_404_NOT_FOUND)

        amount = serializer.validated_data['amount']

        if wallet.balance < amount:
            return Response({"detail": "Insufficient balance."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            # Perform the transfer operation
            recipient_wallet.credit(amount, wallet.currency)
            wallet.debit(amount)

            # Success response
            return Response({"detail": "Transfer successful."}, status=status.HTTP_200_OK)

        except Exception as e:
            logger.error(f"Transfer from wallet failed: {str(e)}", exc_info=True)
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
    queryset = ManualBalanceUpdate.objects.all()
    serializer_class = ManualBalanceUpdateSerializer


class ManualBalanceUpdateDetailView(generics.RetrieveUpdateDestroyAPIView):
    """
    Retrieve, update, and delete view for ManualBalanceUpdate.
    
    Only admin users can access this view.
    """
    
    permission_classes = [IsAdminUser]
    queryset = ManualBalanceUpdate.objects.all()
    serializer_class = ManualBalanceUpdateSerializer


class WithdrawFundsView(APIView):
    def post(self, request):
        serializer = WithdrawFundsSerializer(data=request.data)
        if serializer.is_valid():
            user = request.user
            account_id = serializer.validated_data['account_id']
            amount = serializer.validated_data['amount']

            try:
                linked_account = LinkedAccount.objects.get(id=account_id, user=user, is_verified=True)
            except LinkedAccount.DoesNotExist:
                return Response({"error": "Invalid or unverified account."}, status=status.HTTP_404_NOT_FOUND)

            try:
                wallet = Wallet.objects.get(user=user, is_active=True, is_real=True)
            except Wallet.DoesNotExist:
                return Response({"error": "Active wallet not found."}, status=status.HTTP_404_NOT_FOUND)

            if wallet.balance < amount:
                return Response({"error": "Insufficient balance."}, status=status.HTTP_400_BAD_REQUEST)

            try:
                wallet.debit(amount, wallet.currency)
            except ValueError as e:
                return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

            return Response(
                {
                    "message": "Withdrawal successful.",
                    "withdrawn_amount": amount,
                    "remaining_balance": wallet.balance,
                },
                status=status.HTTP_200_OK,
            )

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
