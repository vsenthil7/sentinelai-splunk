# Security Model

SentinelAI is a security product; its own posture is part of the design.

## Authentication & authorization
- JWT bearer tokens (HS256) carrying principal: user id, **tenant**, role.
- Passwords hashed with bcrypt; SSO-ready (`external_id` links an OIDC/SAML
  subject to a user for an IdP callback).
- Every protected route is gated by a `require(permission)` dependency against
  the RBAC matrix (viewer / analyst / responder / admin). See API.md.

## Multi-tenant isolation
Every business row carries `tenant_id`; repositories filter by it, so a token
for tenant A can neither list nor fetch tenant B's data (cross-tenant reads
return 404). Verified behavior, not convention.

## Human-in-the-loop containment
State-changing actions (isolate_host, disable_user, block_ip, kill_process) are
**planned → approved → executed** as distinct steps. Execution requires
`action:approve` and a prior approval (else 409). Read-only actions
(collect_forensics) are not gated.

## Tamper-evident audit
Every privileged action (login success/failure, run, approve, execute, status
change, assignment, notes, rule toggle, all admin ops) is recorded append-only.
Each entry hashes the previous entry per tenant; `GET /audit` exposes
`chain_valid`. Editing or deleting any historical row breaks the chain.

## Input & dependency handling
- SPL validated before dispatch; query errors are deterministic (not retried).
- Model output parsed defensively; malformed JSON → safe "needs review" verdict.
- External calls wrapped in retry + circuit breaker.
- Rate limiting per client; configurable CORS.

## Hardening checklist for production
- [ ] Strong `SENTINEL_JWT_SECRET`.
- [ ] `CORS_ORIGINS` restricted to known frontends.
- [ ] TLS verification enabled on the live Splunk client.
- [ ] Postgres + Alembic migrations (not metadata create-all).
- [ ] Redis-backed rate limiter for multi-instance.
- [ ] Reverse proxy with WAF / additional rate limiting.
