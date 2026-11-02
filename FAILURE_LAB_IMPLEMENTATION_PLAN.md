# Failure Lab Implementation Plan

## Overview

Building a controlled Docker Failure Lab integrated with existing KiboLens infrastructure for testing incident detection, AI investigation, and RAG-enhanced diagnosis.

## Architecture

### Existing Components (Reuse)
- ✅ Prometheus + Alertmanager (monitoring profile)
- ✅ cAdvisor + node-exporter (metrics)
- ✅ Qdrant (vector database for RAG)
- ✅ Incident API and database models
- ✅ Conversation and AI investigation services
- ✅ Cloud AI router (Gemini → Groq → OpenRouter)
- ✅ Authentication and frontend

### New Components (To Build)
1. **Docker Failure Lab** - Optional `lab` profile with controlled failure scenarios
2. **Lab Observer Service** - Docker event monitoring and incident creation
3. **Enhanced RAG Ingestion** - Infrastructure documents (Dockerfiles, logs, configs)
4. **Lab API** - Scenario control endpoints
5. **Frontend Lab Interface** - Admin UI for scenario management
6. **Enhanced Incident UI** - Investigation integration

## Phase 1: Docker Failure Lab (Core)

### 1.1 Lab Profile Services

**File:** `deployment/docker-compose.yml` (extend)

Add `lab` profile with failure scenarios:

```yaml
profiles: [lab]

services:
  lab-crasher:
    # Exits with non-zero code
    
  lab-unhealthy:
    # Health check fails
    
  lab-stress-cpu:
    # CPU stress test
    
  lab-stress-memory:
    # Memory pressure test
    
  lab-misconfig:
    # Configuration error
    
  lab-missing-dep:
    # Missing dependency
```

**Security Controls:**
- Resource limits on all lab containers
- Isolated `lab` network (no access to kibolens internal)
- No production credentials
- No privileged mode
- No Docker socket access
- Labeled with `kibolens.lab=true`
- Auto-cleanup after duration

### 1.2 Failure Scenarios

Each scenario has:
- **Start trigger:** API call from authenticated admin
- **Duration:** Configurable, max 10 minutes
- **Resource limits:** CPU, memory
- **Lifecycle:** start → fail → stop → cleanup
- **Evidence:** Logs, exit codes, events

**Scenarios:**

1. **crasher** - Container exits immediately (code 137)
2. **unhealthy** - Health check fails after 30s
3. **config-error** - Application config missing/invalid
4. **missing-dep** - Required file/service unavailable
5. **cpu-stress** - Sustained high CPU (stress-ng)
6. **memory-pressure** - Memory allocation until OOM
7. **restart-loop** - Repeatedly crashes and restarts
8. **build-failure** - Dockerfile with syntax error
9. **compose-invalid** - Invalid Compose YAML

### 1.3 Lab Observer Service

**File:** `backend/app/services/lab_observer.py` (new)

Monitors Docker events and creates incidents:

```python
class LabObserver:
    - Monitor container lifecycle events
    - Detect health check failures
    - Capture exit codes and restart counts
    - Collect container logs (last 100 lines)
    - Query Prometheus for metrics
    - Create incident with evidence
    - Update incident on recovery
```

**Integration:**
- Subscribe to Docker events via API (not socket mount)
- Query Docker API for inspection
- Create incidents via existing `IncidentService`
- Label incidents with `source="lab"`

## Phase 2: Enhanced RAG Ingestion

### 2.1 Infrastructure Document Ingestion

**File:** `backend/app/services/infrastructure_rag.py` (new)

Ingest infrastructure docs:

```python
def ingest_dockerfile(path, metadata)
def ingest_compose_yaml(path, metadata)
def ingest_container_logs(container_id, metadata)
def ingest_build_logs(build_id, metadata)
def ingest_runbook(path, metadata)
def ingest_config_file(path, metadata)
```

**Metadata:**
- source_path
- environment (lab, staging, production)
- service_name
- content_hash (deduplication)
- ingestion_timestamp
- file_type

