# KiboLens Issue Fixes

## Issues Identified from Screenshots

### Issue 1: AI Chat Incomplete Responses ⚠️
**Symptom**: "The provider stopped at its output-token limit. The content above is the complete provider response but may be incomplete."

**Root Cause**: The `llm_max_tokens` setting (8000) may exceed some providers' actual limits, causing truncation.

**Impact**: AI investigation responses are cut off mid-analysis.

### Issue 2: Virtual Machines Section Error ⚠️
**Symptom**: "Optional libvirt Python binding is unavailable."

**Root Cause**: Missing `libvirt-python` package in requirements.txt

**Impact**: VM monitoring completely unavailable (shows error on Infrastructure page).

### Issue 3: Incidents Page Database Error 🔴
**Symptom**: "Could not load incidents - Incident storage is unavailable. Verify the database and run migrations."

**Root Cause**: Database migrations exist but haven't been run in deployment.

**Impact**: Incident management feature completely broken.

---

## Fixes

### Fix 1: Add libvirt-python to Requirements

**File**: `backend/requirements.txt`

**Action**: Add libvirt-python as optional dependency with error handling.

```diff
+ # Optional VM monitoring
+ libvirt-python==11.1.0
```

**Note**: libvirt-python requires system libvirt libraries. On systems without libvirt, the code already handles ImportError gracefully and shows the "unavailable" message, which is correct behavior. Adding the package makes it available where libvirt IS installed.

**Alternative**: If libvirt should truly be optional, keep current behavior and document that VM monitoring requires manual `pip install libvirt-python` on libvirt-enabled hosts.

### Fix 2: Run Database Migrations

**Problem**: Incident tables don't exist in database despite migrations being present.

**Solution**: Run Alembic migrations in deployment.

```bash
# From deployment directory with Docker Desktop running
docker compose exec backend alembic upgrade head
```

**OR** Add migration step to docker-compose.yml healthcheck/startup:

```yaml
# In deployment/Dockerfiles/backend.Dockerfile
# Add migration command to entrypoint
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
```

### Fix 3: Adjust LLM Token Limits (Configuration)

**File**: `.env` or `backend/.env`

**Current Default**: `KIBOLENS_LLM_MAX_TOKENS=8000`

**Recommended**: 
```env
KIBOLENS_LLM_MAX_TOKENS=4000
```

