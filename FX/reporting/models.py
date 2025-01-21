from django.db import models
from users.models import User

class Transaction(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    date = models.DateTimeField()
    transaction_type = models.CharField(max_length=50)  # e.g., "Buy", "Sell"
    category = models.CharField(max_length=50, null=True, blank=True)

class Revenue(models.Model):
    date = models.DateTimeField()
    amount = models.DecimalField(max_digits=15, decimal_places=2)

class UserActivity(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    last_active = models.DateTimeField()
    is_active = models.BooleanField(default=False)

class Trade(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    asset = models.CharField(max_length=50)
    trade_volume = models.DecimalField(max_digits=15, decimal_places=2)
    trade_date = models.DateTimeField()

class Report(models.Model):
    category = models.CharField(max_length=50)  # e.g., "Transactions", "User Activity"
    generated_at = models.DateTimeField(auto_now_add=True)
    file_path = models.FileField(upload_to='reports/')
    scheduled_time = models.DateTimeField(null=True, blank=True)
    frequency = models.CharField(max_length=20, choices=(
        ('daily', 'Daily'),
        ('weekly', 'Weekly'),
        ('monthly', 'Monthly')
    ), null=True, blank=True)