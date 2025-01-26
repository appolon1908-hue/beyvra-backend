from django.db import models
from trade.models import Asset
from users.models import User
# Create your models here.

class PriceAlert(models.Model):
    
    ALERT_TYPES = [
        ('above', 'Above Threshold'),
        ('below', 'Below Threshold')
    ]
    
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    asset = models.ForeignKey(Asset, on_delete=models.CASCADE)
    threshold = models.DecimalField(max_digits=20, decimal_places=10)
    alert_type = models.CharField(max_length=10, choices=ALERT_TYPES)
    
    
    def __str__(self):
        return self.user.asset
    