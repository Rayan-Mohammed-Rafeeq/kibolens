# Architecture

KiboLens starts as a modular monolith. FastAPI exposes versioned APIs and owns application services; React communicates only with that API. PostgreSQL with pgvector is the sole planned relational and vector datastore. Caddy serves the built client and proxies API traffic.

The Phase 1 Compose network is internal. Only Caddy is published, and it binds to `127.0.0.1:8080`; PostgreSQL has no host port. Future monitoring and AI services will be separate Compose profiles so constrained Kibo hardware can enable them deliberately.

No container has Docker socket access in Phase 1. Future infrastructure reads will be implemented through bounded, allowlisted service adapters rather than agent shell access.

## Authentication and conversations

Phase 2 uses a random opaque session token stored only in an HttpOnly, SameSite=Lax cookie. The database holds an HMAC-SHA-256 hash of that token, its expiry, revocation state, and a separate hashed CSRF token. Browser state-changing requests supply the CSRF token from memory in `X-CSRF-Token`; it is never persisted in local storage. Session hashes use `KIBOLENS_SESSION_HASH_SECRET`.

Conversation queries always include the authenticated `owner_id`. A missing or foreign conversation returns 404, so its existence is not disclosed. The Phase 2 chat UI persists user messages only and explicitly marks agent responses as unavailable.

## Monitoring

The optional `monitoring` Compose profile keeps Prometheus, Node Exporter, cAdvisor, Alertmanager, and Grafana on the private network. FastAPI queries Prometheus with a narrow, versioned service layer; React only consumes FastAPI responses. Prometheus failure, malformed values, and stale timestamps are represented as unavailable evidence and lead to `UNKNOWN`, never `HEALTHY`.
