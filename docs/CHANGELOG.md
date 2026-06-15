# Changelog

Format per [Keep a Changelog](https://keepachangelog.com/).

## [0.3.0] - 2026-06-09 — Enterprise hardening

### Added
- **Persistence:** async SQLAlchemy 2.0, tenant-scoped ORM + repositories
  (SQLite dev / Postgres prod).
- **Audit:** append-only, hash-chained, tamper-evident audit log with integrity
  verification.
- **AuthZ:** multi-tenant isolation, RBAC (viewer/analyst/responder/admin),
  SSO-ready identity linking.
- **Detection engine:** expanded MITRE-mapped rule library, entity extraction,
  enrichment (threat intel, asset criticality, identity context).
- **Incidents:** correlation of related investigations into risk-ranked incidents.
- **Risk scoring:** severity × triage confidence × enrichment boost.
- **Response:** action execution engine with pluggable connectors
  (EDR/IdP/firewall), approve→execute gating, rollback tokens.
- **Case management:** status workflow with transition rules, SLA timers, notes,
  assignment.
- **Notifications:** pluggable channels (capture + webhook), high-risk and
  action-executed triggers.
- **Admin API:** tenant-scoped user CRUD, role assignment, SSO linking.
- **Rule management:** per-tenant enable/disable + MITRE coverage.
- **Ops:** structured logging + request IDs, Prometheus `/metrics`, rate
  limiting, retry + circuit breaker, config-driven CORS, pagination/filtering.
- **Frontend:** tenant login + role/permission gating; investigation depth
  (enrichment, SLA, status, execute, notes); incidents, audit, rules/MITRE, and
  admin surfaces; permission-aware navigation and dashboard filters.

## [0.1.0] - 2026-06-08 — Prototype
- Initial agentic detect→triage→respond pipeline, mock Splunk + model, React
  console, full test suites (since superseded by the persistence refactor).
