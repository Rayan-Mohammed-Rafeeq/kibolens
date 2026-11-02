from __future__ import annotations

import pytest

from app.monitoring.vm_observer import VMObserver


def test_libvirt_binding_is_importable_when_installed() -> None:
    """The production image build also runs this import as a hard build check."""
    libvirt = pytest.importorskip("libvirt")
    assert callable(libvirt.openReadOnly)


@pytest.mark.anyio
async def test_vm_observer_handles_missing_python_binding(monkeypatch) -> None:
    monkeypatch.setattr(VMObserver, "_libvirt", staticmethod(lambda: None))

    observer = VMObserver()

    assert await observer.list_vms() == []
    assert observer.last_error is not None
    assert "libvirt Python binding is not installed" in observer.last_error


@pytest.mark.anyio
async def test_vm_observer_handles_unavailable_socket(monkeypatch) -> None:
    """When libvirt socket is absent, treat as unconfigured state."""
    class FakeLibvirt:
        @staticmethod
        def openReadOnly(uri: str):
            assert uri == "qemu:///system"
            return None

    monkeypatch.setattr(VMObserver, "_libvirt", staticmethod(lambda: FakeLibvirt))

    observer = VMObserver()

    assert await observer.list_vms() == []
    assert observer.last_error is None
    assert observer.is_unconfigured is True


@pytest.mark.anyio
async def test_vm_observer_handles_unavailable_daemon(monkeypatch) -> None:
    """When libvirt daemon fails to connect, report genuine error."""
    class FakeLibvirt:
        @staticmethod
        def openReadOnly(uri: str):
            raise RuntimeError("failed to connect to the libvirt daemon")

    monkeypatch.setattr(VMObserver, "_libvirt", staticmethod(lambda: FakeLibvirt))

    observer = VMObserver()

    assert await observer.list_vms() == []
    assert observer.last_error is not None
    assert "failed to connect to the libvirt daemon" in observer.last_error


@pytest.mark.anyio
async def test_vm_observer_handles_permission_error(monkeypatch) -> None:
    """When libvirt socket exists but connection fails due to permission, report error."""
    class FakeLibvirt:
        @staticmethod
        def openReadOnly(uri: str):
            raise PermissionError("Permission denied")

    monkeypatch.setattr(VMObserver, "_libvirt", staticmethod(lambda: FakeLibvirt))

    observer = VMObserver()

    assert await observer.list_vms() == []
    assert observer.last_error is not None
    assert "Permission denied" in observer.last_error


@pytest.mark.anyio
async def test_vm_observer_reports_available_empty_inventory(monkeypatch) -> None:
    """Successful connection with zero VMs reports available (not unconfigured)."""
    class FakeConnection:
        def listAllDomains(self, flags: int):
            assert flags == 0
            return []

        def close(self):
            pass

    class FakeLibvirt:
        @staticmethod
        def openReadOnly(uri: str):
            return FakeConnection()

    monkeypatch.setattr(VMObserver, "_libvirt", staticmethod(lambda: FakeLibvirt))

    observer = VMObserver()

    assert await observer.list_vms() == []
    assert observer.last_error is None
    assert observer.is_unconfigured is False


@pytest.mark.anyio
async def test_vm_observer_discovers_domains_from_test_connection(monkeypatch) -> None:
    class FakeDomain:
        def UUIDString(self):
            return "vm-uuid-1"

        def name(self):
            return "future-vm"

        def isActive(self):
            return True

        def info(self):
            return (1, 1024, 512, 2, 0)

        def XMLDesc(self, flags: int):
            return """
                <domain>
                  <os><type>hvm</type></os>
                  <devices>
                    <channel type="unix">
                      <target type="virtio" name="org.qemu.guest_agent.0"/>
                    </channel>
                  </devices>
                </domain>
            """

        def interfaceAddresses(self, source: int, flags: int):
            return {"vnet0": {"addrs": [{"addr": "192.0.2.10"}]}}

    class FakeConnection:
        def listAllDomains(self, flags: int):
            return [FakeDomain()]

        def close(self):
            pass

    class FakeLibvirt:
        VIR_DOMAIN_RUNNING = 1
        VIR_DOMAIN_PAUSED = 3
        VIR_DOMAIN_SHUTOFF = 5

        @staticmethod
        def openReadOnly(uri: str):
            assert uri == "qemu:///system"
            return FakeConnection()

    monkeypatch.setattr(VMObserver, "_libvirt", staticmethod(lambda: FakeLibvirt))

    observer = VMObserver("qemu:///system")
    result = await observer.list_vms()

    assert len(result) == 1
    assert result[0]["id"] == "vm-uuid-1"
    assert result[0]["name"] == "future-vm"
    assert result[0]["status"] == "RUNNING"
    assert result[0]["ip_addresses"] == ["192.0.2.10"]
    assert result[0]["guest_agent_configured"] is True
    assert observer.last_error is None
