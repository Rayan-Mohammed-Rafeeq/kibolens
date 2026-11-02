# KiboLens interview demonstration

KiboLens is an evidence-first SRE workspace combining Prometheus, Alertmanager,
PostgreSQL incident history, Qdrant retrieval, and free-only cloud AI routing:
Gemini, then Groq, then OpenRouter.

## Demonstration

Use a suitable non-production host for the lab scenarios:

```bash
docker compose -f deployment/docker-compose.yml up -d
docker compose -f deployment/docker-compose.yml --profile monitoring up -d
docker compose -f deployment/docker-compose.yml ps
curl http://127.0.0.1:8080/api/v1/health
```

Open Overview and Infrastructure to show current exporter-backed telemetry.
Upload a runbook in Knowledge Base, confirm its indexed chunks, search it, and
ask AI Chat about the retrieved content.

Start exactly one isolated lab scenario:

```bash
docker compose -f deployment/failure-lab/docker-compose.yml --profile lab up -d lab-crasher
docker compose -f deployment/failure-lab/docker-compose.yml --profile lab ps
docker compose -f deployment/failure-lab/docker-compose.yml --profile lab logs lab-crasher
```

Open Incidents, inspect Docker evidence and logs, then choose **Investigate**.
The linked conversation contains incident context, telemetry and retrieved
documentation. Stop or repair the test scenario and wait for recovery before
showing the resolved lifecycle.

Do not run CPU-stress or memory-pressure scenarios on production Kibo.

## Safe reset

An administrator can reset only containers labeled `kibolens.lab=true` and
close synthetic demo incidents. It cannot delete production data:

```text
POST /api/v1/infrastructure/lab/reset
```

The endpoint requires the session cookie and CSRF token.

## Design and limitations

- Prometheus is the source of truth for host history; cAdvisor supplies
  container resource series.
- The Docker observer is read-only for inspection and logs. Cleanup is a
  separate allowlisted controller restricted to labeled lab containers.
- AI outputs are evidence-based hypotheses with uncertainty; remediation is
  never executed automatically.
- Qdrant uses one configured embedding model and dimension. Ingestion rejects
  incompatible vectors and redacts secret-like configuration lines.
- Docker observation requires the Docker Python package and a read-only Engine
  socket. Cloud AI and alert delivery require configured external credentials.
- VM support currently means standard Node Exporter telemetry, not automatic
  universal inventory discovery.
