# Monitoring

KiboLens uses Prometheus as the sole Phase 3 time-series source. The backend contains fixed PromQL templates for host and container views; it accepts no arbitrary PromQL from the browser or future AI components.

## Components

- **Node Exporter** reads host CPU, memory, disk, network, uptime, and load metrics through a read-only root mount.
- **cAdvisor** reads container runtime metrics using read-only Docker, sysfs, and root filesystem mounts. It is not privileged and no KiboLens backend/AI container receives Docker socket access.
- **Prometheus** scrapes every 30 seconds, evaluates alert rules every 30 seconds, and retains data for 15 days.
- **Alertmanager** groups by alert/resource and forwards alerts over the private Compose network with a bearer token.
- **Grafana** is provisioned with Prometheus and a host/container dashboard. It has no host port; set non-default credentials in `.env`.

## Health semantics

The summary requires fresh CPU, memory, and disk-utilization measurements. If any is unavailable or older than `KIBOLENS_MONITORING_STALE_SECONDS` (120 seconds by default), KiboLens reports `UNKNOWN`. `HEALTHY` only means those metrics are present and below the configured warning thresholds; it is not a blanket assertion about every host component.

Default warning/critical thresholds are CPU 80/90%, memory 80/90%, and disk 80/90%. Adjust them through the `KIBOLENS_*` environment variables documented in `.env.example`.

## Enable on Kibo

1. Put a randomly generated alert token in a root-readable file outside the repository, e.g. `/etc/kibolens/alert-token`.
2. In `.env`, set matching `KIBOLENS_ALERT_WEBHOOK_TOKEN` and `KIBOLENS_ALERT_TOKEN_FILE`, plus a non-default `GRAFANA_ADMIN_PASSWORD`.
3. Review host mount paths and available resources, then run `docker compose -f deployment/docker-compose.yml --profile monitoring up -d`.

Prometheus, exporters, Alertmanager, and Grafana are private-network services and are intentionally not published on host ports. The Caddy public route rejects the Alertmanager webhook path.

## Validation

Run `docker compose -f deployment/docker-compose.yml --profile monitoring config` before deployment. Once started, verify targets from inside the private network and query the authenticated KiboLens endpoints. This development machine cannot run these checks because Docker is unavailable.
