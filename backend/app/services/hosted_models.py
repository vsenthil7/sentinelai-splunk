"""Splunk hosted-model catalog and task→model routing.

The hackathon highlights specific Splunk-hosted models. SentinelAI does not call
them interchangeably — it routes each agent task to the model designed for it,
which is the difference between "we called a hosted model" and "we used the
*right* hosted model for the job":

- **Foundation-Sec-1.1-8B-Instruct** — Cisco Foundation security LLM. Used for
  the security-reasoning task: alert triage verdicts (true/false positive,
  confidence, recommended severity, MITRE-aware rationale). This is the
  load-bearing model for the Security track.
- **gpt-oss-120b / gpt-oss-20b** — general open-weight LLMs hosted by Splunk.
  Used for the natural-language summarization task (stakeholder incident
  summaries) where a general model is appropriate and cheaper.
- **Cisco Deep Time Series Model** — used for time-series anomaly scoring on
  event-volume baselines (e.g. is this auth-failure burst anomalous vs. the
  host's 30-day baseline). Routed via the ``TIME_SERIES`` task.

Model-agnosticism: every agent depends on the :class:`AIModel` interface, never
a concrete model. This catalog only decides *which* hosted model id and base
task each capability maps to; swapping models is config, not code. The
deterministic parts of the pipeline (rule matching, risk scoring, SLA math,
audit chain) never depend on a model at all (see ``docs/SPLUNK_INTEGRATION.md``).
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class ModelTask(str, Enum):
    """The distinct AI tasks in the pipeline, each routed to a fit-for-purpose model."""

    SECURITY_TRIAGE = "security_triage"
    SUMMARIZATION = "summarization"
    TIME_SERIES = "time_series"


@dataclass(frozen=True)
class HostedModel:
    """A Splunk-hosted model and how SentinelAI uses it."""

    model_id: str
    provider: str
    task: ModelTask
    purpose: str
    # Whether the model is an LLM chat endpoint (vs. a specialized scorer).
    is_chat: bool = True


# Catalog of the Splunk-hosted models referenced by the hackathon, mapped to the
# pipeline task each one serves. This is surfaced read-only at GET /ai/models so
# judges can see the routing.
HOSTED_MODELS: tuple[HostedModel, ...] = (
    HostedModel(
        model_id="Foundation-Sec-1.1-8B-Instruct",
        provider="Cisco Foundation AI (Splunk-hosted)",
        task=ModelTask.SECURITY_TRIAGE,
        purpose="Security-specialized triage: TP/FP verdict, confidence, severity, rationale.",
    ),
    HostedModel(
        model_id="gpt-oss-120b",
        provider="Splunk-hosted (OpenAI gpt-oss)",
        task=ModelTask.SUMMARIZATION,
        purpose="Natural-language incident summaries for stakeholders.",
    ),
    HostedModel(
        model_id="gpt-oss-20b",
        provider="Splunk-hosted (OpenAI gpt-oss)",
        task=ModelTask.SUMMARIZATION,
        purpose="Lighter-weight summarization fallback where latency/cost matters.",
    ),
    HostedModel(
        model_id="Cisco-DeepTimeSeries",
        provider="Cisco Deep Time Series (Splunk-hosted)",
        task=ModelTask.TIME_SERIES,
        purpose="Anomaly scoring of event-volume against per-host baselines.",
        is_chat=False,
    ),
)

# Default model id per task. Live deployments override via env without code change.
DEFAULT_MODEL_FOR_TASK: dict[ModelTask, str] = {
    ModelTask.SECURITY_TRIAGE: "Foundation-Sec-1.1-8B-Instruct",
    ModelTask.SUMMARIZATION: "gpt-oss-120b",
    ModelTask.TIME_SERIES: "Cisco-DeepTimeSeries",
}


def model_for_task(task: ModelTask) -> str:
    """Return the default hosted-model id routed to a task."""
    return DEFAULT_MODEL_FOR_TASK[task]


def catalog() -> list[dict[str, str | bool]]:
    """Serializable view of the hosted-model catalog for the API/UI."""
    return [
        {
            "model_id": m.model_id,
            "provider": m.provider,
            "task": m.task.value,
            "purpose": m.purpose,
            "is_chat": m.is_chat,
        }
        for m in HOSTED_MODELS
    ]
