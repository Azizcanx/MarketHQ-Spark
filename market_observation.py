# -*- coding: utf-8 -*-
"""Market Observation — Phase J4.

Observation layer for autonomous research loop.
Captures market state without generating fake data.

Research-only. No trading. No broker.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class DataQuality(Enum):
    GOOD = "GOOD"
    DEGRADED = "DEGRADED"
    POOR = "POOR"
    INSUFFICIENT = "INSUFFICIENT"
    NO_DATA = "NO_DATA"
    UNKNOWN = "UNKNOWN"


@dataclass
class MarketObservation:
    """Single market observation at a point in time."""
    observation_id: str = ""
    symbol: str = ""
    timeframe: str = ""
    timestamp: str = ""
    data_cutoff_timestamp: str = ""
    context_version: str = ""

    # Data availability
    ohlcv_available: bool = False
    bar_count: int = 0
    volume_available: bool = False
    feature_availability: dict[str, bool] = field(default_factory=dict)

    # Market state
    regime: str = "UNKNOWN"
    volatility: float = 0.0
    trend: str = "UNKNOWN"
    momentum: float = 0.0
    structure: str = "UNKNOWN"
    liquidity: str = "UNKNOWN"

    # Data quality
    data_quality: DataQuality = DataQuality.UNKNOWN
    null_rate: float = 0.0
    stale_data: bool = False
    timestamp_continuity: bool = False

    # Provenance
    source: str = ""
    provenance_ref: str = ""
    timestamp_raw: str = ""

    # Feature snapshot metadata
    feature_snapshot_id: str = ""
    feature_set_version: str = ""

    # Error
    error_type: str = ""
    error_message: str = ""

    def __post_init__(self) -> None:
        if not self.observation_id:
            self.observation_id = f"OBS-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')}"
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> dict[str, Any]:
        return {
            "observation_id": self.observation_id,
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "timestamp": self.timestamp,
            "data_cutoff_timestamp": self.data_cutoff_timestamp,
            "context_version": self.context_version,
            "ohlcv_available": self.ohlcv_available,
            "bar_count": self.bar_count,
            "volume_available": self.volume_available,
            "feature_availability": self.feature_availability,
            "regime": self.regime,
            "volatility": self.volatility,
            "trend": self.trend,
            "momentum": self.momentum,
            "structure": self.structure,
            "liquidity": self.liquidity,
            "data_quality": self.data_quality.value,
            "null_rate": self.null_rate,
            "stale_data": self.stale_data,
            "timestamp_continuity": self.timestamp_continuity,
            "source": self.source,
            "provenance_ref": self.provenance_ref,
            "feature_snapshot_id": self.feature_snapshot_id,
            "error_type": self.error_type,
            "error_message": self.error_message,
        }


@dataclass
class ObservationBundle:
    """Multiple observations for a symbol/timeframe scope."""
    observations: list[MarketObservation] = field(default_factory=list)
    scope_symbol: str = ""
    scope_timeframe: str = ""
    cutoff_timestamp: str = ""
    context_version: str = ""
    total_count: int = 0
    quality_summary: dict[str, int] = field(default_factory=dict)
    error_count: int = 0

    def __post_init__(self) -> None:
        self.total_count = len(self.observations)
        self._quality_summary()

    def _quality_summary(self) -> None:
        qs: dict[str, int] = {}
        for obs in self.observations:
            qs[obs.data_quality.value] = qs.get(obs.data_quality.value, 0) + 1
        self.quality_summary = qs
        self.error_count = sum(
            v for k, v in qs.items() if k in ("NO_DATA", "UNKNOWN", "INSUFFICIENT")
        )