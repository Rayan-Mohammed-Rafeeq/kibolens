import pytest

from app.monitoring.vm_observer import VMObserver


@pytest.mark.anyio
async def test_vm_observer_returns_empty_inventory_without_optional_binding(monkeypatch) -> None:
    monkeypatch.setattr(VMObserver, "_libvirt", staticmethod(lambda: None))
    observer = VMObserver()
    assert await observer.list_vms() == []
    assert observer.last_error == (
        "VM inventory is unavailable because the host libvirt connection "
        "could not be queried; VM presence cannot be determined."
    )
