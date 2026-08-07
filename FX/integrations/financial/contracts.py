from dataclasses import dataclass


@dataclass(frozen=True)
class FinancialRequestContext:
    tenant_ref: str
    subject_ref: str
    request_id: str
    correlation_id: str
