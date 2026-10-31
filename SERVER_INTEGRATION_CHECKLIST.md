# KiboLens Server Integration Checklist
## Phase 4 - Incident Management System

**Target Server:** Kibo (Ubuntu server)  
**Integration Date:** TBD  
**Status:** Ready for integration approval

---

## Prerequisites

### 1. Server Requirements

#### Hardware Specifications
- [  ] Lenovo ThinkCentre M91p available
- [  ] Minimum 12 GB RAM confirmed
- [  ] Sufficient disk space for PostgreSQL and logs (recommend 20GB+ free)
- [  ] Intel i5 processor confirmed

#### Software Requirements
- [  ] Ubuntu Server installed and updated
- [  ] SSH access configured
- [  ] User account with sudo privileges
- [  ] Internet connectivity for package installation

### 2. Docker and Docker Compose

#### Docker Installation
```bash
# Check Docker version (minimum: 20.10)
docker --version

# Check Docker service status
systemctl status docker

# Verify Docker can run containers
docker run hello-world
```

- [  ] Docker version 20.10+ installed
- [  ] Docker service running
- [  ] Docker socket accessible
- [  ] User added to docker group (`sudo usermod -aG docker $USER`)
- [  ] Docker hello-world test passed

#### Docker Compose Installation
```bash
# Check Docker Compose version (minimum: 2.0)
docker compose version

# Alternative check for older installations
docker-compose --version
```

- [  ] Docker Compose version 2.0+ installed
- [  ] `docker compose` command available
- [  ] Compose V2 plugin enabled

### 3. Port Availability

Check that required ports are not in use:

```bash
# Check port 8080 (Caddy)
sudo lsof -i :8080

# Check port 5432 (PostgreSQL - should be unavailable externally)
sudo lsof -i :5432

# Check port 9090 (Prometheus)
sudo lsof -i :9090

# Check port 9093 (Alertmanager)
sudo lsof -i :9093

# Check port 3000 (Grafana)
sudo lsof -i :3000

# Check port 9100 (Node Exporter)
sudo lsof -i :9100

# Check port 8081 (cAdvisor)
sudo lsof -i :8081
```

**Port Requirements:**
- [  ] Port 8080 available for Caddy
- [  ] Port 9090 available for Prometheus (internal)
- [  ] Port 9093 available for Alertmanager (internal)
- [  ] Port 3000 available for Grafana (internal)
- [  ] Port 9100 available for Node Exporter (internal)
- [  ] Port 8081 available for cAdvisor (internal)
- [  ] PostgreSQL port 5432 will be container-internal only

**Conflict Resolution:**
If ports are in use by existing services (e.g., Cockpit on 9090):
- [  ] Document conflicting services
- [  ] Plan port remapping in docker-compose.yml
- [  ] Update Prometheus URLs in backend config

### 4. Firewall Configuration

```bash
# Check firewall status
sudo ufw status

# List current rules
sudo iptables -L -n
```

**Required Rules:**
- [  ] Allow loopback traffic (127.0.0.1)
- [  ] Allow localhost connections to port 8080
- [  ] Block external access to monitoring ports (9090, 9093, 3000, 9100, 8081)
- [  ] PostgreSQL port 5432 never exposed to host

**Action Required:**
- [  ] No firewall changes needed (all services bind to 127.0.0.1 or internal network)
- [  ] Verify `ufw` or `iptables` not blocking loopback
- [  ] Document existing firewall rules

### 5. Storage and Persistent Volumes

#### Volume Locations
- PostgreSQL data: `/var/lib/docker/volumes/kibolens_postgres_data`
- Prometheus data: `/var/lib/docker/volumes/kibolens_prometheus_data`
- Grafana data: `/var/lib/docker/volumes/kibolens_grafana_data`

```bash
# Check available disk space
df -h /var/lib/docker

# Check Docker volume list
docker volume ls
```

**Storage Requirements:**
- [  ] Minimum 10 GB free space on /var/lib/docker
- [  ] Disk I/O performance acceptable for database workloads
- [  ] No existing volumes conflict with kibolens_* names

**Backup Strategy:**
- [  ] Documented backup location
- [  ] Backup schedule defined (recommend daily)
- [  ] Restore procedure tested

---

## Environment Configuration

### 1. Environment Variables

Create `backend/.env` file with:

