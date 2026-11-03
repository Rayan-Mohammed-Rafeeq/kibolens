# KiboLens Virtual Machines Empty State Fix - Summary

## Problem
On Kibo, no virtual machines are deployed and the host does not currently have a running libvirt daemon or exposed libvirt socket. The Infrastructure page displayed:

"VM inventory is unavailable because the host libvirt connection could not be queried; VM presence cannot be determined."

This was misleading for the current setup. The expected behavior was a normal empty state, not an infrastructure error.

## Solution Implemented - Three Explicit States

The implementation now distinguishes between three explicit API states:

1. **`available`**: libvirt connection succeeded; VM inventory was queried successfully, including when zero VMs exist
2. **`unconfigured`**: libvirt integration/socket is absent and VM discovery is not configured on the host
3. **`unavailable`**: libvirt is configured but a genuine connection, permission, or daemon error prevents discovery

### Files Changed

#### Backend Changes

1. **`backend/app/schemas/monitoring.py`**
   - Added "unconfigured" to `MetricAvailability` type

2. **`backend/app/monitoring/vm_observer.py`**
   - Added `is_unconfigured` boolean attribute to track unconfigured state
   - When `libvirt.openReadOnly()` returns `None` (socket absent), sets `is_unconfigured = True`
   - Preserved genuine error handling for RuntimeError, PermissionError, etc. (sets `last_error`)

3. **`backend/app/monitoring/service.py`**
   - Updated `vm_inventory()` to check three conditions:
     - `is_unconfigured = True` → returns `("unconfigured", None)`
     - `last_error` set → returns `("unavailable", error_message)`
     - Otherwise → returns `("available", None)`

4. **`backend/tests/test_vm_observer.py`**
   - Updated `test_vm_observer_handles_unavailable_socket`: Now expects `is_unconfigured = True`
   - Updated `test_vm_observer_reports_available_empty_inventory`: Verifies `is_unconfigured = False`
   - Added `test_vm_observer_handles_permission_error`: Tests permission failures set error

5. **`backend/tests/test_monitoring.py`**
   - Renamed and updated `test_unconfigured_vm_observer_returns_unconfigured_inventory`: Verifies `availability = "unconfigured"`
   - Added `test_available_vm_observer_with_zero_vms`: Verifies successful connection with 0 VMs returns `availability = "available"`
   - Preserved `test_unavailable_vm_observer_does_not_break_docker_inventory`: Docker remains operational when VM observer fails

#### Frontend Changes

6. **`frontend/src/types/monitoring.ts`**
   - Added "unconfigured" to `Availability` type

7. **`frontend/src/pages/infrastructure-page.tsx`**
   - Updated VM section rendering logic:
     - **Loading**: "Checking VM inventory…"
     - **Error** (`vms.isError`): Generic error message
     - **Unavailable** (`availability === "unavailable"`): Shows detail message from backend with diagnostic
     - **Empty available** (`availability === "available"` && 0 items):
       - Heading: "No virtual machines detected"
       - Text: "No libvirt-managed virtual machines are currently configured on this host."
     - **Empty unconfigured** (`availability === "unconfigured"` && 0 items):
       - Heading: "No virtual machines detected"
       - Text: "No libvirt-managed virtual machines are currently configured on this host. Configure libvirt on this host to monitor virtual machines."
     - **With VMs**: Displays VM inventory table

8. **`frontend/src/pages/infrastructure-page.test.tsx`**
   - Created comprehensive test suite with 6 test cases:
     - `displays empty state for unconfigured VM integration (socket absent)` - verifies "Configure libvirt" message shown
     - `displays empty state when libvirt connects successfully with zero VMs` - verifies "Configure libvirt" message NOT shown
     - `displays error state when libvirt socket exists but connection fails` - verifies error with diagnostic
     - `displays error state when libvirt daemon is configured but unavailable` - verifies daemon error
     - `displays VM inventory when VMs are discovered` - verifies VM display
     - `displays generic error when API request fails completely` - verifies network error handling

## State Behavior Matrix

