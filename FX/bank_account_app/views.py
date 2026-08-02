from django.shortcuts import render
from django.db.models import Q
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

class BankAccountView(APIView):
    """ APIs to get, create, update and delete a bank account for a user. """

    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        user_id = request.user.id
        # get_object_or_404(User, id=user_id)
        bank_account_instance = BankAccount.objects.filter(user=user_id)
        return Response({"data":BankAccountSerializer(bank_account_instance, many=True).data}, status=status.HTTP_200_OK)

    @extend_schema(
        request=BankAccountSerializer,
        responses={201: BankAccountSerializer, 400: 'Bad Request'},
    )
    def post(self, request):
        try:
            bank_account_serializer = BankAccountSerializer(
                data=request.data, context={'request': request})
            
            if bank_account_serializer.is_valid(raise_exception=True):
                bank_account_serializer.save()
                return Response({"data": bank_account_serializer.data}, status=status.HTTP_201_CREATED)
        except Exception as e:
            return Response({"Error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        
    @extend_schema(
        request=BankAccountSerializer,
        responses={201: BankAccountSerializer, 400: 'Bad Request'},
    )
    def patch(self, request):
        try:
            bank_account = BankAccount.objects.filter(user=request.user, bank_name=request.data['bank_name']).first()
            if not bank_account:
                return Response({"Error": "Bank account not found for the authenticated user in {} bank".format(request.data['bank_name'])}, status=status.HTTP_404_NOT_FOUND)
            serializer = BankAccountSerializer(
                bank_account, data=request.data, context={'request': request}, partial=True)
            if not serializer.is_valid():
                return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
            serializer.save()
            return Response({"data": serializer.data}, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({"Error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request):
        try:
            account_number = request.data.get('account_number')
            bank_name = request.data.get('bank_name')
            if not account_number or not bank_name:
                return Response({"Error": "Missing required fields: account_number and bank_name"}, status=status.HTTP_400_BAD_REQUEST)
            bank_account = BankAccount.objects.filter(
                account_number=account_number, user=request.user, bank_name=bank_name
            ).first()
            if not bank_account:
                return Response({"Error": "Bank account not found."}, status=status.HTTP_404_NOT_FOUND)
            bank_account.delete()
            return Response({"Message": "Bank account deleted successfully"}, status=status.HTTP_200_OK)
        
        except Exception as e:
            return Response({"Error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        

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
            serializer = WithdrawalRequestSerializer(data=data)
            if not serializer.is_valid():
                    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
            serializer.save(user=request.user, bank_account=bank_account)
            return Response({"data": serializer.data}, status=status.HTTP_201_CREATED)
        except Exception as e:
            return Response({"Error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @extend_schema(
        request=WithdrawalRequestSerializer,
        responses={201: WithdrawalRequestSerializer, 400: 'Bad Request'},
    )
    def patch(self, request):
        try:
            withdrawal_id = request.data.get('withdrawal_id', None)
            if not withdrawal_id:
                return Response({"Error": "Please give a withdrawal id"}, status=status.HTTP_400_BAD_REQUEST)
            withdrawal_instance = get_object_or_404(
                WithdrawalRequest, withdrawal_id=withdrawal_id, user=request.user
            )
            serializer = WithdrawalRequestSerializer(withdrawal_instance, data=request.data, partial=True)
            if not serializer.is_valid():
                return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
            serializer.save()
            return Response({"data": serializer.data}, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({"Error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

    
class AdminBankAccountView(APIView):
    """ APIs to get Super Admin bank accounts """
    
    permission_classes = [IsAdminUser]

    def get(self, request):
        bank_account_instance = BankAccount.objects.filter(user__role='Super Admin')
        return Response({"data":BankAccountSerializer(
            bank_account_instance, many=True).data}, status=status.HTTP_200_OK)
