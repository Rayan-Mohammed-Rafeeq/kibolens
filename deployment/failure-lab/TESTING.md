# Testing Guide - Docker Failure Lab

## Prerequisites

1. **Docker Desktop must be running**
   - Windows: Start Docker Desktop from Start Menu
   - Verify: `docker info` should succeed

2. **Navigate to lab directory**
   ```powershell
   cd d:\Projects\kibolens\deployment\failure-lab
   ```

## Quick Test - Manual

### 1. Validate Configuration
```powershell
docker compose -f docker-compose.yml config --quiet
```
Expected: No errors (version warning is harmless)

### 2. Build All Images
```powershell
docker compose --profile lab build
```
Expected: 7 images built successfully
- kibolens/lab-crasher:latest
- kibolens/lab-unhealthy:latest
- kibolens/lab-restart-loop:latest
- kibolens/lab-cpu-stress:latest
- kibolens/lab-memory-pressure:latest
- kibolens/lab-missing-dependency:latest
- kibolens/lab-config-error:latest

### 3. Test Individual Scenarios

#### Test 1: Crasher
```powershell
docker compose --profile lab up lab-crasher
```
**Expected**: 
- Exits after ~2 seconds
- Exit code 137 (SIGKILL simulation)
- Logs show countdown

**Cleanup**: Automatic (restart: no)

#### Test 2: Unhealthy
```powershell
docker compose --profile lab up -d lab-unhealthy
Start-Sleep -Seconds 20
docker compose --profile lab ps
docker inspect kibolens-lab-unhealthy --format='{{.State.Health.Status}}'
```
**Expected**:
- Container starts and runs
- Health status transitions to "unhealthy" after ~20s
- Health check count increments

**Cleanup**:
```powershell
docker compose --profile lab down
```

#### Test 3: Restart Loop
```powershell
docker compose --profile lab up -d lab-restart-loop
Start-Sleep -Seconds 30
docker inspect kibolens-lab-restart-loop --format='{{.RestartCount}}'
docker compose --profile lab logs lab-restart-loop
```
**Expected**:
- Container crashes and restarts repeatedly
- Restart count > 0 after 30 seconds
- Logs show multiple "crashing" messages

**Cleanup**:
```powershell
docker compose --profile lab down
```

#### Test 4: CPU Stress
```powershell
docker compose --profile lab up lab-cpu-stress
```
**Expected**:
- Runs for 60 seconds
- High CPU usage visible in Docker Desktop or `docker stats`
- Exits cleanly with code 0
- Logs show stress-ng output

**Cleanup**: Automatic

#### Test 5: Memory Pressure
```powershell
docker compose --profile lab up lab-memory-pressure
```
**Expected**:
- Runs for 60 seconds attempting memory allocation
- May be OOM killed (exit 137) or complete (exit 0)
- Memory usage visible in `docker stats`
- Logs show stress-ng attempting allocation

**Cleanup**: Automatic

#### Test 6: Missing Dependency
```powershell
docker compose --profile lab up lab-missing-dependency
docker compose --profile lab logs lab-missing-dependency
```
**Expected**:
- Exits quickly (~3-5 seconds)
- Exit code 127 (command not found) or 1 (connection error)
- Logs show "not found" or "connection refused"

**Cleanup**: Automatic

#### Test 7: Config Error
```powershell
docker compose --profile lab up lab-config-error
docker compose --profile lab logs lab-config-error
```
**Expected**:
- Exits quickly (~2-5 seconds)
- Exit code 78 (EX_CONFIG)
- Logs show "Configuration validation failed"
- Mentions REQUIRED_ENV_VAR missing

**Cleanup**: Automatic

## Automated Test Suite

### Using PowerShell Script

```powershell
# Run all tests
.\test-scenarios.ps1 -Build -Verbose

# Test specific scenario
.\test-scenarios.ps1 -Scenario crasher
.\test-scenarios.ps1 -Scenario unhealthy
.\test-scenarios.ps1 -Scenario cpu-stress

# Test isolation only
.\test-scenarios.ps1 -Scenario isolation

# Build images first
.\test-scenarios.ps1 -Build
```

## Verification Checklist

### Build Phase
- [ ] All 7 Dockerfiles build without errors
- [ ] Images are tagged correctly (kibolens/lab-*)
- [ ] Images are minimal size (<50MB each)

### Runtime Phase
- [ ] Crasher exits with code 137 after delay
- [ ] Unhealthy becomes unhealthy after N checks
- [ ] Restart-loop restarts multiple times
- [ ] CPU-stress generates high CPU load
- [ ] Memory-pressure consumes memory
- [ ] Missing-dependency fails with 127/1
- [ ] Config-error fails with 78

### Isolation Phase
- [ ] Lab network exists and is internal
- [ ] No connections to production services
- [ ] All containers have kibolens.lab=true label
- [ ] Containers run as user 1001:1001
- [ ] CPU limits enforced (NanoCPUs > 0)
- [ ] Memory limits enforced
- [ ] Read-only filesystems where specified
- [ ] No privileged containers
- [ ] Security opts applied (no-new-privileges)

