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


def test_alert_webhook_requires_bearer_token_and_deduplicates(
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
    assert client.post("/api/v1/monitoring/alerts", json=payload, headers=headers).json() == {
        "accepted": 0,
        "deduplicated": 1,
    }
