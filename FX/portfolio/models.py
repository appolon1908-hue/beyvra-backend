from django.db import models
from django.conf import settings
from django.contrib.auth import get_user_model

user = get_user_model()

class AssetType(models.Model):
    name = models.CharField(max_length=255, db_index=True)

    def __str__(self):
        return self.name

class Asset(models.Model):
    user = models.ForeignKey(user, on_delete=models.CASCADE, related_name="assets")
    name = models.CharField(max_length=255, db_index=True)
    number_of_shares = models.IntegerField()
    initial_price = models.FloatField()
    current_price = models.FloatField()
    asset_type = models.ForeignKey(AssetType, on_delete=models.CASCADE, related_name="assets")

    def __str__(self):
        return self.name

class AssetBalance(models.Model):
    asset = models.OneToOneField(Asset, on_delete=models.CASCADE, related_name="balance")
    current_balance = models.FloatField()

    def __str__(self):
        return f"{self.asset.name} Balance"

class AssetProfitLoss(models.Model):
    asset = models.OneToOneField(Asset, on_delete=models.CASCADE, related_name="profit_loss")
    profit_loss = models.FloatField()

    def __str__(self):
        return f"{self.asset.name} Profit/Loss"

    def save(self, *args, **kwargs):
        self.profit_loss = (self.asset.current_price - self.asset.initial_price) * self.asset.number_of_shares
        super().save(*args, **kwargs)