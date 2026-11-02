# Quick Fix Guide - KiboLens Issues

## 🔴 Issues You're Seeing

1. **AI Chat**: "The provider stopped at its output-token limit"
2. **Incidents Page**: "Incident storage is unavailable"  
3. **Infrastructure Page**: "Optional libvirt Python binding is unavailable"

## ✅ Quick Fix (Copy-Paste)

**Prerequisites**: Docker Desktop must be running

```powershell
# 1. Navigate to project
cd d:\Projects\kibolens\deployment

# 2. Run automated fix script
.\fix-issues.ps1 -Verbose
```

That's it! The script will:
- ✅ Run database migrations (fixes Incidents page)
- ✅ Adjust token limits (fixes AI chat truncation)
- ✅ Restart backend automatically
- ✅ Verify fixes worked

## 🔧 Manual Fix (If Script Fails)

### Fix 1: Database Migrations (CRITICAL)

```powershell
cd d:\Projects\kibolens\deployment

# Run migrations
docker compose exec backend alembic upgrade head

# Verify incident tables
docker compose exec postgres psql -U kibolens -d kibolens -c "\dt incident*"
```

**Expected output**:
```
incident_events
incident_sequences  
incidents
```

### Fix 2: Token Limits (HIGH PRIORITY)

Edit `deployment/.env`:

```env
# Add this line (or update if exists)
KIBOLENS_LLM_MAX_TOKENS=4000
```

Then restart:

```powershell
docker compose restart backend
```

### Fix 3: VM Monitoring (INFORMATIONAL)

The "libvirt unavailable" message is **expected on Windows**. This is not an error.

VM monitoring requires libvirt (Linux/WSL2 only). To hide the message, disable VM observer:

```env
# In deployment/.env
KIBOLENS_VM_OBSERVER_ENABLED=false
```

## 🧪 Verify Fixes

### Test 1: Incidents Page
```
URL: http://localhost:5173/incidents
Expected: Shows empty list or incidents (no error)
```

### Test 2: AI Chat
```
URL: http://localhost:5173/ai-chat
Expected: Complete responses, no truncation warning
```

### Test 3: Infrastructure
```
URL: http://localhost:5173/infrastructure
Expected: Shows containers, no crashes
```

## 🚨 Troubleshooting

### Script Says "Backend must be running"

```powershell
cd deployment
docker compose up -d backend
# Wait 10 seconds
.\fix-issues.ps1
```

### Docker Desktop Not Running

```
Error: failed to connect to docker API
```

**Fix**: Start Docker Desktop from Windows Start Menu, wait for "Docker Desktop is running"

### Migrations Still Fail

Check database logs:

```powershell
docker compose logs postgres | Select-Object -Last 30
docker compose logs backend | Select-Object -Last 30
```

### Token Limit Still Causing Truncation

Reduce further:

```env
# In deployment/.env
KIBOLENS_LLM_MAX_TOKENS=2000
```

Restart backend:
```powershell
docker compose restart backend
```

## 📊 What Changed

### Code Changes Made
- ✅ `backend/app/core/config.py` - Changed default token limit 8000 → 4000

### Files Created
- ✅ `deployment/fix-issues.ps1` - Automated fix script
- ✅ `FIXES_FOR_ISSUES.md` - Detailed explanation
- ✅ `QUICK_FIX_GUIDE.md` - This file

### Runtime Changes (Script Does This)
- ✅ Runs database migrations
- ✅ Creates/updates `deployment/.env` with token limit
- ✅ Restarts backend container

## 💡 Why These Issues Occurred

**Issue 1 (Token Limits)**: 
- Default was 8000 tokens
- Some providers (OpenRouter, Groq) have limits around 4096-8000
- Hitting exact limit causes truncation
- Now: Default 4000 with safety margin

**Issue 2 (Incidents Database)**:
- Migrations existed but weren't run
- Incident tables never created
- Now: Script runs `alembic upgrade head`

**Issue 3 (VM Monitoring)**:
- libvirt-python not available on Windows
- Code correctly handles this with fallback
- Message is informational, not error
- Now: Documented as expected behavior

## 🎯 Priority Order

1. **MUST FIX**: Database migrations (Incidents broken)
2. **SHOULD FIX**: Token limits (AI truncated)
3. **OPTIONAL**: VM observer message (informational only)

## ⏱️ Time Required

- Automated script: **~30 seconds**
- Manual fixes: **~2 minutes**
- Verification: **~1 minute**

**Total**: 3 minutes to fully resolve

## 📞 Still Having Issues?

Check logs:

```powershell
cd deployment

# Backend logs
docker compose logs backend -f

# Database logs  
docker compose logs postgres -f

# All services status
docker compose ps
```

Look for:
- Database connection errors
- Migration failures
- API startup errors
- Token configuration not loading

## ✅ Success Indicators

After fixes, you should see:

```
✓ Incidents page loads without errors
✓ AI chat responses complete fully  
✓ Infrastructure page shows container stats
✓ No database connection errors in logs
```

---

**Quick Command Reference**:

```powershell
# Fix everything automatically
cd d:\Projects\kibolens\deployment
.\fix-issues.ps1 -Verbose

# Verify backend is running
docker compose ps backend

# Check backend logs
docker compose logs backend --tail 50

# Test incidents API
curl http://localhost:8000/api/v1/incidents

# Restart everything if needed
docker compose restart
```
