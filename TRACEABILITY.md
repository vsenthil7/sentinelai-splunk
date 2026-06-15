# SentinelAI — Traceability Matrix

Maps every requirement (hackathon submission rules, judging criteria, and the
SaaS-depth product requirements) to the component that implements it, the tests
that verify it, and the sprint that delivers it. Kept in lockstep with
`SPRINT_TRACKER.md`. Status: ✅ done · 🅿️ partial · ⬜ planned.

---

## A. Hackathon submission requirements (splunk.devpost.com/rules)

| ID | Requirement | Implementation | Tests / Evidence | Status |
|----|-------------|----------------|------------------|--------|
| H-1 | Security track fit (detect threats faster, investigate, automate) | full agentic pipeline `app/agents/*` | integration `test_investigations.py` | ✅ |
| H-2 | Uses Splunk AI capability | MCP Server backend + hosted models | `test_infra::TestMcpSplunkClient`, `TestHostedModels` | ✅ |
| H-3 | Public OSS repo + OSI license | `LICENSE` (MIT) | visible at repo root | 🅿️ (push = SP13) |
| H-4 | README with setup/run instructions | `README.md` + `docs/` | manual | 🅿️ (re-point = SP12) |
| H-5 | Required deps + example config | `pyproject.toml`, `.env.example`, compose | install verified | ✅ |
| H-6 | `architecture_diagram.(md\|pdf\|png)` at root | `architecture_diagram.md` | renders on GitHub | ✅ |
| H-7 | Shows how app interacts with Splunk | diagram §1 + `splunk/` | `TestMcpSplunkClient`, `TestLiveSplunkSuccess` | ✅ |
| H-8 | Shows how AI/agents integrated | diagram §2 + `agents/`, `hosted_models.py` | `test_agents_security.py` | ✅ |
| H-9 | Shows data flow services/APIs/components | diagram §3 | n/a | ✅ |
| H-10 | Demo video <3 min (public) | script in SP14 | Senthil records | ⬜ |

## B. Judging criteria (equally weighted)

| ID | Criterion | How addressed | Status |
|----|-----------|---------------|--------|
| J-1 | Technological implementation (quality dev) | 155 BE/74 FE tests, mypy --strict, CI, migrations, Docker | ✅ |
| J-2 | Design (UX well thought out) | permission-aware React console; SaaS surfaces SP11 | 🅿️ |
| J-3 | Potential impact | autonomous SOC loop + multi-tenant SaaS + cost model | 🅿️ |
| J-4 | Quality/creativity of idea | agent-to-Splunk via MCP + right-model-for-task routing | ✅ |

## C. Bonus prizes

| ID | Prize | Implementation | Tests | Status |
|----|-------|----------------|-------|--------|
| B-1 | Best Use of Splunk MCP Server | `splunk/mcp_client.py` + factory `mcp` backend | `TestMcpSplunkClient` (13) | ✅ |
| B-2 | Best Use of Splunk Hosted Models | `services/hosted_models.py` task routing | `TestHostedModels` (3) + `GET /ai/models` | ✅ |
| B-3 | Best Use of Splunk Developer Tools | Python SDK patterns, App Inspect alignment | SP12 docs | ⬜ |

## D. Multi-tenant SaaS product requirements (Senthil)

| ID | Requirement | Implementation (planned) | Tests | Sprint | Status |
|----|-------------|--------------------------|-------|--------|--------|
| S-1 | Tenant isolation at data layer | `tenant_id` on every row + scoped repos | `test_auth_rbac.py` cross-tenant 404 | SP0 | ✅ |
| S-2 | Login with tenant + role-based access | `LoginPage` (tenant field), RBAC matrix | `test_auth_rbac.py`, FE `pages.test` | SP0 | ✅ |
| S-3 | Role is assigned, not self-selected | role from `UserRow`, RBAC `require()` | `test_auth_rbac.py` | SP0 | ✅ |
| S-4 | Tenant-scoped admin (manage own users) | `admin_routes.py`, `AdminPage` | `TestAdmin` | SP0 | 🅿️ (users only) |
| S-5 | Tenant model: status/plan/trial/settings | `TenantRow` + `TenantRepository` + migration b1f2c3d4e5a6 | `test_repositories::test_tenant_*`, `test_admin_rules_audit::TestTenantStatus` | SP5 | ✅ |
| S-6 | Provider super-admin (manage ALL tenants/users) | `provider_routes.py` + `PROVIDER_ADMIN` role | `test_provider::TestProviderTenantManagement`, `TestProviderIsolation`, `test_agents_security::TestRBACProviderScope` | SP6 | ✅ |
| S-7 | Provider impersonation for support (audited) | `provider_routes::impersonate` (dual-partition audit) | `test_provider::test_impersonate` | SP6 | ✅ |
| S-8 | Per-tenant credentials (BYO Splunk/model/MCP) | `TenantCredentialRow` (encrypted) + resolver | new | SP7 | ⬜ |
| S-9 | "Use managed (our keys)" vs "BYO" toggle | settings API + resolver fallback + UI | new | SP7/SP11 | ⬜ |
| S-10 | Per-tenant env/config page | `GET/PUT /tenant/settings` + Settings UI | new | SP7/SP11 | ⬜ |
| S-11 | Usage metering (searches/model/tokens/actions) | `UsageEventRow` + meter hooks | new | SP8 | ⬜ |
| S-12 | Cost calculation (price book → per-tenant cost) | `CostService` + price book | new | SP8 | ⬜ |
| S-13 | Quotas + plan enforcement | plan→quota map, 402/429 gating | new | SP9 | ⬜ |
| S-14 | Usage & cost dashboard (tenant + provider rollup) | `GET /tenant/usage`, `/provider/usage` + UI | new | SP9/SP11 | ⬜ |
| S-15 | Tenant self-service signup/onboarding | `POST /signup` + wizard | new | SP10 | ⬜ |
| S-16 | Secrets never leak (write-only, encrypted, not logged) | Fernet + redaction + write-only schema | new | SP7 | ⬜ |

## E. Enterprise non-functionals (carried, verified)

| ID | Requirement | Implementation | Status |
|----|-------------|----------------|--------|
| E-1 | Append-only tamper-evident audit | `services/audit.py` hash chain | ✅ |
| E-2 | Observability (metrics, request-id, structured logs) | `core/metrics.py`, `middleware.py` | ✅ |
| E-3 | Resilience (retry + circuit breaker on Splunk) | `core/resilience.py` | ✅ |
| E-4 | Migrations (Alembic) | `backend/alembic/` | ✅ |
| E-5 | Containerized deploy | Dockerfiles + compose + nginx | ✅ |
| E-6 | Health probes (live/ready) | `/health/live`, `/health/ready` | ✅ |
| E-7 | Server-side token revocation | `RevokedTokenRow` + `/auth/logout` | ✅ |
| E-8 | Detection precision/recall vs ground truth | `SEED_MANIFEST.md` + `test_detection_quality.py` | ✅ |
