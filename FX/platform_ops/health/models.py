import uuid
from django.db import models


class ServiceDefinition(models.Model):
    TYPES = tuple((v, v) for v in ("API", "WORKER", "CONSUMER", "REALTIME", "SCHEDULER", "DATABASE", "CACHE", "MESSAGE_BROKER", "PROVIDER_ADAPTER", "INTERNAL_SERVICE"))
    CRITICALITY = tuple((v, v) for v in ("TIER_0", "TIER_1", "TIER_2", "TIER_3"))
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=80, unique=True)
    name = models.CharField(max_length=160)
    service_type = models.CharField(max_length=32, choices=TYPES)
    criticality = models.CharField(max_length=8, choices=CRITICALITY)
    owner = models.CharField(max_length=120)
    runtime_type = models.CharField(max_length=64)
    health_check_type = models.CharField(max_length=64)
    readiness_policy = models.JSONField(default=dict)
    status = models.CharField(max_length=24, default="ACTIVE")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class ServiceDependency(models.Model):
    service = models.ForeignKey(ServiceDefinition, on_delete=models.CASCADE, related_name="dependencies")
    dependency_code = models.CharField(max_length=80)
    dependency_type = models.CharField(max_length=32)
    required_for_liveness = models.BooleanField(default=False)
    required_for_readiness = models.BooleanField(default=True)
    required_for_writes = models.BooleanField(default=True)
    required_for_simulation = models.BooleanField(default=True)
    failure_mode = models.CharField(max_length=32)
    timeout_ms = models.PositiveIntegerField(default=500)
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta: constraints = [models.UniqueConstraint(fields=("service", "dependency_code"), name="ops_service_dependency_unique")]


class HealthCheckResult(models.Model):
    STATES = tuple((v, v) for v in ("HEALTHY", "DEGRADED", "UNHEALTHY", "UNKNOWN"))
    service_code = models.CharField(max_length=80)
    check_code = models.CharField(max_length=80)
    state = models.CharField(max_length=16, choices=STATES)
    latency_ms = models.DecimalField(max_digits=12, decimal_places=3)
    observed_at = models.DateTimeField()
    failure_reason_safe = models.CharField(max_length=160, blank=True)
    evidence_ref = models.CharField(max_length=160, blank=True)
    class Meta: indexes = [models.Index(fields=("service_code", "check_code", "-observed_at"), name="ops_health_latest_idx")]