### Production Safety
- [ ] Running `docker compose up` (without --profile lab) starts NO lab containers
- [ ] Lab containers not visible in `docker ps` without explicit profile
- [ ] Production services unaffected by lab network
- [ ] No shared volumes between lab and production

## Integration Testing

### With Prometheus/cAdvisor

1. **Start monitoring stack**:
   ```powershell
   cd d:\Projects\kibolens\deployment
   docker compose --profile monitoring up -d
   ```

2. **Start a lab scenario**:
   ```powershell
   cd failure-lab
   docker compose --profile lab up -d lab-cpu-stress
   ```

3. **Verify metrics collection**:
   ```powershell
   # Check cAdvisor sees container
   curl http://localhost:8080/containers/docker/kibolens-lab-cpu-stress
   
   # Check Prometheus has metrics
   curl "http://localhost:9090/api/v1/query?query=container_last_seen{name='kibolens-lab-cpu-stress'}"
   ```

4. **Query specific metrics**:
   ```promql
   # CPU usage
   rate(container_cpu_usage_seconds_total{name=~"kibolens-lab-.*"}[1m])
   
   # Memory usage
   container_memory_usage_bytes{name=~"kibolens-lab-.*"}
   
   # Container state
   container_state{name=~"kibolens-lab-.*"}
   ```

### With Alertmanager

1. **Trigger alert** by running crasher:
   ```powershell
   docker compose --profile lab up lab-crasher
   ```

2. **Check alerts**:
   ```powershell
   curl http://localhost:9090/api/v1/alerts | jq '.data.alerts[] | select(.labels.container_label_kibolens_lab == "true")'
   ```

3. **Verify notification** (if configured):
   - Check Slack/email for alert
   - Verify alert includes lab labels

## Troubleshooting

### Docker Desktop Not Running
```
Error: failed to connect to docker API
```
**Solution**: Start Docker Desktop, wait for it to fully initialize

### Permission Errors
```
Error: permission denied
```
**Solution**: Ensure Docker Desktop is running with proper permissions

### Build Failures
```
Error: failed to solve
```
**Solution**: 
- Check internet connectivity (pulling alpine:3.19)
- Clear build cache: `docker builder prune`
- Rebuild: `docker compose --profile lab build --no-cache`

### Container Won't Stop
```
Container still running after docker compose down
```
**Solution**:
```powershell
docker stop kibolens-lab-<scenario> --time 1
docker rm kibolens-lab-<scenario>
```

### Resource Limit Errors
```
Error: insufficient resources
```
**Solution**:
- Close other Docker containers
- Check Docker Desktop resource limits
- Run scenarios one at a time

### Network Conflicts
```
Error: network failure-lab_lab already exists
```
**Solution**:
```powershell
docker compose --profile lab down
docker network rm failure-lab_lab
```

## Expected Test Results

### Success Criteria

When all tests pass, you should see:

```
[✓] Docker daemon is running
[✓] Build all scenario images

[✓] Crasher exits with code 137
[✓] Container becomes unhealthy
[✓] Container restarts after crashes
[✓] CPU stress completes successfully
[✓] Memory pressure behaves as expected
[✓] Missing dependency fails as expected
[✓] Config error detected correctly

[✓] Lab network is internal
[✓] Container has lab label
[✓] CPU limit enforced
[✓] Memory limit enforced
[✓] Runs as non-root user

✓ Test suite completed
```

### Known Good Exit Codes

- **Crasher**: 137 (SIGKILL)
- **Unhealthy**: 0 (runs indefinitely)
- **Restart-loop**: 1 (repeated failures)
- **CPU-stress**: 0 (clean exit)
- **Memory-pressure**: 0 or 137 (OOM)
- **Missing-dependency**: 127 or 1
- **Config-error**: 78 (EX_CONFIG)

## Cleanup

### Remove All Lab Resources
```powershell
# Stop and remove containers
docker compose --profile lab down

# Remove images
docker compose --profile lab down --rmi all

# Remove network
docker network rm failure-lab_lab

# Verify cleanup
docker ps -a --filter "label=kibolens.lab=true"
docker images | Select-String "lab"
docker network ls | Select-String "lab"
```

Expected: No lab resources remaining

## Next Steps

After successful testing:

1. **Document results** - Save test output for reference
2. **Integrate with CI** - Add to GitHub Actions workflow
3. **Configure alerts** - Set up Prometheus rules for lab containers
4. **Train AI** - Feed lab incidents to RAG system
5. **Iterate scenarios** - Add new failure patterns as needed

## Support

If issues persist:
- Check Docker Desktop logs
- Review container logs: `docker compose --profile lab logs <service>`
- Verify system resources with `docker system df`
- Check Docker version: `docker --version`
