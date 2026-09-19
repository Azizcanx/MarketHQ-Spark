# -*- coding: utf-8 -*-
"""
MarketHQ Agent Contract V1
============================

Phase B — Agentic HQ Agent Contract + Existing Engine Adapter Layer

Bu modül:
  - AgentResult (ortak agent output sözleşmesi)
  - Evidence (structured evidence modeli)
  - Claim (structured claim modeli — Brain test edebilsin)
  - MarketContext (shared feature snapshot)
  - FeatureSnapshot (hesaplanmış indicator'lar)
  - BaseAgentAdapter (tüm adapter'ların base sınıfı)

Mevcut modeller yeniden kullanılır:
  - setup_object_model.SetupModel → AgentResult.setup
  - setup_object_model.QualityScore → AgentResult.quality
  - setup_object_model.Evidence → AgentResult.evidence (genişletilmiş)
  - setup_object_model.RegimeInfo → AgentResult.regime_info
  - setup_object_model.StructureInfo → AgentResult.structure_info
  - setup_object_model.LiquidityInfo → AgentResult.liquidity_info

Yeni alanlar:
  - AgentResult.agent_id / agent_version / execution_id / timestamp
  - AgentResult.observation_timestamp / data_cutoff_timestamp
  - AgentResult.status / confidence / uncertainty
  - AgentResult.supporting_features / conflicting_features
  - AgentResult.claims / reasoning / invalidation_conditions
  - AgentResult.source_engine / source_engine_version
  - AgentResult.opportunity_id / setup_id
  - AgentResult.data_quality / feature_availability
  - AgentResult.engine_metadata (per-engine debug trace)

Research only — no live trading.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


# =========================================================
# STATUS
# =========================================================

class AgentStatus(str, Enum):
    SUCCESS = "SUCCESS"
    PARTIAL = "PARTIAL"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
    ERROR = "ERROR"


# =========================================================
# EVIDENCE (extension of setup_object_model.Evidence)
# =========================================================

@dataclass
class EvidenceItem:
    """Single piece of structured evidence."""
    evidence_id: str = ""
    type: str = ""              # indicator | structure | regime | historical | volume
    feature: str = ""           # feature name
    value: float | None = None
    timestamp: str = ""         # when this evidence was computed
    data_cutoff_timestamp: str = ""  # latest data used
    direction: str = ""         # LONG | SHORT | NEUTRAL
    strength: float = 0.0       # 0..1
    source: str = ""            # which engine/adapter produced this
    explanation: str = ""       # human-readable explanation


@dataclass
class Evidence:
    """Structured evidence container — extends setup_object_model.Evidence."""
    supporting: list[dict[str, Any]] = field(default_factory=list)
    conflicting: list[dict[str, Any]] = field(default_factory=list)
    neutral: list[dict[str, Any]] = field(default_factory=list)
    evidence_score: float = 0.0
    # Extended fields for Agentic HQ
    items: list[EvidenceItem] = field(default_factory=list)
    observation_timestamp: str = ""
    data_cutoff_timestamp: str = ""


# =========================================================
# CLAIM
# =========================================================

class ClaimStatus(str, Enum):
    UNTESTED = "UNTESTED"
    TESTING = "TESTING"
    SUPPORTED = "SUPPORTED"
    WEAKENED = "WEAKENED"
    REJECTED = "REJECTED"


@dataclass
class Claim:
    """Structured claim for Brain validation."""
    claim_id: str = ""
    statement: str = ""
    source_agent: str = ""
    source_agent_version: str = ""
    observation_timestamp: str = ""
    data_cutoff_timestamp: str = ""
    evidence_refs: list[str] = field(default_factory=list)
    validation_status: ClaimStatus = ClaimStatus.UNTESTED
    # Optional metadata
    feature: str = ""
    regime: str = ""
    timeframe: str = ""
    symbol: str = ""
    sample_size: int = 0
    confidence: float = 0.0


# =========================================================
# MARKET CONTEXT (shared feature snapshot)
# =========================================================

@dataclass
class FeatureSnapshot:
    """Computed features for a single symbol+timeframe at a given cutoff."""
    symbol: str = ""
    timeframe: str = ""
    observation_timestamp: str = ""
    data_cutoff_timestamp: str = ""

    # Indicators (from signal_engine)
    sma_fast: float | None = None
    sma_slow: float | None = None
    ema_fast: float | None = None
    ema_slow: float | None = None
    rsi: float | None = None
    macd: float | None = None
    macd_signal: float | None = None
    bollinger_upper: float | None = None
    bollinger_lower: float | None = None
    atr: float | None = None
    atr_pct: float | None = None
    volume_ratio: float | None = None
    adx: float | None = None
    adx_trend: str | None = None

    # Derived
    regime: str = "UNKNOWN"
    structure_type: str = ""
    liquidity_side: str = ""
    momentum_at_entry: float | None = None
    volatility_context: float | None = None
    liquidity_balance: float | None = None

    # Availability tracking
    available_features: dict[str, bool] = field(default_factory=dict)
    null_features: dict[str, bool] = field(default_factory=dict)

    # Data quality
    bar_count: int = 0
    null_count: int = 0
    data_quality_score: float = 0.0  # 0..1


@dataclass
class MarketContext:
    """Shared, immutable context for all agents operating on same symbol+timeframe.

    Agents read from context, produce their own AgentResult.
    Same symbol+timeframe+cutoff → same context → deterministic replay.
    """
    symbol: str = ""
    timeframe: str = ""
    observation_timestamp: str = ""
    data_cutoff_timestamp: str = ""

    feature_snapshot: FeatureSnapshot = field(default_factory=FeatureSnapshot)

    # OHLCV reference (DataFrame — not serialized, passed at runtime)
    ohlcv_ref: Any = None  # pd.DataFrame | None

    # Source metadata
    dataset_id: int | None = None
    dataset_status: str = "unknown"
    provider: str = "yfinance"

    # Immutability guard
    _frozen: bool = field(default=False, repr=False)

    def process_ohlcv(self) -> None:
        """Populate feature_snapshot from ohlcv_ref.

        Called by adapters or manually after setting ohlcv_ref.
        """
        if self._frozen:
            return
        df = self.ohlcv_ref
        if df is None or df.empty:
            self.feature_snapshot.bar_count = 0
            self.feature_snapshot.data_quality_score = 0.0
            return
        self.feature_snapshot.symbol = self.symbol
        self.feature_snapshot.timeframe = self.timeframe
        self.feature_snapshot.bar_count = len(df)
        self.feature_snapshot.data_cutoff_timestamp = (
            str(df.index[-1]) if hasattr(df.index, '__getitem__') and len(df) > 0 else ""
        )
        nulls = int(df.isnull().sum().sum())
        self.feature_snapshot.null_count = nulls
        total_cells = len(df) * len(df.columns)
        self.feature_snapshot.data_quality_score = (
            1.0 - (nulls / total_cells) if total_cells > 0 else 0.0
        )
        for col in ["Open", "High", "Low", "Close", "Volume"]:
            has_col = col in df.columns
            self.feature_snapshot.available_features[col] = bool(has_col)
            self.feature_snapshot.null_features[col] = bool(
                has_col and df[col].isnull().any()
            )

    def freeze(self) -> None:
        self._frozen = True

    def __setattr__(self, name: str, value: Any) -> None:
        if self._frozen and name != "_frozen":
            raise RuntimeError(
                f"MarketContext is frozen — cannot set {name}. "
                "Create a new context instead."
            )
        super().__setattr__(name, value)


# =========================================================
# AGENT RESULT (core contract)
# =========================================================

@dataclass
class AgentResult:
    """Universal agent output — all agents produce this.

    Generic — no strategy-specific fields in core contract.
    Strategy-specific fields go in engine_metadata dict.
    """
    agent_id: str = ""
    agent_version: str = "v1"
    execution_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    observation_timestamp: str = ""   # when agent observed the market
    data_cutoff_timestamp: str = ""   # latest data used (lookahead protection)

    symbol: str = ""
    timeframe: str = ""

    status: AgentStatus = AgentStatus.SUCCESS
    direction: str = "NEUTRAL"        # LONG | SHORT | NEUTRAL
    regime: str = "UNKNOWN"

    confidence: float = 0.0           # agent's self-assessment (NOT win probability)
    uncertainty: float = 0.0          # 0..1, higher = more uncertain

    evidence: Evidence = field(default_factory=Evidence)
    supporting_features: list[str] = field(default_factory=list)
    conflicting_features: list[str] = field(default_factory=list)
    claims: list[Claim] = field(default_factory=list)

    reasoning: str = ""
    invalidation_conditions: str = ""

    # Engine traceability
    source_engine: str = ""
    source_engine_version: str = ""
    engine_metadata: dict[str, Any] = field(default_factory=dict)

    # Linkage
    opportunity_id: str = ""
    setup_id: str = ""

    # Data quality & availability
    data_quality: float = 0.0         # 0..1
    feature_availability: dict[str, bool] = field(default_factory=dict)

    # Error info (when status == ERROR)
    error_type: str = ""
    error_message: str = ""

    def __post_init__(self) -> None:
        if not self.observation_timestamp:
            self.observation_timestamp = self.timestamp
        if not self.data_cutoff_timestamp:
            self.data_cutoff_timestamp = self.timestamp

    def to_dict(self) -> dict[str, Any]:
        """Serialize AgentResult to a plain dict."""
        return {
            "agent_id": self.agent_id,
            "agent_version": self.agent_version,
            "execution_id": self.execution_id,
            "timestamp": self.timestamp,
            "observation_timestamp": self.observation_timestamp,
            "data_cutoff_timestamp": self.data_cutoff_timestamp,
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "status": self.status.value,
            "direction": self.direction,
            "regime": self.regime,
            "confidence": self.confidence,
            "uncertainty": self.uncertainty,
            "evidence": {
                "supporting": self.evidence.supporting,
                "conflicting": self.evidence.conflicting,
                "neutral": self.evidence.neutral,
                "evidence_score": self.evidence.evidence_score,
                "items": [
                    {
                        "evidence_id": item.evidence_id,
                        "type": item.type,
                        "feature": item.feature,
                        "value": item.value,
                        "timestamp": item.timestamp,
                        "data_cutoff_timestamp": item.data_cutoff_timestamp,
                        "direction": item.direction,
                        "strength": item.strength,
                        "source": item.source,
                        "explanation": item.explanation,
                    }
                    for item in self.evidence.items
                ],
            },
            "supporting_features": self.supporting_features,
            "conflicting_features": self.conflicting_features,
            "claims": [
                {
                    "claim_id": c.claim_id,
                    "statement": c.statement,
                    "source_agent": c.source_agent,
                    "source_agent_version": c.source_agent_version,
                    "observation_timestamp": c.observation_timestamp,
                    "data_cutoff_timestamp": c.data_cutoff_timestamp,
                    "evidence_refs": c.evidence_refs,
                    "validation_status": c.validation_status.value,
                    "feature": c.feature,
                    "regime": c.regime,
                    "timeframe": c.timeframe,
                    "symbol": c.symbol,
                    "sample_size": c.sample_size,
                    "confidence": c.confidence,
                }
                for c in self.claims
            ],
            "reasoning": self.reasoning,
            "invalidation_conditions": self.invalidation_conditions,
            "source_engine": self.source_engine,
            "source_engine_version": self.source_engine_version,
            "engine_metadata": self.engine_metadata,
            "opportunity_id": self.opportunity_id,
            "setup_id": self.setup_id,
            "data_quality": self.data_quality,
            "feature_availability": self.feature_availability,
            "error_type": self.error_type,
            "error_message": self.error_message,
        }


# =========================================================
# ADAPTER BASE CLASS
# =========================================================

@dataclass
class AdapterInfo:
    """Metadata about an adapter."""
    adapter_id: str = ""
    adapter_version: str = "v1"
    source_engine: str = ""
    source_engine_version: str = ""


class BaseAgentAdapter:
    """Base class for all engine adapters.

    Each adapter:
    1. Takes MarketContext as input
    2. Calls the existing engine
    3. Returns AgentResult
    4. Never raises — errors captured in AgentResult.status=ERROR
    """

    adapter_id: str = "base"
    adapter_version: str = "v1"
    source_engine: str = "unknown"
    source_engine_version: str = "unknown"

    def __init__(self, context: MarketContext) -> None:
        self.context = context

    def run(self) -> AgentResult:
        """Execute the adapter. Must be overridden."""
        return AgentResult(
            agent_id=self.adapter_id,
            agent_version=self.adapter_version,
            source_engine=self.source_engine,
            source_engine_version=self.source_engine_version,
            status=AgentStatus.ERROR,
            error_type="NOT_IMPLEMENTED",
            error_message=f"{self.adapter_id} run() not implemented",
            symbol=self.context.symbol,
            timeframe=self.context.timeframe,
            observation_timestamp=self.context.observation_timestamp,
            data_cutoff_timestamp=self.context.data_cutoff_timestamp,
        )

    def _error_result(self, error_type: str, message: str) -> AgentResult:
        """Create a standardized error AgentResult."""
        return AgentResult(
            agent_id=self.adapter_id,
            agent_version=self.adapter_version,
            source_engine=self.source_engine,
            source_engine_version=self.source_engine_version,
            status=AgentStatus.ERROR,
            error_type=error_type,
            error_message=message,
            symbol=self.context.symbol,
            timeframe=self.context.timeframe,
            observation_timestamp=self.context.observation_timestamp,
            data_cutoff_timestamp=self.context.data_cutoff_timestamp,
            data_quality=self.context.feature_snapshot.data_quality_score,
            feature_availability=self.context.feature_snapshot.available_features,
        )

    def _success_result(
        self,
        direction: str = "NEUTRAL",
        regime: str = "UNKNOWN",
        confidence: float = 0.0,
        uncertainty: float = 0.0,
        evidence: Evidence | None = None,
        supporting_features: list[str] | None = None,
        conflicting_features: list[str] | None = None,
        claims: list[Claim] | None = None,
        reasoning: str = "",
        invalidation_conditions: str = "",
        engine_metadata: dict[str, Any] | None = None,
        opportunity_id: str = "",
        setup_id: str = "",
    ) -> AgentResult:
        """Create a standardized success AgentResult."""
        return AgentResult(
            agent_id=self.adapter_id,
            agent_version=self.adapter_version,
            source_engine=self.source_engine,
            source_engine_version=self.source_engine_version,
            status=AgentStatus.SUCCESS,
            direction=direction,
            regime=regime,
            confidence=confidence,
            uncertainty=uncertainty,
            evidence=evidence or Evidence(),
            supporting_features=supporting_features or [],
            conflicting_features=conflicting_features or [],
            claims=claims or [],
            reasoning=reasoning,
            invalidation_conditions=invalidation_conditions,
            engine_metadata=engine_metadata or {},
            opportunity_id=opportunity_id,
            setup_id=setup_id,
            symbol=self.context.symbol,
            timeframe=self.context.timeframe,
            observation_timestamp=self.context.observation_timestamp,
            data_cutoff_timestamp=self.context.data_cutoff_timestamp,
            data_quality=self.context.feature_snapshot.data_quality_score,
            feature_availability=self.context.feature_snapshot.available_features,
        )
