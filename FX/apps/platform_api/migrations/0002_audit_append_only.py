from django.db import migrations


FORWARD = """
CREATE OR REPLACE FUNCTION platform_api_reject_audit_mutation() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'platform audit events are append-only';
END;
$$ LANGUAGE plpgsql;
DROP TRIGGER IF EXISTS platform_api_audit_append_only ON platform_api_platformauditevent;
CREATE TRIGGER platform_api_audit_append_only
BEFORE UPDATE OR DELETE ON platform_api_platformauditevent
FOR EACH ROW EXECUTE FUNCTION platform_api_reject_audit_mutation();
"""

REVERSE = """
DROP TRIGGER IF EXISTS platform_api_audit_append_only ON platform_api_platformauditevent;
DROP FUNCTION IF EXISTS platform_api_reject_audit_mutation();
"""


class Migration(migrations.Migration):
    dependencies = [("platform_api", "0001_initial")]
    operations = [migrations.RunSQL(FORWARD, REVERSE)]
