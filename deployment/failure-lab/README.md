# Docker Failure Lab

Isolated testing environment for validating KiboLens monitoring, alerting, and AI investigation capabilities under controlled failure conditions.

## Overview

The Docker Failure Lab provides 7 distinct failure scenarios in completely isolated containers. These scenarios simulate real-world infrastructure failures to test:

- Prometheus metric collection and alerting rules
- Alertmanager notification delivery
- AI incident investigation and root cause analysis
- Evidence collection and RAG retrieval
- Incident lifecycle management

## Architecture

### Isolation Guarantees

The lab environment is **completely isolated** from production:

- ✅ Separate `lab` network with `internal: true` (no external access)
- ✅ No connections to production databases, Qdrant, or application services
- ✅ No access to production credentials or `.env` files
- ✅ Non-privileged containers (user 1001:1001)
- ✅ No Docker socket mounting
- ✅ Read-only filesystems where practical
- ✅ Strict resource limits (CPU, memory, PIDs)
- ✅ Profile-based activation (`--profile lab` required)
- ✅ All resources labeled `kibolens.lab=true`

### Security Controls

Every scenario container enforces:

```yaml
user: "1001:1001"              # Non-root execution
read_only: true                # Immutable filesystem
security_opt:
  - no-new-privileges:true     # Prevent privilege escalation
cap_drop:
  - ALL                        # Drop all capabilities
deploy:
  resources:
    limits:
      cpus: '0.1-0.5'          # CPU throttling
      memory: 32M-64M          # Memory limits
      pids: 10-20              # Process limits
```

## Scenarios

### 1. Crasher - Immediate Exit

**Purpose**: Test detection of containers that exit immediately with non-zero codes.

**Behavior**:
- Exits after configurable delay with specified exit code
- Default: exit 137 (SIGKILL simulation) after 2 seconds

**Configuration**:
```bash
LAB_CRASHER_EXIT_CODE=137    # Exit code to return
LAB_CRASHER_DELAY=2          # Seconds before exit
```

**Expected Metrics**:
- `container_last_seen` stops updating
- `container_state{state="exited"}` = 1
- Exit code visible in container inspect

**Usage**:
```bash
docker compose --profile lab up lab-crasher
```

### 2. Unhealthy - Failing Health Checks

**Purpose**: Test detection of services failing health checks.

**Behavior**:
- Passes first N health checks
- Fails all subsequent checks
- Transitions to "unhealthy" state

**Configuration**:
```bash
LAB_UNHEALTHY_FAIL_AFTER=3   # Pass first N checks, then fail
```

**Expected Metrics**:
- `container_health_status{status="unhealthy"}` = 1
- Health check failures increment

**Usage**:
```bash
docker compose --profile lab up lab-unhealthy
# Wait ~20 seconds for unhealthy state
docker compose --profile lab ps
```

### 3. Restart Loop - Repeated Crashes

**Purpose**: Test detection of containers in crash loops.

**Behavior**:
- Runs for configured duration, then crashes
- Docker restart policy triggers (max 5 attempts)
- Eventually enters "restarting" state

**Configuration**:
```bash
LAB_RESTART_CRASH_AFTER=10   # Seconds before crash
LAB_RESTART_EXIT_CODE=1      # Exit code on crash
```

**Expected Metrics**:
- `container_state{state="restarting"}` = 1
- High restart count
- Repeated exit events

**Usage**:
```bash
docker compose --profile lab up lab-restart-loop
# Observe restart count increment
docker compose --profile lab ps
```

### 4. CPU Stress - High CPU Load

**Purpose**: Test detection of CPU exhaustion.

**Behavior**:
- Spawns CPU-bound workers using `stress-ng`
- Runs for configured duration, then exits cleanly
- Hits CPU limits (0.5 cores)

**Configuration**:
```bash
LAB_CPU_WORKERS=2            # Number of CPU workers
LAB_CPU_DURATION=60          # Duration in seconds
```

