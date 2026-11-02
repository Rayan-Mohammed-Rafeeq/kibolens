from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

MetricAvailability = Literal["available", "stale", "unavailable", "unconfigured"]
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


class VirtualMachineStatus(BaseModel):
    id: str
    name: str
    status: Literal["RUNNING", "STOPPED", "PAUSED", "UNKNOWN"]
    vcpu_count: int | None
    memory_allocated_bytes: float | None
    memory_used_bytes: float | None
    cpu_percent: float | None
    disk_read_bytes: float | None
    disk_write_bytes: float | None
    network_receive_bytes: float | None
    network_transmit_bytes: float | None
    ip_addresses: list[str] = Field(default_factory=list)
    operating_system: str | None = None
    guest_agent_configured: bool | None = None
    uptime_seconds: float | None = None
    last_observation: datetime | None = None
    availability: MetricAvailability
    error: str | None = None


class VMInventoryResponse(BaseModel):
    items: list[VirtualMachineStatus] = Field(default_factory=list)
    availability: MetricAvailability
    detail: str | None = None


class InfrastructureSummary(BaseModel):
    health: HealthAssessment
    metrics: list[MetricReading]
    monitoring_available: bool
    last_successful_collection: datetime | None
    vms: list[VirtualMachineStatus] = Field(default_factory=list)


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
    """Canonical Docker container record merged with cAdvisor telemetry."""
    id: str | None
    name: str
    status: Literal["RUNNING", "STOPPED", "RESTARTING", "UNHEALTHY", "UNKNOWN"]
    docker_state: Literal["RUNNING", "STOPPED", "RESTARTING", "UNKNOWN"] = "UNKNOWN"
    health: Literal["HEALTHY", "UNHEALTHY", "STARTING", "NO_CHECK", "UNKNOWN"] = "UNKNOWN"
    cpu_percent: float | None
    memory_bytes: float | None
    network_receive_bytes_per_second: float | None
    network_transmit_bytes_per_second: float | None
    last_observation: datetime | None
    availability: MetricAvailability
    image: str | None = None
    restart_count: int | None = None
    exit_code: int | None = None
    labels: dict[str, str] = Field(default_factory=dict)
    logs: str | None = None
    compose_service: str | None = None
    memory_limit_bytes: float | None = None
    block_read_bytes_per_second: float | None = None
    block_write_bytes_per_second: float | None = None
    uptime_seconds: float | None = None
    error: str | None = None


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
