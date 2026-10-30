# Deployment

KiboLens is intended for a private LAN deployment. It does not change firewall rules, partitions, Cockpit, DNS, or router configuration.

## Core

Create `.env` from `.env.example`, use strong database/session secrets, then run:

```bash
docker compose -f deployment/docker-compose.yml up -d --build
docker compose -f deployment/docker-compose.yml exec backend alembic upgrade head
docker compose -f deployment/docker-compose.yml exec backend python -m app.cli.bootstrap_admin
```

## Monitoring profile

Monitoring is optional to limit memory pressure on Kibo's 12 GB host. Review `docs/MONITORING.md`, provision a separate alert-token file, set Grafana credentials, then start it explicitly:

```bash
docker compose -f deployment/docker-compose.yml --profile monitoring up -d
```

Begin with the 30-second scrape interval and 15-day retention. Measure CPU, memory, and disk usage before enabling additional future profiles such as local LLM inference.
