# Testing

SentinelAI is built to enterprise test standards: 100% coverage on both tiers,
plus full end-to-end coverage across web and mobile viewports.

## Coverage summary

| Suite | Tool | Tests | Coverage |
|-------|------|-------|----------|
| Backend unit + integration + negative | pytest | 92 | 100% lines |
| Frontend functional + negative | Vitest | 48 | 100% stmts/branches/funcs/lines |
| End-to-end (web + mobile) | Playwright | 22 | all user flows × 2 viewports |

## Backend

```bash
cd backend
pip install -e ".[dev]"
pytest --cov=app --cov-report=term-missing
```

Structure:
- `tests/unit/` — Splunk clients, AI model, agents, core/security/stores/domain.
  Live transports are exercised with stubbed `httpx` clients, so no network is needed.
- `tests/integration/` — full API flows through FastAPI's `TestClient`.
- `tests/negative/` — auth failures, malformed input, missing resources, degraded health.

## Frontend (functional + negative)

```bash
cd frontend
npm install
npm run test:unit          # vitest run --coverage
```

`fetch` is mocked per-test (see `tests/helpers.tsx`), so the component and page
tests run hermetically in jsdom. Coverage thresholds are enforced at 100% in
`vite.config.ts`; the build fails if coverage regresses.

Two genuinely unreachable defensive guards in the detail page are annotated with
`/* c8 ignore */` and a reason, rather than covered with artificial tests.

## End-to-end (Playwright)

```bash
cd frontend
npx playwright install chromium     # one-time, needs network
npm run test:e2e
```

The config boots both servers automatically (FastAPI on :8000 with the mock
backend, Vite preview on :4173) and runs every flow against two projects:
`desktop-chromium` and `mobile-chromium` (Pixel 7).

> **Sandbox note.** In the build sandbox the Playwright browser binary could not
> be downloaded (`cdn.playwright.dev` was outside the network allowlist), so the
> e2e suite is validated via `playwright test --list` there and executes in CI
> and on any machine with normal network access.

## CI

`.github/workflows/ci.yml` runs three gated jobs on every push/PR: backend
(pytest + coverage), frontend unit (vitest + 100% threshold), and e2e
(Playwright across both viewports). Any coverage regression or failing test
breaks the build.
