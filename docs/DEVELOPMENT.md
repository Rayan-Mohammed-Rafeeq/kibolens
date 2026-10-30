# Local Development

## Requirements

- Python 3.14 or a supported Python version compatible with pinned dependencies.
- Node 22.
- Docker Engine plus the Docker Compose plugin for the full stack.

## Backend

From `backend`, create a virtual environment, install `requirements-dev.txt`, and run:

```bash
uvicorn app.main:app --reload
```

The liveness endpoint is `GET /api/v1/health`. `GET /api/v1/ready` returns 503 while PostgreSQL is unreachable. Run migrations only against the Compose database with `alembic upgrade head`.

## Frontend

From `frontend`, install packages and run `npm run dev`. Vite serves on port 5173 and proxies `/api` to a locally running backend on port 8000.

## Verification

```bash
pytest backend/tests
npm --prefix frontend run build
docker compose -f deployment/docker-compose.yml config
```
