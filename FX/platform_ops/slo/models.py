import uuid
from django.db import models


class SliDefinition(models.Model):
    id=models.UUIDField(primary_key=True,default=uuid.uuid4,editable=False)
    code=models.CharField(max_length=100,unique=True); service_code=models.CharField(max_length=80)
    metric_type=models.CharField(max_length=32); query_definition=models.TextField()
    aggregation=models.CharField(max_length=24); window=models.DurationField(); status=models.CharField(max_length=24,default="ACTIVE"); version=models.CharField(max_length=32)


class SloDefinition(models.Model):
    id=models.UUIDField(primary_key=True,default=uuid.uuid4,editable=False)
    code=models.CharField(max_length=100,unique=True); sli=models.ForeignKey(SliDefinition,on_delete=models.PROTECT,related_name="slos")
    target=models.DecimalField(max_digits=12,decimal_places=6); comparison=models.CharField(max_length=8); window=models.DurationField()
    error_budget_policy=models.JSONField(default=dict); status=models.CharField(max_length=24,default="ACTIVE"); version=models.CharField(max_length=32)
    effective_from=models.DateTimeField(); effective_to=models.DateTimeField(null=True,blank=True)


class SliObservation(models.Model):
    sli=models.ForeignKey(SliDefinition,on_delete=models.CASCADE,related_name="observations")
    good_events=models.PositiveBigIntegerField(); bad_events=models.PositiveBigIntegerField(); observed_at=models.DateTimeField()
