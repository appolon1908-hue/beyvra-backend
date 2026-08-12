
from decimal import Decimal
from django.conf import settings
from rest_framework import serializers
from wallet.models import Currency, Transaction, Wallet, ManualBalanceUpdate
from users.serializers import UserSerializer

WALLET_BASE_READ_ONLY = [
    "user",
    "balance",
    "is_active",
    "created_at",
    "updated_at",
    "is_real",
]


class CurrencySerializer(serializers.ModelSerializer):
    class Meta:
        model = Currency
        exclude = (
            "created_at",
            "updated_at",
        )


class WalletListSerializer(serializers.ModelSerializer):
    # account_type__image = serializers.ImageField(source="account_type.image", read_only=True)
    # account_type__symbol = serializers.CharField(source="account_type.symbol", read_only=True)
    # account_type__name = serializers.CharField(source="account_type.name", read_only=True)
    currency = CurrencySerializer()

    class Meta:
        model = Wallet
        exclude = ("organization",)
        read_only_fields = [*WALLET_BASE_READ_ONLY]

    def create(self, validated_data):
        request = self.context.get("request")
        validated_data["user"] = request.user
        if settings.PAPER_TRADING_ONLY:
            validated_data["is_real"] = False
        return super().create(validated_data)


class WalletCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Wallet
        fields = "__all__"
        read_only_fields = [*WALLET_BASE_READ_ONLY]

    def create(self, validated_data):
        request = self.context.get("request")
        validated_data["user"] = request.user
        if settings.PAPER_TRADING_ONLY:
            validated_data["is_real"] = False
        return super().create(validated_data)


class WalletDetailSerializer(serializers.ModelSerializer):

    user = UserSerializer(read_only=True)
    class Meta:
        model = Wallet
        fields = "__all__"
        read_only_fields = [*WALLET_BASE_READ_ONLY, "currency"]

    def validate_name(self, value):
        if Wallet.objects.filter(name=value, id=self.instance.id).exists():
            raise serializers.ValidationError([{"name": "This name is already taken."}])
        return value


class WalletArchivedSerializer(serializers.ModelSerializer):
    class Meta:
        model = Wallet
        fields = "__all__"

    def validate_is_archived(self, value):
        instance = self.instance
        request = self.context.get("request")
        if not request:
            raise serializers.ValidationError("Request context is required.")

        if value and instance.is_archived:
            raise serializers.ValidationError("Wallet already archived.")

        if value and instance.balance > 0 and instance.available_balance > 0:
            raise serializers.ValidationError("Cannot archive wallet with money in the account.")

        live_accounts = Wallet.objects.filter(user=request.user, is_archived=False).count()
        if value and live_accounts <= 1:
            raise serializers.ValidationError("You must have more than one live account to archive this wallet.")

        transaction = Transaction.objects.filter(id=instance.id).exists()
        if value and transaction:
            raise serializers.ValidationError("You must have no transactions for this account.")

        return value

class TransactionSerializer(serializers.ModelSerializer):
    wallet = WalletDetailSerializer()
    # status = serializers.SerializerMethodField()
    type = serializers.CharField(source="get_type_display")
    status = serializers.CharField(source="get_status_display")

    class Meta:
        model = Transaction
        fields = "__all__"
        read_only_fields = (
            "wallet",
            "type",
            "amount",
            "currency",
            "status",
            "gateway_ref",
            "created_at",
            "updated_at",
            "wallet",
        )



MIN_REQUIRED_DEPOSIT = Decimal('1.00')
class DepositSerializer(serializers.Serializer):

    amount = serializers.DecimalField(max_digits=10, decimal_places=2)
    currency = serializers.CharField(max_length=3, default="USD")
    gateway = serializers.CharField(max_length=50)
    payment_method = serializers.CharField(required=False, allow_blank=True)
    paymentMethodTagName = serializers.CharField(required=False, allow_blank=True)
    token = serializers.CharField(required=False, allow_blank=True)

    def validate_amount(self, value):
        if value <= 0:
            raise serializers.ValidationError("Deposit amount must be greater than zero.")
        if value < MIN_REQUIRED_DEPOSIT:
            raise serializers.ValidationError(f"Deposit amount must be greater than the minimum required: {MIN_REQUIRED_DEPOSIT}.")
        return value


class WithdrawSerializer(serializers.Serializer):
    amount = serializers.FloatField()
    gateway = serializers.CharField()
    address = serializers.CharField(required=False)  # For crypto withdrawal


class TransferSerializer(serializers.Serializer):
    recipient_id = serializers.IntegerField()
    amount = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal("0.01"))


class ManualBalanceUpdateSerializer(serializers.ModelSerializer):
    # admin is current request user
    admin = serializers.HiddenField(default=serializers.CurrentUserDefault())

    class Meta:
        model = ManualBalanceUpdate
        fields = ['id', 'admin', 'wallet', 'previous_balance',
                  'new_balance', 'reason', 'description', 'created_at']
        read_only_fields = ['created_at', 'previous_balance', 'admin']

    def validate_wallet(self, value):
        if not Wallet.objects.filter(id=value.id).exists():
            raise serializers.ValidationError("Invalid wallet ID.")
        if value.is_real:
            raise serializers.ValidationError("FEATURE_DISABLED: real balances are Financial Service authoritative")
        return value

    def validate_new_balance(self, value):
        wallet = self.initial_data['wallet']
        if self.initial_data['reason'] == 'FEE' and value > wallet.balance:
            raise serializers.ValidationError("Fee deduction should reduce the balance.")
        if value < 0:
            raise serializers.ValidationError("Balance cannot be negative.")
        return value

    def create(self, validated_data):
        # Automatically set the previous_balance from the wallet's current balance
        wallet = validated_data['wallet']
        validated_data['previous_balance'] = wallet.balance
        return super().create(validated_data)
