# Live Splunk Setup Guide

How to take SentinelAI from the offline `mock` backend to a real Splunk
instance. The product runs fully on mock with zero Splunk required; this guide
unlocks the `live` and `mcp` backends and the two bonus-prize integrations.

> **Network prerequisite (the key constraint):** SentinelAI's backend and the
> Splunk instance must be able to reach each other over the network. Pick one:
> 1. Run SentinelAI locally (docker compose on the same PC as Splunk) → reaches `localhost:8089`.
> 2. Splunk Cloud (public URL) → the Vultr-hosted SentinelAI can reach it.
> 3. Splunk on the same Vultr box as SentinelAI → reaches it at `localhost`.

## Part 1 — Install Splunk Enterprise (Windows)
1. splunk.com → Trials & Downloads → Splunk Enterprise → Windows 64-bit `.msi` (60-day trial).
2. Install; run as Local System; set an admin username + password (save them).
3. Splunk opens at http://localhost:8000. Web UI = :8000, REST/management API = :8089 (SentinelAI uses :8089).

## Part 2 — Load data
- Settings → Add Data → Upload a log file (or use tutorial data). Note the index (default `main`).

## Part 3 — Create an auth token
- Settings → Tokens → Enable Token Authentication → New Token.
- User `admin`, Audience `sentinelai`, Expiration +180d → Create.
- Copy the token once (starts with `eyJ...`). This is `SENTINEL_SPLUNK_TOKEN`.

## Part 4 — Verify Splunk API (before SentinelAI)
```
curl.exe -k -H "Authorization: Bearer YOUR_TOKEN" "https://localhost:8089/services/server/info?output_mode=json"
```
JSON = good. 401 = bad token. Refused = Splunk not running.

## Part 5 — Wire SentinelAI (per-tenant BYO, recommended)
Log in to SentinelAI as the tenant admin to get a login token, then:
```
curl -s -X PUT http://<sentinelai-host>:8093/api/v1/tenant/credentials \
  -H "Authorization: Bearer <SENTINELAI_LOGIN_TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{"mode":"byo","splunk_backend":"live","splunk_host":"https://<splunk>:8089","splunk_token":"<SPLUNK_TOKEN>"}'
```
Run the pipeline against live Splunk:
```
curl -s -X POST http://<sentinelai-host>:8093/api/v1/investigations/run \
  -H "Authorization: Bearer <SENTINELAI_LOGIN_TOKEN>"
```
Global alternative: set `SPLUNK_BACKEND=live`, `SENTINEL_SPLUNK_HOST`, `SENTINEL_SPLUNK_TOKEN` in `.env` (only if SentinelAI runs on the same host as Splunk).

## Part 6 — Bonus-prize integrations
- **Splunk MCP Server** (Splunkbase): install into Splunk → set tenant creds `splunk_backend=mcp`, `splunk_mcp_url=...`, MCP token. → "Best Use of Splunk MCP Server".
- **Splunk AI Toolkit** (Splunkbase): install → hosted models (Foundation-Sec, gpt-oss, Cisco Deep Time Series) → set `ai_backend=live`. → "Best Use of Splunk Hosted Models".

## Part 7 — Developer License (optional, extends trial)
dev.splunk.com → request Developer License → apply in Splunk (Settings → Licensing) to extend 60-day trial to 6 months.

## Honest validation note
The integration code (live + mcp clients, hosted-model routing) is tested against
faithful stubbed transports in CI. The live round-trip must be validated against a
real instance using the curl checks above — it cannot be exercised from the build
sandbox (no network path to Splunk).
