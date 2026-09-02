from rest_framework import serializers
from rest_framework.exceptions import ValidationError
from .models import BankAccount, WithdrawalRequest
from wallet.serializers import CurrencySerializer
from users.serializers import UserSerializer
from wallet.models import Currency, Wallet
from integrations.crypto import encrypt, fingerprint
from django.db.models import Q


class WithdrawalRequestCreateWithBank(serializers.ModelSerializer):
    class Meta:
        model = WithdrawalRequest
        fields = ['amount', 'currency', 'description']

    def validate(self, data):
        """
        Custom validation for WithdrawalRequest model.
        """
        bank_account = data.get('bank_account', None)
        user = self.context['request'].user

        # Validate if the bank account belongs to the user (if provided).
        if bank_account and bank_account.user != user:
            raise ValidationError(
                'The provided bank account does not belong to the user.'
            )

        # Ensure the amount is positive.
        if data['amount'] <= 0:
            raise ValidationError(
                'The withdrawal amount must be greater than zero.')

        return data


class BankAccountSerializer(serializers.ModelSerializer):
    account_number = serializers.CharField(write_only=True, min_length=4, max_length=50, required=True)
    routing_number = serializers.CharField(write_only=True, max_length=50, required=False, allow_blank=True, allow_null=True)
    swift_code = serializers.CharField(write_only=True, max_length=50, required=False, allow_blank=True, allow_null=True)
    iban = serializers.CharField(write_only=True, max_length=50, required=False, allow_blank=True, allow_null=True)

    class Meta:
        model = BankAccount
        # Ensure the user is added automatically in the view
        exclude = [
            'user', 'account_number_ciphertext', 'account_number_nonce',
            'account_number_key_version', 'account_number_fingerprint',
            'account_number_last_four', 'revoked_at',
        ]
        read_only_fields = ('is_active',)

    def to_representation(self, instance):
        data = super().to_representation(instance)
        last_four = instance.account_number_last_four or (instance.account_number or "")[-4:]
        data["account_number"] = f"****{last_four}" if last_four else ""
        for field in ("routing_number", "swift_code", "iban"):
            value = getattr(instance, field, None) or ""
            data[field] = f"****{value[-4:]}" if value else ""
        return data

    def validate(self, attrs):
        if "withdrawal_request" in self.initial_data:
            raise ValidationError({"withdrawal_request": "Use the governed withdrawal workflow."})
        return attrs

    def create(self, validated_data):
        user = self.context['request'].user

        raw_account_number = validated_data.pop('account_number')
        digest = fingerprint(raw_account_number)
        bank_account = BankAccount.objects.filter(user=user).filter(
            Q(account_number_fingerprint=digest) | Q(account_number=raw_account_number)
        ).first()

        if not bank_account:
            ciphertext, nonce, version = encrypt(raw_account_number)
            bank_account = BankAccount.objects.create(
                user=user, account_number=None, account_number_ciphertext=ciphertext,
                account_number_nonce=nonce, account_number_key_version=version,
                account_number_fingerprint=digest, account_number_last_four=raw_account_number[-4:],
                **validated_data)

        return bank_account

    def update(self, instance, validated_data):
        raw_account_number = validated_data.pop('account_number', None)
        if raw_account_number:
            digest = fingerprint(raw_account_number)
            duplicate = BankAccount.objects.filter(user=instance.user).filter(
                Q(account_number_fingerprint=digest) | Q(account_number=raw_account_number)
            ).exclude(pk=instance.pk).exists()
            if duplicate:
                raise ValidationError({'account_number': 'Bank account already exists.'})
            ciphertext, nonce, version = encrypt(raw_account_number)
            instance.account_number = None
            instance.account_number_ciphertext = ciphertext
            instance.account_number_nonce = nonce
            instance.account_number_key_version = version
            instance.account_number_fingerprint = digest
            instance.account_number_last_four = raw_account_number[-4:]
        return super().update(instance, validated_data)


class WithdrawalRequestSerializer(serializers.ModelSerializer):
    bank_account = BankAccountSerializer(read_only=True)
    currency = serializers.PrimaryKeyRelatedField(queryset=Currency.objects.all())
    wallet = serializers.PrimaryKeyRelatedField(queryset=Wallet.objects.all(), required=False, allow_null=True)
    user = serializers.SerializerMethodField()

    class Meta:
        model = WithdrawalRequest
        fields = '__all__'
        read_only_fields = (
            'user', 'status', 'approved_by', 'approval_date', 'denial_date',
            'txid', 'request_date', 'network_fee', 'estimated_completion_time',
        )

    def get_user(self, obj):
        return {
            'id': obj.user.id,
            'first_name': obj.user.first_name,
            'last_name': obj.user.last_name,
            'email': obj.user.email,
            'phone_number': obj.user.phone_number
        }

    def validate(self, attrs):
        request = self.context.get('request')
        if request is None:
            raise ValidationError('Request context is required.')
        wallet = attrs.get('wallet')
        if wallet is not None and wallet.user_id != request.user.id:
            raise ValidationError({'wallet': 'The wallet does not belong to the authenticated user.'})
        amount = attrs.get('amount')
        if amount is not None and amount <= 0:
            raise ValidationError({'amount': 'The withdrawal amount must be greater than zero.'})
        return attrs
