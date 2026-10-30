import asyncio
from datetime import UTC, datetime, timedelta

from app.core.config import Settings
from app.monitoring.prometheus import (
    PrometheusClient,
    PrometheusError,
    PrometheusMalformedResponse,
    parse_sample,
)
from app.schemas.monitoring import (
    ContainerStatus,
    HealthAssessment,
    InfrastructureSummary,
    MetricHistory,
    MetricHistoryPoint,
    MetricReading,
)

SUMMARY_QUERIES = {
    "cpu_utilization": (
        '100 - (avg(rate(node_cpu_seconds_total{mode="idle"}[5m])) * 100)',
        "percent",
    ),
    "cpu_load_1m": ("node_load1", "load"),
    "memory_utilization": (
        "100 * (1 - (node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes))",
        "percent",
    ),
    "memory_available": ("node_memory_MemAvailable_bytes", "bytes"),
    "swap_used": ("node_memory_SwapTotal_bytes - node_memory_SwapFree_bytes", "bytes"),
    "disk_utilization": (
        'max(100 * (1 - (node_filesystem_avail_bytes{fstype!~"tmpfs|overlay"} / '
        'node_filesystem_size_bytes{fstype!~"tmpfs|overlay"})))',
        "percent",
    ),
    "filesystem_available": (
        'min(node_filesystem_avail_bytes{fstype!~"tmpfs|overlay"})',
        "bytes",
    ),
    "disk_read": ("sum(rate(node_disk_read_bytes_total[5m]))", "bytes_per_second"),
    "disk_written": ("sum(rate(node_disk_written_bytes_total[5m]))", "bytes_per_second"),
    "network_receive": (
        'sum(rate(node_network_receive_bytes_total{device!="lo"}[5m]))',
        "bytes_per_second",
    ),
    "network_transmit": (
        'sum(rate(node_network_transmit_bytes_total{device!="lo"}[5m]))',
        "bytes_per_second",
    ),
    "network_receive_errors": (
        'sum(rate(node_network_receive_errs_total{device!="lo"}[5m]))',
        "errors_per_second",
    ),
    "network_transmit_errors": (
        'sum(rate(node_network_transmit_errs_total{device!="lo"}[5m]))',
        "errors_per_second",
    ),
    "uptime": ("time() - node_boot_time_seconds", "seconds"),
}

HISTORY_QUERIES = {
    "cpu_utilization": SUMMARY_QUERIES["cpu_utilization"],
    "memory_utilization": SUMMARY_QUERIES["memory_utilization"],
    "disk_utilization": SUMMARY_QUERIES["disk_utilization"],
    "network_receive": SUMMARY_QUERIES["network_receive"],
}


