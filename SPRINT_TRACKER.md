# SentinelAI — Sprint Tracker (Splunk Agentic Ops Hackathon · Security track)

**Mode:** continuous mini-sprint dev. Every sprint leaves the product releasable
(backend + frontend green, tests pass, docs updated). Submission is a *snapshot*;
dev continues after. No scope reduction without explicit sign-off from Senthil.

**Definition of Done (every sprint):** feature works end-to-end (API + UI where
user-facing) · RBAC + tenant isolation enforced & tested · every material action
audited · unit + integration + negative tests pass · `ruff` + `mypy --strict`
clean · frontend `tsc` + build clean · docs + this tracker + TRACEABILITY.md
updated.

Legend: ✅ done · 🔄 in progress · ⬜ planned · 🅿️ partial (built but shallow)

---

## Part A — Done before SaaS-depth planning (this session)

| Sprint | Goal | Tests | Gates | Status | Commit |
|--------|------|-------|-------|--------|--------|
| SP0 | Baseline import, git init, LF normalization | 137 BE / 74 FE pass (verified) | ruff/mypy clean | ✅ | 74fd637 |
| SP0.1 | Fix real bugs: pyproject build-system/packaging; ruff lint in tests | 137 BE pass | ✅ | ✅ | e4fea91 |
| SP1 | **Splunk MCP Server backend** (McpSplunkClient, JSON-RPC tools/call, factory+config) | +13 (150 BE) | ✅ | ✅ | 5021f92 |
| SP2 | **Splunk hosted-model catalog + task routing** + GET /ai/models | +5 (155 BE) | ✅ | ✅ | f71d99b |
| SP3 | Required root `architecture_diagram.md` (Splunk/AI/dataflow) | n/a (docs) | n/a | ✅ | 7ed2d79 |

Current verified baseline: **Backend 155 tests / 98% cov · Frontend 74 tests / 99% · ruff + mypy --strict clean.**

---

## Part B — SaaS-depth roadmap (planned now, execute sprint by sprint)

> Rationale: the product is *architecturally* multi-tenant (every row tenant-scoped,
> cross-tenant reads 404) but not *operationally* SaaS. There is no tenant
> self-service, no provider super-admin plane, no per-tenant credentials/BYO-key,
> no usage metering / cost / billing. Part B closes that gap. Ordered by dependency.

### SP4 — Detection-quality evidence (carry-over, fast) ✅
`SEED_MANIFEST.md` enumerates 5 planted threats (GT-1..GT-5) with ground-truth
rule/entity/MITRE labels, enrichment + correlation ground truth, and metric
definitions. `tests/test_detection_quality.py` is the regression gate: verified
**recall 1.0, precision 1.0, F1 1.0** on the seed, 3 incidents from 5
investigations, crown-jewel exfil triaged true-positive, benign query → 0
detections. 159 BE tests / 98% cov. (THREAT_MODEL.md folded into SP12 docs.)

### SP5 — Tenancy model deepened (foundation for all SaaS work) ✅
Extended `TenantRow` with `status` (active/suspended/trial), `plan`
(free/pro/enterprise), `trial_ends_at`, `settings` JSON. `TenantRepository` gains
create(status/plan/trial), list-all (provider use), set_status, set_plan,
update_settings (merge). Migration `b1f2c3d4e5a6` adds the columns with server
defaults; verified upgrade+downgrade clean on fresh DB. **Suspended-tenant
enforcement**: blocked at login (403) AND on existing tokens via get_principal
(403). 164 BE tests / 98% cov, ruff + mypy clean. Default tenant seeds as
enterprise/active.

### SP6 — Provider super-admin plane (the "manage ALL tenants/users" page) ✅
New `PROVIDER_ADMIN` role + `PROVIDER` permission. **Critical isolation fix:**
tenant ADMIN's wildcard no longer grants the provider scope (was `set(Permission)`,
now excludes PROVIDER; `has_permission` hard-denies PROVIDER to non-provider roles).
`provider_routes.py`: GET/POST tenants, suspend/reactivate (PUT status), set plan,
cross-tenant user list, audited impersonation (token issued as tenant admin, logged
on BOTH platform + target-tenant partitions). `require_provider` gate. Seeded
platform tenant `__platform__` + provider user. 187 BE tests / 98% cov (provider
routes fully covered incl. all 403 isolation paths), ruff + mypy clean.
Provider login: tenant `__platform__`, user `provider`, password `provider-demo`.

