"""Production Monitoring — J12.

Metrics, health checks, structured logging, correlation IDs.
"""

from __future__ import annotations

import time
import uuid
import logging
from datetime import datetime, timezone
from typing import Any, Optional
from collections import defaultdict


# ─── Metrics ──────────────────────────────────────────────────────

class WorkforceMetrics:
    """Operational metrics for workforce monitoring."""

    def __init__(self):
        self._counters: dict[str, int] = defaultdict(int)
        self._gauges: dict[str, float] = {}
        self._histograms: dict[str, list[float]] = defaultdict(list)
        self._start_time = time.time()

    # Counters
    def increment(self, metric: str, value: int = 1) -> None:
        self._counters[metric] += value

    def get_counter(self, metric: str) -> int:
        return self._counters.get(metric, 0)

    def get_all_counters(self) -> dict[str, int]:
        return dict(self._counters)

    # Gauges
    def set_gauge(self, metric: str, value: float) -> None:
        self._gauges[metric] = value

    def get_gauge(self, metric: str) -> Optional[float]:
        return self._gauges.get(metric)

    def get_all_gauges(self) -> dict[str, float]:
        return dict(self._gauges)

    # Histograms
    def observe(self, metric: str, value: float) -> None:
        self._histograms[metric].append(value)
        # Keep last 1000 values
        if len(self._histograms[metric]) > 1000:
            self._histograms[metric] = self._histograms[metric][-1000:]

    def get_histogram(self, metric: str) -> list[float]:
        return self._histograms.get(metric, [])

    # Convenience methods
    def task_created(self) -> None:
        self.increment("tasks_created")

    def task_completed(self) -> None:
        self.increment("tasks_completed")

    def task_failed(self) -> None:
        self.increment("tasks_failed")

    def task_reassigned(self) -> None:
        self.increment("tasks_reassigned")

    def worker_active(self) -> None:
        self.increment("workers_active")

    def worker_busy(self) -> None:
        self.increment("workers_busy")

    def ai_request(self) -> None:
        self.increment("ai_requests")

    def ai_fallback(self) -> None:
        self.increment("ai_fallbacks")

    def ai_failure(self) -> None:
        self.increment("ai_failures")

    def sse_connection(self) -> None:
        self.increment("sse_connections")

    def sse_reconnect(self) -> None:
        self.increment("sse_reconnects")

    def brain_observation(self) -> None:
        self.increment("brain_observations")

    def memory_write(self) -> None:
        self.increment("memory_writes")

    def research_failure(self) -> None:
        self.increment("research_failures")

    # Aggregate stats
    def get_stats(self) -> dict[str, Any]:
        uptime = time.time() - self._start_time
        return {
            "uptime_seconds": round(uptime, 1),
            "counters": self.get_all_counters(),
            "gauges": self.get_all_gauges(),
        }


# ─── Health Check ─────────────────────────────────────────────────

class HealthChecker:
    """System health check."""

    def __init__(self):
        self._checks: dict[str, str] = {}

    def register(self, name: str, status: str) -> None:
        """Register a health check result.

        Status: HEALTHY, DEGRADED, UNAVAILABLE
        """
        self._checks[name] = status

    def get_overall(self) -> str:
        """Overall system health."""
        if not self._checks:
            return "HEALTHY"
        if any(s == "UNAVAILABLE" for s in self._checks.values()):
            return "DEGRADED"
        if any(s == "DEGRADED" for s in self._checks.values()):
            return "DEGRADED"
        return "HEALTHY"

    def get_all(self) -> dict[str, str]:
        return dict(self._checks)

    def get_report(self) -> dict[str, Any]:
        return {
            "overall": self.get_overall(),
            "checks": self.get_all(),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }


# ─── Structured Logger ────────────────────────────────────────────

class WorkforceLogger:
    """Structured logger with correlation IDs."""

    def __init__(self):
        self.logger = logging.getLogger("workforce")
        self.logger.setLevel(logging.INFO)

        if not self.logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter(
                '{"timestamp":"%(asctime)s","level":"%(levelname)s",'
                '"component":"%(name)s","message":"%(message)s"}'
            )
            handler.setFormatter(formatter)
            self.logger.addHandler(handler)

    def log(
        self,
        level: str,
        message: str,
        correlation_id: Optional[str] = None,
        **kwargs: Any,
    ) -> None:
        extra = {
            "correlation_id": correlation_id or "",
            **kwargs,
        }
        getattr(self.logger, level.lower(), self.logger.info)(
            message, extra=extra
        )

    def task_event(
        self,
        event: str,
        task_id: str,
        correlation_id: str,
        **kwargs: Any,
    ) -> None:
        self.log("info", f"Task {event}", correlation_id=correlation_id,
                 task_id=task_id, event=event, **kwargs)

    def worker_event(
        self,
        event: str,
        worker_id: str,
        correlation_id: str,
        **kwargs: Any,
    ) -> None:
        self.log("info", f"Worker {event}", correlation_id=correlation_id,
                 worker_id=worker_id, event=event, **kwargs)

    def ai_event(
        self,
        event: str,
        provider: str,
        correlation_id: str,
        **kwargs: Any,
    ) -> None:
        self.log("info", f"AI {event}", correlation_id=correlation_id,
                 provider=provider, event=event, **kwargs)


# ─── Global Instances ─────────────────────────────────────────────

metrics = WorkforceMetrics()
health_checker = HealthChecker()
logger = WorkforceLogger()