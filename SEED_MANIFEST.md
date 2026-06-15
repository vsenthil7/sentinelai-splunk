# SEED_MANIFEST.md — Ground-truth labels for the deterministic mock

The mock Splunk backend (`app/splunk/mock_client.py`) emits deterministic
security telemetry so the full agentic pipeline runs offline and its detection
quality is **measurable**, not asserted. This manifest enumerates every planted
threat, the rule that should catch it, and the expected detection — enabling
precision / recall / F1 measurement against ground truth (verified by
`tests/test_detection_quality.py`, a CI regression gate).

All values below were verified empirically against the running pipeline on
2026-06-15 (5/5 planted threats detected; 0 false positives).

## Planted threats (ground truth)

| GT-ID | Scenario | Mock signal | Detecting rule | MITRE | Expected entity | Events | Severity |
|-------|----------|-------------|----------------|-------|-----------------|--------|----------|
| GT-1 | Brute-force authentication | 12 failed logins for `admin` from `203.0.113.0/24` (TI-malicious) | R001 | TA0006 | web-prod-01 | 12 | high |
| GT-2 | Successful login after brute force (compromise) | same failed-auth burst, success branch | R004 | TA0006, TA0001 | web-prod-01 | 12 | critical |
| GT-3 | Suspicious outbound traffic (exfil) | 5 outbound conns to `198.51.100.0/24:4444` (TI-malicious), 540 KB each | R002 | TA0010 | db-prod-02 (crown jewel) | 5 | high |
| GT-4 | Encoded PowerShell execution | 3 `powershell.exe -enc` from `winword.exe` parent | R003 | TA0002, TA0005 | ws-finance-07 | 3 | critical |
| GT-5 | Privilege escalation attempt | 3 endpoint process events (priv-esc) | R005 | TA0004 | ws-finance-07 | 3 | high |

**Total planted threats: 5. Expected detections: 5. Expected false positives: 0.**

## Enrichment ground truth (for risk-scoring validation)

- **Malicious IP prefixes** (threat-intel verdict = malicious): `203.0.113.`, `198.51.100.`
- **Crown-jewel assets** (criticality = crown_jewel): `db-prod-02`, `dc-01`, `vault-01`
- **High-value assets** (criticality = high): `web-prod-01`, `ws-finance-07`
- **Privileged users**: `admin`, `root`, `svc_backup`

These drive the deterministic risk boost (crown_jewel ×1.3, malicious TI ×1.25,
privileged identity ×1.15), so GT-2 and GT-3 should risk-rank highest.

## Correlation ground truth

Investigations correlate into **incidents** by shared entity / overlapping
indicators:
- GT-1 + GT-2 merge on shared host `web-prod-01` + shared `203.0.113.*` IPs.
- GT-4 + GT-5 merge on shared host `ws-finance-07`.
- GT-3 stands alone on `db-prod-02`.
Expected incidents: **3** (from 5 investigations).

## Negative controls (must NOT detect)

A query matching none of the planted families returns **0 events**, so a
benign/empty search must produce **0 detections** — this is the false-positive
guard in the quality test.

## Metric definitions

- **Recall** = detected planted threats / total planted threats. Target: 1.0 (5/5).
- **Precision** = true detections / all detections. Target: 1.0 (no FPs on mock).
- **F1** = harmonic mean. Target: 1.0.
- **Regression gate:** `test_detection_quality.py` fails the build if recall < 1.0
  or any unexpected detection appears on the seeded mock.
