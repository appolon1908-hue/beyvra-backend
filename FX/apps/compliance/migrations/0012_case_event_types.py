from django.db import migrations, models


EVENTS=["CASE_CREATED","CASE_ASSIGNED","CASE_NOTE_ADDED","CASE_ESCALATED","CASE_APPROVED","CASE_REJECTED","CASE_CLOSED"]


class Migration(migrations.Migration):
    dependencies = [("canonical_compliance", "0011_restriction_reason_codes")]
    operations = [
        migrations.AlterField(model_name="compliancecaseevent",name="event_type",field=models.CharField(choices=[(value,value) for value in EVENTS],max_length=32)),
        migrations.AddConstraint(model_name="compliancecaseevent",constraint=models.CheckConstraint(condition=models.Q(("event_type__in",EVENTS)),name="valid_compliance_case_event")),
    ]
