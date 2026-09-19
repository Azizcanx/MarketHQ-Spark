# -*- coding: utf-8 -*-
"""Phase J5 — Change Detection Engine.
Detects market changes that warrant research attention.

Detects (NOT predicts):
- Regime transitions
- Volatility transitions
- Momentum transitions
- Trend transitions
- Liquidity changes
- Structure changes
- Feature distribution changes
- Opportunity frequency changes
- Setup distribution changes
- Historical behavior drift
- Agent evidence drift

Each detection creates a ChangeDetectionEvent that serves as a
research trigger — NOT a trading signal.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from market_observation import MarketObservation, ObservationBundle, DataQuality


class ChangeType(Enum):
    """Types of market changes that can be detected."""

    REGIME_TRANSITION = "regime_transition"
    VOLATILITY_TRANSITION = "volatility_transition"
    MOMENTUM_TRANSITION = "momentum_transition"
    TREND_TRANSITION = "trend_transition"
    LIQUIDITY_CHANGE = "liquidity_change"
    STRUCTURE_CHANGE = "structure_change"
    FEATURE_DISTRIBUTION_CHANGE = "feature_distribution_change"
    OPPORTUNITY_FREQUENCY_CHANGE = "opportunity_frequency_change"
    SETUP_DISTRIBUTION_CHANGE = "setup_distribution_change"
    HISTORICAL_BEHAVIOR_DRIFT = "historical_behavior_drift"
    AGENT_EVIDENCE_DRIFT = "agent_evidence_drift"
    DATA_QUALITY_DEGRADATION = "data_quality_degradation"
    UNKNOWN_CHANGE = "unknown_change"


class ChangeSeverity(Enum):
    """Severity of detected change."""

    MINOR = "minor"           # Low research priority
    MODERATE = "moderate"    # Worth investigation
    SIGNIFICANT = "significant"  # Should trigger research
    MAJOR = "major"          # Strong research trigger


@dataclass
class ChangeDetectionEvent:
    """A detected change that warrants research attention.

    NOT a prediction. NOT a trading signal.
    "Araştırma yapılmasını gerektirir" seviyesinde.
    """

    event_id: str
    change_type: ChangeType
    severity: ChangeSeverity
    symbol: str
    timeframe: str
    previous_state: str
    new_state: str
    context: dict[str, Any] = field(default_factory=dict)
    evidence: list[str] = field(default_factory=list)
    research_priority: float = 0.0  # 0-1, higher = more research-worthy
    detected_at: str = ""
    provenance: str = ""
    source_observation_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "change_type": self.change_type.value,
            "severity": self.severity.value,
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "previous_state": self.previous_state,
            "new_state": self.new_state,
            "context": self.context,
            "evidence": self.evidence,
            "research_priority": self.research_priority,
            "detected_at": self.detected_at,
            "provenance": self.provenance,
            "source_observation_id": self.source_observation_id,
        }


@dataclass
class ChangeDetectionResult:
    """Result of a change detection run."""

    events: list[ChangeDetectionEvent] = field(default_factory=list)
    total_changes: int = 0
    significant_changes: int = 0
    minor_changes: int = 0
    detection_timestamp: str = ""
    observation_count: int = 0
    data_quality: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "events": [e.to_dict() for e in self.events],
            "total_changes": self.total_changes,
            "significant_changes": self.significant_changes,
            "minor_changes": self.minor_changes,
            "detection_timestamp": self.detection_timestamp,
            "observation_count": self.observation_count,
            "data_quality": self.data_quality,
        }


class ChangeDetectionEngine:
    """Detects market changes from observations and data quality signals.

    Uses MarketObservation bundles as input. Detects transitions
    between states (e.g., UPTREND → RANGE) without predicting
    future states.
    """

    def __init__(self) -> None:
        self._event_counter: int = 0

    def _generate_event_id(self, change_type: ChangeType, symbol: str, timeframe: str) -> str:
        now = datetime.now(timezone.utc).isoformat()
        self._event_counter += 1
        raw = f"{now}{change_type.value}{symbol}{timeframe}{self._event_counter}"
        return f"CHG-{hashlib.sha256(raw.encode()).hexdigest()[:12].upper()}"

    def detect_regime_transition(
        self,
        symbol: str,
        timeframe: str,
        previous_regime: str,
        new_regime: str,
        observations: list[MarketObservation] | None = None,
        severity: ChangeSeverity = ChangeSeverity.SIGNIFICANT,
        research_priority: float = 0.7,
        context: dict[str, Any] | None = None,
    ) -> ChangeDetectionEvent:
        """Detect a regime transition.

        Example: RANGE_LOW_VOL → EXPANDING_VOLATILITY → UPTREND
        """
        now = datetime.now(timezone.utc).isoformat()
        event_id = self._generate_event_id(ChangeType.REGIME_TRANSITION, symbol, timeframe)

        return ChangeDetectionEvent(
            event_id=event_id,
            change_type=ChangeType.REGIME_TRANSITION,
            severity=severity,
            symbol=symbol,
            timeframe=timeframe,
            previous_state=previous_regime,
            new_state=new_regime,
            context=context or {
                "transition_type": f"{previous_regime}_to_{new_regime}",
                "observation_count": len(observations) if observations else 0,
            },
            evidence=[f"Regime shift: {previous_regime} → {new_regime}"],
            research_priority=research_priority,
            detected_at=now,
            provenance="ChangeDetectionEngine.detect_regime_transition",
            source_observation_id=observations[0].observation_id if observations else "",
        )

    def detect_volatility_transition(
        self,
        symbol: str,
        timeframe: str,
        previous_volatility: str,
        new_volatility: str,
        vol_change_percent: float | None = None,
        severity: ChangeSeverity = ChangeSeverity.MODERATE,
        research_priority: float = 0.5,
        context: dict[str, Any] | None = None,
    ) -> ChangeDetectionEvent:
        """Detect a volatility regime change.

        Example: LOW_VOL → HIGH_VOL
        """
        now = datetime.now(timezone.utc).isoformat()
        event_id = self._generate_event_id(ChangeType.VOLATILITY_TRANSITION, symbol, timeframe)

        ctx = context or {}
        if vol_change_percent is not None:
            ctx["vol_change_percent"] = vol_change_percent

        return ChangeDetectionEvent(
            event_id=event_id,
            change_type=ChangeType.VOLATILITY_TRANSITION,
            severity=severity,
            symbol=symbol,
            timeframe=timeframe,
            previous_state=previous_volatility,
            new_state=new_volatility,
            context=ctx,
            evidence=[f"Volatility shift: {previous_volatility} → {new_volatility}"],
            research_priority=research_priority,
            detected_at=now,
            provenance="ChangeDetectionEngine.detect_volatility_transition",
        )

    def detect_momentum_transition(
        self,
        symbol: str,
        timeframe: str,
        previous_momentum: str,
        new_momentum: str,
        momentum_change: float | None = None,
        severity: ChangeSeverity = ChangeSeverity.MODERATE,
        research_priority: float = 0.5,
        context: dict[str, Any] | None = None,
    ) -> ChangeDetectionEvent:
        """Detect a momentum regime change."""
        now = datetime.now(timezone.utc).isoformat()
        event_id = self._generate_event_id(ChangeType.MOMENTUM_TRANSITION, symbol, timeframe)

        ctx = context or {}
        if momentum_change is not None:
            ctx["momentum_change"] = momentum_change

        return ChangeDetectionEvent(
            event_id=event_id,
            change_type=ChangeType.MOMENTUM_TRANSITION,
            severity=severity,
            symbol=symbol,
            timeframe=timeframe,
            previous_state=previous_momentum,
            new_state=new_momentum,
            context=ctx,
            evidence=[f"Momentum shift: {previous_momentum} → {new_momentum}"],
            research_priority=research_priority,
            detected_at=now,
            provenance="ChangeDetectionEngine.detect_momentum_transition",
        )

    def detect_trend_transition(
        self,
        symbol: str,
        timeframe: str,
        previous_trend: str,
        new_trend: str,
        trend_strength_change: float | None = None,
        severity: ChangeSeverity = ChangeSeverity.SIGNIFICANT,
        research_priority: float = 0.6,
        context: dict[str, Any] | None = None,
    ) -> ChangeDetectionEvent:
        """Detect a trend direction change.

        Example: UPTREND → RANGE, DOWNTREND → UPTREND
        """
        now = datetime.now(timezone.utc).isoformat()
        event_id = self._generate_event_id(ChangeType.TREND_TRANSITION, symbol, timeframe)

        ctx = context or {}
        if trend_strength_change is not None:
            ctx["trend_strength_change"] = trend_strength_change

        return ChangeDetectionEvent(
            event_id=event_id,
            change_type=ChangeType.TREND_TRANSITION,
            severity=severity,
            symbol=symbol,
            timeframe=timeframe,
            previous_state=previous_trend,
            new_state=new_trend,
            context=ctx,
            evidence=[f"Trend shift: {previous_trend} → {new_trend}"],
            research_priority=research_priority,
            detected_at=now,
            provenance="ChangeDetectionEngine.detect_trend_transition",
        )

    def detect_liquidity_change(
        self,
        symbol: str,
        timeframe: str,
        previous_liquidity: str,
        new_liquidity: str,
        spread_change: float | None = None,
        volume_change: float | None = None,
        severity: ChangeSeverity = ChangeSeverity.MODERATE,
        research_priority: float = 0.4,
        context: dict[str, Any] | None = None,
    ) -> ChangeDetectionEvent:
        """Detect a liquidity state change."""
        now = datetime.now(timezone.utc).isoformat()
        event_id = self._generate_event_id(ChangeType.LIQUIDITY_CHANGE, symbol, timeframe)

        ctx = context or {}
        if spread_change is not None:
            ctx["spread_change"] = spread_change
        if volume_change is not None:
            ctx["volume_change"] = volume_change

        return ChangeDetectionEvent(
            event_id=event_id,
            change_type=ChangeType.LIQUIDITY_CHANGE,
            severity=severity,
            symbol=symbol,
            timeframe=timeframe,
            previous_state=previous_liquidity,
            new_state=new_liquidity,
            context=ctx,
            evidence=[f"Liquidity shift: {previous_liquidity} → {new_liquidity}"],
            research_priority=research_priority,
            detected_at=now,
            provenance="ChangeDetectionEngine.detect_liquidity_change",
        )

    def detect_feature_distribution_change(
        self,
        symbol: str,
        timeframe: str,
        feature_name: str,
        distribution_shift_description: str,
        statistical_test: str = "visual",
        severity: ChangeSeverity = ChangeSeverity.MODERATE,
        research_priority: float = 0.5,
        context: dict[str, Any] | None = None,
    ) -> ChangeDetectionEvent:
        """Detect a feature distribution drift."""
        now = datetime.now(timezone.utc).isoformat()
        event_id = self._generate_event_id(
            ChangeType.FEATURE_DISTRIBUTION_CHANGE, symbol, timeframe
        )

        return ChangeDetectionEvent(
            event_id=event_id,
            change_type=ChangeType.FEATURE_DISTRIBUTION_CHANGE,
            severity=severity,
            symbol=symbol,
            timeframe=timeframe,
            previous_state="baseline_distribution",
            new_state=distribution_shift_description,
            context=context or {
                "feature_name": feature_name,
                "statistical_test": statistical_test,
            },
            evidence=[f"Feature {feature_name} distribution shift detected"],
            research_priority=research_priority,
            detected_at=now,
            provenance="ChangeDetectionEngine.detect_feature_distribution_change",
        )

    def detect_opportunity_frequency_change(
        self,
        symbol: str,
        timeframe: str,
        previous_frequency: float,
        new_frequency: float,
        frequency_change_percent: float | None = None,
        severity: ChangeSeverity = ChangeSeverity.MODERATE,
        research_priority: float = 0.5,
        context: dict[str, Any] | None = None,
    ) -> ChangeDetectionEvent:
        """Detect a change in opportunity frequency."""
        now = datetime.now(timezone.utc).isoformat()
        event_id = self._generate_event_id(
            ChangeType.OPPORTUNITY_FREQUENCY_CHANGE, symbol, timeframe
        )

        ctx = context or {}
        if frequency_change_percent is not None:
            ctx["frequency_change_percent"] = frequency_change_percent

        return ChangeDetectionEvent(
            event_id=event_id,
            change_type=ChangeType.OPPORTUNITY_FREQUENCY_CHANGE,
            severity=severity,
            symbol=symbol,
            timeframe=timeframe,
            previous_state=f"frequency_{previous_frequency:.4f}",
            new_state=f"frequency_{new_frequency:.4f}",
            context=ctx,
            evidence=[f"Opportunity frequency change: {previous_frequency:.4f} → {new_frequency:.4f}"],
            research_priority=research_priority,
            detected_at=now,
            provenance="ChangeDetectionEngine.detect_opportunity_frequency_change",
        )

    def detect_setup_distribution_change(
        self,
        symbol: str,
        timeframe: str,
        previous_setup_distribution: dict[str, int],
        new_setup_distribution: dict[str, int],
        severity: ChangeSeverity = ChangeSeverity.MODERATE,
        research_priority: float = 0.4,
        context: dict[str, Any] | None = None,
    ) -> ChangeDetectionEvent:
        """Detect a change in setup type distribution."""
        now = datetime.now(timezone.utc).isoformat()
        event_id = self._generate_event_id(
            ChangeType.SETUP_DISTRIBUTION_CHANGE, symbol, timeframe
        )

        return ChangeDetectionEvent(
            event_id=event_id,
            change_type=ChangeType.SETUP_DISTRIBUTION_CHANGE,
            severity=severity,
            symbol=symbol,
            timeframe=timeframe,
            previous_state=str(previous_setup_distribution),
            new_state=str(new_setup_distribution),
            context=context or {
                "previous_distribution": previous_setup_distribution,
                "new_distribution": new_setup_distribution,
            },
            evidence=["Setup type distribution changed"],
            research_priority=research_priority,
            detected_at=now,
            provenance="ChangeDetectionEngine.detect_setup_distribution_change",
        )

    def detect_from_observation_bundle(
        self,
        bundle: ObservationBundle,
        previous_state: dict[str, Any] | None = None,
    ) -> ChangeDetectionResult:
        """Run change detection on an ObservationBundle.

        Compares current observations against previous state
        to detect changes.
        """
        now = datetime.now(timezone.utc).isoformat()
        events: list[ChangeDetectionEvent] = []

        prev = previous_state or {}
        prev_regime = prev.get("regime", "")
        prev_volatility = prev.get("volatility", "")
        prev_momentum = prev.get("momentum", "")
        prev_trend = prev.get("trend", "")

        for obs in bundle.observations:
            # Regime transition
            if prev_regime and obs.regime != prev_regime:
                events.append(self.detect_regime_transition(
                    symbol=obs.asset or bundle.symbol or "",
                    timeframe=obs.timeframe or bundle.timeframe or "",
                    previous_regime=prev_regime,
                    new_regime=obs.regime,
                    observations=[obs],
                ))

            # Volatility transition
            if prev_volatility and obs.context.get("volatility_category", "") != prev_volatility:
                events.append(self.detect_volatility_transition(
                    symbol=obs.asset or bundle.symbol or "",
                    timeframe=obs.timeframe or bundle.timeframe or "",
                    previous_volatility=prev_volatility,
                    new_volatility=obs.context.get("volatility_category", "UNKNOWN"),
                    context={"source_observation": obs.observation_id},
                ))

            # Trend transition
            if prev_trend and obs.context.get("trend_direction", "") != prev_trend:
                events.append(self.detect_trend_transition(
                    symbol=obs.asset or bundle.symbol or "",
                    timeframe=obs.timeframe or bundle.timeframe or "",
                    previous_trend=prev_trend,
                    new_trend=obs.context.get("trend_direction", "UNKNOWN"),
                    context={"source_observation": obs.observation_id},
                ))

            # Momentum transition
            if prev_momentum and obs.context.get("momentum_category", "") != prev_momentum:
                events.append(self.detect_momentum_transition(
                    symbol=obs.asset or bundle.symbol or "",
                    timeframe=obs.timeframe or bundle.timeframe or "",
                    previous_momentum=prev_momentum,
                    new_momentum=obs.context.get("momentum_category", "UNKNOWN"),
                    context={"source_observation": obs.observation_id},
                ))

            # Data quality degradation
            if obs.data_quality and obs.data_quality.quality_score < 0.7:
                events.append(ChangeDetectionEvent(
                    event_id=self._generate_event_id(
                        ChangeType.DATA_QUALITY_DEGRADATION,
                        obs.asset or bundle.symbol or "",
                        obs.timeframe or bundle.timeframe or "",
                    ),
                    change_type=ChangeType.DATA_QUALITY_DEGRADATION,
                    severity=ChangeSeverity.MINOR,
                    symbol=obs.asset or bundle.symbol or "",
                    timeframe=obs.timeframe or bundle.timeframe or "",
                    previous_state="good_quality",
                    new_state=f"quality_score_{obs.data_quality.quality_score:.2f}",
                    context={"quality_score": obs.data_quality.quality_score},
                    evidence=[f"Data quality degraded: {obs.data_quality.quality_score:.2f}"],
                    research_priority=0.3,
                    detected_at=now,
                    provenance="ChangeDetectionEngine.detect_from_observation_bundle",
                    source_observation_id=obs.observation_id,
                ))

        significant = sum(1 for e in events if e.severity in (ChangeSeverity.SIGNIFICANT, ChangeSeverity.MAJOR))
        minor = sum(1 for e in events if e.severity == ChangeSeverity.MINOR)

        return ChangeDetectionResult(
            events=events,
            total_changes=len(events),
            significant_changes=significant,
            minor_changes=minor,
            detection_timestamp=now,
            observation_count=len(bundle.observations),
            data_quality={
                "overall_quality": bundle.data_quality.quality_score if bundle.data_quality else 0.0,
                "missing_bars": bundle.data_quality.missing_bars if bundle.data_quality else 0,
            },
        )

    def get_researchworthy_events(
        self,
        result: ChangeDetectionResult,
        min_severity: ChangeSeverity = ChangeSeverity.MODERATE,
    ) -> list[ChangeDetectionEvent]:
        """Filter events that warrant research attention."""
        severity_order = {
            ChangeSeverity.MINOR: 0,
            ChangeSeverity.MODERATE: 1,
            ChangeSeverity.SIGNIFICANT: 2,
            ChangeSeverity.MAJOR: 3,
        }
        min_order = severity_order.get(min_severity, 0)

        return [
            e for e in result.events
            if severity_order.get(e.severity, 0) >= min_order
        ]

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_counter": self._event_counter,
        }