```env
# Required
KIBOLENS_DATABASE_URL=postgresql+psycopg://kibolens:CHANGE_ME_TO_STRONG_PASSWORD@postgres:5432/kibolens
KIBOLENS_SESSION_HASH_SECRET=GENERATE_RANDOM_64_CHAR_STRING
KIBOLENS_ALERT_WEBHOOK_TOKEN=GENERATE_RANDOM_TOKEN

# Recommended
KIBOLENS_ENVIRONMENT=production
KIBOLENS_SESSION_COOKIE_SECURE=true
KIBOLENS_SESSION_TTL_HOURS=8

# Optional
KIBOLENS_PROMETHEUS_URL=http://prometheus:9090
KIBOLENS_PROMETHEUS_TIMEOUT_SECONDS=5
KIBOLENS_CPU_WARNING_PERCENT=75
KIBOLENS_CPU_CRITICAL_PERCENT=90
KIBOLENS_MEMORY_WARNING_PERCENT=80
KIBOLENS_MEMORY_CRITICAL_PERCENT=90
KIBOLENS_DISK_WARNING_PERCENT=80
KIBOLENS_DISK_CRITICAL_PERCENT=90
```

**Generate Secrets:**
```bash
# Session hash secret (64 characters)
openssl rand -hex 32

# Alert webhook token (32 characters recommended)
openssl rand -hex 16
```

**Checklist:**
- [  ] .env file created in backend/
- [  ] DATABASE_URL configured with strong password
- [  ] SESSION_HASH_SECRET generated (64 chars)
- [  ] ALERT_WEBHOOK_TOKEN generated
- [  ] ENVIRONMENT=production set
- [  ] SESSION_COOKIE_SECURE=true set
- [  ] .env file permissions set to 600 (`chmod 600 backend/.env`)
- [  ] .env file added to .gitignore (should already be there)
- [  ] Secrets documented in secure password manager

### 2. Alertmanager Configuration

Update `deployment/monitoring/alertmanager.yml`:

```yaml
receivers:
  - name: 'kibolens-webhook'
    webhook_configs:
      - url: 'http://backend:8000/api/v1/monitoring/alerts'
        send_resolved: true
        http_config:
          authorization:
            credentials: 'YOUR_ALERT_WEBHOOK_TOKEN_HERE'
```

**Checklist:**
- [  ] alertmanager.yml updated with webhook URL
- [  ] Authorization header configured with token
- [  ] send_resolved: true enabled
- [  ] Webhook URL points to internal Docker network (backend:8000)

### 3. Prometheus Alert Rules

Create or update `deployment/monitoring/alert_rules.yml`:

```yaml
groups:
  - name: infrastructure_alerts
    interval: 30s
    rules:
      - alert: HighCPUUsage
        expr: 100 - (avg by(instance) (rate(node_cpu_seconds_total{mode="idle"}[5m])) * 100) > 90
        for: 2m
        labels:
          severity: high
          service: system
        annotations:
          summary: "High CPU usage detected"
          description: "CPU usage is above 90% for more than 2 minutes"
      
      - alert: HighMemoryUsage
        expr: (node_memory_MemTotal_bytes - node_memory_MemAvailable_bytes) / node_memory_MemTotal_bytes * 100 > 90
        for: 2m
        labels:
          severity: high
          service: system
        annotations:
          summary: "High memory usage detected"
          description: "Memory usage is above 90%"
      
      - alert: DiskSpaceLow
        expr: (node_filesystem_avail_bytes{mountpoint="/"} / node_filesystem_size_bytes{mountpoint="/"}) * 100 < 10
        for: 5m
        labels:
          severity: critical
          service: system
        annotations:
          summary: "Disk space critically low"
          description: "Less than 10% disk space available"
      
      - alert: ContainerDown
        expr: up{job="cadvisor"} == 0
        for: 1m
        labels:
          severity: critical
          service: docker
        annotations:
          summary: "Container monitoring unavailable"
          description: "cAdvisor is not responding"
```

**Checklist:**
- [  ] Alert rules file created
- [  ] Rules include severity labels (info, warning, high, critical)
- [  ] Rules include service/job labels
- [  ] Annotations provide summary and description
- [  ] Alert thresholds aligned with KiboLens config

---

## Deployment Procedure

### Phase 1: Pre-Deployment Validation

