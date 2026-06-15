"""Incident response agent.

Translates a triage verdict into concrete containment actions. Actions that
change state in the environment always require human approval (human-in-the-loop),
which is an enterprise SOC requirement.
"""
from __future__ import annotations

from app.models.domain import Detection, IncidentAction, TriageVerdict

# Actions that mutate the environment and therefore must be gated.
_GATED_ACTIONS = {"isolate_host", "disable_user", "block_ip", "kill_process"}

_ACTION_TARGET_HINT = {
    "isolate_host": "host",
    "kill_process": "host",
    "disable_user": "user",
    "block_ip": "src_ip",
}


class ResponseAgent:
    def plan(self, detection: Detection, verdict: TriageVerdict) -> list[IncidentAction]:
        if not verdict.is_true_positive:
            return []
        actions: list[IncidentAction] = []
        for action_type in verdict.suggested_actions:
            if action_type in {"monitor", "close_as_fp", "manual_review"}:
                continue
            target = self._resolve_target(detection, action_type)
            actions.append(
                IncidentAction(
                    action_type=action_type,
                    target=target,
                    rationale=f"Recommended by triage (confidence {verdict.confidence:.2f}).",
                    requires_approval=action_type in _GATED_ACTIONS,
                )
            )
        return actions

    @staticmethod
    def _resolve_target(detection: Detection, action_type: str) -> str:
        hint = _ACTION_TARGET_HINT.get(action_type, "entity")
        if hint == "src_ip":
            # entity is a host; in a real system we'd pull src_ip from events.
            return detection.entity
        return detection.entity
