# Splunk Integration

SentinelAI talks to Splunk through the `SplunkClient` abstraction and to a
hosted model through the `AIModel` abstraction. Both default to deterministic
**mock** implementations so the product runs with no external dependencies.
Switching to live infrastructure is configuration only — no code changes.

## Configuration

All settings are read from environment variables (prefix `SENTINEL_`) or a
`.env` file in `backend/`.

| Variable | Default | Purpose |
|----------|---------|---------|
| `SENTINEL_SPLUNK_BACKEND` | `mock` | `mock` or `live` |
| `SENTINEL_SPLUNK_HOST` | `https://localhost:8089` | Splunk management/REST endpoint |
| `SENTINEL_SPLUNK_TOKEN` | — | Splunk auth token (bearer) |
| `SENTINEL_SPLUNK_MCP_URL` | — | Splunk MCP Server URL (optional) |
| `SENTINEL_AI_BACKEND` | `mock` | `mock` or `live` |
| `SENTINEL_AI_MODEL` | `Foundation-Sec-1.1-8B-Instruct` | Hosted model id |
| `SENTINEL_JWT_SECRET` | `change-me-in-prod` | **Set a strong secret in prod** |

## Going live

1. **Create a Splunk auth token.** In Splunk Web: *Settings → Tokens*, or via
   the REST API. (OAuth client credentials are in Controlled Availability; token
   auth is the supported path to start.)
2. **Point SentinelAI at your instance:**

   ```bash
   export SENTINEL_SPLUNK_BACKEND=live
   export SENTINEL_SPLUNK_HOST=https://your-splunk:8089
   export SENTINEL_SPLUNK_TOKEN=<your-token>
   ```

3. **Enable a hosted model for triage:**

   ```bash
   export SENTINEL_AI_BACKEND=live
   export SENTINEL_AI_MODEL=Foundation-Sec-1.1-8B-Instruct
   ```

   `LiveAIModel` targets an OpenAI-compatible `/v1/chat/completions` endpoint;
   set `SENTINEL_SPLUNK_MCP_URL` if you route model calls via the MCP Server.

4. **Restart the backend.** `GET /api/v1/health` should report
   `"splunk": true, "backend": "live"`.

## Using the Splunk MCP Server (Claude Desktop)

The `LiveSplunkClient` and `LiveAIModel` are structured so the only thing that
changes between the REST transport and the MCP Server transport is the request
plumbing in `_post_search` / `complete`. When wiring through Claude Desktop's
MCP integration, set `SENTINEL_SPLUNK_MCP_URL` to the MCP endpoint and provide
the token; the agent interfaces are unchanged.

## Detection rules

Detection logic lives in `backend/app/agents/detection_agent.py` as a tuple of
`DetectionRule`s. Each rule carries its SPL, base severity, MITRE tactics, and a
minimum event threshold. Add coverage by appending a rule:

```python
DetectionRule(
    rule_id="R004",
    title="Impossible travel",
    description="Same user authenticating from distant geographies in a short window.",
    spl="search index=auth | iplocation src_ip | ...",
    base_severity=Severity.MEDIUM,
    mitre_tactics=("TA0001",),
    min_events=2,
)
```

Against the mock backend, queries containing keywords like `failed`, `network`,
`bytes`, or `powershell` return representative seeded events so you can develop
and test rules offline before validating SPL against live data.
