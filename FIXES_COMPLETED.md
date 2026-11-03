# Completed Fixes Summary

**Branch**: `fix/vm-inventory-empty-state`  
**Date**: November 3, 2026

## Two Critical Fixes

### 1. VM Inventory UI - Friendly Static Message

**Problem**: VM section was showing misleading technical error messages when libvirt wasn't configured.

**Solution**: Replaced dynamic backend-driven UI with a simple, friendly static message.

**Changes**:
- **Frontend** (`infrastructure-page.tsx`):
  - Removed vms query and state checking
  - Shows static message: "Virtual machine monitoring is not currently enabled"
  - Explanation: "VM monitoring is planned for a future release. Your Docker containers and host infrastructure continue to be monitored normally."
  - Removed unused `VMRow` component and `VirtualMachineStatus` import

- **Tests** (`infrastructure-page.test.tsx`):
  - Replaced 6 state-dependent tests with 1 simple test
  - Verifies friendly message is always displayed
  - All 31 frontend tests passing

**User Experience**: Users now see a clear, reassuring message instead of confusing error states.

---

### 2. Incident Email Routing - Use Configured Recipients

**Problem**: Incident email notifications weren't reaching both configured server owners.

**Solution**: Changed email routing to use configured notification recipients for ALL incidents (simulated and real).

**Changes**:
- **Backend** (`lab.py`):
  - Line 41: `notify_incident(db, incident, recipients=configured_recipients)` for simulated incidents
  - Line 80: `notify_incident(db, incident, recipients=configured_recipients)` for real incidents
  - Uses `settings.get_incident_notification_emails()` as authoritative source

- **Frontend** (`failure-lab-page.tsx`):
  - Updated checkbox label: "Notify both configured server owners by email"
  - Accurately reflects the new behavior

- **Email Subject**: Already marked `[SIMULATED]` by existing code in `notify_incident()`

**User Experience**: Both configured notification recipients receive emails for all incidents.

---

## Testing Results

✅ **Frontend**: 31/31 tests passing  
✅ **Backend**: 8/8 notification tests passing  
✅ **Lint**: No issues  
✅ **Build**: Successful

## Deployment Instructions

1. Pull the branch: `git pull origin fix/vm-inventory-empty-state`
2. Restart containers:
   ```bash
   docker compose restart frontend backend
   ```
3. No database migrations needed
4. No environment variable changes needed

## Verification Steps

### VM UI:
1. Visit Infrastructure page
2. Scroll to "Virtual machines" section
3. Should see: "Virtual machine monitoring is not currently enabled" message
4. No error states or technical messages

### Email Routing:
1. Go to Failure Lab
2. Check "Notify both configured server owners by email"
3. Click "Simulate alert"
4. Both configured notification recipients should receive email with `[SIMULATED]` in subject

## Production Safety

- ✅ No backend VM monitoring changes
- ✅ No hardcoded email addresses
- ✅ No `.env` modifications required
- ✅ No volume deletions
- ✅ No disruption to running containers
- ✅ Settings page shows: "2 configured notification recipients, 0 configured test recipients"

## Files Modified

1. `backend/app/api/routes/lab.py` - Email routing logic
2. `frontend/src/pages/failure-lab-page.tsx` - UI label
3. `frontend/src/pages/infrastructure-page.tsx` - VM section simplified
4. `frontend/src/pages/infrastructure-page.test.tsx` - Updated tests
