# SentinelAI — Agentic Threat Detection & Incident Response on Splunk

> AT-Hack0029 · Splunk Agentic Ops Hackathon · Security track

SentinelAI is an enterprise-grade agentic SOC assistant built on Splunk. A
chain of AI agents continuously **detects** threats from Splunk telemetry,
**triages** each detection with a Splunk hosted model, and **plans containment
actions** — keeping a human analyst in the loop for anything that changes state
in the environment.

```
 Splunk telemetry ──▶ Detection agent ──▶ Triage agent ──▶ Response agent ──▶ Analyst console
   (SPL rules)          (rule library)     (hosted model)   (gated actions)     (approve / act)
```

## Why it matters

SOC teams drown in alerts. SentinelAI compresses the detect→triage→respond loop
into an agentic pipeline that an analyst supervises rather than operates,
surfacing only true positives with a recommended, reversible action plan.

## Highlights

- **Agentic pipeline** — detection → enrichment → triage → response, orchestrated end-to-end.
- **Multi-tenant + RBAC** — tenant-isolated data, four roles, SSO-ready identity linking.
- **Tamper-evident audit** — append-only hash-chained log with integrity verification.
- **Incident correlation** — related investigations grouped into risk-ranked incidents.
- **SOAR-style response** — pluggable connectors (EDR/IdP/firewall), approve→execute gating, rollback tokens.
- **Case management** — status workflow, SLA timers, notes, assignment.
- **Enrichment & risk scoring** — threat intel, asset criticality, identity context feeding a 0–100 risk score.
- **Splunk-native** — transport-agnostic client (REST search API or MCP Server) with retry + circuit breaker.
- **Operable** — structured logs, Prometheus `/metrics`, rate limiting, configurable CORS.
- **Persistent** — async SQLAlchemy (SQLite dev / Postgres prod).

## Quick start

```bash
# Backend
cd backend
pip install -e ".[dev]"
uvicorn app.main:app --reload --port 8000

# Frontend (separate terminal)
cd frontend
npm install
npm run dev          # http://localhost:5173
```

Sign in with the seeded demo operator: `analyst` / `sentinel-demo`.

By default the app runs against a deterministic **mock Splunk backend** so the
full pipeline and UI work with zero external dependencies. To point it at a real
Splunk instance, see [docs/SPLUNK_INTEGRATION.md](docs/SPLUNK_INTEGRATION.md).

## Documentation

| Doc | Purpose |
|-----|---------|
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | System design, components, data flow, diagrams |
| [docs/API.md](docs/API.md) | REST API reference + RBAC matrix |
| [docs/SECURITY.md](docs/SECURITY.md) | Security model: authZ, tenancy, audit, hardening |
| [docs/OPERATIONS.md](docs/OPERATIONS.md) | Config, observability, resilience, runbook |
| [docs/SPLUNK_INTEGRATION.md](docs/SPLUNK_INTEGRATION.md) | Wiring to real Splunk / MCP / hosted models |
| [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) | Running, configuring, and deploying |
| [docs/TESTING.md](docs/TESTING.md) | Test strategy (suite repair pending post-refactor) |
| [docs/CONTRIBUTING.md](docs/CONTRIBUTING.md) | Dev workflow and standards |
| [docs/CHANGELOG.md](docs/CHANGELOG.md) | Release history |
| [BUILD_PLAN.md](BUILD_PLAN.md) | Enterprise hardening sprint log |
| [ENTERPRISE_TRACKER.md](ENTERPRISE_TRACKER.md) | Module-level status |

## Tech stack

Backend: Python 3.11+, FastAPI, Pydantic v2, pytest.
Frontend: React 18, TypeScript, Vite, Vitest, Playwright.

## License

See [LICENSE](LICENSE).
