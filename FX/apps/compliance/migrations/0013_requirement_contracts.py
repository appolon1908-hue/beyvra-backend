from django.db import migrations, models


TYPES=["IDENTITY_VERIFICATION","ADDRESS_VERIFICATION","SOURCE_OF_FUNDS","TAX_INFORMATION","MANUAL_REVIEW"]
STATUSES=["OPEN","PENDING","COMPLETED","WAIVED","EXPIRED"]


class Migration(migrations.Migration):
    dependencies = [("canonical_compliance", "0012_case_event_types")]
    operations = [
        migrations.AlterField(model_name="compliancerequirement",name="type",field=models.CharField(choices=[(value,value) for value in TYPES],max_length=40)),
        migrations.AlterField(model_name="compliancerequirement",name="status",field=models.CharField(choices=[(value,value) for value in STATUSES],default="OPEN",max_length=20)),
        migrations.AddConstraint(model_name="compliancerequirement",constraint=models.CheckConstraint(condition=models.Q(("type__in",TYPES)),name="valid_compliance_requirement_type")),
        migrations.AddConstraint(model_name="compliancerequirement",constraint=models.CheckConstraint(condition=models.Q(("status__in",STATUSES)),name="valid_compliance_requirement_status")),
    ]
