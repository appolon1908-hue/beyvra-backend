import Adyen
import requests
import hmac
import hashlib
import time
from urllib.parse import urlencode
import json
from django.conf import settings
from wallet.models import Transaction
from bank_account_app.models import WithdrawalRequest


def update_transaction(status, transaction_id, amount=None, currency=None):
    try:
        transaction = Transaction.objects.get(transaction_id=transaction_id)
        wallet = transaction.wallet
        
        if transaction.type == "W":
            withdrawal_request = WithdrawalRequest.objects.get(withdrawal_id=transaction.reference)
            if status == 200:
                withdrawal_request.status = "Approved"
                withdrawal_request.save()
            else:
                withdrawal_request.status = "Rejected"
                withdrawal_request.save()

        if status == 200:
            transaction.status = "S"
            transaction.save()
            if transaction.type == "D":
                wallet.credit(amount, currency)
            elif transaction.type == "W":
                wallet.debit(amount, currency)
            return True
        else:
            transaction.status = "F"
            transaction.save()
            return {"error": "Payment Failed"}
    except Exception as e:
        return {"error": str(e)}

class AdyenService:

    def __init__(self) -> None:
        self.adyen = Adyen.Adyen()
        self.adyen.client.xapikey = settings.ADYEN_API_KEY
        self.adyen.client.platform = settings.ADYEN_ENVIRONMENT
        self.balanceAccountID = settings.ADYEN_BALANCE_ACCOUNT_ID
        self.merchant_account = settings.ADYEN_MERCHANT_ACCOUNT

    def get_payment_methods(self, amount, currency, country_code=None):
        json_request = {
            "merchantAccount": self.merchant_account,
            "amount": {
                "currency": currency,
                "value": amount
            },
        }
        result = self.adyen.checkout.payments_api.payment_methods(json_request)
        return result
    
    def deposit_to_wallet(self, amount, currency, payment_method, transaction_id):
        try:
            json_request = {
                "merchantAccount": self.merchant_account,
                "amount": {
                    "currency": currency,
                    "value": amount,
                },
                "paymentMethod": payment_method,
                "reference": transaction_id
            }
            result = self.adyen.checkout.payments_api.payments(json_request)
            transaction = Transaction.objects.get(transaction_id=transaction_id)
            if result["resultCode"] == "Authorised":
                result = update_transaction(200, transaction_id, amount, currency)
            else:
                update_transaction(400, transaction_id)
                return {"error": result.message}
        except Exception as e:
            return {"error": str(e)}

    def withdraw_from_wallet(self, amount, currency, transfer_details, transaction_id):
       
        if transfer_details.get("type") == "internal":
            counterparty = {"balanceAccountId": transfer_details.get("balanceAccountId")}
        elif transfer_details.get("type") == "card":
            counterparty = {
                "cardHolder": transfer_details.get("holder"),
                "cardIdentification": transfer_details.get("identification")
            }
        elif transfer_details.get("type") == "bank":
            if transfer_details.get("transferInstrumentId", None) is not None:
                counterparty = {
                    "transferInstrumentId": transfer_details.get("transferInstrumentId")
                }
            else:
                counterparty = {
                    "accountHolder": transfer_details.get("holder"),
                    "accountIdentification": transfer_details.get("identification")
                }
        transfer_request = {
            "amount": {
                "currency": currency,
                "value": amount,  # Amount in minor units (e.g., cents)
            },
            "balanceAccountId": self.balanceAccountID,
            "category": transfer_details.get("type"),
            "counterparty": counterparty,
            "priority": transfer_details.get("priority", "wire"),
            "reference": transaction_id,  # Transaction reference for tracking
        }

        try:
            result = self.adyen.transfers.transfers_api.transfer_funds(transfer_request)
            if result["status"] == "authorised":
                update_transaction(200, transaction_id, amount, currency)
                return
            else:
                update_transaction(400, transaction_id)
                return {"error": result.message}
        except Exception as e:
            return {"error": str(e)}

