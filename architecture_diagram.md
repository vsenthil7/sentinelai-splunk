# SentinelAI — Architecture Diagram

> Submission-required diagram (Splunk Agentic Ops Hackathon · **Security** track).
> Shows (1) how the application interacts with Splunk, (2) how AI models/agents
> are integrated, and (3) data flow between services, APIs, and components.
> Renders on GitHub (Mermaid). A PNG export is at `docs/architecture_diagram.png`
> when generated; this Markdown file is the source of truth.

SentinelAI is an **agentic Threat Detection & Incident Response** platform that
runs an autonomous SOC loop on Splunk security data: it detects with SPL,
enriches, triages with a Splunk-hosted security LLM, plans containment actions
behind a human approval gate, executes via connectors, and writes every step to
a tamper-evident audit log — all multi-tenant and RBAC-scoped.

---

## 1. How the application interacts with Splunk

SentinelAI talks to Splunk through a single transport-agnostic `SplunkClient`
interface with **three interchangeable backends**, selected by one env var
(`SENTINEL_SPLUNK_BACKEND`). The agents never know which is active.

```mermaid
flowchart LR
    Agent[Detection Agent<br/>SPL rule library]
    subgraph Iface["SplunkClient interface (app/splunk/client.py)"]
        direction TB
        Mock[MockSplunkClient<br/>deterministic seed data]
        Live[LiveSplunkClient<br/>REST /services/search/v2]
        MCP[McpSplunkClient<br/>JSON-RPC tools/call]
    end
    SplunkEnt[(Splunk Enterprise / Cloud<br/>indexes: auth, network, endpoint)]
    MCPSrv[Splunk MCP Server<br/>token auth]

    Agent -->|search SPL| Iface
    Mock -.offline / CI / demo.-> Agent
    Live -->|Bearer token| SplunkEnt
    MCP -->|Bearer token| MCPSrv --> SplunkEnt
```

- **mock** — deterministic synthetic telemetry; powers tests + offline demo, no Splunk needed.
- **live** — Splunk REST search export API, token auth (OAuth is in Controlled Availability per hackathon guidance).
- **mcp** — **Splunk MCP Server** over MCP/JSON-RPC `tools/call`; the agent calls Splunk *as a tool* through one audited channel (targets "Best Use of Splunk MCP Server").

Resilience: every SPL call is wrapped in retry-with-backoff + a circuit breaker;
deterministic query errors are not retried.

---

## 2. How AI models / agents are integrated

Five cooperating agents form the loop. The AI sits behind an `AIModel`
interface; each task is routed to the **fit-for-purpose Splunk-hosted model**.

```mermaid
flowchart TB
    subgraph Agents["Agentic pipeline (app/agents)"]
        Orch[Orchestrator]
        Det[Detection Agent]
        Enr[Enrichment Service]
        Tri[Triage Agent]
        Resp[Response Agent]
    end
    subgraph Models["Splunk hosted models (task-routed)"]
        FSEC[Foundation-Sec-1.1-8B<br/>security triage verdict]
        GPT[gpt-oss-120b/20b<br/>incident summary]
        DTS[Cisco Deep Time Series<br/>volume anomaly score]
    end
    Det -->|SPL hits| Orch
    Orch --> Enr
    Orch --> Tri -->|structured JSON verdict| FSEC
    Orch -->|stakeholder summary| GPT
    Det -.baseline anomaly.-> DTS
    Orch --> Resp
    Resp -->|gated actions| Gate{Human approval}
```

- **Boundary is enforced:** the model returns a *verdict* (TP/FP, confidence,
  rationale); the final **severity/risk number comes from the deterministic
  engine**, not the LLM. Malformed model output falls back to analyst review.
- **Model-agnostic:** swapping a model is config (`SENTINEL_AI_MODEL`,
  `SENTINEL_AI_BACKEND`), never code. Catalog is inspectable at `GET /ai/models`.

---

## 3. Data flow between services, APIs, and components

```mermaid
flowchart LR
    subgraph Client["React/TS Console (web + mobile)"]
        UI[Login · Dashboard · Investigation · Incidents · Audit · Rules · Admin]
    end
    subgraph API["FastAPI · /api/v1 (versioned, RBAC-gated)"]
        MW[Middleware<br/>rate-limit · request-id · metrics]
        Auth[JWT principal + RBAC guard]
        Routes[Routes]
    end
    subgraph Core["Domain services"]
        Orch2[Orchestrator] --> Splk[(Splunk backend)]
        Orch2 --> Mdl[(Hosted model)]
        Exec[Action Executor] --> Conn[(EDR/IdP/Firewall connectors)]
        Corr[Correlation → Incidents]
        Notif[Notifications]
        AuditSvc[Hash-chained Audit]
    end
    DB[(SQLAlchemy async<br/>SQLite dev / Postgres prod<br/>tenant-scoped rows)]

    UI -->|HTTPS JWT| MW --> Auth --> Routes
    Routes --> Orch2
    Routes --> Exec
    Routes --> Corr
    Routes --> Notif
    Routes --> AuditSvc
    Orch2 --> DB
    Exec --> DB
    Corr --> DB
    AuditSvc --> DB
```

**Golden thread (end-to-end, runs in CI on mock):** analyst triggers
`POST /investigations/run` → Detection Agent runs SPL rules against Splunk →
events become Detections with extracted entities → Enrichment adds TI/asset/
identity context → Triage Agent calls Foundation-Sec for a verdict →
deterministic risk score assigned → Response Agent plans containment actions
(approval-gated) → investigations correlated into Incidents → high-risk
Incidents fire notifications → every step appended to the tamper-evident audit
log → analyst approves an action → Executor runs the connector → result audited.

## Tech stack

Backend: Python 3.11+, FastAPI, async SQLAlchemy 2.0, Alembic, structlog,
httpx, python-jose, bcrypt. Frontend: React 18, TypeScript, Vite, React Router.
Tests: pytest (150+ tests), Vitest, Playwright. Deploy: Docker + Compose + nginx.
