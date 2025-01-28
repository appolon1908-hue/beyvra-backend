from django.db import models
from django.contrib.auth import get_user_model
# Create your models here.
User = get_user_model()

class AssetSubscription(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    asset_id = models.CharField(max_length=50)  # e.g., 'bitcoin'
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        unique_together = ['user', 'asset_id']
        
    def __str__(self):
        return f"{self.asset_id}"
    
    
# docker compose exec web python3 manage.py makemigrations