# SentinelAI — Enterprise Hardening Tracker

**Goal:** Take SentinelAI from architectural prototype to a POC a design partner
would pilot. Build in dependency order. Testing deferred to Claude Desktop.

**Started:** 09 Jun 2026 06:13

---

## Phase Plan (dependency-ordered)

| # | Module | Status | Why it's first / notes |
|---|--------|--------|------------------------|
| E1 | Persistence layer (SQLAlchemy + migrations) | ✅ DONE | Async SQLAlchemy 2.0, tenant-scoped ORM, repositories; SQLite dev / Postgres prod; verified e2e |
| E2 | Immutable audit log | ✅ DONE | Append-only hash-chained audit; tamper-detection verified (chain breaks on edit) |
| E3 | SSO-ready authN + RBAC + multi-tenant isolation | ✅ DONE | Principal/tenant claims in JWT; 4 roles × permission sets; data-layer tenant isolation verified (cross-tenant = 404). SSO hook (external_id) ready for OIDC callback. |
| E4 | Correlation + enrichment + entity resolution | ✅ DONE | Expanded rule library (5 MITRE-mapped rules), entity extraction (IPs/users from events), enrichment service (threat-intel reputation, asset criticality incl. crown-jewels, identity/privilege context) with pluggable provider; verified e2e |
| E5 | Risk scoring + incident grouping (notables) | ✅ DONE | Risk scoring + incident correlation (group by entity/indicators, risk roll-up); GET /incidents |
| E6 | Action execution engine (SOAR-style playbooks) | ✅ DONE | Pluggable connectors (EDR/IdP/firewall mock), approve-gated execution, state tracking, rollback tokens, audited; bug fixed in S1 |
| E7 | Case management (assignment, notes, status, SLA) | ✅ DONE | Notes, assignment, status workflow (transition rules), SLA timers + breach flags |
| E8 | Notifications (email/Slack/PagerDuty webhooks) | ✅ DONE | Pluggable channels (capture + webhook), high-risk + action-executed triggers, configurable threshold/URL |
| E9 | Operational maturity (logging/metrics/rate limit/pagination) | ✅ DONE | Structured logging + request-id, rate limiting, pagination/filtering, /metrics, retry+circuit-breaker, config CORS |
| E10 | Frontend surfaces (cases, admin, audit, rules, incidents) | ✅ DONE | Login(tenant), detail depth, incidents, audit, rules/MITRE, admin, nav, filters — all permission-aware |

---

## Decisions
- **DE1:** SQLAlchemy 2.0 (async) + SQLite for dev / Postgres for prod, Alembic migrations. Keeps the existing store *interfaces* — swap impl, not callers.
- **DE2:** Audit log is append-only with a hash chain (tamper-evidence) — each entry hashes the previous, so deletion/edits are detectable.
- **DE3:** Multi-tenant via a `tenant_id` column on every row + a tenant-scoped repository layer; authZ enforced in a dependency, not ad hoc.

## Changelog
- 2026-06-09 06:13 — Phase kicked off. Starting E1.