**Expected Metrics**:
- `container_cpu_usage_seconds_total` rate increases
- CPU throttling metrics spike
- `container_spec_cpu_quota` enforcement

**Usage**:
```bash
docker compose --profile lab up lab-cpu-stress
# Monitor CPU metrics in Prometheus/Grafana
```

### 5. Memory Pressure - Memory Exhaustion

**Purpose**: Test detection of memory pressure and OOM kills.

**Behavior**:
- Allocates memory in workers using `stress-ng`
- Attempts to exceed 64M limit
- May be OOM killed by kernel

**Configuration**:
```bash
LAB_MEM_WORKERS=1            # Number of memory workers
LAB_MEM_PER_WORKER=48M       # Memory per worker
LAB_MEM_DURATION=60          # Duration in seconds
```

**Expected Metrics**:
- `container_memory_usage_bytes` approaches limit
- `container_memory_failures_total` increments
- Possible OOM kill (exit code 137)

**Usage**:
```bash
docker compose --profile lab up lab-memory-pressure
# Watch for OOM kill
docker compose --profile lab logs lab-memory-pressure
```

### 6. Missing Dependency - Startup Failure

**Purpose**: Test detection of containers failing due to missing dependencies.

**Behavior**:
- Attempts to execute non-existent command
- Fails with "command not found" or "connection refused"
- Exits with code 127 or 1

**Configuration**:
```bash
LAB_MISSING_CMD=postgresql   # Command to attempt
LAB_MISSING_DELAY=3          # Seconds before failure
```

**Expected Metrics**:
- Container exits quickly with code 127
- Logs show dependency errors
- Never reaches "running" state

**Usage**:
```bash
docker compose --profile lab up lab-missing-dependency
docker compose --profile lab logs lab-missing-dependency
```

### 7. Configuration Error - Invalid Config

**Purpose**: Test detection of misconfiguration at startup.

**Behavior**:
- Validates required environment variables
- Checks for expected configuration files
- Exits with code 78 (EX_CONFIG)

**Configuration**:
```bash
REQUIRED_ENV_VAR=""          # Intentionally empty
LAB_CONFIG_FILE=/config/app.conf
LAB_CONFIG_DELAY=2
```

**Expected Metrics**:
- Container exits with code 78
- Logs show configuration validation errors
- Quick failure pattern

**Usage**:
```bash
docker compose --profile lab up lab-config-error
docker compose --profile lab logs lab-config-error
```

## Usage Guide

### Prerequisites

- Docker Engine 20.10+ with Compose V2
- KiboLens monitoring stack deployed (Prometheus, Alertmanager, Grafana)
- Sufficient resources: 2GB RAM, 2 CPU cores available

### Running Individual Scenarios

```bash
# Navigate to failure lab directory
cd deployment/failure-lab

# Run specific scenario
docker compose --profile lab up lab-crasher

# Run in background
docker compose --profile lab up -d lab-cpu-stress

# View logs
docker compose --profile lab logs -f lab-unhealthy

# Stop scenario
docker compose --profile lab down lab-restart-loop
```

### Running Multiple Scenarios

```bash
# Run several scenarios simultaneously
docker compose --profile lab up lab-crasher lab-unhealthy lab-cpu-stress

# Stop all lab containers
docker compose --profile lab down
```

### Environment Variable Configuration

Create `deployment/failure-lab/.env` (optional):

```bash
# Crasher
LAB_CRASHER_EXIT_CODE=137
LAB_CRASHER_DELAY=2

# Unhealthy
LAB_UNHEALTHY_FAIL_AFTER=3

# Restart Loop
LAB_RESTART_CRASH_AFTER=10
LAB_RESTART_EXIT_CODE=1

# CPU Stress
LAB_CPU_WORKERS=2
LAB_CPU_DURATION=60

# Memory Pressure
LAB_MEM_WORKERS=1
LAB_MEM_PER_WORKER=48M
LAB_MEM_DURATION=60

# Missing Dependency
LAB_MISSING_CMD=postgresql
LAB_MISSING_DELAY=3

# Config Error
LAB_CONFIG_FILE=/config/app.conf
LAB_CONFIG_DELAY=2
```