### SP7 — Per-tenant credentials + BYO-API / key management ✅
`TenantCredentialRow` with secrets **encrypted at rest** (Fernet via
`app/core/crypto.py`, key from `SENTINEL_SECRET_KEY`). `CredentialRepository`
(upsert with None=unchanged / ""=clear semantics) + `CredentialView` (secrets
exposed only as `*_set` booleans, never values). Resolver `resolve_splunk_client`
/ `resolve_ai_model` picks managed (shared) vs BYO (tenant's own decrypted creds)
per request; `get_tenant_orchestrator` makes it load-bearing so two tenants can
target different Splunk/MCP/model backends in one running server. API:
GET/PUT `/tenant/settings`, GET/PUT `/tenant/credentials` (admin-only,
secrets write-only, audited without leaking values). Migration `c2d3e4f5a6b7`
(upgrade+downgrade verified). Caught+fixed a real def-time NameError
(`get_tenant_orchestrator` referencing `get_principal` before definition).
207 BE tests / 98% cov, ruff + mypy clean. cryptography added to deps.

### SP8 — Usage metering + cost engine ✅
`UsageEventRow` (kind: search|model_call|tokens|action, quantity, denormalized
`cost_cents`, detail, ts) + migration `d3e4f5a6b7c8`. `MeteringService` with a
configurable `PriceBook` (cents-per-unit from env: search 2¢, model_call 5¢,
tokens 1¢/1k, action 10¢) computes cost at record time and rolls up per tenant
grouped by kind (SQL aggregation, optional time window; tokens billed per-1k block,
rounded up). **Meter hooks**: `investigations/run` records 1 search per enabled
rule + 1 model_call per investigation; `execute` records 1 action. **APIs**:
`GET /tenant/usage` (own rollup, admin-gated) + `GET /provider/usage` (platform-wide
per-tenant + grand total, provider-gated). 222 BE tests / 98% cov (metering 100%),
ruff + mypy clean, all 4 migrations upgrade+downgrade verified. Honest note: token
counts will be estimates until a live model returns real usage.

### SP9 — Billing surface: quotas, plans, cost dashboard ✅ (APIs; UI in SP11)
`PLAN_QUOTAS` map (free 100 searches/50 model-calls per month, trial 250/150,
pro 10k/5k, enterprise unlimited). `QuotaService` computes month-to-date usage
from `usage_events` and enforces: `investigations/run` calls `check_or_raise`
BEFORE doing work and returns **429** with `{error:quota_exceeded,kind,used,limit}`
when a plan cap would be exceeded; enterprise is never blocked. Soft-warn flag at
80%. `GET /tenant/quota` exposes per-kind headroom (used/limit/remaining/warn).
236 BE tests / 98% cov (quotas 100%), ruff + mypy clean. Honest gap: counts are
read per-check (no row lock) so tiny overage is possible under high concurrency —
documented; a hard financial gate would use reserved counters.

### SP10 — Tenant self-service onboarding ⬜
Public `POST /signup` → creates tenant (trial plan) + first admin user, audited,
rate-limited, with guard rails (no provider escalation). "Create workspace" flow in UI
+ first-run setup wizard (pick managed vs BYO Splunk). 
*DoD:* a brand-new tenant can sign up, log in, and run the golden thread on managed mock.

### SP11 — Frontend SaaS surfaces ⬜
Provider console (tenant list + suspend/usage), tenant Settings (credentials/BYO,
plan, seats), Usage & Cost page, signup/onboarding wizard, plan/quota banners.
Permission-gated nav for `PROVIDER_ADMIN` vs tenant `ADMIN`.
*DoD:* all new surfaces render, permission-aware, covered by Vitest + a Playwright e2e.

### SP12 — Re-point docs + README to Security track & SaaS ⬜
README: Security-track framing, rubric map, editions/packaging, BYO vs managed,
cost model, setup (mock + live Splunk + MCP). SECURITY.md: add credential encryption,
provider-plane threat model. OPERATIONS.md: key rotation, quota ops.
*DoD:* docs match shipped behavior; KNOWN_GAPS honest.

### SP13 — Push to GitHub (public, MIT) + CI green ✅
Repo live + public: **https://github.com/vsenthil7/sentinelai-splunk** (MIT detected
by GitHub, root architecture_diagram.md present). Moved ahead of SaaS sprints
because Vultr deploy clones from GitHub. CI green check pending first Actions run.

**Deployed live (2026-06-15):** http://45.77.52.54:8093 (Vultr, Docker compose +
override). Verified: title=SentinelAI, /health ok, /health/ready ready (Postgres +
Alembic migrations + nginx proxy all confirmed). Three real deploy bugs fixed in the
process: (1) Dockerfile copied app/ after `pip install -e .` though pyproject
declares packages=[app]; (2) backend host-port 8000 collided via compose port-list
merge — moved to `expose`; (3) frontend host-port 8080 same issue — published only
via override (8093). db on 5435.

### SP14 — Demo script + live-Splunk validation guide ⬜
3-min demo shot list (problem → golden thread → MCP/hosted-model proof → audit →
provider plane). Consolidated live-Splunk + MCP + AITK setup guide in repo.
*DoD:* you can record from the script; live wiring documented step-by-step.

---

## Live-infra dependencies (Senthil, in parallel — does not block dev)
1. Splunk Enterprise trial + Developer License → host + token.
2. Splunk MCP Server app (Splunkbase) → MCP endpoint URL + token.
3. Splunk AI Toolkit + hosted-model access → model endpoint.
4. Devpost registration (Security track) + YouTube for demo video.

## Honest gaps (live until addressed)
- Token-usage cost is an estimate unless the live model returns real usage counts.
- Credential encryption uses app-managed Fernet key (`SENTINEL_SECRET_KEY`); a prod
  deployment should use a KMS/Key Vault. Documented, not faked.
- Rate limiter / quota counters in-process; multi-instance needs Redis.
- Live Splunk/MCP/model wiring requires validation against real infra (SP14).
