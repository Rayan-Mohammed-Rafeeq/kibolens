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
                status = "UNHEALTHY" if health == "unhealthy" else (
                    "RUNNING" if state.get("Running") else "STOPPED"
                )
                observed = state.get("StartedAt") or state.get("FinishedAt")
                try:
                    observed_at = datetime.fromisoformat(observed.replace("Z", "+00:00")) if observed else None
                except (AttributeError, ValueError):
                    observed_at = None
                output.append({
                    "id": container.id,
                    "name": container.name,
                    "status": status,
                    "restart_count": int(attrs.get("RestartCount", 0)),
                    "image": (attrs.get("Config", {}).get("Image") or ""),
                    "labels": {k: v for k, v in (attrs.get("Config", {}).get("Labels") or {}).items() if k.startswith("kibolens.") or k.startswith("com.docker.compose.")},
                    "exit_code": state.get("ExitCode"),
                    "last_observation": observed_at,
                    "logs": self._logs_sync(container),
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

    async def lab_failures(self) -> list[dict]:
        """Return only qualifying lab failures for incident correlation."""
        containers = await self.list_containers()
        failures = []
        for container in containers:
            labels = container.get("labels", {})
            if labels.get("kibolens.lab") != "true":
                continue
            if container["status"] == "UNHEALTHY" or (
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
            return removed
        finally:
            client.close()

    async def reset(self) -> int:
        return await asyncio.to_thread(self._reset_sync)