### Building Images

```bash
# Build all scenario images
docker compose --profile lab build

# Build specific scenario
docker compose --profile lab build lab-crasher

# Rebuild without cache
docker compose --profile lab build --no-cache
```

## Testing Workflow

### 1. Validate Configuration

```bash
# Verify compose syntax
docker compose -f docker-compose.yml config

# Check for profile isolation
docker compose config | grep -A5 "profile"
```

### 2. Build Scenarios

```bash
cd deployment/failure-lab
docker compose --profile lab build
```

### 3. Test Individual Scenarios

```bash
# Test crasher
docker compose --profile lab up lab-crasher
# Expected: exits with code 137 after 2 seconds

# Test unhealthy
docker compose --profile lab up -d lab-unhealthy
sleep 20
docker compose --profile lab ps
# Expected: health status shows "unhealthy"

# Test restart loop
docker compose --profile lab up -d lab-restart-loop
sleep 30
docker inspect kibolens-lab-restart-loop --format='{{.RestartCount}}'
# Expected: restart count > 0

# Test CPU stress
docker compose --profile lab up lab-cpu-stress
# Expected: high CPU usage for 60 seconds, clean exit

# Test memory pressure
docker compose --profile lab up lab-memory-pressure
# Expected: memory usage spikes, possible OOM

# Test missing dependency
docker compose --profile lab up lab-missing-dependency
# Expected: exits with 127, logs show "command not found"

# Test config error
docker compose --profile lab up lab-config-error
# Expected: exits with 78, logs show validation errors
```

### 4. Verify Isolation

```bash
# Verify lab network exists and is internal
docker network inspect failure-lab_lab | jq '.[0].Internal'
# Expected: true

# Verify no production service connections
docker network inspect failure-lab_lab | jq '.[0].Containers'
# Expected: only lab-* containers

# Verify resource limits
docker inspect kibolens-lab-cpu-stress | jq '.[0].HostConfig.NanoCpus'
# Expected: 500000000 (0.5 CPU)
```

### 5. Verify Prometheus Integration

```bash
# Check that cAdvisor sees lab containers
curl -s http://localhost:8080/metrics | grep 'container_last_seen.*kibolens-lab'

# Verify Prometheus scrapes lab metrics
curl -s http://localhost:9090/api/v1/query?query=container_last_seen | \
  jq '.data.result[] | select(.metric.name | contains("lab"))'
```

### 6. Clean Up

```bash
# Stop all lab containers
docker compose --profile lab down

# Remove images (optional)
docker compose --profile lab down --rmi all

# Verify clean state
docker ps -a --filter "label=kibolens.lab=true"
# Expected: no containers
```

## Integration with KiboLens

### Prometheus Scraping

Lab containers are discovered via cAdvisor:
- Exposed via cAdvisor on existing monitoring port
- Labeled with `kibolens.lab=true` for filtering
- Metrics available under `container_*` namespace

### Alert Testing

Trigger alerts by running scenarios:

```bash
# Trigger ContainerDown alert
docker compose --profile lab up lab-crasher

# Trigger ContainerUnhealthy alert
docker compose --profile lab up -d lab-unhealthy

# Trigger HighCPU alert
docker compose --profile lab up lab-cpu-stress

# Trigger HighMemory alert
docker compose --profile lab up lab-memory-pressure
```

### AI Investigation Testing

After alerts fire:

1. Check incident creation in database
2. Verify evidence collection includes lab container logs
3. Confirm RAG retrieval of relevant lab documentation
4. Validate AI analysis identifies lab scenario correctly