**Rationale**: 
- Gemini Flash models: 8192 output tokens (we're under limit)
- Groq Llama models: 8000 output tokens (we're AT limit)
- OpenRouter varies by model (many are 4096)

Setting to 4000 provides safety margin and is sufficient for most investigations.

**Better Fix**: Add per-provider token limits in router logic (already partially implemented).

---

## Step-by-Step Resolution

### Prerequisites
1. **Start Docker Desktop**
2. Navigate to project: `cd d:\Projects\kibolens`

### Step 1: Fix Requirements (Optional VM Support)

```powershell
# Add libvirt-python to requirements.txt
# This makes VM monitoring work on libvirt-enabled systems
# On Windows without libvirt, it will fail gracefully (current behavior)
```

**Decision needed**: 
- Add `libvirt-python==11.1.0` to requirements.txt?
- OR keep it truly optional and document manual installation?

**Recommendation**: Keep optional. The error message is correct - libvirt IS unavailable on Windows without WSL2+libvirt setup.

### Step 2: Fix Database Migrations (CRITICAL)

```powershell
# Check current migration status
cd deployment
docker compose exec backend alembic current

# Run pending migrations
docker compose exec backend alembic upgrade head

# Verify incident tables exist
docker compose exec postgres psql -U kibolens -d kibolens -c "\dt incidents*"
```

**Expected output**:
```
                    List of relations
 Schema |         Name          | Type  |  Owner   
--------+-----------------------+-------+----------
 public | incident_events       | table | kibolens
 public | incident_sequences    | table | kibolens
 public | incidents             | table | kibolens
```

### Step 3: Adjust Token Limits (RECOMMENDED)

**Option A: Environment Variable** (Quick fix)
```powershell
# Edit deployment/.env
# Add or modify:
KIBOLENS_LLM_MAX_TOKENS=4000
```

**Option B: Fix in Code** (Better fix)
```python
# backend/app/core/config.py
# Change default from 8000 to 4000
llm_max_tokens: int = Field(default=4000, ge=100, le=32000)
```

### Step 4: Restart Backend

```powershell
cd deployment
docker compose restart backend

# Check logs for startup success
docker compose logs backend | Select-Object -Last 30
```

### Step 5: Verify Fixes

1. **Check Incidents Page**:
   - Navigate to http://localhost:5173/incidents
   - Should show empty list or existing incidents
   - No "storage unavailable" error

2. **Check Infrastructure Page**:
   - Navigate to http://localhost:5173/infrastructure
   - Virtual Machines section should show "VM monitoring is disabled" (correct for Windows)
   - OR show "Optional libvirt Python binding is unavailable" (acceptable)
   - Should NOT crash the page

3. **Check AI Chat**:
   - Start new investigation
   - Verify responses complete without truncation
   - If still truncated, reduce token limit further

---

## Detailed Migration Fix Script

Create `deployment/run-migrations.sh`:

```bash
#!/bin/bash
set -e

echo "Running KiboLens database migrations..."

# Wait for postgres to be ready
until docker compose exec -T postgres pg_isready -U kibolens; do
  echo "Waiting for Postgres..."
  sleep 2
done

echo "Postgres ready. Running Alembic migrations..."
docker compose exec -T backend alembic upgrade head

echo "✓ Migrations complete"
echo ""
echo "Verifying incident tables..."
docker compose exec -T postgres psql -U kibolens -d kibolens -c "\dt incident*"
```

**Usage**:
```powershell
cd deployment
bash run-migrations.sh
```

---

## Testing After Fixes

### Test 1: Incident Management

```powershell
# Create test incident via API
curl -X POST http://localhost:8000/api/v1/incidents \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Test incident",
    "description": "Testing incident creation",
    "severity": "HIGH",
    "source": "manual"
  }'

# Check incidents page
# Should show test incident
```

### Test 2: AI Chat Token Limits

```powershell
# Trigger investigation
# Watch for response completion
# Should NOT see "output-token limit" message
```

### Test 3: Infrastructure Page

```powershell
# Navigate to /infrastructure
# Should NOT crash
# VM section should show appropriate message
```

---

## Priority Order

1. **CRITICAL**: Fix database migrations (Incidents completely broken)
2. **HIGH**: Adjust token limits (AI responses incomplete)
3. **LOW**: libvirt-python (Expected behavior on Windows without libvirt)

---

## Quick Fix Commands (Copy-Paste Ready)

```powershell
# 1. Ensure Docker Desktop is running
docker info

# 2. Navigate to deployment
cd d:\Projects\kibolens\deployment

# 3. Run migrations
docker compose exec backend alembic upgrade head

# 4. Verify incident tables
docker compose exec postgres psql -U kibolens -d kibolens -c "\dt incident*"

# 5. Edit .env to reduce token limit
# Add: KIBOLENS_LLM_MAX_TOKENS=4000

# 6. Restart backend
docker compose restart backend

# 7. Test incidents page
Start-Process "http://localhost:5173/incidents"

# 8. Test infrastructure page  
Start-Process "http://localhost:5173/infrastructure"
```

---

## Expected Results After Fixes

✅ **Incidents Page**: Shows incident list (may be empty), no errors  
✅ **AI Chat**: Complete responses without truncation warnings  
✅ **Infrastructure Page**: Shows containers, VMs section shows "unavailable" message (acceptable)  
✅ **Backend Logs**: No database connection errors  

---

## If Issues Persist

### Incident Storage Still Unavailable

```powershell
# Check migration status
docker compose exec backend alembic current

# Check database tables
docker compose exec postgres psql -U kibolens -d kibolens -c "\d"

# Verify database connection
docker compose logs backend | Select-String "database"
```

### AI Responses Still Truncated

```powershell
# Check current token setting
docker compose exec backend python -c "from app.core.config import Settings; print(Settings().llm_max_tokens)"

# Reduce further if needed
# In .env: KIBOLENS_LLM_MAX_TOKENS=2000
```

### VM Section Still Errors

```powershell
# Check if VM observer is disabled
docker compose exec backend python -c "from app.core.config import Settings; print(Settings().vm_observer_enabled)"

# Disable VM observer entirely in .env
# Add: KIBOLENS_VM_OBSERVER_ENABLED=false
```

---

## Summary

The three issues have clear fixes:

1. **Incidents database**: Run `alembic upgrade head` 
2. **Token limits**: Set `KIBOLENS_LLM_MAX_TOKENS=4000`
3. **libvirt unavailable**: Expected on Windows, informational message is correct

Most critical is #1 (database migrations). This should be run immediately.
