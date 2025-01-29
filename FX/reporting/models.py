from django.db import models
from django.contrib.auth import get_user_model

User = get_user_model()

class Transaction(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    date = models.DateTimeField()
    transaction_type = models.CharField(max_length=50)  # e.g., "Buy", "Sell"
    category = models.CharField(max_length=50, null=True, blank=True)

    class Meta:
        indexes = [
                    models.Index(fields=['user']),
                    models.Index(fields=['amount']),
                    models.Index(fields=['date']),
                    models.Index(fields=['transaction_type']),
                    models.Index(fields=['category']),
                ]

class Revenue(models.Model):
    date = models.DateTimeField()
    amount = models.DecimalField(max_digits=15, decimal_places=2)

    class Meta:
        indexes = [
                    models.Index(fields=['date']),
                    models.Index(fields=['amount']),
                ]

class UserActivity(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    last_active = models.DateTimeField()
    is_active = models.BooleanField(default=False)

    class Meta:
        indexes = [
                    models.Index(fields=['user']),
                    models.Index(fields=['is_active']),
                ]

class Trade(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    asset = models.CharField(max_length=50)
    trade_volume = models.DecimalField(max_digits=15, decimal_places=2)
    trade_date = models.DateTimeField()

    class Meta:
        indexes = [
                    models.Index(fields=['user']),
                    models.Index(fields=['asset']),
                    models.Index(fields=['trade_volume']),
                    models.Index(fields=['trade_date']),
                ]

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

class SystemHealth(models.Model):
    status = models.CharField(max_length=20, choices=(('good', 'Good'), ('issue', 'Issue')))
    last_check = models.DateTimeField(auto_now=True)
    details = models.TextField()