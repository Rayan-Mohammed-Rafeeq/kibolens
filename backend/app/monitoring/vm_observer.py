"""Optional-at-runtime, read-only libvirt observer.

The production image includes the Python binding, but hosts without a libvirt
daemon or socket return an explicit unavailable inventory. No VM is inferred
from Docker or Prometheus labels.
"""

from __future__ import annotations

import asyncio
import logging
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


class VMObserver:
    def __init__(self, uri: str = "qemu:///system") -> None:
        self.uri = uri
        self._previous_cpu: dict[str, tuple[int, float]] = {}
        self._active_since: dict[str, float] = {}
        self.last_error: str | None = None
        self.is_unconfigured: bool = False

    @staticmethod
    def _libvirt():
        try:
            import libvirt  # type: ignore
        except (ImportError, OSError) as exc:
            logger.info("Optional libvirt Python binding unavailable: %s", type(exc).__name__)
            return None
        return libvirt

    def _connection_error(self, reason: str | None = None) -> str:
        detail = (
            f" {reason.strip()}"
            if reason and reason.strip()
            else " Ensure libvirtd is running and /var/run/libvirt is mounted and authorized."
        )
        return (
            f"VM inventory is unavailable: the libvirt connection '{self.uri}' "
            f"could not be queried.{detail}"
        )

    def _list_sync(self) -> list[dict]:
        self.last_error = None
        self.is_unconfigured = False
        libvirt = self._libvirt()
        if libvirt is None:
            self.last_error = (
                "VM inventory is unavailable: the libvirt Python binding is not "
                "installed in the backend image. Rebuild the production backend "
                "with VM support enabled."
            )
            return []
        connection = None
        try:
            connection = libvirt.openReadOnly(self.uri)
            if connection is None:
                # Socket absent or libvirt not configured - treat as unconfigured
                logger.info("libvirt socket not available, treating as unconfigured VM integration")
                self.is_unconfigured = True
                return []
            now = time.monotonic()
            observed_at = datetime.now(timezone.utc)
            output: list[dict] = []
            for domain in connection.listAllDomains(0):
                try:
                    output.append(self._inspect_domain(domain, libvirt, now, observed_at))
                except Exception as exc:
                    logger.debug("Unable to inspect libvirt domain: %s", exc)
            return output
        except Exception as exc:
            self.last_error = self._connection_error(str(exc))
            logger.info("libvirt inventory unavailable: %s", type(exc).__name__)
            return []
        finally:
            if connection is not None:
                try:
                    connection.close()
                except Exception:
                    pass

    def _inspect_domain(self, domain, libvirt, now: float, observed_at: datetime) -> dict:
        domain_id = domain.UUIDString()
        name = domain.name()
        active = bool(domain.isActive())
        state_code = domain.info()[0]
        state_names = {
            getattr(libvirt, "VIR_DOMAIN_RUNNING", 1): "RUNNING",
            getattr(libvirt, "VIR_DOMAIN_PAUSED", 3): "PAUSED",
            getattr(libvirt, "VIR_DOMAIN_SHUTOFF", 5): "STOPPED",
        }
        status = state_names.get(state_code, "UNKNOWN") if active or state_code == 5 else "UNKNOWN"
        if active:
            self._active_since.setdefault(domain_id, now)
        else:
            self._active_since.pop(domain_id, None)
        info = domain.info()
        allocated_bytes = int(info[1]) * 1024
        used_bytes = int(info[2]) * 1024 if active else None
        vcpus = int(info[3])
        cpu_time = int(info[4])
        previous = self._previous_cpu.get(domain_id)
        cpu_percent = None
        if previous and active:
            previous_cpu, previous_at = previous
            elapsed = now - previous_at
            if elapsed > 0 and cpu_time >= previous_cpu and vcpus > 0:
                cpu_percent = min(100.0, max(0.0, (cpu_time - previous_cpu) / (elapsed * 1e9 * vcpus) * 100))
        self._previous_cpu[domain_id] = (cpu_time, now)

        xml = ET.fromstring(domain.XMLDesc(0))
        os_type = next((node.text for node in xml.findall("./os/type") if node.text), None)
        guest_agent = xml.find(".//channel/target[@name='org.qemu.guest_agent.0']") is not None
        addresses: list[str] = []
        if active:
            try:
                for interface in domain.interfaceAddresses(1, 0).values():
                    for address in interface.get("addrs", []):
                        if address.get("addr"):
                            addresses.append(address["addr"])
            except Exception:
                pass

        block_read = block_write = network_rx = network_tx = None
        if active:
            block_read = block_write = 0
            for disk in xml.findall("./devices/disk"):
                target = disk.find("target")
                target_name = target.get("dev") if target is not None else None
                if not target_name:
                    continue
                try:
                    stats = domain.blockStats(target_name)
                    block_read += int(stats[1])
                    block_write += int(stats[3])
                except Exception:
                    pass
            network_rx = network_tx = 0
            for interface in xml.findall("./devices/interface"):
                target = interface.find("target")
                target_name = target.get("dev") if target is not None else None
                if not target_name:
                    continue
                try:
                    stats = domain.interfaceStats(target_name)
                    network_rx += int(stats[0])
                    network_tx += int(stats[4])
                except Exception:
                    pass

        return {
            "id": domain_id,
            "name": name,
            "status": status,
            "vcpu_count": vcpus,
            "memory_allocated_bytes": allocated_bytes,
            "memory_used_bytes": used_bytes,
            "cpu_percent": cpu_percent,
            "disk_read_bytes": block_read,
            "disk_write_bytes": block_write,
            "network_receive_bytes": network_rx,
            "network_transmit_bytes": network_tx,
            "ip_addresses": sorted(set(addresses)),
            "operating_system": os_type,
            "guest_agent_configured": guest_agent,
            "uptime_seconds": max(0.0, now - self._active_since[domain_id]) if active else None,
            "last_observation": observed_at,
            "availability": "available",
            "error": None,
        }

    async def list_vms(self) -> list[dict]:
        try:
            return await asyncio.to_thread(self._list_sync)
        except Exception as exc:
            self.last_error = self._connection_error(str(exc))
            logger.warning("VM observer unavailable: %s", type(exc).__name__)
            return []
