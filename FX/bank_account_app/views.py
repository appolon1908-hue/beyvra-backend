from django.shortcuts import render
from django.db.models import Q
from django.db import transaction
from .models import BankAccount, WithdrawalRequest
from .serializers import BankAccountSerializer, WithdrawalRequestSerializer
from rest_framework.views import APIView
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework.permissions import IsAdminUser, IsAuthenticated
from rest_framework.decorators import api_view, permission_classes
from rest_framework import status
from django.shortcuts import get_object_or_404
from users.models import User
from drf_spectacular.utils import extend_schema
from rest_framework.exceptions import ValidationError
from .commands import COMMAND_PARAMETERS, VERSIONED_COMMAND_PARAMETERS, begin_command, command_context, complete_command

from operations.services import assert_sensitive_mutation_allowed, tenant_for


def deny_withdrawal_mutation(user):
    try:
        assert_sensitive_mutation_allowed(
            tenant_id=tenant_for(user), account=user, action="withdrawal"
        )
    except PermissionError as exc:
        raise ValidationError("ACCOUNT_FROZEN") from exc
    raise ValidationError("Real-money trading is disabled in this environment.")

class BankAccountView(APIView):
    """ APIs to get, create, update and delete a bank account for a user. """

    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        user_id = request.user.id
        # get_object_or_404(User, id=user_id)
        bank_account_instance = BankAccount.objects.filter(user=user_id, is_active=True)
        return Response({"data":BankAccountSerializer(bank_account_instance, many=True).data}, status=status.HTTP_200_OK)

    @extend_schema(
        request=BankAccountSerializer,
        responses={201: BankAccountSerializer, 400: 'Bad Request'},
        parameters=COMMAND_PARAMETERS,
    )
    @transaction.atomic
    def post(self, request):
        try:
            bank_account_serializer = BankAccountSerializer(
                data=request.data, context={'request': request})
            bank_account_serializer.is_valid(raise_exception=True)
            command, error = command_context(request)
            if error: return error
            key, _, correlation_id, _ = command
            organization, record, replay = begin_command(request, key=key, payload=bank_account_serializer.validated_data)
            if replay: return replay
            bank_account_serializer.save()
            body = complete_command(record, request=request, organization=organization, correlation_id=correlation_id, action="bank_account.create", status=201, body={"data": bank_account_serializer.data}, resource_id=bank_account_serializer.instance.pk)
            return Response(body, status=status.HTTP_201_CREATED)
        except Exception as e:
            raise ValidationError("Bank account request failed") from e
        
    @extend_schema(
        request=BankAccountSerializer,
        responses={201: BankAccountSerializer, 400: 'Bad Request'},
        parameters=VERSIONED_COMMAND_PARAMETERS,
    )
    @transaction.atomic
    def patch(self, request):
        try:
            command, error = command_context(request, require_version=True)
            if error: return error
            key, _, correlation_id, expected_version = command
            bank_account = BankAccount.objects.select_for_update().filter(user=request.user, pk=request.data.get('bank_account_id'), is_active=True).first()
            if not bank_account:
                return Response({"Error": "Bank account not found."}, status=status.HTTP_404_NOT_FOUND)
            serializer = BankAccountSerializer(
                bank_account, data=request.data, context={'request': request}, partial=True)
            serializer.is_valid(raise_exception=True)
            organization, record, replay = begin_command(request, key=key, payload={"bank_account_id": bank_account.pk, "expected_version": expected_version, **serializer.validated_data})
            if replay: return replay
            if expected_version != bank_account.updated_at.isoformat().replace("+00:00", "Z"):
                record.delete(); return Response({"detail": "VERSION_CONFLICT"}, status=409)
            serializer.save()
            body = complete_command(record, request=request, organization=organization, correlation_id=correlation_id, action="bank_account.update", status=200, body={"data": serializer.data}, resource_id=bank_account.pk)
            return Response(body, status=status.HTTP_200_OK)
        except Exception as e:
            raise ValidationError("Bank account request failed") from e

    @extend_schema(parameters=VERSIONED_COMMAND_PARAMETERS)
    @transaction.atomic
    def delete(self, request):
        try:
            command, error = command_context(request, require_version=True)
            if error: return error
            key, _, correlation_id, expected_version = command
            bank_account = BankAccount.objects.select_for_update().filter(
                pk=request.data.get('bank_account_id'), user=request.user, is_active=True,
            ).first()
            if not bank_account:
                return Response({"Error": "Bank account not found."}, status=status.HTTP_404_NOT_FOUND)
            organization, record, replay = begin_command(request, key=key, payload={"bank_account_id": bank_account.pk, "action": "retire", "expected_version": expected_version})
            if replay: return replay
            if expected_version != bank_account.updated_at.isoformat().replace("+00:00", "Z"):
                record.delete(); return Response({"detail": "VERSION_CONFLICT"}, status=409)
            bank_account.retire()
            body = complete_command(record, request=request, organization=organization, correlation_id=correlation_id, action="bank_account.retire", status=200, body={"bank_account_id": bank_account.pk, "status": "retired"}, resource_id=bank_account.pk)
            return Response(body, status=status.HTTP_200_OK)
        
        except Exception as e:
            raise ValidationError("Bank account request failed") from e
        

