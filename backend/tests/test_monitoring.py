from datetime import datetime, timedelta
from datetime import timezone as tz

UTC = tz.utc

import pytest
from app.api.routes import infrastructure
from app.core.config import Settings
from app.monitoring.prometheus import (
    PrometheusMalformedResponse,
    PrometheusUnavailable,
    parse_sample,
)
from app.monitoring.service import MonitoringService, assess_health
from app.schemas.monitoring import MetricReading
from fastapi.testclient import TestClient
from pydantic import SecretStr


class FakePrometheusClient:
    def __init__(self, stale: bool = False, unavailable: bool = False) -> None:
        self.stale = stale
        self.unavailable = unavailable

    async def instant_query(self, _: str):
        if self.unavailable:
            raise PrometheusUnavailable
        timestamp = (
            datetime.now(UTC) - timedelta(minutes=10) if self.stale else datetime.now(UTC)
        ).timestamp()
        return [{"metric": {}, "value": [timestamp, "42"]}]

    async def range_query(self, *_):
        if self.unavailable:
            raise PrometheusUnavailable
        return [{"metric": {}, "values": [[datetime.now(UTC).timestamp(), "42"]]}]


def test_prometheus_sample_parsing_rejects_invalid_values() -> None:
    timestamp, value = parse_sample([1_700_000_000, "42.5"])
    assert timestamp.tzinfo is UTC
    assert value == 42.5
    with pytest.raises(PrometheusMalformedResponse):
        parse_sample(["invalid"])


@pytest.mark.anyio
async def test_monitoring_summary_classifies_available_and_stale_telemetry() -> None:
    settings = Settings()
    healthy = await MonitoringService(FakePrometheusClient(), settings).summary()
    assert healthy.health.state == "HEALTHY"
    assert healthy.monitoring_available

    stale = await MonitoringService(FakePrometheusClient(stale=True), settings).summary()
    assert stale.health.state == "UNKNOWN"
    assert not stale.monitoring_available


@pytest.mark.anyio
async def test_monitoring_handles_prometheus_unavailable_and_history_errors() -> None:
    service = MonitoringService(FakePrometheusClient(unavailable=True), Settings())
    summary = await service.summary()
    history = await service.history("cpu_utilization", 6)
    assert summary.health.state == "UNKNOWN"
    assert history.availability == "unavailable"


def test_health_assessment_uses_configured_thresholds() -> None:
    now = datetime.now(UTC)
    readings = [
        MetricReading(
            name="cpu_utilization",
            value=91,
            unit="percent",
            observation_at=now,
            availability="available",
        ),
        MetricReading(
            name="memory_utilization",
            value=42,
            unit="percent",
            observation_at=now,
            availability="available",
        ),
        MetricReading(
            name="disk_utilization",
            value=42,
            unit="percent",
            observation_at=now,
            availability="available",
        ),
    ]
    assert assess_health(readings, Settings()).state == "CRITICAL"


def test_infrastructure_endpoint_requires_authentication(client: TestClient) -> None:
    assert client.get("/api/v1/infrastructure/summary").status_code == 401
    assert client.get("/api/v1/infrastructure/vms").status_code == 401
    assert client.get("/api/v1/infrastructure/vms/status").status_code == 401


def test_alert_webhook_requires_bearer_token_and_correlates_repeats(
    client: TestClient, monkeypatch
) -> None:
    monkeypatch.setattr(
        infrastructure,
        "get_settings",
        lambda: Settings(alert_webhook_token=SecretStr("test-alert-token")),
    )
    monkeypatch.setattr(infrastructure, "deduplicator", infrastructure.AlertDeduplicator())
    payload = {"status": "firing", "alerts": [{"status": "firing", "fingerprint": "abc"}]}
    assert client.post("/api/v1/monitoring/alerts", json=payload).status_code == 401
    headers = {"Authorization": "Bearer test-alert-token"}
    assert client.post("/api/v1/monitoring/alerts", json=payload, headers=headers).json() == {
        "accepted": 1,
        "deduplicated": 0,
    }
    repeated = client.post("/api/v1/monitoring/alerts", json=payload, headers=headers)
    assert repeated.json() == {"accepted": 1, "deduplicated": 0}


