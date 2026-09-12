from django.db import migrations


FORWARD_SQL = """
CREATE FUNCTION beyvra_validate_account_identity() RETURNS trigger AS $$
BEGIN
    IF TG_OP = 'UPDATE' AND ROW(
        NEW.id, NEW.tenant_ref, NEW.subject_ref, NEW.account_ref,
        NEW.execution_mode, NEW.base_currency, NEW.paper_projection_id
    ) IS DISTINCT FROM ROW(
        OLD.id, OLD.tenant_ref, OLD.subject_ref, OLD.account_ref,
        OLD.execution_mode, OLD.base_currency, OLD.paper_projection_id
    ) THEN
        RAISE EXCEPTION 'ACCOUNT_IDENTITY_IMMUTABLE' USING ERRCODE = '23514';
    END IF;
    IF NEW.execution_mode = 'PAPER' AND NOT EXISTS (
        SELECT 1 FROM canonical_trading_simulatedaccount AS projection
        WHERE projection.id = NEW.paper_projection_id
          AND projection.id = NEW.id
          AND projection.tenant_ref = NEW.tenant_ref
          AND projection.subject_ref = NEW.subject_ref
          AND projection.account_ref = NEW.account_ref
          AND projection.quote_currency = NEW.base_currency
    ) THEN
        RAISE EXCEPTION 'ACCOUNT_PROJECTION_MISMATCH' USING ERRCODE = '23514';
    END IF;
    IF TG_OP = 'INSERT' AND NEW.execution_mode = 'LIVE' AND (
        NEW.status <> 'PENDING' OR NEW.trading_enabled
        OR NEW.funding_enabled OR NEW.withdrawals_enabled
    ) THEN
        RAISE EXCEPTION 'LIVE_ACCOUNT_REQUIRES_APPLICATION' USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER beyvra_account_identity_boundary
BEFORE INSERT OR UPDATE ON canonical_trading_tradingaccount
FOR EACH ROW EXECUTE FUNCTION beyvra_validate_account_identity();
"""

REVERSE_SQL = """
DROP TRIGGER beyvra_account_identity_boundary ON canonical_trading_tradingaccount;
DROP FUNCTION beyvra_validate_account_identity();
"""


class Migration(migrations.Migration):
    dependencies = [("canonical_trading", "0010_unified_trading_account")]
    operations = [migrations.RunSQL(FORWARD_SQL, REVERSE_SQL)]
