# Operations Runbook

## Configuration (env vars, prefix `SENTINEL_`)
| Var | Default | Purpose |
|-----|---------|---------|
| `DATABASE_URL` | `sqlite+aiosqlite:///./sentinel.db` | Dev SQLite; set Postgres DSN in prod |
| `JWT_SECRET` | `change-me-in-prod` | **Must set** a strong secret in prod |
| `JWT_EXPIRE_MINUTES` | 60 | Token lifetime |
| `SPLUNK_BACKEND` / `AI_BACKEND` | `mock` | `live` to use real Splunk / hosted model |
| `SPLUNK_HOST` / `SPLUNK_TOKEN` / `SPLUNK_MCP_URL` | — | Live Splunk wiring |
| `RATE_LIMIT_PER_MINUTE` | 120 | Per-client request cap |
| `CORS_ORIGINS` | `*` | Comma-separated allowed origins (tighten in prod) |
| `NOTIFY_WEBHOOK_URL` | — | Slack-compatible alert webhook |
| `NOTIFY_HIGH_RISK_THRESHOLD` | 80 | Risk score that triggers alerts |
| `LOG_JSON` | true | Structured JSON logs |

## Observability
- **Logs:** structured JSON via structlog; every request logged with
  `request_id`, method, path, status, duration_ms.
- **Metrics:** `GET /metrics` (Prometheus text) — request counts by
  method/status, average latency. Scrape with Prometheus; alert on error rate.
- **Health:** `GET /health` — `status: ok|degraded`. Wire to liveness/readiness.

## Resilience
Splunk calls run through retry-with-backoff + a circuit breaker. When Splunk is
down, the breaker opens after repeated failures and `/health` reports
`degraded`. Deterministic query errors are not retried.

## Audit integrity
`GET /audit` returns `chain_valid`. If it ever reads `false`, the hash chain has
been broken — investigate database tampering immediately. The chain is per
tenant and append-only by design.

## Multi-tenant operations
All data is tenant-scoped. Seed additional tenants/users via the admin API
(`POST /admin/users` after creating the tenant) or programmatically through
`TenantRepository.ensure` + `UserRepository.create`.

## Deployment

Containerized via `docker-compose.yml` (Postgres + backend + frontend/nginx).
Backend image runs `alembic upgrade head` on start when `SENTINEL_DB_CREATE_ALL=false`.
Quick start:

```
cp backend/.env.example backend/.env   # set a strong JWT secret
docker compose up --build
# frontend: http://localhost:8080  API: http://localhost:8000
```

## Database migrations

Schema is managed by Alembic (`backend/alembic/`). The initial migration creates
all tables. For schema changes: edit the ORM models, then
`alembic revision --autogenerate -m "describe change"` and review the generated
file before committing. Apply with `alembic upgrade head`. In dev with SQLite,
`SENTINEL_DB_CREATE_ALL=true` creates tables from metadata for convenience; set
it `false` in prod so migrations are authoritative.

## Health probes

- `GET /api/v1/health/live` — liveness (process up); wire to the container
  liveness probe.
- `GET /api/v1/health/ready` — readiness (DB + Splunk reachable); returns 503
  when a dependency is down so the orchestrator stops routing traffic.
- `GET /api/v1/health` — combined status (back-compat).

## Session security

Tokens carry a unique `jti`. `POST /api/v1/auth/logout` revokes the caller's
token server-side (denylist), so logout invalidates a token immediately rather
than waiting for expiry. Revoked-token rows can be purged after their original
expiry.

## Known gaps before production
- **Rate limiter** is in-process (per instance). Back it with Redis for
  multi-instance deployments.
- **Notifications** capture channel is in-memory; configure a webhook
  (`SENTINEL_NOTIFY_WEBHOOK_URL`) for real alerting.
- **Revoked-token purge** is not yet scheduled; add a periodic job to delete
  expired jti rows (they are harmless but accumulate).
- **Live Splunk / hosted-model wiring** is implemented behind the `live`
  backends but must be validated against real infrastructure (deferred to
  Claude Desktop per project setup).
