from dataclasses import dataclass
from enum import StrEnum


class KycStatus(StrEnum):
    NOT_STARTED = "NOT_STARTED"
    PENDING = "PENDING"
    REVIEW = "REVIEW"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"


class ScreeningStatus(StrEnum):
    NOT_STARTED = "NOT_STARTED"
    PENDING = "PENDING"
    REVIEW = "REVIEW"
    CLEARED = "CLEARED"
    BLOCKED = "BLOCKED"


@dataclass(frozen=True)
class ComplianceEligibility:
    kyc_status: KycStatus
    aml_status: ScreeningStatus
    sanctions_status: ScreeningStatus
    trading_eligible: bool
    deposit_eligible: bool
    withdrawal_eligible: bool

    def permits_trading(self):
        return (
            self.kyc_status == KycStatus.APPROVED
            and self.aml_status == ScreeningStatus.CLEARED
            and self.sanctions_status == ScreeningStatus.CLEARED
            and self.trading_eligible
        )
