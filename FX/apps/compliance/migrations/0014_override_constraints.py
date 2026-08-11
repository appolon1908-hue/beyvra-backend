from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("canonical_compliance", "0013_requirement_contracts")]
    operations = [
        migrations.AddConstraint(model_name="complianceoverride",constraint=models.CheckConstraint(condition=models.Q(("approved_by__isnull",True),models.Q(("approved_by",models.F("requested_by")),_negated=True),_connector="OR"),name="override_independent_checker")),
        migrations.AddConstraint(model_name="complianceoverride",constraint=models.CheckConstraint(condition=models.Q(models.Q(("approved_at__isnull",True),("approved_by__isnull",True)),models.Q(("approved_at__isnull",False),("approved_by__isnull",False)),_connector="OR"),name="override_approval_complete")),
        migrations.AddConstraint(model_name="complianceoverride",constraint=models.CheckConstraint(condition=models.Q(models.Q(("control","KYC_STATE"),("new_state","APPROVED")),models.Q(("control","AML_STATE"),("new_state","CLEARED")),models.Q(("control","SANCTIONS_STATE"),("new_state","CLEAR")),_connector="OR",_negated=True)|~models.Q(("evidence_ref","")),name="override_clearance_has_evidence")),
    ]
