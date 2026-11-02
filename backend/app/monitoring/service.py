import asyncio
from datetime import datetime, timedelta
from datetime import timezone as tz

UTC = tz.utc

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
from app.monitoring.docker_observer import DockerObserver

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
    def __init__(self, client: PrometheusClient, settings: Settings, docker_observer: DockerObserver | None = None) -> None:
        self.client = client
        self.settings = settings
        self.docker_observer = docker_observer

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
            results = await self.client.instant_query('container_last_seen{id!=""}')
        except PrometheusError:
            results = []

        containers_by_id: dict[str, dict] = {}
        for result in results:
            labels, value = result.get("metric", {}), result.get("value")
            if not isinstance(labels, dict) or not isinstance(value, list):
                continue
            try:
                observed_at, _ = parse_sample(value)
            except PrometheusMalformedResponse:
                continue
            container_id = self._normalize_container_id(labels.get("id"))
            if not container_id:
                continue
            raw_name = labels.get("name")
            normalized_name = raw_name.lstrip("/") if isinstance(raw_name, str) and raw_name else container_id[:12]
            current = containers_by_id.get(container_id)
            if current is None or ("_" in current["name"] and "_" not in normalized_name):
                containers_by_id[container_id] = {
                    "id": container_id, "name": normalized_name, "observed_at": observed_at
                }

        docker_by_id: dict[str, dict] = {}
        if self.docker_observer:
            for item in await self.docker_observer.list_containers():
                container_id = self._normalize_container_id(item.get("id"))
                if not container_id:
                    continue
                docker_by_id[container_id] = item
                containers_by_id.setdefault(container_id, {
                    "id": container_id,
                    "name": item.get("name") or container_id[:12],
                    "observed_at": item.get("last_observation"),
                })

        if not containers_by_id:
            return []

        metric_queries = {
            "cpu_percent": 'sum by (id) (rate(container_cpu_usage_seconds_total{image!="",id!=""}[5m])) * 100',
            "memory_bytes": 'sum by (id) (container_memory_working_set_bytes{image!="",id!=""} or container_memory_usage_bytes{image!="",id!=""})',
            "network_receive_bytes_per_second": 'sum by (id) (rate(container_network_receive_bytes_total{image!="",id!=""}[5m]))',
            "network_transmit_bytes_per_second": 'sum by (id) (rate(container_network_transmit_bytes_total{image!="",id!=""}[5m]))',
        }
        query_results = await asyncio.gather(*(self._container_metric(query) for query in metric_queries.values()))
        measurements = dict(zip(metric_queries, query_results, strict=True))
        output = []
        for container_id, container_data in containers_by_id.items():
            docker_data = docker_by_id.get(container_id, {})
            observed_at = container_data["observed_at"]
            output.append(ContainerStatus(
                id=container_id,
                name=docker_data.get("name") or container_data["name"],
                status=docker_data.get("status", "UNKNOWN"),
                cpu_percent=measurements["cpu_percent"].get(container_id),
                memory_bytes=measurements["memory_bytes"].get(container_id),
                network_receive_bytes_per_second=measurements["network_receive_bytes_per_second"].get(container_id),
                network_transmit_bytes_per_second=measurements["network_transmit_bytes_per_second"].get(container_id),
                restart_count=docker_data.get("restart_count"),
                last_observation=observed_at,
                availability=self._availability(observed_at) if observed_at else "unavailable",
                image=docker_data.get("image"), exit_code=docker_data.get("exit_code"),
                labels=docker_data.get("labels", {}), logs=docker_data.get("logs"),
            ))
        return output

    @staticmethod
    def _normalize_container_id(value: object) -> str | None:
        if not isinstance(value, str) or not value:
            return None
        value = value.strip().lstrip("/")
        return value.removeprefix("docker/") or None

    async def _container_metric(self, query: str) -> dict[str, float]:
        """
        Execute container metric query and return values keyed by container ID.
        
        Uses container ID (not name) as the lookup key for stable deduplication.
        """
        try:
            results = await self.client.instant_query(query)
        except PrometheusError:
            return {}
        values = {}
        for result in results:
            labels, sample = result.get("metric"), result.get("value")
            if not isinstance(labels, dict) or not isinstance(sample, list):
                continue
            # Use container ID for stable lookups (not name, which can vary)
            container_id = self._normalize_container_id(labels.get("id"))
            if not container_id:
                continue
            try:
                _, value = parse_sample(sample)
            except PrometheusMalformedResponse:
                continue
            values[container_id] = value
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
