# Security

KiboLens sessions are opaque, HttpOnly, SameSite=Lax cookies. Session and CSRF tokens are stored as hashes in PostgreSQL; browser JavaScript keeps the current CSRF token only in memory. State-changing browser requests require `X-CSRF-Token`.

Monitoring APIs require an authenticated KiboLens session. Prometheus is queried through validated fixed query templates and never receives browser-supplied or model-supplied PromQL. cAdvisor's Docker socket mount is read-only and restricted to the cAdvisor container; it is never available to FastAPI, Ollama, or an agent process.

Alertmanager sends an `Authorization: Bearer` token from a mounted secret file to the backend's alert webhook. Caddy blocks that webhook from public ingress. Configure `KIBOLENS_ALERT_WEBHOOK_TOKEN` and its mounted-file equivalent with a unique random value; do not commit either.