```bash
# 1. Clone or pull latest code
cd /path/to/kibolens
git pull origin main

# 2. Verify Docker Compose configuration
docker compose -f deployment/docker-compose.yml config

# 3. Check for syntax errors
cat deployment/docker-compose.yml
```

**Checklist:**
- [  ] Repository code up to date
- [  ] docker-compose.yml syntax valid
- [  ] All required files present (Dockerfiles, configs, migrations)
- [  ] No sensitive data in repository

### Phase 2: Database Migration

```bash
# 1. Start PostgreSQL only
docker compose -f deployment/docker-compose.yml up -d postgres

# 2. Wait for PostgreSQL to be ready
docker compose -f deployment/docker-compose.yml logs postgres | grep "ready to accept connections"

# 3. Run migrations
docker compose -f deployment/docker-compose.yml run --rm backend alembic upgrade head

# 4. Verify migration success
docker compose -f deployment/docker-compose.yml exec postgres psql -U kibolens -d kibolens -c "\dt"
```

**Expected Tables:**
- [  ] users
- [  ] user_sessions
- [  ] conversations
- [  ] messages
- [  ] incidents
- [  ] incident_events
- [  ] evidence_records
- [  ] incident_sequences

**Validation Queries:**
```sql
-- Check incidents table structure
SELECT column_name, data_type FROM information_schema.columns WHERE table_name = 'incidents';

-- Check incident_sequences initialized
SELECT * FROM incident_sequences;

-- Should return: id=1, next_number=1
```

**Checklist:**
- [  ] PostgreSQL started successfully
- [  ] Alembic migrations completed without errors
- [  ] All 8 tables created
- [  ] incident_sequences initialized
- [  ] No foreign key errors

### Phase 3: Core Services Start

```bash
# Start core services (backend, caddy)
docker compose -f deployment/docker-compose.yml up -d backend caddy

# Check service health
docker compose -f deployment/docker-compose.yml ps
docker compose -f deployment/docker-compose.yml logs backend | tail -20
docker compose -f deployment/docker-compose.yml logs caddy | tail -20

# Test health endpoints
curl http://localhost:8080/api/v1/health/liveness
curl http://localhost:8080/api/v1/health/readiness
```

**Expected Responses:**
- Liveness: `{"status": "ok"}`
- Readiness: `{"status": "ok", "database": "available"}`

**Checklist:**
- [  ] Backend container running
- [  ] Caddy container running
- [  ] No error logs visible
- [  ] Health endpoints responding
- [  ] Database connection successful

### Phase 4: Bootstrap Administrator

```bash
# Create admin user
docker compose -f deployment/docker-compose.yml exec backend python -m app.cli.bootstrap_admin

# Follow prompts to set username and password
# Recommended: username=admin, strong password
```

**Checklist:**
- [  ] Admin user created successfully
- [  ] Password stored securely in password manager
- [  ] User can login via frontend

### Phase 5: Frontend Build and Deploy

```bash
# Build frontend production bundle
cd frontend
npm install
npm run build

# Verify build output
ls -lh dist/
```

**Checklist:**
- [  ] Frontend builds without errors
- [  ] dist/ directory created
- [  ] Assets optimized (check chunk sizes)
- [  ] Caddy serves frontend at http://localhost:8080

### Phase 6: Monitoring Stack Start

```bash
# Start monitoring profile
docker compose -f deployment/docker-compose.yml --profile monitoring up -d

# Verify monitoring services
docker compose -f deployment/docker-compose.yml ps

# Check Prometheus targets
curl http://localhost:9090/api/v1/targets | jq '.data.activeTargets[] | {job: .labels.job, health: .health}'

# Check Alertmanager status
curl http://localhost:9093/api/v2/status | jq
```

**Expected Services:**
- [  ] prometheus - running
- [  ] alertmanager - running
- [  ] node-exporter - running
- [  ] cadvisor - running
- [  ] grafana - running

**Prometheus Targets:**
- [  ] prometheus (self) - up
- [  ] node-exporter - up
- [  ] cadvisor - up
- [  ] alertmanager - up

**Checklist:**
- [  ] All monitoring containers running
- [  ] Prometheus scraping targets successfully
- [  ] Alertmanager API responding
- [  ] Node Exporter exporting metrics
- [  ] cAdvisor collecting container stats

---

## Integration Testing

### 1. Authentication Flow

