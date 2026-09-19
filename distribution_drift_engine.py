# -*- coding: utf-8 -*-
"""Phase J5 — Distribution Drift Engine.
Detects distribution shifts in research metrics over time.

Monitors:
- Quality distribution
- Regime distribution
- Setup distribution
- Strategy family distribution
- Feature distribution
- Outcome distribution
- Duration distribution
- RR distribution
- Volatility distribution
- Evidence distribution

Each detection creates a DriftDetectionEvent — a validation trigger,
NOT an automatic "strategy no longer works" signal.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class DriftType(Enum):
    """Types of distribution drift that can be detected."""

    QUALITY_DRIFT = "quality_drift"
    REGIME_DRIFT = "regime_drift"
    SETUP_DRIFT = "setup_drift"
    STRATEGY_FAMILY_DRIFT = "strategy_family_drift"
    FEATURE_DRIFT = "feature_drift"
    OUTCOME_DRIFT = "outcome_drift"
    DURATION_DRIFT = "duration_drift"
    RR_DRIFT = "rr_drift"
    VOLATILITY_DRIFT = "volatility_drift"
    EVIDENCE_DRIFT = "evidence_drift"


class DriftCategory(Enum):
    """Category of drift — distinguishes root cause."""

    DATA_DRIFT = "data_drift"          # Data quality/distribution changed
    MARKET_DRIFT = "market_drift"      # Market behavior changed
    MODEL_DRIFT = "model_drift"        # Research model behavior changed
    RESEARCH_DRIFT = "research_drift"  # Agent/evidence/claim distribution changed


class DriftSeverity(Enum):
    """Severity of detected drift."""

    NEGLIGIBLE = "negligible"      # Within expected noise
    MINOR = "minor"               # Slight change, monitor
    MODERATE = "moderate"         # Worth investigation
    SIGNIFICANT = "significant"   # Should trigger validation
    MAJOR = "major"               # Strong validation trigger


@dataclass
class DriftDetectionEvent:
    """A detected distribution drift event.

    NOT automatic "strategy fails" — validation trigger only.
    """

    event_id: str
    drift_type: DriftType
    drift_category: DriftCategory
    symbol: str
    timeframe: str
    metric_name: str
    baseline_distribution: dict[str, Any]
    current_distribution: dict[str, Any]
    drift_magnitude: float = 0.0  # 0-1, higher = more drift
    statistical_measure: str = "visual"
    sample_size: int = 0
    severity: DriftSeverity = DriftSeverity.MINOR
    detected_at: str = ""
    provenance: str = ""
    research_trigger: bool = True  # If True, warrants validation research
    context: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "drift_type": self.drift_type.value,
            "drift_category": self.drift_category.value,
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "metric_name": self.metric_name,
            "baseline_distribution": self.baseline_distribution,
            "current_distribution": self.current_distribution,
            "drift_magnitude": self.drift_magnitude,
            "statistical_measure": self.statistical_measure,
            "sample_size": self.sample_size,
            "severity": self.severity.value,
            "detected_at": self.detected_at,
            "provenance": self.provenance,
            "research_trigger": self.research_trigger,
            "context": self.context,
        }


@dataclass
class DriftDetectionResult:
    """Result of a drift detection run."""

    events: list[DriftDetectionEvent] = field(default_factory=list)
    total_drifts: int = 0
    significant_drifts: int = 0
    research_triggers: int = 0
    detection_timestamp: str = ""
    baseline_window: str = ""
    current_window: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "events": [e.to_dict() for e in self.events],
            "total_drifts": self.total_drifts,
            "significant_drifts": self.significant_drifts,
            "research_triggers": self.research_triggers,
            "detection_timestamp": self.detection_timestamp,
            "baseline_window": self.baseline_window,
            "current_window": self.current_window,
        }


class DistributionDriftEngine:
    """Detects distribution drift across research metrics.

    Compares baseline distribution against current distribution
    to detect significant shifts. Each drift creates a
    DriftDetectionEvent that serves as a validation trigger.
    """

    def __init__(self) -> None:
        self._event_counter: int = 0

    def _generate_event_id(
        self,
        drift_type: DriftType,
        symbol: str,
        timeframe: str,
        metric_name: str,
    ) -> str:
        now = datetime.now(timezone.utc).isoformat()
        self._event_counter += 1
        raw = f"{now}{drift_type.value}{symbol}{timeframe}{metric_name}{self._event_counter}"
        return f"DRF-{hashlib.sha256(raw.encode()).hexdigest()[:12].upper()}"

    def _compute_drift_magnitude(
        self,
        baseline: dict[str, Any],
        current: dict[str, Any],
    ) -> float:
        """Compute a simple drift magnitude (0-1).

        Uses relative difference in key statistics.
        """
        # For histogram-like distributions
        baseline_total = sum(baseline.values()) if isinstance(baseline, dict) else 0
        current_total = sum(current.values()) if isinstance(current, dict) else 0

        if baseline_total == 0 and current_total == 0:
            return 0.0

        # Normalize to probabilities
        baseline_probs: dict[str, float] = {}
        current_probs: dict[str, float] = {}

        if isinstance(baseline, dict) and baseline_total > 0:
            for k, v in baseline.items():
                baseline_probs[k] = v / baseline_total

        if isinstance(current, dict) and current_total > 0:
            for k, v in current.items():
                current_probs[k] = v / current_total

        # Compute total variation distance
        all_keys = set(baseline_probs.keys()) | set(current_probs.keys())
        total_variation = 0.0

        for key in all_keys:
            bp = baseline_probs.get(key, 0.0)
            cp = current_probs.get(key, 0.0)
            total_variation += abs(bp - cp)

        # Normalize to 0-1 (TV distance is 0-2, so divide by 2)
        drift = total_variation / 2.0

        return min(max(drift, 0.0), 1.0)

    def _determine_severity(self, drift_magnitude: float) -> DriftSeverity:
        """Map drift magnitude to severity level."""
        if drift_magnitude < 0.05:
            return DriftSeverity.NEGLIGIBLE
        elif drift_magnitude < 0.10:
            return DriftSeverity.MINOR
        elif drift_magnitude < 0.20:
            return DriftSeverity.MODERATE
        elif drift_magnitude < 0.35:
            return DriftSeverity.SIGNIFICANT
        else:
            return DriftSeverity.MAJOR

    def detect_quality_drift(
        self,
        symbol: str,
        timeframe: str,
        baseline_quality_dist: dict[str, int],
        current_quality_dist: dict[str, int],
        baseline_window: str = "",
        current_window: str = "",
        context: dict[str, Any] | None = None,
    ) -> DriftDetectionEvent:
        """Detect drift in quality score distribution."""
        now = datetime.now(timezone.utc).isoformat()
        event_id = self._generate_event_id(
            DriftType.QUALITY_DRIFT, symbol, timeframe, "quality_score"
        )

        drift_mag = self._compute_drift_magnitude(baseline_quality_dist, current_quality_dist)

        return DriftDetectionEvent(
            event_id=event_id,
            drift_type=DriftType.QUALITY_DRIFT,
            drift_category=DriftCategory.DATA_DRIFT,
            symbol=symbol,
            timeframe=timeframe,
            metric_name="quality_score",
            baseline_distribution=baseline_quality_dist,
            current_distribution=current_quality_dist,
            drift_magnitude=drift_mag,
            statistical_measure="distribution_comparison",
            sample_size=sum(baseline_quality_dist.values()) + sum(current_quality_dist.values()),
            severity=self._determine_severity(drift_mag),
            detected_at=now,
            provenance="DistributionDriftEngine.detect_quality_drift",
            research_trigger=drift_mag >= 0.10,
            context=context or {},
        )

    def detect_regime_drift(
        self,
        symbol: str,
        timeframe: str,
        baseline_regime_dist: dict[str, int],
        current_regime_dist: dict[str, int],
        baseline_window: str = "",
        current_window: str = "",
        context: dict[str, Any] | None = None,
    ) -> DriftDetectionEvent:
        """Detect drift in regime distribution."""
        now = datetime.now(timezone.utc).isoformat()
        event_id = self._generate_event_id(
            DriftType.REGIME_DRIFT, symbol, timeframe, "regime"
        )

        drift_mag = self._compute_drift_magnitude(baseline_regime_dist, current_regime_dist)

        return DriftDetectionEvent(
            event_id=event_id,
            drift_type=DriftType.REGIME_DRIFT,
            drift_category=DriftCategory.MARKET_DRIFT,
            symbol=symbol,
            timeframe=timeframe,
            metric_name="regime",
            baseline_distribution=baseline_regime_dist,
            current_distribution=current_regime_dist,
            drift_magnitude=drift_mag,
            statistical_measure="distribution_comparison",
            sample_size=sum(baseline_regime_dist.values()) + sum(current_regime_dist.values()),
            severity=self._determine_severity(drift_mag),
            detected_at=now,
            provenance="DistributionDriftEngine.detect_regime_drift",
            research_trigger=drift_mag >= 0.10,
            context=context or {},
        )

    def detect_setup_drift(
        self,
        symbol: str,
        timeframe: str,
        baseline_setup_dist: dict[str, int],
        current_setup_dist: dict[str, int],
        baseline_window: str = "",
        current_window: str = "",
        context: dict[str, Any] | None = None,
    ) -> DriftDetectionEvent:
        """Detect drift in setup type distribution."""
        now = datetime.now(timezone.utc).isoformat()
        event_id = self._generate_event_id(
            DriftType.SETUP_DRIFT, symbol, timeframe, "setup_type"
        )

        drift_mag = self._compute_drift_magnitude(baseline_setup_dist, current_setup_dist)

        return DriftDetectionEvent(
            event_id=event_id,
            drift_type=DriftType.SETUP_DRIFT,
            drift_category=DriftCategory.RESEARCH_DRIFT,
            symbol=symbol,
            timeframe=timeframe,
            metric_name="setup_type",
            baseline_distribution=baseline_setup_dist,
            current_distribution=current_setup_dist,
            drift_magnitude=drift_mag,
            statistical_measure="distribution_comparison",
            sample_size=sum(baseline_setup_dist.values()) + sum(current_setup_dist.values()),
            severity=self._determine_severity(drift_mag),
            detected_at=now,
            provenance="DistributionDriftEngine.detect_setup_drift",
            research_trigger=drift_mag >= 0.10,
            context=context or {},
        )

    def detect_strategy_family_drift(
        self,
        symbol: str,
        timeframe: str,
        baseline_family_dist: dict[str, int],
        current_family_dist: dict[str, int],
        baseline_window: str = "",
        current_window: str = "",
        context: dict[str, Any] | None = None,
    ) -> DriftDetectionEvent:
        """Detect drift in strategy family distribution."""
        now = datetime.now(timezone.utc).isoformat()
        event_id = self._generate_event_id(
            DriftType.STRATEGY_FAMILY_DRIFT, symbol, timeframe, "strategy_family"
        )

        drift_mag = self._compute_drift_magnitude(baseline_family_dist, current_family_dist)

        return DriftDetectionEvent(
            event_id=event_id,
            drift_type=DriftType.STRATEGY_FAMILY_DRIFT,
            drift_category=DriftCategory.RESEARCH_DRIFT,
            symbol=symbol,
            timeframe=timeframe,
            metric_name="strategy_family",
            baseline_distribution=baseline_family_dist,
            current_distribution=current_family_dist,
            drift_magnitude=drift_mag,
            statistical_measure="distribution_comparison",
            sample_size=sum(baseline_family_dist.values()) + sum(current_family_dist.values()),
            severity=self._determine_severity(drift_mag),
            detected_at=now,
            provenance="DistributionDriftEngine.detect_strategy_family_drift",
            research_trigger=drift_mag >= 0.10,
            context=context or {},
        )

    def detect_outcome_drift(
        self,
        symbol: str,
        timeframe: str,
        baseline_outcome_dist: dict[str, int],
        current_outcome_dist: dict[str, int],
        baseline_window: str = "",
        current_window: str = "",
        context: dict[str, Any] | None = None,
    ) -> DriftDetectionEvent:
        """Detect drift in outcome distribution (hit rates, R values)."""
        now = datetime.now(timezone.utc).isoformat()
        event_id = self._generate_event_id(
            DriftType.OUTCOME_DRIFT, symbol, timeframe, "outcome"
        )

        drift_mag = self._compute_drift_magnitude(baseline_outcome_dist, current_outcome_dist)

        return DriftDetectionEvent(
            event_id=event_id,
            drift_type=DriftType.OUTCOME_DRIFT,
            drift_category=DriftCategory.MARKET_DRIFT,
            symbol=symbol,
            timeframe=timeframe,
            metric_name="outcome",
            baseline_distribution=baseline_outcome_dist,
            current_distribution=current_outcome_dist,
            drift_magnitude=drift_mag,
            statistical_measure="distribution_comparison",
            sample_size=sum(baseline_outcome_dist.values()) + sum(current_outcome_dist.values()),
            severity=self._determine_severity(drift_mag),
            detected_at=now,
            provenance="DistributionDriftEngine.detect_outcome_drift",
            research_trigger=drift_mag >= 0.15,
            context=context or {},
        )

    def detect_rr_drift(
        self,
        symbol: str,
        timeframe: str,
        baseline_rr_stats: dict[str, float],
        current_rr_stats: dict[str, float],
        baseline_window: str = "",
        current_window: str = "",
        context: dict[str, Any] | None = None,
    ) -> DriftDetectionEvent:
        """Detect drift in RR (Risk/Reward) distribution.

        Compares mean/median/std of RR values between windows.
        """
        now = datetime.now(timezone.utc).isoformat()
        event_id = self._generate_event_id(
            DriftType.RR_DRIFT, symbol, timeframe, "rr"
        )

        # For continuous stats, compute relative difference
        drift_mag = 0.0
        count = 0
        for key in set(baseline_rr_stats.keys()) | set(current_rr_stats.keys()):
            base_val = baseline_rr_stats.get(key, 0.0)
            curr_val = current_rr_stats.get(key, 0.0)
            if base_val != 0:
                rel_diff = abs(curr_val - base_val) / abs(base_val)
                drift_mag += min(rel_diff, 1.0)
                count += 1

        drift_mag = drift_mag / max(count, 1)

        return DriftDetectionEvent(
            event_id=event_id,
            drift_type=DriftType.RR_DRIFT,
            drift_category=DriftCategory.MARKET_DRIFT,
            symbol=symbol,
            timeframe=timeframe,
            metric_name="rr",
            baseline_distribution={k: round(v, 4) for k, v in baseline_rr_stats.items()},
            current_distribution={k: round(v, 4) for k, v in current_rr_stats.items()},
            drift_magnitude=min(drift_mag, 1.0),
            statistical_measure="relative_difference",
            sample_size=0,
            severity=self._determine_severity(min(drift_mag, 1.0)),
            detected_at=now,
            provenance="DistributionDriftEngine.detect_rr_drift",
            research_trigger=drift_mag >= 0.20,
            context=context or {},
        )

    def detect_volatility_drift(
        self,
        symbol: str,
        timeframe: str,
        baseline_vol_stats: dict[str, float],
        current_vol_stats: dict[str, float],
        baseline_window: str = "",
        current_window: str = "",
        context: dict[str, Any] | None = None,
    ) -> DriftDetectionEvent:
        """Detect drift in volatility distribution."""
        now = datetime.now(timezone.utc).isoformat()
        event_id = self._generate_event_id(
            DriftType.VOLATILITY_DRIFT, symbol, timeframe, "volatility"
        )

        drift_mag = 0.0
        count = 0
        for key in set(baseline_vol_stats.keys()) | set(current_vol_stats.keys()):
            base_val = baseline_vol_stats.get(key, 0.0)
            curr_val = current_vol_stats.get(key, 0.0)
            if base_val != 0:
                rel_diff = abs(curr_val - base_val) / abs(base_val)
                drift_mag += min(rel_diff, 1.0)
                count += 1

        drift_mag = drift_mag / max(count, 1)

        return DriftDetectionEvent(
            event_id=event_id,
            drift_type=DriftType.VOLATILITY_DRIFT,
            drift_category=DriftCategory.MARKET_DRIFT,
            symbol=symbol,
            timeframe=timeframe,
            metric_name="volatility",
            baseline_distribution={k: round(v, 4) for k, v in baseline_vol_stats.items()},
            current_distribution={k: round(v, 4) for k, v in current_vol_stats.items()},
            drift_magnitude=min(drift_mag, 1.0),
            statistical_measure="relative_difference",
            sample_size=0,
            severity=self._determine_severity(min(drift_mag, 1.0)),
            detected_at=now,
            provenance="DistributionDriftEngine.detect_volatility_drift",
            research_trigger=drift_mag >= 0.20,
            context=context or {},
        )

    def detect_evidence_drift(
        self,
        symbol: str,
        timeframe: str,
        baseline_evidence_dist: dict[str, int],
        current_evidence_dist: dict[str, int],
        baseline_window: str = "",
        current_window: str = "",
        context: dict[str, Any] | None = None,
    ) -> DriftDetectionEvent:
        """Detect drift in evidence distribution (supporting vs contradicting)."""
        now = datetime.now(timezone.utc).isoformat()
        event_id = self._generate_event_id(
            DriftType.EVIDENCE_DRIFT, symbol, timeframe, "evidence"
        )

        drift_mag = self._compute_drift_magnitude(baseline_evidence_dist, current_evidence_dist)

        return DriftDetectionEvent(
            event_id=event_id,
            drift_type=DriftType.EVIDENCE_DRIFT,
            drift_category=DriftCategory.RESEARCH_DRIFT,
            symbol=symbol,
            timeframe=timeframe,
            metric_name="evidence",
            baseline_distribution=baseline_evidence_dist,
            current_distribution=current_evidence_dist,
            drift_magnitude=drift_mag,
            statistical_measure="distribution_comparison",
            sample_size=sum(baseline_evidence_dist.values()) + sum(current_evidence_dist.values()),
            severity=self._determine_severity(drift_mag),
            detected_at=now,
            provenance="DistributionDriftEngine.detect_evidence_drift",
            research_trigger=drift_mag >= 0.15,
            context=context or {},
        )

    def detect_from_comparisons(
        self,
        symbol: str,
        timeframe: str,
        comparisons: dict[str, tuple[dict[str, Any], dict[str, Any]]],
        baseline_window: str = "",
        current_window: str = "",
    ) -> DriftDetectionResult:
        """Run drift detection from a dict of metric comparisons.

        Args:
            symbol: Asset symbol
            timeframe: Timeframe
            comparisons: {metric_name: (baseline_dist, current_dist)}
            baseline_window: Description of baseline window
            current_window: Description of current window
        """
        now = datetime.now(timezone.utc).isoformat()
        events: list[DriftDetectionEvent] = []

        for metric_name, (baseline, current) in comparisons.items():
            # Skip if both empty
            if not baseline and not current:
                continue

            # Select appropriate detector
            if metric_name == "quality_score":
                event = self.detect_quality_drift(
                    symbol, timeframe, baseline, current,
                    baseline_window, current_window,
                )
            elif metric_name == "regime":
                event = self.detect_regime_drift(
                    symbol, timeframe, baseline, current,
                    baseline_window, current_window,
                )
            elif metric_name == "setup_type":
                event = self.detect_setup_drift(
                    symbol, timeframe, baseline, current,
                    baseline_window, current_window,
                )
            elif metric_name == "strategy_family":
                event = self.detect_strategy_family_drift(
                    symbol, timeframe, baseline, current,
                    baseline_window, current_window,
                )
            elif metric_name == "outcome":
                event = self.detect_outcome_drift(
                    symbol, timeframe, baseline, current,
                    baseline_window, current_window,
                )
            elif metric_name == "rr":
                event = self.detect_rr_drift(
                    symbol, timeframe, baseline, current,
                    baseline_window, current_window,
                )
            elif metric_name == "volatility":
                event = self.detect_volatility_drift(
                    symbol, timeframe, baseline, current,
                    baseline_window, current_window,
                )
            elif metric_name == "evidence":
                event = self.detect_evidence_drift(
                    symbol, timeframe, baseline, current,
                    baseline_window, current_window,
                )
            else:
                # Generic drift detection
                drift_mag = self._compute_drift_magnitude(baseline, current)
                event = DriftDetectionEvent(
                    event_id=self._generate_event_id(
                        DriftType.FEATURE_DRIFT, symbol, timeframe, metric_name
                    ),
                    drift_type=DriftType.FEATURE_DRIFT,
                    drift_category=DriftCategory.DATA_DRIFT,
                    symbol=symbol,
                    timeframe=timeframe,
                    metric_name=metric_name,
                    baseline_distribution=baseline,
                    current_distribution=current,
                    drift_magnitude=drift_mag,
                    statistical_measure="distribution_comparison",
                    sample_size=sum(baseline.values()) + sum(current.values()) if isinstance(baseline, dict) and isinstance(current, dict) else 0,
                    severity=self._determine_severity(drift_mag),
                    detected_at=now,
                    provenance="DistributionDriftEngine.detect_from_comparisons",
                    research_trigger=drift_mag >= 0.10,
                )

            events.append(event)

        significant = sum(1 for e in events if e.severity in (DriftSeverity.SIGNIFICANT, DriftSeverity.MAJOR))
        research_triggers = sum(1 for e in events if e.research_trigger)

        return DriftDetectionResult(
            events=events,
            total_drifts=len(events),
            significant_drifts=significant,
            research_triggers=research_triggers,
            detection_timestamp=now,
            baseline_window=baseline_window,
            current_window=current_window,
        )

    def get_research_triggers(self, result: DriftDetectionResult) -> list[DriftDetectionEvent]:
        """Return events that warrant research/validation."""
        return [e for e in result.events if e.research_trigger]

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_counter": self._event_counter,
        }
