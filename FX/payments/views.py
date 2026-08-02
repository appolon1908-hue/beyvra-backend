import stripe
from django.conf import settings
from django.db import transaction as db_transaction
from drf_spectacular.utils import extend_schema
from rest_framework import generics, status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView
from wallet.models import Transaction, Wallet
from decimal import Decimal

from .models import PaymentMethod, Payment, PaymentsProvider
from .serializers import BinancePaymentResponseSerializer, PaymentMethodSerializer, PaymentRequestSerializer, PaymentSerializer
from django.shortcuts import get_object_or_404



stripe.api_key = settings.STRIPE_SECRET_KEY


@extend_schema(request=PaymentRequestSerializer)
class StripeCheckoutView(APIView):
    """
    Load balance to user wallet via stripe payment gateway.
    This endpoint will return stripe checkout URL, where user can complete the transaction.
    User's email and Phone must be verified before loading amount to wallet.
    """

    @extend_schema(
        request=PaymentRequestSerializer,
        responses={201: PaymentRequestSerializer, 400: 'Bad Request'},
    )
    def post(self, request):
        serializer = PaymentRequestSerializer(data=request.data)

        if not serializer.is_valid():
            return Response(serializer.errors, status=400)

        wallet_id = serializer.data["wallet_id"]
        amount = serializer.data["amount"]

        # Ensure users's email and mobile number are validated before loading wallet balance
        email_verification_pending = not request.user.email_verified
        phone_verification_pending = not request.user.phone_verified

        if email_verification_pending and phone_verification_pending:
            response = {
                "detail": "Email ID and Phone number verification must be completed before loading balance to wallet."
            }
            return Response(response, status=status.HTTP_404_NOT_FOUND)

        elif email_verification_pending:
            response = {"detail": "Email ID verification must be completed before loading balance to wallet."}
            return Response(response, status=status.HTTP_404_NOT_FOUND)

        elif phone_verification_pending:
            response = {"detail": "Phone number verification must be completed before loading balance to wallet."}
            return Response(response, status=status.HTTP_404_NOT_FOUND)

        # Input Validations:
        try:
            wallet = Wallet.objects.get(id=wallet_id)
        except Wallet.DoesNotExist:
            response = {"detail": f"Wallet with id {wallet_id} doesn't exist"}
            return Response(response, status=status.HTTP_404_NOT_FOUND)

        # Ensure wallet ID belongs to the authenticated user.
        if not wallet.user.id == request.user.id:
            response = {"detail": "You do not have permission to perform this action."}
            return Response(response, status=status.HTTP_403_FORBIDDEN)

        currency = wallet.currency.symbol.lower()

        # TODO:
        # Based on wallet curreny, convert amount to unit amount
        unit_amount = int(amount * 100)

        # Create Transaction in DB
        transaction = Transaction.objects.create(
            wallet=wallet,
            type="D",
            amount=amount,
            status="P",
            reference="",
        )

        try:
            checkout_session = stripe.checkout.Session.create(
                payment_method_types=["card"],
                mode="payment",
                customer_email=request.user.email,
                line_items=[
                    {
                        "price_data": {
                            "currency": currency,
                            "unit_amount": unit_amount,
                            "product_data": {
                                "name": "Load funds to your FX account",
                            },
                        },
                        "quantity": 1,
                    },
                ],
                success_url=settings.FRONTEND_URL + f"/platform?t={transaction.id}&s=success",
                cancel_url=settings.FRONTEND_URL + f"/platform?t={transaction.id}&s=cancel",
            )
            checkout_url = checkout_session.url
            checkout_session_id = checkout_session.id
        except Exception as e:
            return Response({"error": str(e)})

        transaction.reference = checkout_session_id
        transaction.save(update_fields=["reference", "updated_at"])
        return Response({"checkout_url": checkout_url})


class StripeWebhook(APIView):
    """This is webhook for stripe. It will be called by stripe system."""

    permission_classes = []

    def post(self, request):
        # webhook_recieved_time = timezone.now()
        endpoint_secret = settings.STRIPE_ENDPOINT_SECRET
        payload = request.body
        sig_header = request.META.get("HTTP_STRIPE_SIGNATURE")
        event = None

        try:
            event = stripe.Webhook.construct_event(payload, sig_header, endpoint_secret)
        except ValueError:
            # Invalid payload
            # print("Error occured during processing webhook data /n", str(e))
            return Response(status=400)
        except stripe.error.SignatureVerificationError:
            # Invalid signature
            # print("Error occured during processing webhook data /n", str(e))
            return Response(status=400)

        # Handle the checkout.session.completed event
        if event["type"] == "checkout.session.completed":

            session = event["data"]["object"]
            checkout_session_id = session.get("id")

            try:
                with db_transaction.atomic():
                    transaction = Transaction.objects.select_for_update().get(reference=checkout_session_id)
                    # Stripe retries webhooks. Only a pending transaction may
                    # mutate a wallet, making completion idempotent.
                    if transaction.status != "P":
                        return Response(status=status.HTTP_200_OK)
                    wallet = Wallet.objects.select_for_update().get(pk=transaction.wallet_id)
                    if transaction.type == "D":
                        wallet.balance += transaction.amount
                    elif transaction.type == "W":
                        if wallet.balance < transaction.amount:
                            return Response(status=status.HTTP_409_CONFLICT)
                        wallet.balance -= transaction.amount
                    wallet.save(update_fields=["balance", "updated_at"])
                    transaction.status = "S"
                    transaction.save(update_fields=["status", "updated_at"])
            except Transaction.DoesNotExist:
                response = {"detail": "Transation not found"}
                return Response(response, status=status.HTTP_404_NOT_FOUND)
        
        elif event["type"] == "checkout.session.failed":
            
            session = event["data"]["object"]
            checkout_session_id = session.get("id")
            
            try:
                transaction = Transaction.objects.get(
                    reference = checkout_session_id
                )
                transaction.status = "F"
                transaction.save()
            except Transaction.DoesNotExist:
                response = {"detail": "Transation not found"}
                return Response(response, status=status.HTTP_404_NOT_FOUND)

        return Response(status=status.HTTP_200_OK)


