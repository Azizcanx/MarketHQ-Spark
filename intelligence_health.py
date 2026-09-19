# -*- coding: utf-8 -*-
"""Phase J5 — Intelligence Health Metrics.

Operational/research metrics for AzizBusiness HQ.
NOT trading performance dashboard.

Metrics:
- data health
- agent health
- research throughput
- validation throughput
- failure rate
- stale research
- unresolved conflicts
- claim instability
- drift alerts
- memory growth
- queue depth
- provider health
- budget usage
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class HealthStatus(Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    WARNING = "warning"
    CRITICAL = "critical"
    UNKNOWN = "unknown"


@dataclass
class MetricSnapshot:
    """Single metric value at a point in time."""
    metric_name: str
    value: float
    unit: str = ""
    status: HealthStatus = HealthStatus.UNKNOWN
    timestamp: str = ""
    threshold_warning: float = 0.0
    threshold_critical: float = 0.0
    provenance: str = ""

    def __post_init__(self) -> None:
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> dict[str, Any]:
        return {
            "metric_name": self.metric_name,
            "value": self.value,
            "unit": self.unit,
            "status": self.status.value,
            "timestamp": self.timestamp,
            "threshold_warning": self.threshold_warning,
            "threshold_critical": self.threshold_critical,
            "provenance": self.provenance,
        }


@dataclass
class IntelligenceHealthReport:
    """Full intelligence health snapshot."""
    report_id: str = ""
    generated_at: str = ""
    overall_status: HealthStatus = HealthStatus.UNKNOWN
    metrics: dict[str, MetricSnapshot] = field(default_factory=dict)
    alerts: list[str] = field(default_factory=list)
    data_health: float = 1.0
    agent_health: float = 1.0
    research_throughput: float = 0.0
    validation_throughput: float = 0.0
    failure_rate: float = 0.0
    stale_research_count: int = 0
    unresolved_conflicts: int = 0
    claim_instability: float = 0.0
    drift_alerts: int = 0
    memory_growth_mb: float = 0.0
    queue_depth: int = 0
    provider_health: float = 1.0
    budget_usage_pct: float = 0.0
    provenance: str = ""

    def __post_init__(self) -> None:
        if not self.report_id:
            now = datetime.now(timezone.utc).isoformat()
            self.report_id = f"IHR-{hashlib.sha256(now.encode()).hexdigest()[:10].upper()}"
            if not self.generated_at:
                self.generated_at = now

    def to_dict(self) -> dict[str, Any]:
        return {
            "report_id": self.report_id,
            "generated_at": self.generated_at,
            "overall_status": self.overall_status.value,
            "data_health": self.data_health,
            "agent_health": self.agent_health,
            "research_throughput": self.research_throughput,
            "validation_throughput": self.validation_throughput,
            "failure_rate": self.failure_rate,
            "stale_research_count": self.stale_research_count,
            "unresolved_conflicts": self.unresolved_conflicts,
            "claim_instability": self.claim_instability,
            "drift_alerts": self.drift_alerts,
            "memory_growth_mb": self.memory_growth_mb,
            "queue_depth": self.queue_depth,
            "provider_health": self.provider_health,
            "budget_usage_pct": self.budget_usage_pct,
            "alerts": self.alerts,
            "metrics": {k: v.to_dict() for k, v in self.metrics.items()},
            "provenance": self.provenance,
        }


class IntelligenceHealthMonitor:
    """Monitors and reports intelligence system health."""

    def __init__(self) -> None:
        self._metrics: dict[str, MetricSnapshot] = {}
        self._alerts: list[str] = []
        self._history: list[IntelligenceHealthReport] = []

    def record_metric(self, metric: MetricSnapshot) -> None:
        """Record a metric snapshot."""
        self._metrics[metric.metric_name] = metric
        # Check thresholds
        if metric.value >= metric.threshold_critical and metric.threshold_critical > 0:
            self._alerts.append(
                f"CRITICAL: {metric.metric_name} = {metric.value} "
                f"(critical threshold: {metric.threshold_critical})"
            )
        elif metric.value >= metric.threshold_warning and metric.threshold_warning > 0:
            self._alerts.append(
                f"WARNING: {metric.metric_name} = {metric.value} "
                f"(warning threshold: {metric.threshold_warning})"
            )

    def compute_overall_status(self) -> HealthStatus:
        """Compute overall status from all metrics."""
        if not self._metrics:
            return HealthStatus.UNKNOWN

        critical_count = sum(
            1 for m in self._metrics.values()
            if m.status == HealthStatus.CRITICAL
        )
        warning_count = sum(
            1 for m in self._metrics.values()
            if m.status == HealthStatus.WARNING
        )

        if critical_count > 0:
            return HealthStatus.CRITICAL
        elif warning_count > 0:
            return HealthStatus.WARNING
        elif len(self._metrics) > 0:
            return HealthStatus.HEALTHY
        return HealthStatus.UNKNOWN

    def generate_report(self, provenance: str = "") -> IntelligenceHealthReport:
        """Generate full health report."""
        overall = self.compute_overall_status()

        now = datetime.now(timezone.utc).isoformat()
        report = IntelligenceHealthReport(
            generated_at=now,
            overall_status=overall,
            metrics=dict(self._metrics),
            alerts=list(self._alerts),
            provenance=provenance or "IntelligenceHealthMonitor.generate_report",
        )

        # Populate from existing metrics
        for name, metric in self._metrics.items():
            if name == "data_health":
                report.data_health = metric.value
            elif name == "agent_health":
                report.agent_health = metric.value
            elif name == "research_throughput":
                report.research_throughput = metric.value
            elif name == "validation_throughput":
                report.validation_throughput = metric.value
            elif name == "failure_rate":
                report.failure_rate = metric.value
            elif name == "claim_instability":
                report.claim_instability = metric.value
            elif name == "drift_alerts":
                report.drift_alerts = int(metric.value)
            elif name == "memory_growth_mb":
                report.memory_growth_mb = metric.value
            elif name == "queue_depth":
                report.queue_depth = int(metric.value)
            elif name == "provider_health":
                report.provider_health = metric.value
            elif name == "budget_usage_pct":
                report.budget_usage_pct = metric.value

        self._history.append(report)
        # Keep last 100 reports
        while len(self._history) > 100:
            self._history.pop(0)

        return report

    @property
    def alerts(self) -> list[str]:
        return list(self._alerts)

    @property
    def history(self) -> list[IntelligenceHealthReport]:
        return list(self._history)

    def clear_alerts(self) -> None:
        self._alerts.clear()

    def to_dict(self) -> dict[str, Any]:
        return {
            "current_status": self.compute_overall_status().value,
            "metrics_count": len(self._metrics),
            "alerts": self.alerts,
            "history_count": len(self._history),
            "latest_report": self.generate_report().to_dict() if self._metrics else None,
        }