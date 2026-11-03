# Implementation Plan: KiboLens Final Product Polish

This plan implements 8 requirements to transform KiboLens into a polished, interview-ready AI-SRE platform. All changes preserve existing functionality and work incrementally.

## Exploration Summary

The codebase uses:
- **Backend**: FastAPI + SQLAlchemy + PostgreSQL, email via Resend (`app/services/email.py`, `app/services/notifications.py`)
- **Frontend**: React + TanStack Query + Tailwind CSS, no existing modal components
- **Testing**: pytest for backend, vitest for frontend
- **Build**: `npm run build` (frontend), Docker Compose for deployment
- **Key findings**:
  - Interview-demo exists in 3 places: frontend scenario list, backend SCENARIOS set, Docker Compose service
  - Notification system already has idempotent delivery, per-recipient tracking, but UI checkbox controls "both owners"
  - Email templates are basic HTML in `email.py` and `notifications.py`
  - Evidence records store `metric_name`, `metric_value`, `unit` but simulation scenarios aren't populating them
  - Docker observer enriches containers synchronously, blocking on stats/logs
  - No modal/dialog component exists; Settings page uses inline forms
  - VM section already shows correct message per requirement 8

---

## Implementation Plan

- [ ] 1. **Remove interview-demo from Failure Lab UI**
      Remove "interview-demo" from `labScenarios` array in `frontend/src/services/lab.ts`. Remove the recovery button and its mutation from `frontend/src/pages/failure-lab-page.tsx` (lines with `recover.mutate()` and the conditional `{scenario === "interview-demo" && ...}`). Keep backend `/lab/{scenario}/recover` endpoint but add deprecation comment. Document that the `interview-demo` Docker service in `deployment/failure-lab/docker-compose.yml` becomes unused but is preserved for backward compatibility.
      
      **Files**: 
      - `d:\Projects\kibolens\frontend\src\services\lab.ts`
      - `d:\Projects\kibolens\frontend\src\pages\failure-lab-page.tsx`
      - `d:\Projects\kibolens\backend\app\api\routes\lab.py` (add deprecation note)
      
      **Verify**: `npm run build` in frontend succeeds; Failure Lab page renders 9 scenarios without interview-demo; no TypeScript errors.

- [ ] 2. **Make email notifications automatic to both server owners**
      Remove `notify_account` checkbox and its state (`notifyDemo`, `setNotifyDemo`) from `frontend/src/pages/failure-lab-page.tsx`. Always pass `notify_account=true` when calling `labService.start()`. In `backend/app/api/routes/lab.py`, when `notify_account` is true, use `settings.get_incident_notification_emails()` (already returns both configured recipients) and call `notify_incident()` with `recipients=configured_recipients`. Update `backend/app/services/notifications.py` `notify_incident()` to send independently to each recipient with separate try/except blocks, ensuring one failure doesn't block the other. Return per-recipient delivery results as list of `{"recipient": str, "status": str, "error": str | None}`. Update frontend `LabContainer` interface and UI to display per-recipient status in Failure Lab cards.
      
      **Files**:
      - `d:\Projects\kibolens\frontend\src\pages\failure-lab-page.tsx`
      - `d:\Projects\kibolens\frontend\src\services\lab.ts`
      - `d:\Projects\kibolens\backend\app\api\routes\lab.py`
      - `d:\Projects\kibolens\backend\app\services\notifications.py`
      
      **Verify**: Start a Failure Lab scenario, check backend logs show 2 separate email sends to both recipients; UI shows per-recipient status; `pytest backend/tests/` passes.

- [ ] 3. **Redesign all KiboLens emails with professional templates**
      Replace HTML templates in `backend/app/services/email.py` (`send_otp_email`) and `backend/app/services/notifications.py` (`notify_incident`). Use mobile-responsive table-based layout with inline CSS. Color scheme: deep navy/dark charcoal background (`#1a1f2e`), KiboLens cyan accent (`#22d3ee`), white text. Include branded header with "KiboLens" logo text, clear section boxes with rounded corners and subtle borders, severity badges (color-coded: INFO=blue, WARNING=amber, HIGH=orange, CRITICAL=red), metric observation section with observed value/unit/threshold, diagnosis section, prominent "View Incident" button (cyan background, white text, rounded, centered). For OTP emails: centered code box with monospace font, clear expiry time, minimal design. For incident emails: structured sections for summary, affected resource, metric observation (with actual values), diagnosis, action button. All emails must have `[SIMULATED]` in subject and yellow banner in body when `incident.source == "simulation"`. Provide plain-text fallback for all HTML emails.
      
      **Files**:
      - `d:\Projects\kibolens\backend\app\services\email.py`
      - `d:\Projects\kibolens\backend\app\services\notifications.py`
      
      **Verify**: Trigger OTP email and incident email, inspect HTML in email client (Gmail/Outlook); verify mobile responsiveness; check plain-text version renders correctly; `pytest backend/tests/` passes.

