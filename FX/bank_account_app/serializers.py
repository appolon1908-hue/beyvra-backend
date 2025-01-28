from rest_framework import serializers
from rest_framework.exceptions import ValidationError
from .models import BankAccount, WithdrawalRequest
from wallet.serializers import CurrencySerializer
from users.serializers import UserSerializer
from wallet.models import Transaction
from utils.encryption import encrypt_data, decrypt_data


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
    # Nesting WithdrawalRequestSerializer (for incoming withdrawal requests)
    withdrawal_request = WithdrawalRequestCreateWithBank(
        write_only=True, required=False
    )

    # Add fields that should expose decrypted data
    account_number = serializers.SerializerMethodField()
    routing_number = serializers.SerializerMethodField()
    iban = serializers.SerializerMethodField()

    class Meta:
        model = BankAccount
        exclude = ['user', '_encrypted_account_number', '_encrypted_routing_number', '_encrypted_iban']

    # Get decrypted data for sensitive fields
    def get_account_number(self, obj):
        return decrypt_data(obj._encrypted_account_number) if obj._encrypted_account_number else None

    def get_routing_number(self, obj):
        return decrypt_data(obj._encrypted_routing_number) if obj._encrypted_routing_number else None

    def get_iban(self, obj):
        return decrypt_data(obj._encrypted_iban) if obj._encrypted_iban else None

    def create(self, validated_data):
        withdrawal_request_data = validated_data.pop('withdrawal_request', None)
        user = self.context['request'].user

        # Encrypt sensitive fields before saving to the database
        if 'account_number' in validated_data:
            validated_data['_encrypted_account_number'] = encrypt_data(validated_data.pop('account_number'))
        if 'routing_number' in validated_data:
            validated_data['_encrypted_routing_number'] = encrypt_data(validated_data.pop('routing_number'))
        if 'iban' in validated_data:
            validated_data['_encrypted_iban'] = encrypt_data(validated_data.pop('iban'))

        # Check if the bank account already exists for the user
        bank_account = BankAccount.objects.filter(
            user=user, _encrypted_account_number=validated_data['_encrypted_account_number']
        ).first()

        if not bank_account:
            bank_account = BankAccount.objects.create(user=user, **validated_data)

        # If there is a withdrawal request, handle it here
        if withdrawal_request_data:
            WithdrawalRequest.objects.create(
                bank_account=bank_account,
                user=user,
                **withdrawal_request_data
            )

        return bank_account


class WithdrawalRequestSerializer(serializers.ModelSerializer):
    bank_account = BankAccountSerializer(read_only=True)
    currency = CurrencySerializer(read_only=True)
    user = serializers.SerializerMethodField()

    class Meta:
        model = WithdrawalRequest
        fields = '__all__'

    def get_user(self, obj):
        return {
            'id': obj.user.id,
            'first_name': obj.user.first_name,
            'last_name': obj.user.last_name,
            'email': obj.user.email,
            'phone_number': obj.user.phone_number
        }
