"""Read-only Docker Engine observer.

The observer exposes sanitized inspection data only. It has no create, exec,
start, stop, or socket-proxying methods, so the public API cannot turn it into
an arbitrary command runner.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


class DockerObserver:
    def __init__(self, socket_path: str = "/var/run/docker.sock") -> None:
        self.socket_path = socket_path

    def _client(self):
        try:
            import docker
        except ImportError:
            return None
        return docker.DockerClient(base_url=f"unix://{self.socket_path}")

    @staticmethod
    def _direct_stats(container) -> dict:
        """Read bounded CPU/memory stats when cAdvisor is unavailable."""
        if not container.status == "running":
            return {}
        try:
            stats = container.stats(stream=False)
            cpu = stats.get("cpu_stats", {})
            previous_cpu = stats.get("precpu_stats", {})
            cpu_delta = cpu.get("cpu_usage", {}).get("total_usage", 0) - previous_cpu.get("cpu_usage", {}).get("total_usage", 0)
            system_delta = cpu.get("system_cpu_usage", 0) - previous_cpu.get("system_cpu_usage", 0)
            online_cpus = cpu.get("online_cpus") or len(cpu.get("cpu_usage", {}).get("percpu_usage") or []) or 1
            cpu_percent = (cpu_delta / system_delta) * online_cpus * 100 if system_delta > 0 and cpu_delta >= 0 else None
            memory_stats = stats.get("memory_stats", {})
            raw_memory = memory_stats.get("usage")
            cache = (memory_stats.get("stats") or {}).get("inactive_file") or (memory_stats.get("stats") or {}).get("cache") or 0
            memory_limit = memory_stats.get("limit")
            return {
                "cpu_percent": cpu_percent,
                "memory_bytes": max(0, raw_memory - cache) if raw_memory is not None else None,
                "memory_limit_bytes": memory_limit,
            }
        except Exception as exc:
            logger.debug("Could not collect direct Docker stats: %s", exc)
            return {}

    def _list_sync(self) -> list[dict]:
        client = self._client()
        if client is None:
            return []
        try:
            containers = client.containers.list(all=True)
            output = []
            for container in containers:
                attrs = container.attrs or {}
                state = attrs.get("State", {})
                health = state.get("Health", {}).get("Status")
                docker_state = (
                    "RESTARTING" if state.get("Restarting") else
                    "RUNNING" if state.get("Running") else "STOPPED"
                )
                health_status = {
                    "healthy": "HEALTHY",
                    "unhealthy": "UNHEALTHY",
                    "starting": "STARTING",
                }.get(health, "NO_CHECK" if health is None else "UNKNOWN")
                status = "UNHEALTHY" if health_status == "UNHEALTHY" else docker_state
                observed = state.get("StartedAt") or state.get("FinishedAt")
                try:
                    observed_at = datetime.fromisoformat(observed.replace("Z", "+00:00")) if observed else None
                except (AttributeError, ValueError):
                    observed_at = None
                uptime_seconds = None
                if state.get("Running") and state.get("StartedAt"):
                    try:
                        started_at = datetime.fromisoformat(state["StartedAt"].replace("Z", "+00:00"))
                        uptime_seconds = max(0.0, (datetime.now(timezone.utc) - started_at).total_seconds())
                    except (AttributeError, ValueError):
                        pass
                output.append({
                    "id": container.id,
                    "name": container.name,
                    "status": status,
                    "docker_state": docker_state,
                    "health": health_status,
                    "restart_count": int(attrs.get("RestartCount", 0)),
                    "image": (attrs.get("Config", {}).get("Image") or ""),
                    "labels": {k: v for k, v in (attrs.get("Config", {}).get("Labels") or {}).items() if k.startswith("kibolens.") or k.startswith("com.docker.compose.")},
                    "compose_service": (attrs.get("Config", {}).get("Labels") or {}).get("com.docker.compose.service"),
                    "memory_limit_bytes": (attrs.get("HostConfig", {}).get("Memory") or None),
                    "uptime_seconds": uptime_seconds,
                    "exit_code": state.get("ExitCode"),
                    "error": state.get("Error") or None,
                    "last_observation": observed_at,
                    "logs": self._logs_sync(container),
                    **self._direct_stats(container),
                })
            return output
        finally:
            client.close()

    @staticmethod
    def _logs_sync(container) -> str:
        try:
            return container.logs(tail=100, timestamps=True).decode("utf-8", errors="replace")[-12000:]
        except Exception as exc:
            logger.debug("Could not collect logs for container: %s", exc)
            return ""

    async def list_containers(self) -> list[dict]:
        try:
            return await asyncio.to_thread(self._list_sync)
        except Exception as exc:
            logger.warning("Docker observer unavailable: %s", exc)
            return []

    def _events_sync(self, since: float, until: float) -> list[dict]:
        client = self._client()
        if client is None:
            return []
        try:
            events = client.events(
                decode=True,
                filters={"type": ["container"]},
                since=since,
                until=until,
            )
            output = []
            for event in events:
                actor = event.get("Actor", {})
                attributes = actor.get("Attributes", {})
                output.append({
                    "id": actor.get("ID"),
                    "status": event.get("status"),
                    "time": event.get("time"),
                    "name": attributes.get("name") or attributes.get("com.docker.compose.service"),
                    "exit_code": attributes.get("exitCode"),
                    "labels": {key: value for key, value in attributes.items() if key.startswith("kibolens.") or key.startswith("com.docker.compose.")},
                })
            return output
        except Exception as exc:
            logger.warning("Docker event stream unavailable: %s", exc)
            return []
        finally:
            client.close()

    async def events_since(self, since: float, until: float) -> list[dict]:
        return await asyncio.to_thread(self._events_sync, since, until)

    async def lab_failures(self) -> list[dict]:
        """Return only qualifying lab failures for incident correlation."""
        containers = await self.list_containers()
        failures = []
        for container in containers:
            labels = container.get("labels", {})
            if labels.get("kibolens.lab") != "true":
                continue
            if container.get("health") == "UNHEALTHY" or (
                container["status"] == "STOPPED" and container.get("exit_code", 0) != 0
            ) or (container.get("restart_count") or 0) > 0:
                failures.append(container)
        return failures

    async def lab_containers(self) -> list[dict]:
        return [
            container for container in await self.list_containers()
            if container.get("labels", {}).get("kibolens.lab") == "true"
        ]


class DockerLabController(DockerObserver):
    """Allowlisted cleanup controller for labeled Failure Lab containers."""

    def _reset_sync(self) -> int:
        client = self._client()
        if client is None:
            return 0
        removed = 0
        try:
            for container in client.containers.list(all=True, filters={"label": "kibolens.lab=true"}):
                labels = container.attrs.get("Config", {}).get("Labels", {})
                if labels.get("kibolens.lab") != "true":
                    continue
                container.remove(force=True)
                removed += 1
            try:
                network = client.networks.get("kibolens-lab")
                if network.attrs.get("Labels", {}).get("kibolens.lab") == "true":
                    network.remove()
            except Exception:
                pass
            return removed
        finally:
            client.close()

    async def reset(self) -> int:
        return await asyncio.to_thread(self._reset_sync)

    SCENARIOS = frozenset({
        "crasher", "unhealthy", "restart-loop", "cpu-stress", "memory-pressure",
        "missing-dependency", "config-error", "interview-demo",
    })

    def _start_sync(self, scenario: str, healthy: bool = False, notify_account: bool | None = False) -> dict:
        if scenario not in self.SCENARIOS:
            raise ValueError("Unsupported Failure Lab scenario.")
        client = self._client()
        if client is None:
            raise RuntimeError("Docker SDK is unavailable.")
        name = f"kibolens-lab-{scenario}"
        try:
            existing = client.containers.list(all=True, filters={"name": f"^{name}$"})
            for container in existing:
                if container.status == "running" and not healthy:
                    return {"name": name, "status": "running"}
                if notify_account is None:
                    existing_labels = container.attrs.get("Config", {}).get("Labels", {})
                    notify_account = existing_labels.get("kibolens.lab.notify_account") == "true"
                container.remove(force=True)
            try:
                network = client.networks.get("kibolens-lab")
            except Exception:
                network = client.networks.create(
                    "kibolens-lab",
                    driver="bridge",
                    internal=True,
                    labels={"kibolens.lab": "true"},
                )
            environment = {"DEMO_MODE": "healthy" if healthy else "failing"} if scenario == "interview-demo" else None
            container = client.containers.run(
                image=f"kibolens/lab-{scenario}:latest",
                name=name,
                detach=True,
                user="1001:1001",
                read_only=True,
                cap_drop=["ALL"],
                security_opt=["no-new-privileges:true"],
                mem_limit="64m",
                nano_cpus=500_000_000,
                pids_limit=20,
                labels={
                    "kibolens.lab": "true",
                    "kibolens.lab.scenario": scenario,
                    "kibolens.lab.notify_account": "true" if notify_account else "false",
                },
                network=network.name,
                restart_policy={"Name": "no"},
                environment=environment,
            )
            return {"name": name, "id": container.id, "status": "healthy" if healthy else "created"}
        finally:
            client.close()

    async def start(self, scenario: str, healthy: bool = False, notify_account: bool | None = False) -> dict:
        return await asyncio.to_thread(self._start_sync, scenario, healthy, notify_account)

    def _stop_sync(self, scenario: str) -> bool:
        if scenario not in self.SCENARIOS:
            raise ValueError("Unsupported Failure Lab scenario.")
        client = self._client()
        if client is None:
            raise RuntimeError("Docker SDK is unavailable.")
        try:
            name = f"kibolens-lab-{scenario}"
            matches = client.containers.list(all=True, filters={"name": f"^{name}$"})
            for container in matches:
                container.stop(timeout=5)
            return bool(matches)
        finally:
            client.close()

    async def stop(self, scenario: str) -> bool:
        return await asyncio.to_thread(self._stop_sync, scenario)
