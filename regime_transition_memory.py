# -*- coding: utf-8 -*-
"""Phase J5 — Regime Transition Memory.

Stores regime transition history:
- previous regime → transition → new regime
- transition context, historical frequency, outcomes
- research findings, supporting/conflicting evidence
- sample size, confidence, timestamps

Transitions are historical records — NOT future guarantees.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class RegimeTransitionType(Enum):
    EXPANSION = "expansion"
    CONTRACTION = "contraction"
    TREND_REVERSAL = "trend_reversal"
    VOLATILITY_SHIFT = "volatility_shift"
    RANGE_BREAKOUT = "range_breakout"
    RANGE_BREAKDOWN = "range_breakdown"
    LIQUIDITY_CHANGE = "liquidity_change"
    STRUCTURE_CHANGE = "structure_change"
    UNKNOWN = "unknown"


@dataclass
class RegimeTransitionRecord:
    """A single regime transition memory entry."""

    transition_id: str = ""
    previous_regime: str = ""
    new_regime: str = ""
    transition_type: RegimeTransitionType = RegimeTransitionType.UNKNOWN
    symbol: str = ""
    timeframe: str = ""
    transition_context: dict[str, Any] = field(default_factory=dict)
    historical_frequency: int = 0
    historical_outcomes: list[str] = field(default_factory=list)
    research_findings: list[str] = field(default_factory=list)
    supporting_evidence: list[str] = field(default_factory=list)
    conflicting_evidence: list[str] = field(default_factory=list)
    sample_size: int = 0
    confidence: float = 0.0
    detected_at: str = ""
    created_at: str = ""
    provenance: str = ""

    def __post_init__(self) -> None:
        if not self.transition_id:
            now = datetime.now(timezone.utc).isoformat()
            self.transition_id = (
                f"RT-{uuid.uuid4().hex[:8].upper()}"
            )
            if not self.detected_at:
                self.detected_at = now
            if not self.created_at:
                self.created_at = now

    def to_dict(self) -> dict[str, Any]:
        return {
            "transition_id": self.transition_id,
            "previous_regime": self.previous_regime,
            "new_regime": self.new_regime,
            "transition_type": self.transition_type.value,
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "transition_context": self.transition_context,
            "historical_frequency": self.historical_frequency,
            "historical_outcomes": self.historical_outcomes,
            "research_findings": self.research_findings,
            "supporting_evidence": self.supporting_evidence,
            "conflicting_evidence": self.conflicting_evidence,
            "sample_size": self.sample_size,
            "confidence": self.confidence,
            "detected_at": self.detected_at,
            "created_at": self.created_at,
            "provenance": self.provenance,
        }


class RegimeTransitionMemory:
    """Manages regime transition memory.

    Stores and queries regime transitions.
    NEVER guarantees future outcomes based on past transitions.
    """

    def __init__(self, max_records: int = 500) -> None:
        self._records: list[RegimeTransitionRecord] = []
        self._max_records = max_records

    def add_transition(
        self,
        previous_regime: str,
        new_regime: str,
        transition_type: RegimeTransitionType = RegimeTransitionType.UNKNOWN,
        symbol: str = "",
        timeframe: str = "",
        context: dict[str, Any] | None = None,
        supporting_evidence: list[str] | None = None,
        conflicting_evidence: list[str] | None = None,
        research_findings: list[str] | None = None,
        sample_size: int = 0,
        confidence: float = 0.0,
        provenance: str = "",
    ) -> RegimeTransitionRecord:
        """Add a regime transition record."""
        record = RegimeTransitionRecord(
            previous_regime=previous_regime,
            new_regime=new_regime,
            transition_type=transition_type,
            symbol=symbol,
            timeframe=timeframe,
            transition_context=context or {},
            supporting_evidence=supporting_evidence or [],
            conflicting_evidence=conflicting_evidence or [],
            research_findings=research_findings or [],
            sample_size=sample_size,
            confidence=confidence,
            provenance=provenance or "RegimeTransitionMemory.add_transition",
        )
        self._records.append(record)
        # Trim to max
        while len(self._records) > self._max_records:
            self._records.pop(0)
        return record

    def get_transitions_for(
        self,
        symbol: str = "",
        timeframe: str = "",
        previous_regime: str = "",
        new_regime: str = "",
        limit: int = 50,
    ) -> list[RegimeTransitionRecord]:
        """Query transitions by filters."""
        results = self._records
        if symbol:
            results = [r for r in results if r.symbol == symbol]
        if timeframe:
            results = [r for r in results if r.timeframe == timeframe]
        if previous_regime:
            results = [r for r in results if r.previous_regime == previous_regime]
        if new_regime:
            results = [r for r in results if r.new_regime == new_regime]
        return results[-limit:]

    def get_frequency(
        self,
        previous_regime: str,
        new_regime: str,
    ) -> int:
        """Count how often a specific transition occurred."""
        return sum(
            1
            for r in self._records
            if r.previous_regime == previous_regime
            and r.new_regime == new_regime
        )

    def get_recent(self, limit: int = 20) -> list[RegimeTransitionRecord]:
        """Get most recent transitions."""
        return self._records[-limit:]

    @property
    def records(self) -> list[RegimeTransitionRecord]:
        return list(self._records)

    @property
    def count(self) -> int:
        return len(self._records)

    def to_dict(self) -> dict[str, Any]:
        return {
            "count": self.count,
            "max_records": self._max_records,
            "recent_transitions": [r.to_dict() for r in self.get_recent(10)],
        }