class MonitoringService:
    def __init__(self, client: PrometheusClient, settings: Settings) -> None:
        self.client = client
        self.settings = settings

    async def summary(self) -> InfrastructureSummary:
        metrics = [
            await self._metric(name, query, unit) for name, (query, unit) in SUMMARY_QUERIES.items()
        ]
        available = any(metric.availability == "available" for metric in metrics)
        timestamps = [
            metric.observation_at for metric in metrics if metric.observation_at is not None
        ]
        return InfrastructureSummary(
            health=assess_health(metrics, self.settings),
            metrics=metrics,
            monitoring_available=available,
            last_successful_collection=max(timestamps) if timestamps else None,
        )

    async def history(self, metric: str, hours: int) -> MetricHistory:
        query, unit = HISTORY_QUERIES[metric]
        end = datetime.now(UTC)
        try:
            results = await self.client.range_query(query, end - timedelta(hours=hours), end, 60)
            if not results:
                return MetricHistory(
                    metric=metric, unit=unit, points=[], availability="unavailable"
                )
            values = results[0].get("values")
            if not isinstance(values, list):
                raise PrometheusMalformedResponse("Prometheus history values are malformed.")
            points = [
                MetricHistoryPoint(timestamp=timestamp, value=value)
                for timestamp, value in map(parse_sample, values)
            ]
            return MetricHistory(metric=metric, unit=unit, points=points, availability="available")
        except PrometheusError:
            return MetricHistory(metric=metric, unit=unit, points=[], availability="unavailable")

    async def containers(self) -> list[ContainerStatus]:
        try:
            results = await self.client.instant_query(
                'max by (id, name) (container_last_seen{name!="",image!=""})'
            )
        except PrometheusError:
            return []
        metric_queries = {
            "cpu_percent": (
                'sum by (name) (rate(container_cpu_usage_seconds_total{image!="",name!=""}[5m])) '
                "* 100"
            ),
            "memory_bytes": (
                'sum by (name) (container_memory_working_set_bytes{image!="",name!=""})'
            ),
            "network_receive_bytes_per_second": (
                'sum by (name) (rate(container_network_receive_bytes_total{image!="",'
                'name!=""}[5m]))'
            ),
            "network_transmit_bytes_per_second": (
                'sum by (name) (rate(container_network_transmit_bytes_total{image!="",'
                'name!=""}[5m]))'
            ),
        }
        query_results = await asyncio.gather(
            *(self._container_metric(query) for query in metric_queries.values())
        )
        measurements = dict(zip(metric_queries, query_results, strict=True))
        containers = []
        for result in results:
            labels = result.get("metric", {})
            value = result.get("value")
            if not isinstance(labels, dict) or not isinstance(value, list):
                continue
            try:
                observed_at, _ = parse_sample(value)
            except PrometheusMalformedResponse:
                continue
            name = labels.get("name") or labels.get("id")
            if not isinstance(name, str):
                continue
            containers.append(
                ContainerStatus(
                    id=labels.get("id") if isinstance(labels.get("id"), str) else None,
                    name=name.lstrip("/"),
                    status="UNKNOWN",
                    cpu_percent=measurements["cpu_percent"].get(name),
                    memory_bytes=measurements["memory_bytes"].get(name),
                    network_receive_bytes_per_second=measurements[
                        "network_receive_bytes_per_second"
                    ].get(name),
                    network_transmit_bytes_per_second=measurements[
                        "network_transmit_bytes_per_second"
                    ].get(name),
                    last_observation=observed_at,
                    availability=self._availability(observed_at),
                )
            )
        return containers

    async def _container_metric(self, query: str) -> dict[str, float]:
        try:
            results = await self.client.instant_query(query)
        except PrometheusError:
            return {}
        values = {}
        for result in results:
            labels, sample = result.get("metric"), result.get("value")
            if not isinstance(labels, dict) or not isinstance(sample, list):
                continue
            name = labels.get("name")
            if not isinstance(name, str):
                continue
            try:
                _, value = parse_sample(sample)
            except PrometheusMalformedResponse:
                continue
            values[name] = value
        return values

    async def _metric(self, name: str, query: str, unit: str) -> MetricReading:
        try:
            results = await self.client.instant_query(query)
            if not results or not isinstance(results[0].get("value"), list):
                return MetricReading(
                    name=name,
                    value=None,
                    unit=unit,
                    observation_at=None,
                    availability="unavailable",
                )
            observed_at, value = parse_sample(results[0]["value"])
            return MetricReading(
                name=name,
                value=value,
                unit=unit,
                observation_at=observed_at,
                availability=self._availability(observed_at),
            )
        except PrometheusError:
            return MetricReading(
                name=name, value=None, unit=unit, observation_at=None, availability="unavailable"
            )

    def _availability(self, observed_at: datetime) -> str:
        if datetime.now(UTC) - observed_at > timedelta(
            seconds=self.settings.monitoring_stale_seconds
        ):
            return "stale"
        return "available"


def assess_health(metrics: list[MetricReading], settings: Settings) -> HealthAssessment:
    required = {"cpu_utilization", "memory_utilization", "disk_utilization"}
    available = {metric.name: metric for metric in metrics if metric.availability == "available"}
    now = datetime.now(UTC)
    if not required.issubset(available):
        missing = ", ".join(sorted(required - set(available)))
        return HealthAssessment(
            state="UNKNOWN",
            evidence=[f"Required telemetry unavailable or stale: {missing}."],
            assessed_at=now,
        )
    thresholds = {
        "cpu_utilization": (settings.cpu_warning_percent, settings.cpu_critical_percent),
        "memory_utilization": (settings.memory_warning_percent, settings.memory_critical_percent),
        "disk_utilization": (settings.disk_warning_percent, settings.disk_critical_percent),
    }
    critical, degraded = [], []
    for name, (warning, critical_threshold) in thresholds.items():
        value = available[name].value
        if value is not None and value >= critical_threshold:
            critical.append(
                f"{name} is {value:.1f}% (critical threshold {critical_threshold:.1f}%)."
            )
        elif value is not None and value >= warning:
            degraded.append(f"{name} is {value:.1f}% (warning threshold {warning:.1f}%).")
    if critical:
        return HealthAssessment(state="CRITICAL", evidence=critical, assessed_at=now)
    if degraded:
        return HealthAssessment(state="DEGRADED", evidence=degraded, assessed_at=now)
    return HealthAssessment(
        state="HEALTHY",
        evidence=["Required utilization metrics are within configured thresholds."],
        assessed_at=now,
    )
