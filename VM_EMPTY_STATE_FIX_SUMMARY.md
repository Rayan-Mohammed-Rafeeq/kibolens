# KiboLens Virtual Machines Empty State Fix - Summary

## Problem
On Kibo, no virtual machines are deployed and the host does not currently have a running libvirt daemon or exposed libvirt socket. The Infrastructure page displayed:

"VM inventory is unavailable because the host libvirt connection could not be queried; VM presence cannot be determined."

This was misleading for the current setup. The expected behavior was a normal empty state, not an infrastructure error.

## Solution Implemented

### Backend Changes

#### 1. **VM Observer (`backend/app/monitoring/vm_observer.py`)**
- Changed behavior when `libvirt.openReadOnly()` returns `None` (socket absent/unconfigured)
- **Before**: Set `last_error` with connection error message
- **After**: Return empty list `[]` with `last_error = None`, treating it as a normal unconfigured state
- **Preserved**: Genuine errors (RuntimeError, PermissionError, etc.) still set `last_error` with diagnostic details

#### 2. **Backend Tests (`backend/tests/test_vm_observer.py`)**
Added/updated test cases:
- ✅ `test_vm_observer_handles_unavailable_socket`: Now expects `last_error = None` for absent socket
- ✅ `test_vm_observer_handles_unavailable_daemon`: RuntimeError still sets error (genuine error)
- ✅ `test_vm_observer_handles_permission_error`: New test for permission failures
- ✅ `test_vm_observer_reports_available_empty_inventory`: Successful connection with 0 VMs
- ✅ `test_vm_observer_discovers_domains_from_test_connection`: Successful discovery of VMs

#### 3. **Monitoring Service Tests (`backend/tests/test_monitoring.py`)**
- ✅ `test_unavailable_vm_observer_does_not_break_docker_inventory`: Docker remains operational when VM observer fails
- ✅ `test_unconfigured_vm_observer_returns_empty_inventory`: New test verifying `availability="available"` with empty inventory when unconfigured

### Frontend Changes

#### 4. **Infrastructure Page (`frontend/src/pages/infrastructure-page.tsx`)**
Updated VM section rendering logic:
- **Loading state**: "Checking VM inventory…"
- **Error state** (`vms.isError`): Shows generic error message
- **Unavailable state** (`availability === "unavailable"`): Shows detail message from backend
- **Empty available state** (`availability === "available"` && 0 items):
  - Heading: "No virtual machines detected"
  - Supporting text: "No libvirt-managed virtual machines are currently configured on this host. Configure libvirt on this host to monitor virtual machines."
- **With VMs**: Displays VM inventory table

#### 5. **Frontend Tests (`frontend/src/pages/infrastructure-page.test.tsx`)**
New comprehensive test suite:
- ✅ `displays empty state for unconfigured VM integration (socket absent)`
- ✅ `displays empty state when libvirt connects successfully with zero VMs`
- ✅ `displays error state when libvirt socket exists but connection fails`
- ✅ `displays error state when libvirt daemon is configured but unavailable`
- ✅ `displays VM inventory when VMs are discovered`
- ✅ `displays generic error when API request fails completely`

## Behavior Matrix

| Scenario | Socket Status | Connection Result | `last_error` | `availability` | UI Display |
|----------|--------------|-------------------|--------------|----------------|------------|
| Libvirt not configured | Absent | `None` returned | `None` | `available` | Empty state message |
| Libvirt connects, 0 VMs | Present | Success | `None` | `available` | Empty state message |
| Permission denied | Present | `PermissionError` | Set | `unavailable` | Error with diagnostic |
| Daemon unavailable | Present | `RuntimeError` | Set | `unavailable` | Error with diagnostic |
| VMs discovered | Present | Success | `None` | `available` | VM inventory table |

## Test Results

### Backend Tests
```bash
cd backend; python -m pytest tests/test_vm_observer.py tests/test_monitoring.py -k "vm" -v
```
**Result**: ✅ 8 passed, 1 skipped (libvirt binding check skipped when not installed)

### Frontend Tests
```bash
cd frontend; npm test
```
**Result**: ✅ 36 tests passed (6 infrastructure page VM tests + 30 existing tests)

### Linting
- **Backend**: N/A (ruff not installed on this machine, but code follows existing patterns)
- **Frontend**: ✅ `npm run lint` passed with 0 errors

### Production Build
```bash
cd frontend; npm run build
```
**Result**: ✅ Build successful (891.39 kB bundle)

## Files Changed

1. `backend/app/monitoring/vm_observer.py` - Core logic change
2. `backend/tests/test_vm_observer.py` - Updated/added tests
3. `backend/tests/test_monitoring.py` - Added new test case
4. `frontend/src/pages/infrastructure-page.tsx` - UI rendering logic
5. `frontend/src/pages/infrastructure-page.test.tsx` - New test file (6 tests)

## Key Design Decisions

1. **No fabricated VM records**: Empty inventory remains empty; no fake VMs are created
2. **Independent Docker monitoring**: Container discovery continues working regardless of VM state
3. **Preserved libvirt dependency**: VM support remains available for future use
4. **API compatibility maintained**: `VMInventoryResponse` schema unchanged
5. **Explicit availability states**: `available` vs `unavailable` clearly distinguish empty from error
6. **Actionable diagnostics**: Real errors include specific messages (permission, daemon, etc.)

## Verification

To verify the fix on Kibo:
1. Access the Infrastructure page
2. **Expected**: "No virtual machines detected" with supporting text
3. **Not Expected**: Error message about unavailable connection

To verify Docker independence:
1. Ensure Docker containers are visible
2. VM section shows empty state
3. Container metrics and health checks remain operational

## Future Considerations

- If libvirt is later configured on Kibo, the empty state will automatically transition to showing discovered VMs
- If libvirt daemon becomes unavailable after being configured, the error state will activate with diagnostic details
- The unconfigured state is indistinguishable from "configured but 0 VMs" by design (both are valid empty states)
