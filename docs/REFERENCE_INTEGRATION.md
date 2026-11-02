# Reference repository integration

KiboLens was reviewed against the local `akmatori-main` and
`Checkmate-develop` repositories on 2026-11-02.

## Akmatori

Akmatori is licensed under Apache License 2.0. KiboLens adapted the following
ideas without importing the Go application or its runtime:

- Stable logical alert identity derived from normalized source, alert name and
  target host. This is implemented in `backend/app/monitoring/alert_fingerprint.py`
  and persisted as `Incident.logical_fingerprint` for recurrence correlation.
- Exact source fingerprint retention alongside logical recurrence correlation.
- Bounded, fail-open incident notification handling and retry state, adapted to
  KiboLens' PostgreSQL and Resend services.

The adapted implementation remains Python/FastAPI-native and uses KiboLens'
existing authentication, database, Alertmanager and AI workflows.

## Checkmate

Checkmate is licensed under GNU Affero General Public License v3. Its Docker
provider and worker reactor were inspected for behavior, including:

- Docker inspect plus stats collection, including CPU delta calculation and
  memory working-set calculation that excludes cache.
- Explicit stopped/unhealthy container breach classification.
- Transition-based incident and notification dispatch.
- Notification test and delivery-failure handling.

No Checkmate source code, client components, server modules, or dependencies
were copied into KiboLens. These behaviors were independently implemented or
were already present in KiboLens, avoiding an AGPL-derived server/client merge.

## Deliberately not integrated

Neither reference Compose stack, database, frontend, agent, MongoDB service,
Go service, Node service, MCP gateway, or LLM provider was added. KiboLens
continues to use one FastAPI/PostgreSQL/Qdrant/Prometheus/Grafana application
and its existing Gemini → Groq → OpenRouter free-only router.