Query example:
```python
# In backend Python shell
from app.services.conversations import trigger_investigation

incident_id = 123  # From alert
await trigger_investigation(incident_id, db)
```

## Fixtures for Testing

### Invalid Dockerfile

Test build failure detection:

```bash
docker build -f fixtures/invalid.Dockerfile -t test-invalid .
# Expected: build fails with syntax errors
```

### Invalid Compose File

Test compose validation:

```bash
docker compose -f fixtures/invalid-compose.yml config
# Expected: validation errors reported
```

## Safety and Limitations

### What This Lab IS

- ✅ Isolated testing environment for monitoring and alerting
- ✅ Safe way to generate controlled failure events
- ✅ Resource-constrained and time-bounded scenarios
- ✅ Labeled and discoverable for automated testing

### What This Lab IS NOT

- ❌ Production infrastructure simulation
- ❌ Load testing or performance benchmarking tool
- ❌ Replacement for proper staging environments
- ❌ Network failure or partition simulator (requires external tools)

### Resource Usage

All scenarios combined:
- CPU: ~1.5 cores peak
- Memory: ~256MB peak
- Disk: ~500MB images
- Network: Minimal (internal only)

### Time Bounds

- Crasher: 2-5 seconds
- Unhealthy: 20-30 seconds to unhealthy state
- Restart Loop: 60-90 seconds until max retries
- CPU Stress: 60 seconds default
- Memory Pressure: 60 seconds default
- Missing Dependency: 3-5 seconds
- Config Error: 2-5 seconds

## Troubleshooting

### Scenario Won't Start

```bash
# Check profile is specified
docker compose --profile lab up lab-crasher

# Verify image built
docker compose --profile lab build lab-crasher

# Check logs
docker compose --profile lab logs lab-crasher
```

### Can't See Metrics

```bash
# Verify cAdvisor is running
docker ps | grep cadvisor

# Check cAdvisor exposes lab containers
curl http://localhost:8080/containers

# Verify Prometheus scrape config includes cAdvisor
curl http://localhost:9090/api/v1/targets
```

### Resource Limit Errors

```bash
# Check available resources
docker system df
docker stats --no-stream

# Reduce concurrent scenarios
# Run one at a time instead of multiple
```

### Network Isolation Issues

```bash
# Verify lab network is internal
docker network inspect failure-lab_lab | jq '.[0].Internal'

# Check no unexpected bridges
docker network ls --filter "label=kibolens.lab=true"
```

## Development

### Adding New Scenarios

1. Create `scenarios/new-scenario.sh` script
2. Create `scenarios/new-scenario.Dockerfile`
3. Add service definition to `docker-compose.yml`
4. Update this README with scenario documentation
5. Add tests to validation suite

### Testing Framework Integration

For automated testing:

```python
# tests/integration/test_failure_lab.py
import pytest
from dockercompose import DockerCompose

@pytest.fixture
def lab():
    compose = DockerCompose("deployment/failure-lab", profile="lab")
    yield compose
    compose.down()

def test_crasher_exits(lab):
    lab.up("lab-crasher")
    exit_code = lab.wait("lab-crasher", timeout=10)
    assert exit_code == 137

def test_unhealthy_detected(lab):
    lab.up("lab-unhealthy", detach=True)
    time.sleep(20)
    health = lab.inspect("lab-unhealthy", format="{{.State.Health.Status}}")
    assert health == "unhealthy"
```

## References

- [Docker Compose Profiles](https://docs.docker.com/compose/profiles/)
- [Container Resource Constraints](https://docs.docker.com/config/containers/resource_constraints/)
- [Docker Security Best Practices](https://docs.docker.com/engine/security/)
- [Prometheus Container Metrics](https://prometheus.io/docs/instrumenting/exposition_formats/)
- [KiboLens Architecture](../../docs/ARCHITECTURE.md)

## License

Part of KiboLens infrastructure monitoring platform.
