"""Detection-quality regression gate (precision / recall / F1 vs SEED_MANIFEST.md).

Runs the real detection + correlation pipeline against the deterministic mock
Splunk backend and asserts it recovers every planted threat with no false
positives. A drop fails the build. See SEED_MANIFEST.md for the ground truth.
"""
from __future__ import annotations

from app.agents.detection_agent import DetectionAgent
from app.agents.orchestrator import Orchestrator
from app.services.ai_model import MockAIModel
from app.services.correlation import correlate
from app.splunk.mock_client import MockSplunkClient

# Ground truth from SEED_MANIFEST.md: rule_id -> (entity, mitre tactics).
GROUND_TRUTH: dict[str, tuple[str, frozenset[str]]] = {
    "R001": ("web-prod-01", frozenset({"TA0006"})),
    "R004": ("web-prod-01", frozenset({"TA0006", "TA0001"})),
    "R002": ("db-prod-02", frozenset({"TA0010"})),
    "R003": ("ws-finance-07", frozenset({"TA0002", "TA0005"})),
    "R005": ("ws-finance-07", frozenset({"TA0004"})),
}
EXPECTED_INCIDENTS = 3


def _title_to_rule(title: str) -> str | None:
    mapping = {
        "Brute-force authentication": "R001",
        "Successful login after brute force": "R004",
        "Suspicious outbound network traffic": "R002",
        "Encoded PowerShell execution": "R003",
        "Privilege escalation attempt": "R005",
    }
    return mapping.get(title)


class TestDetectionQuality:
    async def test_recall_precision_f1_perfect_on_seed(self):
        agent = DetectionAgent(MockSplunkClient())
        detections = await agent.run()

        detected_rules: dict[str, tuple[str, frozenset[str]]] = {}
        false_positives = 0
        for d in detections:
            rule = _title_to_rule(d.title)
            if rule is None or rule not in GROUND_TRUTH:
                false_positives += 1
                continue
            detected_rules[rule] = (d.entity, frozenset(d.mitre_tactics))

        true_positives = 0
        for rule, (entity, tactics) in GROUND_TRUTH.items():
            if rule in detected_rules:
                got_entity, got_tactics = detected_rules[rule]
                assert got_entity == entity, f"{rule}: entity {got_entity} != {entity}"
                assert got_tactics == tactics, f"{rule}: tactics {got_tactics} != {tactics}"
                true_positives += 1

        recall = true_positives / len(GROUND_TRUTH)
        precision = true_positives / (true_positives + false_positives)
        f1 = 2 * precision * recall / (precision + recall)

        assert recall == 1.0, f"recall {recall} (detected {true_positives}/{len(GROUND_TRUTH)})"
        assert precision == 1.0, f"precision {precision} ({false_positives} false positives)"
        assert f1 == 1.0

    async def test_negative_control_no_detection_on_benign(self):
        # A query matching no planted family returns 0 events -> 0 detections.
        client = MockSplunkClient()
        result = await client.search("search index=web status=200 benign traffic")
        assert result.event_count == 0

    async def test_correlation_groups_to_expected_incidents(self):
        orch = Orchestrator(MockSplunkClient(), MockAIModel())
        investigations = await orch.run_full_pipeline()
        incidents = correlate(investigations)
        assert len(investigations) == len(GROUND_TRUTH)
        assert len(incidents) == EXPECTED_INCIDENTS

    async def test_crown_jewel_exfil_risk_ranks_high(self):
        # GT-3 (db-prod-02 crown jewel + malicious TI) should triage true-positive.
        orch = Orchestrator(MockSplunkClient(), MockAIModel())
        investigations = await orch.run_full_pipeline()
        exfil = next(
            i for i in investigations
            if i.detection.title == "Suspicious outbound network traffic"
        )
        assert exfil.detection.enrichment["asset_criticality"] == "crown_jewel"
        assert exfil.verdict is not None and exfil.verdict.is_true_positive is True
