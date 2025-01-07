# users/resources.py
import re
from import_export import resources, fields
from django.utils.crypto import get_random_string
from users.models import User
from wallet.models import Wallet, Currency
from users.tasks import async_send_welcome_email
from users.signals import update_user_upon_creation
from django.db.models.signals import post_save


class UserResource(resources.ModelResource):
    temp_password = fields.Field(attribute='temp_password', readonly=True)

    class Meta:
        model = User
        fields = ('id', 'first_name', 'last_name', 'email',
                  'phone_number', 'country_name', 'brand')

    def before_import_row(self, row, **kwargs):
        # Validations before importing the row
        NAME_REGEX = re.compile(r"^[a-zA-Z]+$")
        EMAIL_REGEX = re.compile(r"[^@]+@[^@]+\.[^@]+")
        PHONE_REGEX = re.compile(r"^\+\d{1,3}\d+$")

        fname = row.get("first_name", "")
        lname = row.get("last_name", "")
        email = row.get("email", "")
        phone = row.get("phone_number", "")

        if not email or not fname or not lname or not phone:
            raise Exception(
                f"Email, first name, last name, and phone are required fields.")

        if User.objects.filter(email=email).exists():
            raise Exception(f"User with email {email} already exists.")

        if User.objects.filter(phone_number=phone).exists():
            raise Exception(f"User with phone {phone} already exists.")

        if not NAME_REGEX.match(fname) or not NAME_REGEX.match(lname):
            raise Exception(
                f"First name and last name should only contain alphabets.")

        if not PHONE_REGEX.match(phone):
            raise Exception(f"Invalid phone number.")

        if not EMAIL_REGEX.match(email):
            raise Exception(f"Invalid email.")

    def after_import_instance(self, instance, new, **kwargs):
        # Set random password for the imported user and create a wallet
        temp_password = get_random_string(8)
        instance.set_password(temp_password)
        instance.is_walkthrough = True
        instance.verification_status = "CHANGE_PASSWORD"
        # Assign temporary password for email notification
        instance.temp_password = temp_password

    def after_save_instance(self, instance, using_transactions, dry_run):
        # Create wallet and send the email after the user is saved
        demo_currency = Currency.objects.filter(name="Đ").first()
        Wallet.objects.create(
            name="Demo Wallet",
            currency=demo_currency,
            user=instance,
            balance=1000,  # Demo balance
            is_real=False
        )
        if not dry_run:
            # Send welcome email with the temporary password
            async_send_welcome_email.delay(
                instance.email, instance.first_name, instance.temp_password)
            
            # Reconnect the post_save signal
            post_save.connect(update_user_upon_creation, sender=User,
                          dispatch_uid="update_user_upon_creation")
                
