# Architecture

KiboLens starts as a modular monolith. FastAPI exposes versioned APIs and owns application services; React communicates only with that API. PostgreSQL with pgvector is the sole planned relational and vector datastore. Caddy serves the built client and proxies API traffic.

The Phase 1 Compose network is internal. Only Caddy is published, and it binds to `127.0.0.1:8080`; PostgreSQL has no host port. Future monitoring and AI services will be separate Compose profiles so constrained Kibo hardware can enable them deliberately.

No container has Docker socket access in Phase 1. Future infrastructure reads will be implemented through bounded, allowlisted service adapters rather than agent shell access.
