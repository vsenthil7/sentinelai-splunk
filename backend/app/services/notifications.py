"""Notifications.

Fans out alerts to channels (Slack/email/PagerDuty/webhook) when noteworthy
events occur — a high-risk investigation is created, or a containment action is
executed. Channels are pluggable; ships with a webhook channel (real HTTP POST)
and an in-memory capture channel for offline dev/demo.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import UTC, datetime

import httpx


@dataclass
class Notification:
    event: str  # e.g. "investigation.high_risk", "action.executed"
    title: str
    severity: str
    body: str
    tenant_id: str
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))


class NotificationChannel(ABC):
    @abstractmethod
    async def send(self, notification: Notification) -> bool: ...


class CaptureChannel(NotificationChannel):
    """Records notifications in memory; useful for dev, demos, and inspection."""

    def __init__(self) -> None:
        self.sent: list[Notification] = []

    async def send(self, notification: Notification) -> bool:
        self.sent.append(notification)
        return True


class WebhookChannel(NotificationChannel):
    """POSTs the notification as JSON to a configured URL (Slack-compatible)."""

    def __init__(self, url: str, timeout: float = 10.0):
        self._url = url
        self._timeout = timeout

    async def send(self, notification: Notification) -> bool:
        payload = {
            "event": notification.event,
            "text": f"[{notification.severity.upper()}] {notification.title}\n{notification.body}",
            "tenant": notification.tenant_id,
        }
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.post(self._url, json=payload)
                return resp.status_code < 400
        except httpx.HTTPError:  # pragma: no cover - network path
            return False


class NotificationService:
    def __init__(self, channels: list[NotificationChannel], high_risk_threshold: int = 80):
        self._channels = channels
        self._threshold = high_risk_threshold

    async def notify(self, notification: Notification) -> int:
        delivered = 0
        for channel in self._channels:
            if await channel.send(notification):
                delivered += 1
        return delivered

    async def maybe_alert_high_risk(
        self, tenant_id: str, title: str, severity: str, risk_score: int
    ) -> int:
        if risk_score < self._threshold:
            return 0
        return await self.notify(
            Notification(
                event="investigation.high_risk",
                title=title,
                severity=severity,
                body=f"High-risk investigation (risk {risk_score}) requires attention.",
                tenant_id=tenant_id,
            )
        )

    async def alert_action_executed(
        self, tenant_id: str, action_type: str, target: str, status: str
    ) -> int:
        return await self.notify(
            Notification(
                event="action.executed",
                title=f"Response action {action_type}",
                severity="high",
                body=f"{action_type} on {target} -> {status}",
                tenant_id=tenant_id,
            )
        )