class BinancePay(APIView):
    @extend_schema(
        request=BinancePaymentResponseSerializer,
        responses={201: BinancePaymentResponseSerializer, 400: 'Bad Request'},
    )
    def post(self, request):
        serializer = BinancePaymentResponseSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        response_data = serializer.data
        return Response(response_data)


class PaymentMethodList(generics.ListAPIView):
    queryset = PaymentMethod.objects.filter(is_active=True)
    serializer_class = PaymentMethodSerializer
    permission_classes = [AllowAny]
    pagination_class = None


class PaymentView(APIView):
    """ APIs to create, update a Payment """

    def get(self, request):
        # List of all payments
        payments = Payment.objects.filter(user=request.user)
        serializer = PaymentSerializer(payments, many=True)
        return Response({"data": serializer.data}, status=status.HTTP_200_OK)
    
    @extend_schema(
        request=PaymentSerializer,
        responses={201: PaymentSerializer, 400: 'Bad Request'},
    )
    def post(self, request):
        try:
            data = request.data
            serializer = PaymentSerializer(data=data, context={'request': request})
            if not serializer.is_valid():
                return Response({"data": serializer.errors}, status=status.HTTP_400_BAD_REQUEST)
            serializer.save(user=request.user)
            return Response({"data": serializer.data}, status=status.HTTP_201_CREATED)
        except Exception as e:
            return Response({"data": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        

    @extend_schema(
        request=PaymentSerializer,
        responses={201: PaymentSerializer, 400: 'Bad Request'},
    )
    def patch(self, request):
        try:
            payment_id = request.data.get('payment_id', None)
            if not payment_id:
                return Response({"Error": "Please give a payment id"}, status=status.HTTP_400_BAD_REQUEST)
            payment_instance = get_object_or_404(Payment, payment_id=payment_id, user=request.user)
            serializer = PaymentSerializer(
                payment_instance, data=request.data, partial=True, context={'request': request}
            )
            if not serializer.is_valid():
                return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
            serializer.save()
            return Response({"data": serializer.data}, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({"Error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
    

class DepositHistoryView(APIView):
    """
    View deposit history for authenticated users.
    """
    def get(self, request):
        deposits = Payment.objects.filter(user=request.user, type='Deposit').order_by('-payment_date')
        serializer = PaymentSerializer(deposits, many=True)
        return Response({"data": serializer.data}, status=status.HTTP_200_OK)


class WalletBalanceView(APIView):
    """
    View wallet balance for authenticated users.
    """
    def get(self, request):
        wallet = get_object_or_404(Wallet, user=request.user)
        return Response({"balance": wallet.balance, "currency": wallet.currency.symbol}, status=status.HTTP_200_OK)


class WalletTransferView(APIView):
    """
    Transfer funds between wallets.
    """
    def post(self, request):
        source_wallet = get_object_or_404(Wallet, user=request.user, id=request.data.get('source_wallet_id'))
        target_wallet = get_object_or_404(Wallet, user=request.user, id=request.data.get('target_wallet_id'))
        amount = Decimal(request.data.get('amount', 0))

        if source_wallet.balance < amount:
            return Response({"error": "Insufficient balance"}, status=status.HTTP_400_BAD_REQUEST)

        source_wallet.balance -= amount
        target_wallet.balance += amount
        source_wallet.save()
        target_wallet.save()

        return Response({"message": "Funds transferred successfully"}, status=status.HTTP_200_OK)


@extend_schema(request=PaymentRequestSerializer)
class PaymentProcessingView(APIView):
    """
    Process payments using different payment methods.
    """
    @extend_schema(
            request=PaymentRequestSerializer,
            responses={201: PaymentRequestSerializer, 400: 'Bad Request'},
        )
    def post(self, request):
        serializer = PaymentRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        payment_method = get_object_or_404(PaymentMethod, id=data['payment_method_id'], is_active=True)
        wallet = get_object_or_404(Wallet, id=data['wallet_id'], user=request.user)
        amount = data['amount']

        if amount <= 0:
            return Response({"error": "Invalid amount"}, status=status.HTTP_400_BAD_REQUEST)

        if payment_method.type == "credit_card":
            return self.handle_credit_card_payment(wallet, amount, payment_method)
        elif payment_method.type == "bank":
            return self.handle_bank_transfer(wallet, amount, payment_method)
        elif payment_method.type == "crypto":
            return self.handle_crypto_payment(wallet, amount, payment_method)
        elif payment_method.type == "e_wallet":
            return self.handle_e_wallet_payment(wallet, amount, payment_method)
        else:
            return Response({"error": "Unsupported payment method"}, status=status.HTTP_400_BAD_REQUEST)

    def handle_credit_card_payment(self, wallet, amount, payment_method):
        return Response({"message": "Credit card payment processed"}, status=status.HTTP_200_OK)

    def handle_bank_transfer(self, wallet, amount, payment_method):
        return Response({"message": "Bank transfer initiated"}, status=status.HTTP_200_OK)

    def handle_crypto_payment(self, wallet, amount, payment_method):
        return Response({"message": "Crypto payment request generated"}, status=status.HTTP_200_OK)

    def handle_e_wallet_payment(self, wallet, amount, payment_method):
        return Response({"message": "E-Wallet payment processed"}, status=status.HTTP_200_OK)
