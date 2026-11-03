"""Safe, persistent synthetic evidence for Failure Lab experiments."""

from __future__ import annotations

from dataclasses import dataclass

from app.schemas.monitoring import AlertmanagerAlert


@dataclass(frozen=True)
class SimulationScenario:
    key: str
    title: str
    severity: str
    resource: str
    description: str
    metric_name: str
    metric_value: float
    unit: str
    threshold: float
    logs: str


SIMULATION_SCENARIOS = (
    SimulationScenario("high-cpu", "High CPU utilization", "WARNING", "kibo-host", "Sustained CPU utilization exceeded the warning threshold.", "cpu_utilization", 94.2, "%", 80.0, "SIMULATED: node CPU utilization 94.2% for 10 minutes."),
    SimulationScenario("high-memory", "High memory utilization", "WARNING", "kibo-host", "Memory utilization crossed the warning threshold.", "memory_utilization", 91.5, "%", 80.0, "SIMULATED: memory utilization 91.5%; available memory is low."),
    SimulationScenario("critical-memory", "Critical memory pressure", "CRITICAL", "kibo-host", "Memory pressure indicates imminent host exhaustion.", "memory_utilization", 98.7, "%", 90.0, "SIMULATED: memory utilization 98.7%; reclaim pressure detected."),
    SimulationScenario("high-temperature", "High host temperature", "HIGH", "kibo-host", "Temperature telemetry crossed the configured safety threshold.", "temperature_celsius", 92.0, "°C", 85.0, "SIMULATED: host temperature 92.0°C."),
    SimulationScenario("disk-nearly-full", "Disk nearly full", "CRITICAL", "kibo-host", "Filesystem utilization is critically high.", "disk_utilization", 96.4, "%", 90.0, "SIMULATED: filesystem utilization 96.4%; only 3.6% remains."),
    SimulationScenario("container-crash", "Simulated container crash", "HIGH", "kibolens-backend", "Synthetic Docker exit event with a non-zero exit code.", "exit_code", 137.0, "code", 0.0, "SIMULATED: kibolens-backend exited with code 137 (OOM/forced termination)."),
    SimulationScenario("container-restart-loop", "Simulated container restart loop", "HIGH", "kibolens-worker", "Synthetic restart counter exceeded the configured sustained threshold.", "restart_count", 5.0, "restarts", 2.0, "SIMULATED: kibolens-worker restarted 5 times in 10 minutes."),
    SimulationScenario("container-unhealthy", "Simulated unhealthy container", "HIGH", "kibolens-frontend", "Synthetic Docker health check failure.", "health_status", 0.0, "failed", 1.0, "SIMULATED: healthcheck failed three consecutive times."),
    SimulationScenario("application-config-failure", "Simulated application configuration failure", "HIGH", "kibolens-backend", "Synthetic startup configuration validation failure.", "configuration_valid", 0.0, "boolean", 1.0, "SIMULATED: required configuration value DATABASE_URL is invalid."),
)

SCENARIO_BY_KEY = {item.key: item for item in SIMULATION_SCENARIOS}


def make_alert(scenario: SimulationScenario, status: str = "firing") -> AlertmanagerAlert:
    return AlertmanagerAlert(
        status=status,
        fingerprint=f"simulation:{scenario.key}",
        labels={
            "alertname": f"KiboLensSimulation{scenario.key.replace('-', '')}",
            "severity": scenario.severity.lower(),
            "service": scenario.resource,
            "kibolens_simulated": "true",
        },
        annotations={
            "summary": scenario.title,
            "description": f"{scenario.description} {scenario.logs}",
        },
    )
