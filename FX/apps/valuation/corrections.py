from django.utils import timezone

from .models import ValuationCorrection


class ValuationCorrectionService:
    @staticmethod
    def request(*, correction_type, source_ref, reason_code, created_by, original_snapshot=None):
        return ValuationCorrection.objects.create(original_snapshot=original_snapshot, correction_type=correction_type, source_ref=source_ref, reason_code=reason_code, effective_at=timezone.now(), created_by=str(created_by), status="PENDING")

    @staticmethod
    def approve(correction, *, approved_by):
        if str(approved_by) == correction.created_by:
            raise ValueError("MAKER_CHECKER_REQUIRED")
        correction.approved_by = str(approved_by); correction.status = "APPROVED"; correction.save(update_fields=("approved_by", "status"))
        return correction