@pytest.mark.anyio
async def test_containers_deduplicated_by_id() -> None:
    """Container inventory deduplicates by container ID when multiple name labels exist."""
    
    class FakeClientWithDuplicates:
        async def instant_query(self, query: str):
            timestamp = datetime.now(UTC).timestamp()
            if "container_last_seen" in query:
                # Simulate same container with different name labels (Compose vs runtime)
                return [
                    {
                        "metric": {
                            "id": "abc123def456",
                            "name": "kibolens-grafana-1",
                            "image": "grafana/grafana:12.3.1"
                        },
                        "value": [timestamp, "1"]
                    },
                    {
                        "metric": {
                            "id": "abc123def456",
                            "name": "/kibolens_grafana_1",
                            "image": "grafana/grafana:12.3.1"
                        },
                        "value": [timestamp, "1"]
                    }
                ]
            elif "container_cpu_usage" in query:
                return [
                    {"metric": {"id": "abc123def456"}, "value": [timestamp, "0.5"]}
                ]
            elif "container_memory" in query:
                return [
                    {"metric": {"id": "abc123def456"}, "value": [timestamp, "536870912"]}
                ]
            return []
    
    service = MonitoringService(FakeClientWithDuplicates(), Settings())
    containers = await service.containers()
    
    # Should only have one container despite two time series
    assert len(containers) == 1
    assert containers[0].id == "abc123def456"
    # Should prefer Compose-style name (with hyphens)
    assert containers[0].name == "kibolens-grafana-1"
    # Metrics should be preserved
    assert containers[0].cpu_percent == 0.5
    assert containers[0].memory_bytes == 536870912


@pytest.mark.anyio
async def test_container_names_normalized() -> None:
    """Container names have leading slashes removed."""
    
    class FakeClientWithSlash:
        async def instant_query(self, query: str):
            timestamp = datetime.now(UTC).timestamp()
            if "container_last_seen" in query:
                return [
                    {
                        "metric": {
                            "id": "def456abc789",
                            "name": "/backend",
                            "image": "backend:latest"
                        },
                        "value": [timestamp, "1"]
                    }
                ]
            return []
    
    service = MonitoringService(FakeClientWithSlash(), Settings())
    containers = await service.containers()
    
    assert len(containers) == 1
    assert containers[0].name == "backend"  # Leading slash removed
    assert not containers[0].name.startswith("/")


@pytest.mark.anyio
async def test_different_containers_remain_separate() -> None:
    """Different container IDs with similar names remain separate entries."""
    
    class FakeClientWithMultiple:
        async def instant_query(self, query: str):
            timestamp = datetime.now(UTC).timestamp()
            if "container_last_seen" in query:
                return [
                    {
                        "metric": {
                            "id": "container1",
                            "name": "backend-1",
                            "image": "backend:v1"
                        },
                        "value": [timestamp, "1"]
                    },
                    {
                        "metric": {
                            "id": "container2",
                            "name": "backend-2",
                            "image": "backend:v1"
                        },
                        "value": [timestamp, "1"]
                    }
                ]
            return []
    
    service = MonitoringService(FakeClientWithMultiple(), Settings())
    containers = await service.containers()
    
    # Should have two separate containers
    assert len(containers) == 2
    container_ids = {c.id for c in containers}
    container_names = {c.name for c in containers}
    assert container_ids == {"container1", "container2"}
    assert container_names == {"backend-1", "backend-2"}


@pytest.mark.anyio
async def test_missing_container_id_skipped() -> None:
    """Containers without IDs are safely skipped."""
    
    class FakeClientWithMissingId:
        async def instant_query(self, query: str):
            timestamp = datetime.now(UTC).timestamp()
            if "container_last_seen" in query:
                return [
                    {
                        "metric": {
                            "name": "some-container",
                            "image": "image:latest"
                            # Missing 'id' field
                        },
                        "value": [timestamp, "1"]
                    },
                    {
                        "metric": {
                            "id": "",  # Empty ID
                            "name": "another-container",
                            "image": "image:latest"
                        },
                        "value": [timestamp, "1"]
                    },
                    {
                        "metric": {
                            "id": "valid123",
                            "name": "valid-container",
                            "image": "image:latest"
                        },
                        "value": [timestamp, "1"]
                    }
                ]
            return []
    
    service = MonitoringService(FakeClientWithMissingId(), Settings())
    containers = await service.containers()
    
    # Only the valid container should be returned
    assert len(containers) == 1
    assert containers[0].id == "valid123"
    assert containers[0].name == "valid-container"


@pytest.mark.anyio
async def test_container_status_remains_unknown() -> None:
    """Container status is UNKNOWN when health info unavailable from cAdvisor."""
    
    class FakeClientWithContainer:
        async def instant_query(self, query: str):
            timestamp = datetime.now(UTC).timestamp()
            if "container_last_seen" in query:
                return [
                    {
                        "metric": {
                            "id": "xyz789",
                            "name": "healthy-container",
                            "image": "app:latest"
                        },
                        "value": [timestamp, "1"]
                    }
                ]
            # Even with metrics, status should remain UNKNOWN
            elif "container_cpu_usage" in query:
                return [{"metric": {"id": "xyz789"}, "value": [timestamp, "0.1"]}]
            elif "container_memory" in query:
                return [{"metric": {"id": "xyz789"}, "value": [timestamp, "268435456"]}]
            return []
    
    service = MonitoringService(FakeClientWithContainer(), Settings())
    containers = await service.containers()
    
    assert len(containers) == 1
    assert containers[0].status == "UNKNOWN"
    # Metrics should still be present
    assert containers[0].cpu_percent == 0.1
    assert containers[0].memory_bytes == 268435456