```bash
# Test login endpoint
curl -X POST http://localhost:8080/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username": "admin", "password": "YOUR_PASSWORD"}' \
  -c cookies.txt -v

# Verify session cookie received
# Should see: Set-Cookie: kibolens_session=...
```

**Checklist:**
- [  ] Login endpoint responds
- [  ] Session cookie set
- [  ] CSRF token returned
- [  ] Login throttling works (test 6 failed attempts)

### 2. Infrastructure API

```bash
# Test infrastructure summary (requires session)
curl http://localhost:8080/api/v1/infrastructure/summary \
  -b cookies.txt | jq

# Expected: health status, metrics, monitoring availability
```

**Checklist:**
- [  ] Infrastructure API responds
- [  ] Prometheus data retrieved
- [  ] Metrics have valid values or marked unavailable
- [  ] Health state calculated correctly (may be UNKNOWN initially)

### 3. Incident API

```bash
# Test incident summary
curl http://localhost:8080/api/v1/incidents/summary \
  -b cookies.txt | jq

# Expected: total_active=0, all counts=0, empty latest_incidents
```

**Checklist:**
- [  ] Incidents API responds
- [  ] Summary returns zero counts (no incidents yet)
- [  ] No errors in response

### 4. Alert Webhook

```bash
# Test webhook with mock alert
curl -X POST http://localhost:8080/api/v1/monitoring/alerts \
  -H "Authorization: Bearer YOUR_ALERT_WEBHOOK_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "status": "firing",
    "alerts": [{
      "status": "firing",
      "labels": {
        "alertname": "TestAlert",
        "severity": "warning",
        "job": "test"
      },
      "annotations": {
        "summary": "Test alert for integration",
        "description": "This is a test"
      },
      "fingerprint": "test-fingerprint-001"
    }]
  }' | jq

# Expected: {"accepted": 1, "deduplicated": 0}
```

**Checklist:**
- [  ] Webhook authentication works
- [  ] Alert processed successfully
- [  ] Incident created in database
- [  ] Event timeline recorded
- [  ] Evidence captured (if Prometheus available)

**Verify Incident Created:**
```bash
# List incidents
curl http://localhost:8080/api/v1/incidents -b cookies.txt | jq

# Should show: INC-000001, status=DETECTED, severity=WARNING
```

- [  ] Incident appears in list
- [  ] Incident number is INC-000001
- [  ] Alert data populated correctly
- [  ] Timeline has INCIDENT_CREATED and ALERT_RECEIVED events

### 5. Incident Lifecycle

```bash
# Get incident ID from previous step
INCIDENT_ID="<uuid-from-previous-test>"

# Get CSRF token
CSRF_TOKEN="<from-login-response>"

# Update incident status
curl -X PATCH http://localhost:8080/api/v1/incidents/$INCIDENT_ID/status \
  -b cookies.txt \
  -H "X-CSRF-Token: $CSRF_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"status": "INVESTIGATING", "note": "Checking test alert"}' | jq

# Add note
curl -X POST http://localhost:8080/api/v1/incidents/$INCIDENT_ID/notes \
  -b cookies.txt \
  -H "X-CSRF-Token: $CSRF_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"note": "Test note added during integration testing"}' | jq

# Get incident timeline
curl http://localhost:8080/api/v1/incidents/$INCIDENT_ID/events -b cookies.txt | jq
```

**Checklist:**
- [  ] Status update successful
- [  ] Note added successfully
- [  ] Timeline shows all events in order
- [  ] Event timestamps are correct

### 6. Resolved Alert

```bash
# Send resolved webhook
curl -X POST http://localhost:8080/api/v1/monitoring/alerts \
  -H "Authorization: Bearer YOUR_ALERT_WEBHOOK_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "status": "resolved",
    "alerts": [{
      "status": "resolved",
      "labels": {
        "alertname": "TestAlert",
        "severity": "warning",
        "job": "test"
      },
      "annotations": {
        "summary": "Test alert for integration",
        "description": "This is a test"
      },
      "fingerprint": "test-fingerprint-001"
    }]
  }' | jq

# Verify incident resolved
curl http://localhost:8080/api/v1/incidents/$INCIDENT_ID -b cookies.txt | jq '.incident | {status, resolved_at}'
```

**Checklist:**
- [  ] Incident status changed to RESOLVED
- [  ] resolved_at timestamp set
- [  ] INCIDENT_RESOLVED event recorded