class WithdrawalRequestView(APIView):
    """ APIs to get, create, update a withdrawal request """
    
    permission_classes = [IsAuthenticated]

    def get(self, request):
        withdrawal_id = request.GET.get('withdrawal_id', None)
        if withdrawal_id:
            withdrawal_request_instance = get_object_or_404(
                WithdrawalRequest, withdrawal_id=withdrawal_id, user=request.user
            )
            return Response({"data": WithdrawalRequestSerializer(withdrawal_request_instance).data}, status=status.HTTP_200_OK)
        else:
            queryset = WithdrawalRequest.objects.filter(user=request.user)
            # Add pagination
            paginator = PageNumberPagination()
            paginated_queryset = paginator.paginate_queryset(queryset, request)
            
            serializer = WithdrawalRequestSerializer(paginated_queryset, many=True)
            
            # Return paginated response
            return paginator.get_paginated_response(serializer.data)
            return Response({"data": WithdrawalRequestSerializer(withdrawal_request_instance, many=True).data}, status=status.HTTP_200_OK)

    @extend_schema(
        request=WithdrawalRequestSerializer,
        responses={201: WithdrawalRequestSerializer, 400: 'Bad Request'},
    )
    def post(self, request):
        deny_withdrawal_mutation(request.user)
        try:
            bank_account = BankAccount.objects.filter(
                bank_name=request.data['bank_name'],
                account_number=request.data['account_number'],
                user=request.user,
            ).first()
            data = request.data.copy()
            if not bank_account:
                return Response({"Error": "Bank account not found for account number {} in {} bank".format(request.data['account_number'], request.data['bank_name'])}, status=status.HTTP_404_NOT_FOUND)
            data['bank_account'] = bank_account.id
            serializer = WithdrawalRequestSerializer(data=data, context={'request': request})
            if not serializer.is_valid():
                    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
            serializer.save(user=request.user, bank_account=bank_account)
            return Response({"data": serializer.data}, status=status.HTTP_201_CREATED)
        except Exception as e:
            raise ValidationError("Withdrawal request failed") from e

    @extend_schema(
        request=WithdrawalRequestSerializer,
        responses={201: WithdrawalRequestSerializer, 400: 'Bad Request'},
    )
    def patch(self, request):
        deny_withdrawal_mutation(request.user)
        try:
            withdrawal_id = request.data.get('withdrawal_id', None)
            if not withdrawal_id:
                return Response({"Error": "Please give a withdrawal id"}, status=status.HTTP_400_BAD_REQUEST)
            withdrawal_instance = get_object_or_404(
                WithdrawalRequest, withdrawal_id=withdrawal_id, user=request.user
            )
            serializer = WithdrawalRequestSerializer(
                withdrawal_instance, data=request.data, partial=True, context={'request': request}
            )
            if not serializer.is_valid():
                return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
            serializer.save()
            return Response({"data": serializer.data}, status=status.HTTP_200_OK)
        except Exception as e:
            raise ValidationError("Withdrawal request failed") from e

    
class AdminBankAccountView(APIView):
    """ APIs to get Super Admin bank accounts """
    
    permission_classes = [IsAdminUser]

    def get(self, request):
        bank_account_instance = BankAccount.objects.filter(user__role='Super Admin', is_active=True)
        return Response({"data":BankAccountSerializer(
            bank_account_instance, many=True).data}, status=status.HTTP_200_OK)