- [ ] 4. **Populate correct observed metric values in evidence records**
      In `backend/app/api/routes/lab.py` `start_lab()`, after creating simulated incident, call `service.capture_evidence()` with `evidence_type="HOST_METRIC"` or `"CONTAINER_METRIC"`, passing `metric_name=synthetic.metric_name`, `metric_value=synthetic.metric_value`, `unit=synthetic.unit`, and store `threshold=synthetic.threshold` in metadata. Verify `backend/app/monitoring/simulation.py` `SIMULATION_SCENARIOS` already defines correct values (e.g., high-cpu: 94.2%, critical-memory: 98.7%). Update `backend/app/services/notifications.py` incident email template to use `evidence.metric_value` and `evidence.unit` instead of "No metric value was recorded." Update frontend incident details page to display evidence with metric values.
      
      **Files**:
      - `d:\Projects\kibolens\backend\app\api\routes\lab.py`
      - `d:\Projects\kibolens\backend\app\services\notifications.py`
      - `d:\Projects\kibolens\backend\app\monitoring\simulation.py` (verify, no changes needed)
      
      **Verify**: Start high-cpu scenario, check incident email shows "cpu_utilization=94.2 percent"; query incident evidence API, confirm `metric_value` is populated; `pytest backend/tests/` passes.

- [ ] 5. **Improve Docker container inventory performance**
      **Backend**: In `backend/app/monitoring/docker_observer.py`, refactor `_list_sync()` to separate basic inventory (ID, name, status, image, labels) from expensive enrichment (stats, logs). Return basic inventory immediately, then enrich with stats/logs using `asyncio.gather()` with timeout and exception handling per container (don't fail entire inventory if one container's stats fail). Reduce logs tail from 100 lines to 50 lines, truncate to 6000 chars instead of 12000. Add `_enrich_container_stats()` helper method that returns empty dict on failure. **Frontend**: In `frontend/src/pages/infrastructure-page.tsx`, add pagination state (10 containers per page), render basic inventory as soon as `containers.data` arrives, show loading skeleton for enrichment data. Add "Loading telemetry..." indicator for containers without stats yet. Update loading message to never show "0 Docker container(s)" while `isLoading=true`; instead show "Loading container inventory…" until data arrives.
      
      **Files**:
      - `d:\Projects\kibolens\backend\app\monitoring\docker_observer.py`
      - `d:\Projects\kibolens\frontend\src\pages\infrastructure-page.tsx`
      
      **Verify**: Open Infrastructure page, observe container names/status appear within 1-2 seconds, telemetry loads progressively; verify 9 containers visible (not 0); `pytest backend/tests/` passes; frontend builds successfully.

- [ ] 6. **Create professional confirmation and form modals**
      Create reusable `frontend/src/components/dialog.tsx` component using React portals and `<dialog>` element. Provide `ConfirmDialog` (title, message, onConfirm, onCancel) and `FormDialog` (title, children, onSubmit, onCancel). Style with KiboLens dark theme: zinc-900 background, cyan-400 accents, proper focus trapping, ESC key support, backdrop click-to-close. Use in: sign-out confirmation (replace `window.confirm` if any exists), Failure Lab reset button, Settings test email (optional enhancement). Implement keyboard navigation (Tab, Enter, ESC), ARIA attributes (`role="dialog"`, `aria-modal="true"`, `aria-labelledby`), focus management (focus first button on open, restore focus on close).
      
      **Files**:
      - `d:\Projects\kibolens\frontend\src\components\dialog.tsx` (new)
      - `d:\Projects\kibolens\frontend\src\pages\failure-lab-page.tsx` (use ConfirmDialog for reset)
      - `d:\Projects\kibolens\frontend\src\components\nav.tsx` or equivalent (sign-out confirmation if exists)
      
      **Verify**: Click reset button, see confirmation dialog; ESC closes it; clicking backdrop closes it; Tab cycles through buttons; `npm run build` succeeds; `npm test` passes.

- [ ] 7. **Overall UI polish for consistency**
      **Failure Lab cards**: Ensure consistent heights with `min-h-[200px]`, add severity indicator dots (colored circles), improve notification status display (green for sent, amber for pending, red for failed), consistent spacing (`gap-3` grid, `p-4` cards). **Infrastructure page**: Add loading skeletons (animated pulse boxes) while `isLoading=true`, improve empty state message ("No containers found" with helpful text), consistent severity badges across pages. **Settings page**: Already well-structured, add loading skeleton if needed. **Incident details**: Add severity badge component, consistent metric display format, improve evidence presentation. Create `frontend/src/components/severity-badge.tsx` component for reuse. Add consistent hover/focus states (cyan-300 on hover for links, scale-105 transition for buttons). Ensure responsive breakpoints work correctly (test at 768px, 1024px, 1440px).
      
      **Files**:
      - `d:\Projects\kibolens\frontend\src\components\severity-badge.tsx` (new)
      - `d:\Projects\kibolens\frontend\src\pages\failure-lab-page.tsx`
      - `d:\Projects\kibolens\frontend\src\pages\infrastructure-page.tsx`
      - `d:\Projects\kibolens\frontend\src\pages\settings-page.tsx` (minor tweaks if needed)
      - `d:\Projects\kibolens\frontend\src\pages\incident-details-page.tsx` (if exists)
      
      **Verify**: Visual inspection of all pages at different screen sizes; consistent card heights; smooth transitions; `npm run build` succeeds; `npm run lint` passes.