| Scenario | Socket Status | Connection Result | `last_error` | `is_unconfigured` | `availability` | UI Display |
|----------|--------------|-------------------|--------------|-------------------|----------------|------------|
| Libvirt not configured | Absent | `None` returned | `None` | `True` | `unconfigured` | Empty state + "Configure libvirt..." |
| Libvirt connects, 0 VMs | Present | Success | `None` | `False` | `available` | Empty state (no config prompt) |
| Permission denied | Present | `PermissionError` | Set | `False` | `unavailable` | Error with diagnostic |
| Daemon unavailable | Present | `RuntimeError` | Set | `False` | `unavailable` | Error with diagnostic |
| VMs discovered | Present | Success | `None` | `False` | `available` | VM inventory table |

## Test Results

### Backend Tests
```bash
cd backend; python -m pytest tests/test_vm_observer.py tests/test_monitoring.py -k "vm" -v
```
**Result**: ✅ 9 passed, 1 skipped (10 total VM tests)

### Frontend Tests
```bash
cd frontend; npm test
```
**Result**: ✅ 36 tests passed (6 infrastructure page VM tests + 30 existing tests)

### Linting
- **Backend**: N/A (not installed on this machine, but code follows existing patterns)
- **Frontend**: ✅ `npm run lint` passed with 0 errors

### Production Build
```bash
cd frontend; npm run build
```
**Result**: ✅ Build successful (891.50 kB bundle)

## Files Changed Summary

**Backend (5 files):**
1. `backend/app/schemas/monitoring.py` - Added "unconfigured" to availability type
2. `backend/app/monitoring/vm_observer.py` - Added `is_unconfigured` tracking
3. `backend/app/monitoring/service.py` - Three-state logic in `vm_inventory()`
4. `backend/tests/test_vm_observer.py` - Updated/added tests
5. `backend/tests/test_monitoring.py` - Added two state-specific tests

**Frontend (3 files):**
6. `frontend/src/types/monitoring.ts` - Added "unconfigured" to availability type
7. `frontend/src/pages/infrastructure-page.tsx` - Three-state UI rendering
8. `frontend/src/pages/infrastructure-page.test.tsx` - 6 comprehensive test cases

## Key Design Decisions

1. **Three explicit states**: `available`, `unconfigured`, `unavailable` - each with distinct meaning and UI
2. **Not describing unconfigured as successful**: Empty unconfigured state does NOT claim discovery succeeded
3. **No fabricated VM records**: Empty inventory remains empty; no fake VMs are created
4. **Independent Docker monitoring**: Container discovery continues working regardless of VM state
5. **Preserved libvirt dependency**: VM support remains available for future use
6. **API compatibility maintained**: `VMInventoryResponse` schema extended (backward compatible)
7. **Explicit availability states**: Clear distinction between empty, unconfigured, and error states
8. **Actionable diagnostics**: Real errors include specific messages (permission, daemon, etc.)

## Verification

To verify the fix on Kibo:

**Expected behavior (socket absent/unconfigured):**
1. Access the Infrastructure page
2. VM section shows: "No virtual machines detected"
3. Subtitle: "No libvirt-managed virtual machines are currently configured on this host. Configure libvirt on this host to monitor virtual machines."
4. This is NOT an error state - it's the normal unconfigured state

**If libvirt is later configured with 0 VMs:**
1. VM section shows: "No virtual machines detected"
2. Subtitle: "No libvirt-managed virtual machines are currently configured on this host." (no "Configure libvirt" prompt)
3. This indicates successful connection with empty inventory

**If libvirt configuration fails (permission/daemon error):**
1. VM section shows error message with diagnostic
2. Subtitle includes actionable error details (e.g., "Permission denied")
3. This is a genuine error state requiring attention

**Docker independence verification:**
1. Ensure Docker containers are visible in Container inventory section
2. VM section shows appropriate empty/unconfigured state
3. Container metrics and health checks remain operational

## Future Considerations

- When libvirt is configured on Kibo, the unconfigured state will transition to available (with 0 VMs initially)
- If libvirt daemon becomes unavailable after being configured, the unavailable state will activate with diagnostics
- The unconfigured and available-with-zero-VMs states are intentionally distinct to avoid claiming successful discovery when none occurred
- Frontend properly distinguishes between "not configured" (shows config hint) and "configured but empty" (no config hint)
