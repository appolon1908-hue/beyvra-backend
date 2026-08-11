import os
import uuid
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urljoin
import requests
from django.conf import settings

class FinancialServiceError(RuntimeError):
    def __init__(self, code, detail, status):
        super().__init__(detail)
        self.code=code; self.detail=detail; self.status=status

class FinancialFeatureDisabled(FinancialServiceError): pass

@dataclass(frozen=True)
class FinancialContext:
    tenant_ref: uuid.UUID
    subject_ref: uuid.UUID
    request_id: str
    correlation_id: uuid.UUID

class FinancialServiceClient:
    def __init__(self, session=None):
        self.base_url=settings.FINANCIAL_SERVICE_URL.rstrip("/")+"/"
        self.cert=(settings.FINANCIAL_SERVICE_CLIENT_CERT,settings.FINANCIAL_SERVICE_CLIENT_KEY)
        self.ca=settings.FINANCIAL_SERVICE_CA_CERT
        self.timeout=(2,5)
        self.session=session or requests.Session()
        if not self.base_url.startswith("https://"):
            raise ValueError("Financial Service requires HTTPS")
        for path in (*self.cert,self.ca):
            resolved=Path(path)
            if not resolved.is_file() or resolved.is_symlink(): raise RuntimeError("Financial Service TLS material is unavailable")

    def _request(self, method, path, context, *, payload=None, idempotency_key=None):
        headers={
          "X-Tenant-Ref":str(context.tenant_ref),"X-Subject-Ref":str(context.subject_ref),
          "X-Request-ID":context.request_id,"X-Correlation-ID":str(context.correlation_id),
          "Accept":"application/json",
        }
        if idempotency_key: headers["Idempotency-Key"]=idempotency_key
        response=self.session.request(method,urljoin(self.base_url,path.lstrip("/")),json=payload,headers=headers,cert=self.cert,verify=self.ca,timeout=self.timeout)
        try: body=response.json()
        except ValueError: body={}
        if response.status_code>=400:
            code=body.get("code","FINANCIAL_SERVICE_ERROR"); detail=body.get("detail","Financial Service request failed.")
            error_class=FinancialFeatureDisabled if code=="FEATURE_DISABLED" else FinancialServiceError
            raise error_class(code,detail,response.status_code)
        return body

    def list_wallets(self,context): return self._request("GET","internal/v1/wallets",context)
    def get_wallet(self,context,wallet_id): return self._request("GET",f"internal/v1/wallets/{uuid.UUID(str(wallet_id))}",context)
    def get_balances(self,context,wallet_id): return self._request("GET",f"internal/v1/wallets/{uuid.UUID(str(wallet_id))}/balances",context)
    def list_deposits(self,context): return self._request("GET","internal/v1/deposits",context)
    def list_withdrawals(self,context): return self._request("GET","internal/v1/withdrawals",context)
    def request_withdrawal(self,context,payload,idempotency_key): return self._request("POST","internal/v1/withdrawals",context,payload=payload,idempotency_key=idempotency_key)
    def request_transfer(self,context,payload,idempotency_key): return self._request("POST","internal/v1/transfers",context,payload=payload,idempotency_key=idempotency_key)
