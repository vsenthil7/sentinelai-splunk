# Deployment

## Local development

```bash
# Backend
cd backend && pip install -e ".[dev]"
uvicorn app.main:app --reload --port 8000

# Frontend
cd frontend && npm install && npm run dev
```

The Vite dev server proxies `/api` to the backend on :8000.

## Production build

```bash
cd frontend && npm run build      # emits dist/
```

Serve `frontend/dist/` from any static host (or behind the same origin as the
API to avoid CORS). Run the API with a production ASGI server:

```bash
cd backend
uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4
```

## Configuration

See [SPLUNK_INTEGRATION.md](SPLUNK_INTEGRATION.md) for the full environment
variable matrix. At minimum, in production set:

- `SENTINEL_JWT_SECRET` — a strong random secret.
- `SENTINEL_SPLUNK_BACKEND=live` plus host/token to use real Splunk.
- `SENTINEL_AI_BACKEND=live` plus model id to use a hosted model.

## Health & readiness

`GET /api/v1/health` returns `200` with `status: ok|degraded`. Wire this to your
orchestrator's liveness/readiness probes; treat `degraded` (Splunk unreachable)
as not-ready if Splunk is required for your deployment.

## Notes

- State (users, investigations) is in-memory in this build; the store interfaces
  are narrow so a persistent datastore can be substituted without touching the
  API layer.
- CORS is currently permissive for demo convenience — tighten `allow_origins`
  in `app/main.py` for production.