class PayRetailersService:
    def __init__(self) -> None:
        self.api_key = settings.PayRetailers_API_KEY
        self.sub_key = settings.PayRetailers_OCP_APIM_SUB_KEY
        self.base_url = settings.PayRetailers_BASE_URL

    def get_payment_method(self, currency, channel, country_code):
        headers = {
            "Content-Type": "application/json",
            "Authorization": self.api_key,
            "Ocp-Apim-Subscription-Key": self.sub_key
        }
        response = requests.get(f"{self.base_url}/paymentMethods?Country={country_code}&channel={channel}&currency={currency}", headers=headers)
        return response.json()
    
    def get_transaction_by_uid(self, transaction_id):
        headers = {
            "Content-Type": "application/json",
            "Authorization": self.api_key,
            "Ocp-Apim-Subscription-Key": self.sub_key
        }
        response = requests.get(f"{self.base_url}/transactions/byTracking/{transaction_id}", headers=headers)
        result = response.json()
        if result["status"] == "SUCCESS":
            update_transaction(200, transaction_id, result["amount"], result["currency"])
        return result
    
    def get_payout_details(self, transaction_id):
        headers = {
            "Content-Type": "application/json",
            "Authorization": self.api_key,
            "Ocp-Apim-Subscription-Key": self.sub_key
        }
        response = requests.get(f"{self.base_url}/{transaction_id}", headers=headers)
        result = response.json()
        if result["statusTypeCode"] == "SUCCESS":
            update_transaction(200, transaction_id, result["amount"], result["currency"])
        return result

    def deposit_to_wallet(self, amount, currency, transfer_details, transaction_id):
        headers = {
            "Content-Type": "application/json",
            "Authorization": self.api_key,
            "Ocp-Apim-Subscription-Key": self.sub_key,
        }
        payload = {
            "paymentMethodTagName": transfer_details["paymentMethodTagName"],
            "amount": amount,
            "currency": currency,
            "description": "Wallet Deposit",
            "trackingId": transaction_id,
            "customer": transfer_details.get("customer")
        }
        response = requests.post(f"{self.base_url}/transaction", payload, headers=headers)
        if response.status_code != 200:
            update_transaction(response.status_code, transaction_id)
        return
    
    def withdraw_from_wallet(self, amount, currency, transfer_details, transaction_id):
        headers = {
            "Content-Type": "application/json",
            "Authorization": self.api_key,
            "Ocp-Apim-Subscription-Key": self.sub_key,
        }
        payload = transfer_details
        response = requests.post(f"{self.base_url}/payout", payload, headers=headers)
        if response.status_code != 200:
            update_transaction(response.status_code, transaction_id, amount, currency)
        return
    
class BinanceService:
    def __init__(self):
        self.api_key = settings.BINANCE_API_KEY
        self.api_secret = settings.BINANCE_API_SECRET
        self.base_url = 'https://api.binance.com'

    def _sign_payload(self, data):
        query_string = urlencode(data)
        signature = hmac.new(self.api_secret.encode('utf-8'), query_string.encode('utf-8'), hashlib.sha256).hexdigest()
        return signature

    def withdraw_crypto(self, coin, amount, address, network=None, address_tag=None):
        url = f"{self.base_url}/sapi/v1/capital/withdraw/apply"

        # Prepare the data to be sent
        data = {
            "coin": coin,  # e.g., BTC, ETH, BNB, etc.
            "amount": amount,  # Amount to be withdrawn
            "address": address,  # Wallet address to send funds to
            "timestamp": int(time.time() * 1000),  # Current timestamp in milliseconds
        }

        if network:
            data["network"] = network  # e.g., ETH, BSC, BTC
        if address_tag:
            data["addressTag"] = address_tag  # Optional tag for some coins (like XRP, XLM)

        # Sign the data
        data["signature"] = self._sign_payload(data)

        # Set the headers with the API key
        headers = {
            "X-MBX-APIKEY": self.api_key,
        }

        # Send the request
        response = requests.post(url, headers=headers, data=data)
        return response.json()
    
    def get_deposit_address(self, coin, amount, network=None):
        """
        Retrieve deposit address for the specified coin (e.g., BTC, ETH, BNB).
        Optionally, specify the network (e.g., ETH, BSC).
        """
        url = f"{self.base_url}/sapi/v1/capital/deposit/address"
        
        data = {
            "coin": coin,  # Example: BTC, ETH, BNB
            "amount": amount,
            "timestamp": int(time.time() * 1000),  # Current timestamp in milliseconds
        }

        if network:
            data["network"] = network  # Optional: ETH, BSC, etc.

        # Sign the data
        data["signature"] = self._sign_payload(data)

        # Set the headers with the API key
        headers = {
            "X-MBX-APIKEY": self.api_key,
        }

        # Send the request
        response = requests.get(url, headers=headers, params=data)
        return response.json()
    
class BitPayService:

    def __init__(self) -> None:
        self.api_key = settings.BITPAY_API_KEY
        self.base_url = settings.BITPAY_BASE_URL

    def withdraw_from_wallet(self, destination_address, amount, currency, transaction_id):
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "X-Accept-Version": "2.0.0"
        }
        payload = {
            "amount": amount,
            "currency": currency,
            "ledgerCurrency": currency,
            "reference": transaction_id,
            "wallet": destination_address,
            "notificationURL": "/notifications"
        }

        response = requests.post(f"{self.base_url}/payouts", headers=headers, data=json.dumps(payload))
        result = update_transaction(response.status_code, amount, currency, transaction_id)
        return result

    def deposit_to_wallet(self, amount, currency, transaction_id, token):
        headers = {
            "Content-Type": "application/json",
            "X-Accept-Version": "2.0.0"
        }
        payload = {
            "price": amount,
            "currency": currency,
            "token": self.api_key,
        }

        response = requests.post(f"{self.base_url}/invoice", headers=headers, data=json.dumps(payload))
        result = update_transaction(response.status_code, amount, currency, transaction_id)
        return result