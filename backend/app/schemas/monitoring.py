from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

MetricAvailability = Literal["available", "stale", "unavailable"]
HealthState = Literal["HEALTHY", "DEGRADED", "CRITICAL", "UNKNOWN"]


class MetricReading(BaseModel):
    name: str
    value: float | None
    unit: str
    observation_at: datetime | None
    source: str = "prometheus"
    availability: MetricAvailability


class HealthAssessment(BaseModel):
    state: HealthState
    evidence: list[str]
    assessed_at: datetime


class InfrastructureSummary(BaseModel):
    health: HealthAssessment
    metrics: list[MetricReading]
    monitoring_available: bool
    last_successful_collection: datetime | None


class MetricHistoryPoint(BaseModel):
    timestamp: datetime
    value: float


class MetricHistory(BaseModel):
    metric: str
    unit: str
    points: list[MetricHistoryPoint]
    source: str = "prometheus"
    availability: MetricAvailability


class ContainerStatus(BaseModel):
    """
    Container resource usage and status.
    
    Note: status field is UNKNOWN because cAdvisor does not expose Docker health-check
    status or running state. Only resource metrics are available. To obtain true container
    health status, Docker API integration would be required (future enhancement).
    """
    id: str | None
    name: str
    status: Literal["RUNNING", "STOPPED", "UNHEALTHY", "UNKNOWN"]
    cpu_percent: float | None
    memory_bytes: float | None
    network_receive_bytes_per_second: float | None
    network_transmit_bytes_per_second: float | None
    restart_count: int | None = None
    last_observation: datetime | None
    availability: MetricAvailability


class MonitoringStatus(BaseModel):
    prometheus_available: bool
    checked_at: datetime
    detail: str | None = None


class AlertmanagerAlert(BaseModel):
    status: Literal["firing", "resolved"]
    labels: dict[str, str] = Field(default_factory=dict)
    annotations: dict[str, str] = Field(default_factory=dict)
    fingerprint: str = Field(min_length=1, max_length=256)


class AlertmanagerWebhook(BaseModel):
    status: Literal["firing", "resolved"]
    alerts: list[AlertmanagerAlert] = Field(min_length=1, max_length=50)


class AlertWebhookResponse(BaseModel):
    accepted: int
    deduplicated: int