**Exclusions:**
- `.env` files
- `*secret*`, `*credential*`, `*key*`
- `.pem`, `.crt`, `.key` files
- Password/token patterns

### 2.2 Validation Integration

Actual validation, not just indexing:

```python
def validate_dockerfile(path) -> dict:
    # Run: docker build --dry-run or hadolint
    return {"valid": bool, "errors": list, "warnings": list}

def validate_compose(path) -> dict:
    # Run: docker compose config
    return {"valid": bool, "errors": list, "services": list}
```

Store validation results as evidence.

## Phase 3: Incident-Specific Investigation

### 3.1 Incident Context Retrieval

**File:** `backend/app/services/incident_investigation.py` (new)

```python
async def gather_incident_context(incident_id):
    - Get incident details from database
    - Get related Docker events
    - Get container logs
    - Query Prometheus for affected service metrics
    - Search Qdrant for related infrastructure docs
    - Find previous similar incidents
    return comprehensive_context
```

### 3.2 Enhanced AI Investigation

Extend `cloud_investigator.py`:

```python
async def investigate_incident(incident_id, question):
    context = await gather_incident_context(incident_id)
    
    system_prompt = f"""
    INCIDENT: {context.incident}
    EVENTS: {context.events}
    LOGS: {context.logs}
    METRICS: {context.metrics}
    RELATED_DOCS: {context.docs}
    
    Analyze and provide:
    1. Root cause hypothesis
    2. Supporting evidence with timestamps
    3. Affected services
    4. Recommended remediation
    5. Validation steps
    
    NEVER invent metrics or logs. Use only provided data.
    """
    
    return await ai_router.generate(question, system_prompt)
```

## Phase 4: API Endpoints

### 4.1 Lab Control API

**File:** `backend/app/api/routes/lab.py` (new)

```python
POST /api/v1/lab/scenarios                  # List available scenarios
POST /api/v1/lab/scenarios/{scenario}/start # Start a scenario
POST /api/v1/lab/scenarios/{scenario}/stop  # Stop a scenario
GET  /api/v1/lab/status                     # Lab execution status
GET  /api/v1/lab/incidents                  # Lab-generated incidents
```

**Authorization:** Admin only (check `user.role == "admin"`)

### 4.2 Enhanced Incident API

**File:** `backend/app/api/routes/incidents.py` (extend)

```python
POST /api/v1/incidents/{id}/investigate  # Create investigation conversation
GET  /api/v1/incidents/{id}/evidence     # Get all evidence
GET  /api/v1/incidents/{id}/timeline     # Get full event timeline
```

## Phase 5: Frontend

### 5.1 Failure Lab Page

**File:** `frontend/src/pages/lab-page.tsx` (new)

Components:
- Scenario list with descriptions
- Start/Stop buttons (admin only)
- Status indicator (running, stopped)
- Live logs viewer
- Generated incidents list
- Quick link to investigate

### 5.2 Enhanced Incidents Page

**File:** `frontend/src/pages/incidents-page.tsx` (extend)

Add columns:
- Source (alertmanager, lab, manual)
- Environment badge
- Affected container/service
- Investigation button

### 5.3 Incident Investigation Modal

**File:** `frontend/src/components/incident-investigation-dialog.tsx` (new)

Opens existing AI Chat with pre-loaded incident context:
- Incident summary
- Timeline
- Evidence
- Ask AI button
- Chat interface (reuse existing)

## Phase 6: Verification Workflow

### Test Scenario: lab-crasher

1. **Start:** Admin clicks "Start" on crasher scenario
2. **Failure:** Container exits with code 137
3. **Detection:** Lab observer sees exit event
4. **Incident:** Creates INC-XXXXXX with:
   - Title: "Lab: Container Crash (lab-crasher)"
   - Source: "lab"
   - Severity: "WARNING"
   - Evidence: exit code, logs, events
5. **Investigation:** User clicks "Investigate"
6. **AI Analysis:** 
   - "Container exited with code 137 (SIGKILL)"
   - "Exit code indicates forceful termination"
   - "Container logs show: [actual log]"
   - "Recommendation: Check entrypoint script"