### 7. Frontend Access

```bash
# Test frontend loads
curl -I http://localhost:8080/

# Expected: HTTP 200, Content-Type: text/html
```

**Browser Tests:**
- [  ] Open http://localhost:8080 in browser
- [  ] Login page displays
- [  ] Can login with admin credentials
- [  ] Overview page shows infrastructure metrics
- [  ] Overview page shows incident summary
- [  ] Incidents page accessible (when implemented)
- [  ] No console errors in browser DevTools

---

## Real Alertmanager Integration

### 1. Configure Prometheus to Fire Test Alert

Create `deployment/monitoring/test_alert.yml`:

```yaml
groups:
  - name: integration_test
    interval: 10s
    rules:
      - alert: IntegrationTestAlert
        expr: up{job="prometheus"} == 1  # Always true
        for: 30s
        labels:
          severity: info
          service: prometheus
        annotations:
          summary: "Integration test alert"
          description: "This alert fires when Prometheus is up for testing KiboLens integration"
```

**Steps:**
```bash
# 1. Add test alert rule to Prometheus config
# Edit deployment/monitoring/prometheus.yml:
# Add: - '/etc/prometheus/test_alert.yml'

# 2. Restart Prometheus
docker compose -f deployment/docker-compose.yml restart prometheus

# 3. Wait 30 seconds for alert to fire

# 4. Check Alertmanager
curl http://localhost:9093/api/v2/alerts | jq

# 5. Check KiboLens for new incident
curl http://localhost:8080/api/v1/incidents -b cookies.txt | jq
```

**Checklist:**
- [  ] Test alert appears in Prometheus alerts UI
- [  ] Alert forwarded to Alertmanager
- [  ] Alertmanager webhook delivered to KiboLens
- [  ] New incident created automatically
- [  ] Evidence collected from Prometheus
- [  ] Timeline shows alert source

### 2. Test Alert Lifecycle

```bash
# 1. Silence alert in Alertmanager (simulates resolution)
curl -X POST http://localhost:9093/api/v2/silences \
  -H "Content-Type: application/json" \
  -d '{
    "matchers": [{"name": "alertname", "value": "IntegrationTestAlert", "isRegex": false}],
    "startsAt": "'$(date -u +%Y-%m-%dT%H:%M:%SZ)'",
    "endsAt": "'$(date -u -d '+1 hour' +%Y-%m-%dT%H:%M:%SZ)'",
    "comment": "Integration test silence",
    "createdBy": "integration-test"
  }'

# 2. Wait for silence to take effect (1-2 minutes)

# 3. Remove test alert rule and restart Prometheus
docker compose -f deployment/docker-compose.yml restart prometheus

# 4. Verify incident resolved
curl http://localhost:8080/api/v1/incidents -b cookies.txt | jq '.incidents[] | select(.status == "RESOLVED")'
```

**Checklist:**
- [  ] Alert silenced in Alertmanager
- [  ] Incident remains DETECTED/INVESTIGATING during silence
- [  ] Alert removed when rule deleted
- [  ] Resolved webhook received
- [  ] Incident status updated to RESOLVED

---

## Performance and Stability

### 1. Resource Usage

```bash
# Monitor container resource usage
docker stats

# Check CPU and memory over time
docker stats --no-stream --format "table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}"
```

**Acceptable Ranges (12GB system):**
- PostgreSQL: < 512 MB RAM, < 10% CPU
- Backend: < 256 MB RAM, < 5% CPU
- Prometheus: < 1 GB RAM, < 15% CPU
- Node Exporter: < 50 MB RAM, < 2% CPU
- cAdvisor: < 100 MB RAM, < 5% CPU
- Alertmanager: < 100 MB RAM, < 2% CPU
- Grafana: < 256 MB RAM, < 5% CPU
- Caddy: < 50 MB RAM, < 2% CPU

**Checklist:**
- [  ] No container using excessive CPU (> 50%)
- [  ] Total memory usage < 8 GB (leaves 4GB for system)
- [  ] No container restart loops
- [  ] Disk I/O acceptable (check `iostat`)

### 2. Log Inspection

```bash
# Check for errors in logs
docker compose -f deployment/docker-compose.yml logs --tail=100 | grep -i error

# Check backend application logs
docker compose -f deployment/docker-compose.yml logs backend | tail -50

# Check Prometheus scrape errors
curl http://localhost:9090/api/v1/targets | jq '.data.activeTargets[] | select(.health != "up")'
```

