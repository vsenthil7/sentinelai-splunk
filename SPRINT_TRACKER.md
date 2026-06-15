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

### SP4 — Detection-quality evidence (carry-over, fast) ⬜
`SEED_MANIFEST.md` enumerating every planted threat in the mock with ground-truth
labels + rule that should catch it; a precision/recall test asserting the pipeline
detects them (regression gate). `THREAT_MODEL.md` (STRIDE) mapped to tests.
*DoD:* precision/recall test in CI; manifest matches mock output.

### SP5 — Tenancy model deepened (foundation for all SaaS work) ⬜
Extend `TenantRow`: `status` (active/suspended/trial), `plan` (free/pro/enterprise),
`created_at`, `trial_ends_at`, `settings` JSON. New `TenantSettingsRow` for
per-tenant config. Domain + repo + migration. Seed default tenant as `enterprise/active`.
*DoD:* migration applies; tenant CRUD respects status; suspended tenant → 403 at auth.

### SP6 — Provider super-admin plane (the "manage ALL tenants/users" page) ⬜
New `PROVIDER_ADMIN` role above tenant admin (platform owner — you). New
`provider_routes.py`: list/create/suspend/reactivate tenants, list users across
tenants, impersonate-for-support (audited), platform-wide audit view. Guarded by a
provider-scope principal claim; **never** exposed to tenant admins.
*DoD:* provider can manage any tenant; tenant admin gets 403 on provider routes;
every provider action audited with `provider.*` actions; tenant isolation still holds
for tenant-scoped roles.

### SP7 — Per-tenant credentials + BYO-API / key management ⬜
`TenantCredentialRow` (encrypted at rest via Fernet/`SENTINEL_SECRET_KEY`): per-tenant
Splunk host/token, MCP URL/token, model backend + key. New settings API
(`GET/PUT /tenant/settings`, `PUT /tenant/credentials`) — tenant admin only,
write-only secrets (never returned in clear). **Credential resolver**: factory picks
per-tenant creds at request time, falling back to provider-managed shared creds when
the tenant opts into "use SentinelAI's Splunk" (managed mode). UI: Settings page with
"Bring your own" vs "Use managed" toggle.
*DoD:* two tenants can target different Splunk backends in the same running server;
secrets never leak in API responses or logs; resolver tested for both modes.

### SP8 — Usage metering + cost engine ⬜
`UsageEventRow` (tenant_id, kind: search|model_call|action|tokens, quantity, cost_cents,
ts). Meter hooks in detection agent (per SPL search), ai_model (per call + token
estimate), executor (per action). `CostService`: configurable price book
(per-search, per-1k-tokens by model, per-action), rolls usage → cost per tenant per
period. Honest note: token counts are estimates unless the live model returns usage.
*DoD:* running the pipeline emits usage events; cost rollup computes; price book
configurable; tested.

### SP9 — Billing surface: quotas, plans, cost dashboard ⬜
Plan → quota map (searches/month, model calls/month, seats). Quota enforcement
(soft warn at 80%, hard 402/429 at 100% for free/trial). `GET /tenant/usage` +
`GET /provider/usage` (all tenants). UI: per-tenant Usage & Cost dashboard (charts),
provider revenue rollup. ROI/cost calculator in README (§P commercial readiness).
*DoD:* quota enforced + tested; usage dashboard renders; provider sees cross-tenant rollup.

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

### SP13 — Push to GitHub (public, MIT) + CI green ⬜
Create public repo under `vsenthil7`, push all history, confirm CI (ruff/mypy/pytest/
frontend/build) passes on GitHub Actions.
*DoD:* public repo with OSI license visible; green CI badge.

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
