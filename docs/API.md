# API Reference

Base URL: `/api/v1`. All responses JSON. Protected endpoints require
`Authorization: Bearer <token>` from `/auth/login`. Interactive docs at `/docs`.

Permissions are enforced per role (viewer / analyst / responder / admin); each
protected route lists the permission it needs.

## Auth
- `POST /auth/login` — `{username, password, tenant}` → `{access_token, role, tenant}`. 401 on bad creds (failure is audited).
- `POST /auth/logout` 🔒 — revokes the caller's token server-side (jti denylist). 204.

## System
- `GET /health` — combined status + Splunk reachability (public).
- `GET /health/live` — liveness (process up).
- `GET /health/ready` — readiness (DB + Splunk); 503 when not ready.
- `GET /metrics` — Prometheus exposition (request counts, avg latency).

## Splunk
- `POST /search` 🔒`search:run` — run SPL. 400 malformed, 401 unauthorized.

## Agents
- `POST /detections/run` 🔒`detection:run` — run rule library (respects disabled rules).
- `POST /investigations/run` 🔒`investigation:run` — full pipeline; persists investigations, correlates incidents, fires high-risk alerts.

## Investigations
- `GET /investigations` 🔒`investigation:read` — paginated/filtered (`status`, `severity`, `assignee`, `limit`, `offset`), risk-ranked.
- `GET /investigations/{id}` 🔒`investigation:read`.
- `POST /investigations/{id}/approve` 🔒`action:approve` — approve a gated action.
- `POST /investigations/{id}/execute` 🔒`action:approve` — execute an approved action (409 if not approved). Sets status `contained`, fires alert.
- `POST /investigations/{id}/status` 🔒`case:write` — transition status (409 illegal, 422 unknown).
- `GET /investigations/{id}/sla` 🔒`investigation:read` — SLA clocks + breach flags.
- `POST /investigations/{id}/assign` 🔒`case:write`.
- `POST /investigations/{id}/notes` 🔒`case:write`; `GET .../notes` 🔒`investigation:read`.

## Incidents
- `GET /incidents` 🔒`investigation:read` — correlated incident groups, risk-ranked.
- `GET /incidents/{id}` 🔒`investigation:read`.

## Rules
- `GET /rules` 🔒`investigation:read` — catalog + per-tenant enabled state.
- `PUT /rules/{id}` 🔒`admin:*` — enable/disable (audited).
- `GET /rules/mitre-coverage` 🔒`investigation:read` — tactic coverage.

## Audit
- `GET /audit` 🔒`audit:read` — entries + `chain_valid` integrity flag.

## Notifications
- `GET /notifications` 🔒`investigation:read` — captured notifications (capture channel).

## Admin (all 🔒`admin:*`, tenant-scoped, audited)
- `GET /admin/users`, `POST /admin/users` (409 dup, 422 bad role),
  `PUT /admin/users/{id}/role`, `POST /admin/users/{id}/link-identity` (SSO),
  `DELETE /admin/users/{id}` (409 self-delete).

## RBAC matrix
| Permission | viewer | analyst | responder | admin |
|-----------|:--:|:--:|:--:|:--:|
| investigation:read | ✓ | ✓ | ✓ | ✓ |
| search/detection/investigation:run | | ✓ | ✓ | ✓ |
| case:write | | ✓ | ✓ | ✓ |
| action:approve | | | ✓ | ✓ |
| audit:read | | | | ✓ |
| admin:* | | | | ✓ |