7. **Fix:** Admin updates Dockerfile
8. **Restart:** Container runs successfully
9. **Recovery:** Incident status → RESOLVED

### Test All Scenarios

Run full suite:
```bash
# Start all scenarios
for scenario in crasher unhealthy cpu-stress memory-pressure config-error; do
  curl -X POST /api/v1/lab/scenarios/$scenario/start
  sleep 60
done

# Verify incidents created
curl /api/v1/incidents?source=lab

# Test AI investigation on each
for incident_id in $incidents; do
  curl -X POST /api/v1/incidents/$incident_id/investigate \
    -d '{"question": "What caused this failure?"}'
done
```

## Security Controls

### Isolation
- ✅ Separate `lab` network (no kibolens access)
- ✅ No production credentials in lab containers
- ✅ No Docker socket mounts
- ✅ No privileged mode
- ✅ Read-only root filesystem where possible

### Resource Limits
- ✅ CPU: max 0.5 per container
- ✅ Memory: max 256MB per container
- ✅ Duration: max 10 minutes
- ✅ Restart: max 3 times

### Access Control
- ✅ Lab API: admin role required
- ✅ Investigation: authenticated users only
- ✅ Lab profile: explicit activation required

### Cleanup
- ✅ Auto-stop after duration
- ✅ Remove stopped containers
- ✅ Clear temporary volumes
- ✅ Reset state

## Implementation Order

1. ✅ Review existing architecture (done)
2. ⏳ Create lab scenarios in docker-compose.yml
3. ⏳ Implement lab observer service
4. ⏳ Add lab control API endpoints
5. ⏳ Enhance RAG with infrastructure docs
6. ⏳ Extend incident investigation
7. ⏳ Build frontend lab interface
8. ⏳ Add incident investigation UI
9. ⏳ Test complete workflow
10. ⏳ Run all tests and build

## Files to Create/Modify

### New Files (15)
- `deployment/lab/` - Lab scenario Dockerfiles
- `backend/app/services/lab_observer.py`
- `backend/app/services/infrastructure_rag.py`
- `backend/app/services/incident_investigation.py`
- `backend/app/api/routes/lab.py`
- `backend/app/schemas/lab.py`
- `backend/tests/test_lab.py`
- `frontend/src/pages/lab-page.tsx`
- `frontend/src/components/lab-scenario-card.tsx`
- `frontend/src/components/incident-investigation-dialog.tsx`
- `frontend/src/services/lab.ts`
- `frontend/src/types/lab.ts`
- `monitoring/prometheus/rules/lab.rules.yml`
- `docs/FAILURE_LAB.md`
- `FAILURE_LAB_IMPLEMENTATION_PLAN.md` (this file)

### Modified Files (8)
- `deployment/docker-compose.yml` - Add lab profile
- `backend/app/ai/cloud_investigator.py` - Add incident context
- `backend/app/api/routes/incidents.py` - Add investigate endpoint
- `backend/app/api/router.py` - Register lab routes
- `frontend/src/pages/incidents-page.tsx` - Add investigation button
- `frontend/src/App.tsx` - Add lab route
- `frontend/src/services/incidents.ts` - Add investigate method
- `README.md` - Document lab feature

## Estimated Complexity

- **Docker Lab:** Medium (profile, scenarios, resource limits)
- **Lab Observer:** High (Docker API, event handling, async)
- **RAG Enhancement:** Medium (file parsing, validation)
- **Incident Investigation:** High (context gathering, AI integration)
- **API Endpoints:** Medium (CRUD, authorization)
- **Frontend:** Medium (new pages, components)
- **Testing:** High (integration tests, workflow validation)

**Total:** ~2000-2500 lines of new code

## Current Status

✅ Architecture reviewed
✅ Implementation plan created
⏳ Ready to begin implementation

## Next Steps

1. Create lab profile in docker-compose.yml
2. Build lab scenario containers
3. Implement lab observer service
4. Add API endpoints
5. Build frontend interface
6. Test complete workflow
