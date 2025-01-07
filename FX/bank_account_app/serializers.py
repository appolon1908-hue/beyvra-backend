from rest_framework import serializers
from rest_framework.exceptions import ValidationError
from .models import BankAccount, WithdrawalRequest
from wallet.serializers import CurrencySerializer
from users.serializers import UserSerializer
from wallet.models import Transaction


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
        write_only=True, required=False)

    class Meta:
        model = BankAccount
        # Ensure the user is added automatically in the view
        exclude = ['user']

    def create(self, validated_data):
        withdrawal_request_data = validated_data.pop(
            'withdrawal_request', None)
        user = self.context['request'].user

        # Check if the bank account already exists for the user
        bank_account = BankAccount.objects.filter(
            user=user, account_number=validated_data['account_number']).first()

        if not bank_account:
            bank_account = BankAccount.objects.create(
                user=user, **validated_data)

        # If there is a withdrawal request, handling it here
        if withdrawal_request_data:
            WithdrawalRequest.objects.create(
                bank_account=bank_account,
                user=user,
                **withdrawal_request_data
            )

            # Create a pending transaction
            # transaction = Transaction.objects.create(
            #     user=user,
            #     amount=withdrawal_request_data['amount'],
            #     type="W",
            #     status="P",
            #     wallet=wallet,
            # )
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