- [ ] 8. **Preserve VM section with exact message**
      Verify `frontend/src/pages/infrastructure-page.tsx` line 72-76 contains: "Virtual machine monitoring is not currently enabled" with subtext "VM monitoring is planned for a future release. Your Docker containers and host infrastructure continue to be monitored normally." Ensure this section is NOT modified and libvirt errors do NOT reappear. Check backend `backend/app/core/config.py` has `vm_observer_enabled: bool = True` but VM observer is not invoked in infrastructure routes. Document that VM section is intentionally static per user requirement.
      
      **Files**:
      - `d:\Projects\kibolens\frontend\src\pages\infrastructure-page.tsx` (verify only, no changes)
      - `d:\Projects\kibolens\backend\app\core\config.py` (verify only)
      
      **Verify**: Open Infrastructure page, scroll to VM section, confirm exact message appears; no libvirt errors in backend logs; no changes to file timestamps.

- [ ] 9. **Run full test suite and validation**
      Execute all verification commands to ensure production-ready state: `cd backend && pytest` (all tests pass), `cd frontend && npm test` (all tests pass), `cd frontend && npm run lint` (no errors), `cd frontend && npm run build` (successful build), `cd backend && ruff check backend` (lint passes), `docker compose -f deployment/docker-compose.yml config` (validates without errors). Review any test failures and fix before proceeding. Document any skipped tests with rationale.
      
      **Files**: (test files across codebase)
      
      **Verify**: All commands exit with code 0; no test failures; no lint errors; build artifacts created in `frontend/dist`.

---

## Digest

### Files Modified

**Frontend:**
- `frontend/src/services/lab.ts` (line 1): Remove "interview-demo" from `labScenarios` array
- `frontend/src/pages/failure-lab-page.tsx` (lines 7-10): Remove `notifyDemo` state and checkbox; remove recover button (line ~28 conditional block); update `start.mutate` to always notify
- `frontend/src/pages/infrastructure-page.tsx` (lines 20-30): Add pagination, update loading message, progressive telemetry loading
- `frontend/src/components/dialog.tsx` (new): Reusable modal component
- `frontend/src/components/severity-badge.tsx` (new): Consistent severity badges
- Various pages: UI polish (spacing, loading states, consistent styling)

**Backend:**
- `backend/app/api/routes/lab.py` (lines 80-140): Update notification logic to always use configured recipients, capture evidence with metric values, deprecate recover endpoint
- `backend/app/services/notifications.py` (lines 50-110): Redesign email HTML template, independent per-recipient delivery, return per-recipient results
- `backend/app/services/email.py` (lines 40-90): Redesign OTP email template with professional styling
- `backend/app/monitoring/docker_observer.py` (lines 40-120): Separate basic inventory from enrichment, parallelize stats collection

**Verified existing:**
- `backend/app/monitoring/simulation.py`: Already has correct metric values (line 15-27: SIMULATION_SCENARIOS with proper metric_name, metric_value, unit, threshold)
- `frontend/src/pages/infrastructure-page.tsx` (lines 72-76): VM section message already correct

### Test Coverage

- **Backend tests**: `pytest backend/tests/` covers email service, notification service, incident service, lab routes
- **Frontend tests**: `vitest` covers component rendering, no existing tests for new modal component (add tests in step 6)
- **Build verification**: `npm run build` produces optimized production bundle
- **Lint verification**: `ruff check backend` and `npm run lint` ensure code quality

### Build and Test Commands

From repository root `d:\Projects\kibolens`:
- Backend tests: `cd backend && pytest`
- Backend lint: `cd backend && ruff check .`
- Frontend tests: `cd frontend && npm test`
- Frontend lint: `cd frontend && npm run lint`
- Frontend build: `cd frontend && npm run build`
- Docker validation: `docker compose -f deployment/docker-compose.yml config`

### What Was Verified During Exploration

- **Email flow**: Traced from `lab.py` → `notifications.py` → `email.py` → Resend API
- **Evidence storage**: `EvidenceRecord` model has `metric_name`, `metric_value`, `unit` columns (lines 80-85 in `backend/app/models/incident.py`)
- **Notification recipients**: `get_incident_notification_emails()` in `backend/app/core/config.py` (line 165) already returns both configured emails
- **Interview-demo usage**: Found in 3 places (frontend, backend SCENARIOS, Docker Compose)
- **Docker observer bottleneck**: `_list_sync()` enriches synchronously with stats/logs for all containers (lines 40-120 in `docker_observer.py`)
- **Modal absence**: No existing modal component found via file_search
- **VM section**: Already displays correct message (lines 72-76 in `infrastructure-page.tsx`)

### Approach

The plan follows dependency order: remove interview-demo first (isolated change), then notification improvements (affects multiple systems), email redesign (self-contained), metric values (data flow fix), performance optimization (backend then frontend), UI polish (incremental improvements), final validation. Each step leaves the system in a working state. Simulation scenarios remain fully operational. No destructive operations on Docker volumes or production data.