**Checklist:**
- [  ] No critical errors in any service logs
- [  ] All Prometheus targets healthy
- [  ] No database connection errors
- [  ] No authentication failures (except expected test failures)

### 3. Database Health

```bash
# Connect to PostgreSQL
docker compose -f deployment/docker-compose.yml exec postgres psql -U kibolens -d kibolens

# Check table sizes
SELECT 
  schemaname, 
  tablename, 
  pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) AS size
FROM pg_tables 
WHERE schemaname = 'public'
ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC;

# Check incident count
SELECT COUNT(*) FROM incidents;

# Check event count
SELECT COUNT(*) FROM incident_events;

# Check evidence count
SELECT COUNT(*) FROM evidence_records;
```

**Checklist:**
- [  ] Database responsive
- [  ] Table sizes reasonable (< 100 MB initially)
- [  ] Incident counts match expectations
- [  ] No orphaned records (all events/evidence link to incidents)

---

## Rollback Procedure

### If Integration Fails

```bash
# 1. Stop all services
docker compose -f deployment/docker-compose.yml --profile monitoring down

# 2. Backup database (if data needs preserving)
docker run --rm \
  -v kibolens_postgres_data:/data \
  -v $(pwd):/backup \
  ubuntu tar czf /backup/kibolens_db_backup_$(date +%Y%m%d_%H%M%S).tar.gz /data

# 3. Remove containers and volumes
docker compose -f deployment/docker-compose.yml --profile monitoring down -v

# 4. Clean up dangling images
docker system prune -f

# 5. Restore previous state (if applicable)
# ... depends on previous deployment
```

**Checklist:**
- [  ] All containers stopped
- [  ] Database backed up (if needed)
- [  ] Volumes removed (if starting fresh)
- [  ] Previous state documented

---

## Post-Integration Validation

### 1. Cockpit Compatibility

```bash
# Check Cockpit status (should be unaffected)
systemctl status cockpit.socket

# Verify Cockpit accessible
curl -I http://localhost:9090
# or appropriate Cockpit port if different
```

**Checklist:**
- [  ] Cockpit still accessible
- [  ] No port conflicts
- [  ] Docker containers visible in Cockpit (if podman plugin installed)

### 2. System Health

```bash
# Check system load
uptime

# Check memory
free -h

# Check disk usage
df -h

# Check Docker disk usage
docker system df
```

**Checklist:**
- [  ] System load acceptable (< 4.0 on quad-core)
- [  ] Memory not exhausted (> 2GB free)
- [  ] Disk space sufficient (> 10GB free)
- [  ] Docker volumes reasonable size

### 3. Network Connectivity

```bash
# Verify internal Docker network
docker network inspect kibolens_default

# Check DNS resolution
docker compose -f deployment/docker-compose.yml exec backend ping -c 2 postgres
docker compose -f deployment/docker-compose.yml exec backend ping -c 2 prometheus
```

**Checklist:**
- [  ] Docker network created
- [  ] Services can resolve each other by name
- [  ] No network errors in logs

---

## Ongoing Monitoring

### Daily Checks

- [  ] Check `docker compose ps` - all services running
- [  ] Check incident count growth - reasonable or investigate spikes
- [  ] Review critical/high incidents - address unresolved issues
- [  ] Check disk space - ensure volumes not filling up
- [  ] Review Grafana dashboards - infrastructure healthy

### Weekly Checks

- [  ] Database backup created and verified
- [  ] Review incident resolution times - identify bottlenecks
- [  ] Check alert rule effectiveness - tune thresholds if needed
- [  ] Review evidence collection success rate
- [  ] Check for Docker/Compose updates

### Monthly Checks

- [  ] Review total incident volume - trending up/down?
- [  ] Analyze common incident types - infrastructure improvements needed?
- [  ] Update alert rules based on false positive rate
- [  ] Review security - rotate secrets if needed
- [  ] Check for KiboLens updates

---

## Troubleshooting Guide

### Issue: Webhook Authentication Fails

**Symptoms:** 401 Unauthorized in Alertmanager logs

**Solution:**
1. Verify ALERT_WEBHOOK_TOKEN in backend/.env matches Alertmanager config
2. Check token has no extra whitespace
3. Restart backend after .env changes
4. Test webhook with curl using correct token

