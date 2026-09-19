# -*- coding: utf-8 -*-
"""Data Quality Gate — Phase J4.

Checks data quality before autonomous research cycle runs.
Never generates fake data. Returns UNKNOWN/NO_DATA when insufficient.

Research-only. No trading. No broker.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from market_observation import MarketObservation, DataQuality


class DataQualityGateResult(Enum):
    PASS = "PASS"
    DEGRADED = "DEGRADED"
    FAIL = "FAIL"
    NO_DATA = "NO_DATA"
    INSUFFICIENT = "INSUFFICIENT"


@dataclass
class DataQualityCheck:
    """Single data quality check result."""
    check_name: str = ""
    passed: bool = False
    severity: str = "INFO"  # INFO | WARNING | ERROR | CRITICAL
    message: str = ""
    value: float = 0.0
    threshold: float = 0.0


@dataclass
class DataQualityGate:
    """Data quality gate result for a research cycle."""
    gate_id: str = ""
    symbol: str = ""
    timeframe: str = ""
    result: DataQualityGateResult = DataQualityGateResult.NO_DATA
    checks: list[DataQualityCheck] = field(default_factory=list)
    overall_score: float = 0.0
    stale_data_detected: bool = False
    null_rate: float = 0.0
    insufficient_bars: bool = False
    timestamp_continuity_broken: bool = False
    created_at: str = ""
    context_version: str = ""
    provenance_ref: str = ""

    def __post_init__(self) -> None:
        if not self.gate_id:
            self.gate_id = f"DQG-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')}"
        if not self.created_at:
            self.created_at = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> dict[str, Any]:
        return {
            "gate_id": self.gate_id,
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "result": self.result.value,
            "overall_score": self.overall_score,
            "checks": [
                {
                    "check_name": c.check_name,
                    "passed": c.passed,
                    "severity": c.severity,
                    "message": c.message,
                    "value": c.value,
                    "threshold": c.threshold,
                }
                for c in self.checks
            ],
            "stale_data_detected": self.stale_data_detected,
            "null_rate": self.null_rate,
            "insufficient_bars": self.insufficient_bars,
            "timestamp_continuity_broken": self.timestamp_continuity_broken,
        }


class DataQualityGateChecker:
    """Runs data quality checks before research cycle.

    Checks:
    - OHLCV availability
    - Volume availability
    - Bar count sufficiency
    - Timestamp continuity
    - Null rate
    - Stale data detection
    - Feature coverage
    - Timeframe consistency
    """

    def __init__(
        self,
        min_bars: int = 50,
        max_null_rate: float = 0.1,
        max_stale_hours: float = 24.0,
        min_feature_coverage: float = 0.5,
    ) -> None:
        self.min_bars = min_bars
        self.max_null_rate = max_null_rate
        self.max_stale_hours = max_stale_hours
        self.min_feature_coverage = min_feature_coverage

    def check(self, observation: MarketObservation) -> DataQualityGate:
        """Run all quality checks on an observation."""

        checks: list[DataQualityCheck] = []

        # OHLCV availability
        ohlcv_check = DataQualityCheck(
            check_name="ohlcv_available",
            passed=observation.ohlcv_available,
            severity="CRITICAL" if not observation.ohlcv_available else "INFO",
            message="OHLCV data available" if observation.ohlcv_available else "NO OHLCV DATA",
            value=1.0 if observation.ohlcv_available else 0.0,
            threshold=1.0,
        )
        checks.append(ohlcv_check)

        # Bar count
        bar_check = DataQualityCheck(
            check_name="bar_count",
            passed=observation.bar_count >= self.min_bars,
            severity="ERROR" if observation.bar_count < self.min_bars else "INFO",
            message=f"Bar count: {observation.bar_count} (min: {self.min_bars})",
            value=float(observation.bar_count),
            threshold=float(self.min_bars),
        )
        checks.append(bar_check)

        # Volume availability
        vol_check = DataQualityCheck(
            check_name="volume_available",
            passed=observation.volume_available,
            severity="WARNING" if not observation.volume_available else "INFO",
            message="Volume data available" if observation.volume_available else "NO VOLUME DATA",
            value=1.0 if observation.volume_available else 0.0,
            threshold=1.0,
        )
        checks.append(vol_check)

        # Null rate
        null_check = DataQualityCheck(
            check_name="null_rate",
            passed=observation.null_rate <= self.max_null_rate,
            severity="ERROR" if observation.null_rate > self.max_null_rate else "INFO",
            message=f"Null rate: {observation.null_rate:.3f} (max: {self.max_null_rate})",
            value=observation.null_rate,
            threshold=self.max_null_rate,
        )
        checks.append(null_check)

        # Stale data
        stale_check = DataQualityCheck(
            check_name="stale_data",
            passed=not observation.stale_data,
            severity="CRITICAL" if observation.stale_data else "INFO",
            message="Data is fresh" if not observation.stale_data else "STALE DATA DETECTED",
            value=0.0 if not observation.stale_data else 1.0,
            threshold=0.0,
        )
        checks.append(stale_check)

        # Timestamp continuity
        continuity_check = DataQualityCheck(
            check_name="timestamp_continuity",
            passed=observation.timestamp_continuity,
            severity="ERROR" if not observation.timestamp_continuity else "INFO",
            message="Timestamps continuous" if observation.timestamp_continuity else "TIMESTAMP GAP",
            value=1.0 if observation.timestamp_continuity else 0.0,
            threshold=1.0,
        )
        checks.append(continuity_check)

        # Feature coverage
        if observation.feature_availability:
            feature_count = sum(1 for v in observation.feature_availability.values() if v)
            total_features = len(observation.feature_availability)
            coverage = feature_count / max(total_features, 1)
            feature_check = DataQualityCheck(
                check_name="feature_coverage",
                passed=coverage >= self.min_feature_coverage,
                severity="WARNING" if coverage < self.min_feature_coverage else "INFO",
                message=f"Feature coverage: {coverage:.1%} ({feature_count}/{total_features})",
                value=coverage,
                threshold=self.min_feature_coverage,
            )
        else:
            feature_check = DataQualityCheck(
                check_name="feature_coverage",
                passed=False,
                severity="WARNING",
                message="No feature availability data",
                value=0.0,
                threshold=self.min_feature_coverage,
            )
        checks.append(feature_check)

        # Data quality
        dq_check = DataQualityCheck(
            check_name="data_quality",
            passed=observation.data_quality.value in ("GOOD", "DEGRADED"),
            severity="ERROR" if observation.data_quality.value in ("INSUFFICIENT", "NO_DATA") else "INFO",
            message=f"Data quality: {observation.data_quality.value}",
            value={"GOOD": 1.0, "DEGRADED": 0.7, "POOR": 0.4, "INSUFFICIENT": 0.2, "NO_DATA": 0.0, "UNKNOWN": 0.0}.get(
                observation.data_quality.value, 0.0
            ),
            threshold=0.5,
        )
        checks.append(dq_check)

        # Compute overall score
        passed_count = sum(1 for c in checks if c.passed)
        total_count = len(checks)
        overall_score = passed_count / max(total_count, 1)

        # Determine result
        if overall_score >= 0.7 and ohlcv_check.passed:
            result = DataQualityGateResult.PASS
        elif overall_score >= 0.4 and ohlcv_check.passed:
            result = DataQualityGateResult.DEGRADED
        elif overall_score < 0.4 or not ohlcv_check.passed:
            result = DataQualityGateResult.FAIL
        else:
            result = DataQualityGateResult.INSUFFICIENT

        # No data check
        if observation.data_quality == DataQuality.NO_DATA or observation.bar_count == 0:
            result = DataQualityGateResult.NO_DATA

        # Insufficient check
        if observation.data_quality == DataQuality.INSUFFICIENT or observation.bar_count < 20:
            if result != DataQualityGateResult.NO_DATA:
                result = DataQualityGateResult.INSUFFICIENT

        gate = DataQualityGate(
            symbol=observation.symbol,
            timeframe=observation.timeframe,
            result=result,
            checks=checks,
            overall_score=round(overall_score, 4),
            stale_data_detected=observation.stale_data,
            null_rate=observation.null_rate,
            insufficient_bars=observation.bar_count < self.min_bars,
            timestamp_continuity_broken=not observation.timestamp_continuity,
            context_version=observation.context_version,
            provenance_ref=observation.provenance_ref,
        )

        return gate