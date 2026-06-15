"""AI model abstraction for Splunk hosted models.

The agentic layer depends only on ``AIModel``. The mock returns deterministic,
structured reasoning so tests are stable; the live impl targets a Splunk hosted
model (Foundation-Sec-1.1-8B-Instruct / gpt-oss) via an OpenAI-compatible
endpoint and is selected with ``SENTINEL_AI_BACKEND=live``.
"""
from __future__ import annotations

import json
from abc import ABC, abstractmethod
from typing import Any

import httpx


class AIModelError(Exception):
    pass


class AIModel(ABC):
    @abstractmethod
    async def complete(self, system: str, user: str) -> str:
        """Return the model's text completion."""

    async def complete_json(self, system: str, user: str) -> dict[str, Any]:
        text = await self.complete(system, user)
        try:
            parsed: dict[str, Any] = json.loads(text)
            return parsed
        except json.JSONDecodeError as exc:
            raise AIModelError(f"Model did not return valid JSON: {text[:200]}") from exc


class MockAIModel(AIModel):
    """Deterministic security analyst reasoning for tests and offline dev."""

    async def complete(self, system: str, user: str) -> str:
        sys_l = system.lower()
        u = user.lower()
        # Triage-style request -> return structured JSON verdict.
        # Triage prompt explicitly asks for a JSON verdict with specific keys.
        if "return a json" in sys_l and "verdict" in sys_l:
            tp = any(
                k in u
                for k in ("failed", "powershell", "4444", "encoded", "exfil", "bytes", "500000")
            )
            severity = (
                "critical"
                if ("4444" in u or "encoded" in u or "exfil" in u or "bytes" in u)
                else ("high" if tp else "low")
            )
            return json.dumps(
                {
                    "is_true_positive": tp,
                    "confidence": 0.92 if tp else 0.34,
                    "rationale": (
                        "Multiple indicators consistent with an active attack: "
                        "anomalous volume and known-bad patterns."
                        if tp
                        else "Activity is within normal baseline; likely benign."
                    ),
                    "recommended_severity": severity,
                    "suggested_actions": (
                        ["isolate_host", "disable_user", "collect_forensics"]
                        if tp
                        else ["monitor", "close_as_fp"]
                    ),
                }
            )
        # Summary-style request
        return (
            "Investigation summary: correlated events indicate a coordinated "
            "intrusion attempt. Recommended containment actions have been queued "
            "for analyst approval."
        )


class LiveAIModel(AIModel):
    """Targets a Splunk hosted model via an OpenAI-compatible chat endpoint."""

    def __init__(self, base_url: str, model: str, token: str = "", timeout: float = 60.0):
        if not base_url:
            raise AIModelError("AI base_url not configured")
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._headers = {"Authorization": f"Bearer {token}"} if token else {}
        self._timeout = timeout

    async def complete(self, system: str, user: str) -> str:
        url = f"{self._base_url}/v1/chat/completions"
        payload = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": 0.0,
        }
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.post(url, headers=self._headers, json=payload)
            if resp.status_code != 200:
                raise AIModelError(f"Model endpoint error {resp.status_code}: {resp.text[:200]}")
            data = resp.json()
            content: str = data["choices"][0]["message"]["content"]
            return content
