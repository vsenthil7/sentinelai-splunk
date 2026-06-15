# Contributing

## Standards

- **Backend:** Python 3.11+, typed, `ruff` clean, `mypy --strict` clean.
- **Frontend:** TypeScript strict, `eslint` clean.
- **Coverage is a gate, not a goal:** 100% on both tiers. New code ships with tests.
- Genuinely unreachable defensive branches may use `/* c8 ignore */`
  (frontend) or `# pragma: no cover` (backend) **with a reason comment** — never
  to dodge real coverage.

## Workflow

1. Branch from `main`.
2. Implement with tests in the same change.
3. Run the full local gate:
   ```bash
   cd backend && pytest --cov=app --cov-report=term-missing
   cd frontend && npm run test:unit && npm run test:e2e
   ```
4. Open a PR. CI must be green (backend, frontend unit, e2e).

## Adding a detection

Append a `DetectionRule` in `backend/app/agents/detection_agent.py` and add a
unit test asserting it fires (and is filtered below threshold). See
[SPLUNK_INTEGRATION.md](SPLUNK_INTEGRATION.md).

## Project layout

```
backend/app/{agents,api,core,models,services,splunk}
frontend/src/{api,components,hooks,pages,types}
docs/
.github/workflows/
```
