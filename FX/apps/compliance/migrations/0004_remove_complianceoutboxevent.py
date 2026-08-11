from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [("canonical_compliance", "0003_append_only_evidence")]
    operations = [migrations.DeleteModel(name="ComplianceOutboxEvent")]
