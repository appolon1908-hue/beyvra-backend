from django.db import migrations


class Migration(migrations.Migration):
    """Compatibility node for the staging database's existing migration history.

    Google is disabled in this release; the node is intentionally schema-free.
    """
    dependencies = [("users", "0028_user_dob")]
    operations = []
