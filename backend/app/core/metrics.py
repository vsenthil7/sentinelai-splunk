"""Minimal in-process metrics.

Tracks request counts, status classes, and latency buckets, and exposes them in
Prometheus text format at /metrics. Intentionally dependency-free; swap for
prometheus_client in prod if richer histograms are needed.
"""
from __future__ import annotations

import threading
from collections import defaultdict


class Metrics:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._requests: dict[tuple[str, int], int] = defaultdict(int)
        self._latency_sum_ms: float = 0.0
        self._latency_count: int = 0

    def record_request(self, method: str, status_code: int, duration_ms: float) -> None:
        with self._lock:
            self._requests[(method, status_code)] += 1
            self._latency_sum_ms += duration_ms
            self._latency_count += 1

    def render(self) -> str:
        with self._lock:
            lines = [
                "# HELP sentinel_requests_total Total HTTP requests by method and status.",
                "# TYPE sentinel_requests_total counter",
            ]
            for (method, code), count in sorted(self._requests.items()):
                lines.append(
                    f'sentinel_requests_total{{method="{method}",status="{code}"}} {count}'
                )
            avg = (
                self._latency_sum_ms / self._latency_count
                if self._latency_count
                else 0.0
            )
            lines.append("# HELP sentinel_request_latency_ms_avg Average request latency.")
            lines.append("# TYPE sentinel_request_latency_ms_avg gauge")
            lines.append(f"sentinel_request_latency_ms_avg {avg:.3f}")
            return "\n".join(lines) + "\n"


metrics = Metrics()
