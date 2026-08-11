from django.db import migrations


FORWARD = """
CREATE OR REPLACE FUNCTION valuation_reject_evidence_mutation() RETURNS trigger AS $$
BEGIN RAISE EXCEPTION 'VALUATION_EVIDENCE_APPEND_ONLY'; END;
$$ LANGUAGE plpgsql;
CREATE TRIGGER valuation_price_guard BEFORE UPDATE OR DELETE ON valuation_valuationprice FOR EACH ROW EXECUTE FUNCTION valuation_reject_evidence_mutation();
CREATE TRIGGER valuation_fx_guard BEFORE UPDATE OR DELETE ON valuation_fxvaluationrate FOR EACH ROW EXECUTE FUNCTION valuation_reject_evidence_mutation();
CREATE TRIGGER valuation_realized_guard BEFORE UPDATE OR DELETE ON valuation_realizedpnlevent FOR EACH ROW EXECUTE FUNCTION valuation_reject_evidence_mutation();
CREATE TRIGGER valuation_disposition_guard BEFORE UPDATE OR DELETE ON valuation_taxlotdisposition FOR EACH ROW EXECUTE FUNCTION valuation_reject_evidence_mutation();
CREATE TRIGGER valuation_snapshot_guard BEFORE UPDATE OR DELETE ON valuation_valuationsnapshot FOR EACH ROW EXECUTE FUNCTION valuation_reject_evidence_mutation();
CREATE TRIGGER valuation_nav_guard BEFORE UPDATE OR DELETE ON valuation_portfolionavsnapshot FOR EACH ROW EXECUTE FUNCTION valuation_reject_evidence_mutation();
CREATE TRIGGER valuation_audit_guard BEFORE UPDATE OR DELETE ON valuation_valuationaudit FOR EACH ROW EXECUTE FUNCTION valuation_reject_evidence_mutation();
"""

REVERSE = """
DROP TRIGGER IF EXISTS valuation_price_guard ON valuation_valuationprice;
DROP TRIGGER IF EXISTS valuation_fx_guard ON valuation_fxvaluationrate;
DROP TRIGGER IF EXISTS valuation_realized_guard ON valuation_realizedpnlevent;
DROP TRIGGER IF EXISTS valuation_disposition_guard ON valuation_taxlotdisposition;
DROP TRIGGER IF EXISTS valuation_snapshot_guard ON valuation_valuationsnapshot;
DROP TRIGGER IF EXISTS valuation_nav_guard ON valuation_portfolionavsnapshot;
DROP TRIGGER IF EXISTS valuation_audit_guard ON valuation_valuationaudit;
DROP FUNCTION IF EXISTS valuation_reject_evidence_mutation();
"""


class Migration(migrations.Migration):
    dependencies = [("valuation", "0001_initial")]
    operations = [migrations.RunSQL(FORWARD, REVERSE)]