### Issue: Incidents Not Created

**Symptoms:** Webhook accepted but no incidents in database

**Solution:**
1. Check backend logs for errors: `docker compose logs backend | grep ERROR`
2. Verify database connection: `curl http://localhost:8080/api/v1/health/readiness`
3. Check alert payload structure matches schema
4. Verify fingerprint uniqueness
5. Check incident_sequences table initialized

### Issue: Evidence Not Collected

**Symptoms:** Incidents created but evidence_records empty

**Solution:**
1. Check Prometheus connectivity: `curl http://prometheus:9090/api/v1/query?query=up`
2. Verify PROMETHEUS_URL in backend/.env correct
3. Check monitoring service logs for errors
4. Evidence collection failures are logged but don't block incidents
5. Verify affected_service matches Prometheus job labels

### Issue: High Database Growth

**Symptoms:** postgres_data volume growing rapidly

**Solution:**
1. Check incident_events count - should be proportional to incidents
2. Check evidence_records count - may need retention policy
3. Implement evidence cleanup for old incidents (future enhancement)
4. Consider PostgreSQL autovacuum tuning

### Issue: Memory Exhaustion

**Symptoms:** Services OOM killed, system swap usage high

**Solution:**
1. Check `docker stats` for memory hogs
2. Reduce Prometheus retention if needed
3. Limit container memory in docker-compose.yml
4. Consider disabling Grafana if not actively used
5. Monitor incident volume - implement pagination limits

---

## Security Checklist

- [  ] All secrets stored in .env file (not committed)
- [  ] .env file permissions 600 (owner read/write only)
- [  ] Strong passwords used (minimum 16 characters)
- [  ] SESSION_HASH_SECRET is random 64 characters
- [  ] ALERT_WEBHOOK_TOKEN is random and documented
- [  ] PostgreSQL password changed from default
- [  ] No services exposed on 0.0.0.0 (all on 127.0.0.1)
- [  ] Firewall rules reviewed
- [  ] HTTPS configured via Caddy (if exposing externally)
- [  ] Admin credentials stored in password manager
- [  ] Backup encryption configured (if storing sensitive data)

---

## Documentation Updates

After successful integration:

- [  ] Update DEVELOPMENT_STATUS.md with integration date
- [  ] Document actual port mappings (if different from defaults)
- [  ] Record any Cockpit compatibility issues and resolutions
- [  ] Update ARCHITECTURE.md with deployed topology
- [  ] Create runbook for common operations
- [  ] Document backup and restore procedures
- [  ] Update README.md with production deployment status

---

## Success Criteria

Phase 4 integration is successful when:

- [  ] All Docker services running stably
- [  ] PostgreSQL migrations applied successfully
- [  ] Admin user can login via frontend
- [  ] Infrastructure monitoring displays real metrics
- [  ] Test alert fires and creates incident automatically
- [  ] Incident lifecycle operations work (status updates, notes)
- [  ] Resolved alerts close incidents
- [  ] Evidence is collected when available
- [  ] No critical errors in any service logs
- [  ] System resources within acceptable limits
- [  ] Cockpit remains accessible and functional
- [  ] Backup procedure validated
- [  ] All checklist items above completed

---

## Next Steps After Integration

1. **Phase 5 Planning**: Begin design for LangChain/LangGraph AI agent
2. **Frontend Completion**: Build remaining incident UI components
3. **Performance Tuning**: Optimize based on real workload
4. **Alert Rule Refinement**: Tune thresholds based on actual infrastructure
5. **Documentation**: Create user guide and operator runbook
6. **Monitoring**: Set up alerting for KiboLens itself (meta-monitoring)

---

## Contact and Support

**Integration Lead:** [Your Name]  
**Server:** Kibo (Ubuntu, Lenovo ThinkCentre M91p)  
**Integration Window:** [Schedule specific date/time]

**Approval Required Before:**
- Starting Docker services
- Running database migrations
- Modifying firewall rules
- Changing Cockpit configuration
- Installing additional packages

**Stop Integration If:**
- Port conflicts cannot be resolved
- Cockpit functionality breaks
- System becomes unstable
- Database migrations fail
- Authentication completely broken

---

**STATUS: AWAITING APPROVAL TO PROCEED WITH SERVER INTEGRATION**