@pytest.mark.anyio
async def test_container_metrics_preserved_after_deduplication() -> None:
    """CPU, memory and network metrics are preserved after deduplication."""
    
    class FakeClientWithMetrics:
        async def instant_query(self, query: str):
            timestamp = datetime.now(UTC).timestamp()
            if "container_last_seen" in query:
                # Duplicate time series for same container
                return [
                    {
                        "metric": {"id": "test123", "name": "app-1", "image": "app:1.0"},
                        "value": [timestamp, "1"]
                    },
                    {
                        "metric": {"id": "test123", "name": "/app_1", "image": "app:1.0"},
                        "value": [timestamp, "1"]
                    }
                ]
            elif "container_cpu_usage" in query:
                return [{"metric": {"id": "test123"}, "value": [timestamp, "0.75"]}]
            elif "container_memory" in query:
                return [{"metric": {"id": "test123"}, "value": [timestamp, "1073741824"]}]
            elif "network_receive" in query:
                return [{"metric": {"id": "test123"}, "value": [timestamp, "1048576"]}]
            elif "network_transmit" in query:
                return [{"metric": {"id": "test123"}, "value": [timestamp, "2097152"]}]
            return []
    
    service = MonitoringService(FakeClientWithMetrics(), Settings())
    containers = await service.containers()
    
    # Should be deduplicated to one container
    assert len(containers) == 1
    container = containers[0]
    
    # All metrics should be preserved
    assert container.id == "test123"
    assert container.cpu_percent == 0.75
    assert container.memory_bytes == 1073741824
    assert container.network_receive_bytes_per_second == 1048576
    assert container.network_transmit_bytes_per_second == 2097152
    assert container.last_observation is not None
    assert container.availability == "available"


@pytest.mark.anyio
async def test_docker_inventory_is_merged_with_cadvisor_metrics() -> None:
    """Docker lifecycle metadata must not replace cAdvisor resource telemetry."""

    class FakeClient:
        async def instant_query(self, query: str):
            timestamp = datetime.now(UTC).timestamp()
            if "container_last_seen" in query:
                return [{"metric": {"id": "/docker/abc123", "name": "/api"}, "value": [timestamp, "1"]}]
            if "container_cpu_usage" in query:
                return [{"metric": {"id": "/docker/abc123"}, "value": [timestamp, "0.25"]}]
            if "container_memory" in query:
                return [{"metric": {"id": "/docker/abc123"}, "value": [timestamp, "104857600"]}]
            if "network_receive" in query:
                return [{"metric": {"id": "/docker/abc123"}, "value": [timestamp, "1200"]}]
            if "network_transmit" in query:
                return [{"metric": {"id": "/docker/abc123"}, "value": [timestamp, "800"]}]
            return []

    class FakeObserver:
        async def list_containers(self):
            return [{
                "id": "abc123", "name": "api", "status": "RUNNING",
                "restart_count": 2, "last_observation": datetime.now(UTC),
                "image": "api:latest", "labels": {"com.docker.compose.service": "api"},
                "exit_code": 0, "logs": "ready",
            }]

    containers = await MonitoringService(FakeClient(), Settings(), FakeObserver()).containers()
    assert len(containers) == 1
    assert containers[0].status == "RUNNING"
    assert containers[0].cpu_percent == 0.25
    assert containers[0].memory_bytes == 104857600
    assert containers[0].network_receive_bytes_per_second == 1200
    assert containers[0].restart_count == 2


@pytest.mark.anyio
async def test_container_health_and_direct_metrics_are_distinct() -> None:
    old_timestamp = (datetime.now(UTC) - timedelta(minutes=10)).timestamp()

    class FakeClient:
        async def instant_query(self, query: str):
            if "container_last_seen" in query:
                return [{"metric": {"id": "container-health"}, "value": [old_timestamp, "1"]}]
            return []

    class FakeObserver:
        async def list_containers(self):
            return [{
                "id": "container-health",
                "name": "api",
                "status": "RUNNING",
                "docker_state": "RUNNING",
                "health": "HEALTHY",
                "compose_service": "api",
                "cpu_percent": 12.5,
                "memory_bytes": 2048,
                "restart_count": 1,
                "last_observation": datetime.now(UTC) - timedelta(hours=1),
            }]

    containers = await MonitoringService(FakeClient(), Settings(), FakeObserver()).containers()

    assert len(containers) == 1
    assert containers[0].status == "RUNNING"
    assert containers[0].docker_state == "RUNNING"
    assert containers[0].health == "HEALTHY"
    assert containers[0].compose_service == "api"
    assert containers[0].availability == "available"
    assert containers[0].cpu_percent == 12.5
