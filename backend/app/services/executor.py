"""Action execution engine (SOAR-style).

Approved response actions are dispatched to connectors that actually effect the
change in the environment (isolate an endpoint via EDR, disable a user in the
IdP, block an IP at the firewall). Connectors are pluggable; ships with a mock
connector for offline dev. Every execution is recorded with a result so the
console can show what ran, what succeeded, and what to roll back.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import UTC, datetime


@dataclass
class ExecutionResult:
    action_type: str
    target: str
    status: str  # success | failed | unsupported
    detail: str
    executed_at: datetime
    rollback_token: str | None = None


class ActionConnector(ABC):
    """A connector executes a class of actions against an external system."""

    @abstractmethod
    def supports(self, action_type: str) -> bool: ...

    @abstractmethod
    async def execute(self, action_type: str, target: str) -> ExecutionResult: ...


class MockConnector(ActionConnector):
    """Deterministic connector simulating EDR/IdP/firewall outcomes."""

    _SUPPORTED = {
        "isolate_host": "EDR",
        "kill_process": "EDR",
        "disable_user": "IdP",
        "block_ip": "Firewall",
        "collect_forensics": "EDR",
    }

    def supports(self, action_type: str) -> bool:
        return action_type in self._SUPPORTED

    async def execute(self, action_type: str, target: str) -> ExecutionResult:
        system = self._SUPPORTED[action_type]
        return ExecutionResult(
            action_type=action_type,
            target=target,
            status="success",
            detail=f"{system}: {action_type} applied to {target}",
            executed_at=datetime.now(UTC),
            rollback_token=f"rb-{action_type}-{target}",
        )


class ActionExecutor:
    def __init__(self, connectors: list[ActionConnector]):
        self._connectors = connectors

    async def execute(self, action_type: str, target: str) -> ExecutionResult:
        for connector in self._connectors:
            if connector.supports(action_type):
                return await connector.execute(action_type, target)
        return ExecutionResult(
            action_type=action_type,
            target=target,
            status="unsupported",
            detail=f"No connector supports '{action_type}'",
            executed_at=datetime.now(UTC),
        )
