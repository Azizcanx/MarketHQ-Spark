# -*- coding: utf-8 -*-
"""
MarketHQ Setup Object Model V1
================================

Zengin, serializable setup objesi — research-only, canli islem yok.

Mevcut setup_engine_v1.build_setup() ciktisini bu modele map eder,
sonra quality engine ve research pipeline bunu kullanir.

Schema (tum fieldler optional — backucompatible):
  market, timeframe, regime, bias, structure, liquidity_context,
  setup_type, entry_zone, confirmation, invalidation, targets,
  risk_reward, supporting_strategies, conflicting_strategies,
  evidence, historical_validation, quality, reasoning,
  invalidation_conditions, outcome, learning_metadata
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Any


# =========================================================
# SUB-MODELS
# =========================================================

@dataclass
class MarketInfo:
    symbol: str = "UNKNOWN"
    market: str = "crypto"  # crypto | stock | forex | commodity
    exchange: str = ""
    data_source: str = "yfinance"


@dataclass
class TimeframeInfo:
    timeframe: str = "1h"
    bar_count: int = 0
    date_range_start: str = ""
    date_range_end: str = ""


@dataclass
class RegimeInfo:
    regime: str = "UNKNOWN"  # UPTREND_STRONG | UPTREND_WEAK | DOWNTREND_STRONG | DOWNTREND_WEAK | RANGE_LOW_VOL | RANGE_HIGH_VOL | EXPANDING_VOLATILITY
    confidence: float = 0.0
    sma_fast: float = 0.0
    sma_slow: float = 0.0
    detail: str = ""
    # Multi-factor enrichment
    adx: float = 0.0
    atr_pct: float = 0.0
    vol_ratio: float | None = None
    vol_confirmed: bool = False
    structure_score: int = 0


@dataclass
class BiasInfo:
    direction: str = "NEUTRAL"  # LONG | SHORT | NEUTRAL
    bias_strength: float = 0.0  # 0..1
    reason: str = ""


@dataclass
class StructureInfo:
    """Market structure from SMC analysis."""
    has_structure: bool = False
    structure_type: str = ""  # BOS_UP | BOS_DOWN | CHoCH_UP | CHoCH_DOWN | NEUTRAL
    swing_highs: list[dict[str, Any]] = field(default_factory=list)
    swing_lows: list[dict[str, Any]] = field(default_factory=list)
    last_swing_high: float | None = None
    last_swing_low: float | None = None
    displacement: float = 0.0
    displacement_quality: str = ""  # strong | weak | none


@dataclass
class LiquidityInfo:
    """Liquidity context — where the big players' stops are."""
    buy_side_liquidity: float | None = None  # recent high above current price
    sell_side_liquidity: float | None = None  # recent low below current price
    liquidity_sweep_detected: bool = False
    liquidity_side: str = ""  # buy | sell | none
    sweep_distance_atr: float = 0.0
    description: str = ""


@dataclass
class EntryZone:
    """Logical entry region — not a single price."""
    center: float = 0.0
    low: float = 0.0
    high: float = 0.0
    width_atr: float = 0.0  # zone width in ATR multiples
    source: str = "atr_based"  # atr_based | structure | vwap | manual
    quality: str = "medium"  # high | medium | low — confluence of touches
    touches: int = 0  # how many times price tested this zone recently


@dataclass
class Confirmation:
    """What confirms the setup."""
    strategy_count: int = 0
    strategies: list[dict[str, Any]] = field(default_factory=list)
    family_agreement: dict[str, str] = field(default_factory=dict)  # family -> direction
    agreement_score: float = 0.0  # 0..1
    strongest_indicator: str = ""
    disqualifiers: list[str] = field(default_factory=list)
    family_conflicts: list[dict[str, Any]] = field(default_factory=list)
    # Correlation-adjusted agreement metadata
    agreement_raw: float = 0.0  # raw consensus share (max(longs,shorts)/total)
    agreement_adjusted: float = 0.0  # correlation-adjusted score
    family_diversity: float = 0.0  # 0..1, ratio of active families
    conflict_count: int = 0  # number of conflicting families
    supporting_strategies: list[str] = field(default_factory=list)
    conflicting_strategies: list[str] = field(default_factory=list)


@dataclass
class InvalidationLevel:
    """Where the setup is wrong."""
    price: float | None = None
    distance_atr: float = 0.0  # distance from entry in ATR multiples
    type: str = ""  # structural | volatility | time_based
    clarity: str = "medium"  # clear | medium | fuzzy — how obvious the stop is
    reasoning: str = ""


@dataclass
class TargetLevel:
    """Profit target."""
    price: float | None = None
    distance_atr: float = 0.0
    type: str = ""  # ATR_target | structure | swing | manual
    priority: str = "primary"  # primary | secondary | trailing
    reasoning: str = ""


@dataclass
class Targets:
    primary: TargetLevel | None = None
    secondary: TargetLevel | None = None
    trailing: TargetLevel | None = None


@dataclass
class RiskReward:
    reward_risk_ratio: float | None = None
    reward: float | None = None
    risk: float | None = None
    breakeven_age: float = 0.0  # ATR distance to breakeven
    feasibility: str = "medium"  # high | medium | low — R:R + win rate combo


@dataclass
class Evidence:
    """Evidence supporting/contradicting the setup."""
    supporting: list[dict[str, Any]] = field(default_factory=list)
    conflicting: list[dict[str, Any]] = field(default_factory=list)
    neutral: list[dict[str, Any]] = field(default_factory=list)
    evidence_score: float = 0.0  # 0..1, net support strength


@dataclass
class HistoricalValidation:
    """How similar setups performed historically."""
    available: bool = False
    similar_count: int = 0
    win_rate: float | None = None
    avg_return: float | None = None
    avg_return_20d: float | None = None
    best_return: float | None = None
    worst_return: float | None = None
    regime_match: str = ""
    lookup_method: str = ""  # regime+direction | full_hash | partial
    notes: str = ""


@dataclass
class QualityScore:
    """Multi-dimensional setup quality (replaces simple confidence)."""
    overall: float = 0.0  # 0..1
    supporting_evidence: float = 0.0
    conflicting_evidence: float = 0.0
    regime_compatibility: float = 0.0
    structure_quality: float = 0.0
    entry_quality: float = 0.0
    risk_reward_feasibility: float = 0.0
    historical_validation: float = 0.0
    strategy_agreement: float = 0.0
    invalidation_clarity: float = 0.0
    formation_chain: float = 0.0
    breakdown: dict[str, float] = field(default_factory=dict)
    flags: list[str] = field(default_factory=list)
    # Sample-size confidence / shrinkage (Task 1)
    sample_size_confidence: str = "unknown"  # low | medium | high
    sample_size_confidence_score: float = 0.0
    raw_expectancy: float = 0.0
    sample_adjusted_expectancy: float = 0.0
    shrinkage_factor: float = 0.0
    # Feature usage tracking (V4)
    feature_usage: dict[str, dict[str, str]] = field(default_factory=dict)
    feature_availability: dict[str, int] = field(default_factory=dict)


@dataclass
class Reasoning:
    """WHY panel — research-backed narrative."""
    entry_rationale: list[str] = field(default_factory=list)
    invalidation_rationale: list[str] = field(default_factory=list)
    target_rationale: list[str] = field(default_factory=list)
    regime_context: str = ""
    agreement_summary: str = ""
    key_insight: str = ""
    warnings: list[str] = field(default_factory=list)


@dataclass
class InvalidationConditions:
    """When to exit the setup as wrong."""
    price_condition: str = ""
    time_condition: str = ""  # e.g. "close beyond 2 ATR without touch"
    alternative_signal: str = ""  # e.g. "daily close below SMA50"
    manual_override: str = ""


@dataclass
class Outcome:
    """If the setup was executed and what happened."""
    executed: bool = False
    entry_price: float | None = None
    exit_price: float | None = None
    pnl_pct: float | None = None
    hit_target: bool = False
    hit_invalidation: bool = False
    duration_bars: int = 0
    max_favorable: float | None = None
    max_adverse: float | None = None


@dataclass
class LearningMetadata:
    """What the brain should learn from this setup."""
    setup_type_signature: str = ""  # e.g. "sweep_choch_downtrend"
    regime: str = ""
    confirmation_combo: str = ""  # e.g. "ema+supertrend+smc"
    learning_priority: float = 0.0  # 0..1 — should brain study this?
    next_research_question: str = ""
    strategy_evolution_hint: str = ""


# =========================================================
# MAIN MODEL
# =========================================================

@dataclass
class SetupModel:
    """Rich setup object — research-backed signal/setup engine output."""

    # Identity
    setup_id: str = ""
    symbol: str = "UNKNOWN"
    timeframe: str = "1h"
    generated_at: str = ""

    # Market context
    market: MarketInfo = field(default_factory=MarketInfo)
    timeframe_info: TimeframeInfo = field(default_factory=TimeframeInfo)
    regime: RegimeInfo = field(default_factory=RegimeInfo)
    bias: BiasInfo = field(default_factory=BiasInfo)

    # Structure & liquidity
    structure: StructureInfo = field(default_factory=StructureInfo)
    liquidity: LiquidityInfo = field(default_factory=LiquidityInfo)

    # Setup definition
    setup_type: str = ""  # e.g. "sweep_choch_breakout", "ema_crossover_r1", "or_breakout"
    entry_zone: EntryZone = field(default_factory=EntryZone)
    confirmation: Confirmation = field(default_factory=Confirmation)
    invalidation: InvalidationLevel = field(default_factory=InvalidationLevel)
    targets: Targets = field(default_factory=Targets)
    risk_reward: RiskReward = field(default_factory=RiskReward)

    # Strategy agreement
    supporting_strategies: list[str] = field(default_factory=list)
    conflicting_strategies: list[str] = field(default_factory=list)

    # Evidence & validation
    evidence: Evidence = field(default_factory=Evidence)
    historical_validation: HistoricalValidation = field(default_factory=HistoricalValidation)
    quality: QualityScore = field(default_factory=QualityScore)

    # Reasoning
    reasoning: Reasoning = field(default_factory=Reasoning)
    invalidation_conditions: InvalidationConditions = field(default_factory=InvalidationConditions)

    # Outcome & learning (filled later if executed)
    outcome: Outcome = field(default_factory=Outcome)
    learning_metadata: LearningMetadata = field(default_factory=LearningMetadata)

    # Meta
    research_only: bool = True
    engine: str = "MARKETHQ_RESEARCH_SETUP_ENGINE"
    version: str = "V1"

    # --- Helpers ---

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dict, handling dataclasses recursively."""
        return _serialize_dataclass(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> SetupModel:
        """Deserialize from dict (best-effort, missing fields get defaults)."""
        return _deserialize_dataclass(cls, d)


# =========================================================
# SERIALIZATION HELPERS
# =========================================================

def _serialize_dataclass(obj: Any) -> Any:
    """Recursively serialize dataclasses to dicts/lists."""
    if hasattr(obj, "__dataclass_fields__"):
        result = {}
        for f in obj.__dataclass_fields__:
            result[f] = _serialize_dataclass(getattr(obj, f))
        return result
    elif isinstance(obj, list):
        return [_serialize_dataclass(item) for item in obj]
    elif isinstance(obj, dict):
        return {k: _serialize_dataclass(v) for k, v in obj.items()}
    else:
        return obj


def _deserialize_dataclass(cls: type, d: dict[str, Any]) -> Any:
    """Best-effort deserialization — missing fields use defaults."""
    if not hasattr(cls, "__dataclass_fields__"):
        return d

    kwargs = {}
    for field_name, field_info in cls.__dataclass_fields__.items():
        if field_name in d and d[field_name] is not None:
            field_type = field_info.type
            # Handle Optional types
            origin = getattr(field_type, "__origin__", None)
            if origin is type | None or str(field_type).endswith("| NoneType"):
                # Try to get the inner type
                args = getattr(field_type, "__args__", ())
                if args:
                    inner = args[0]
                    if hasattr(inner, "__dataclass_fields__") and isinstance(d[field_name], dict):
                        kwargs[field_name] = _deserialize_dataclass(inner, d[field_name])
                    else:
                        kwargs[field_name] = d[field_name]
                else:
                    kwargs[field_name] = d[field_name]
            elif hasattr(field_type, "__dataclass_fields__") and isinstance(d[field_name], dict):
                kwargs[field_name] = _deserialize_dataclass(field_type, d[field_name])
            elif isinstance(field_type, type) and hasattr(field_type, "__dataclass_fields__") and isinstance(d[field_name], dict):
                kwargs[field_name] = _deserialize_dataclass(field_type, d[field_name])
            else:
                kwargs[field_name] = d[field_name]
        # else: use default from dataclass field

    return cls(**kwargs)


def setup_model_to_flat_dict(model: SetupModel) -> dict[str, Any]:
    """Flat dict for database storage — dot-notation keys."""
    d = model.to_dict()
    flat: dict[str, Any] = {}

    def _flatten(prefix: str, obj: Any) -> None:
        if isinstance(obj, dict):
            for k, v in obj.items():
                _flatten(f"{prefix}.{k}" if prefix else k, v)
        else:
            flat[prefix] = obj

    _flatten("", d)
    return flat


def format_setup_markdown(model: SetupModel) -> str:
    """WHY panel markdown from SetupModel."""
    lines = [
        f"## 🔬 Research WHY Paneli",
        "",
        f"**Sembol:** {model.symbol} | **Dönem:** {model.timeframe} | **Rejim:** {model.regime.regime}",
        f"**Yön:** {model.bias.direction} | **Güven:** {model.quality.overall:.0%} | **Setup:** {model.setup_type}",
        f"**Structure:** {model.structure.structure_type} | **Liquidity:** {model.liquidity.liquidity_side}",
        "",
        "### Entry Gerekcesi",
    ]
    for r in model.reasoning.entry_rationale:
        lines.append(f"- {r}")

    lines.append("")
    lines.append("### Invalidation Gerekcesi")
    for r in model.reasoning.invalidation_rationale:
        lines.append(f"- {r}")

    lines.append("")
    lines.append("### Hedef Gerekcesi")
    for r in model.reasoning.target_rationale:
        lines.append(f"- {r}")

    lines.append("")
    lines.append("### Strateji Birleşimi")
    lines.append(f"- Agreement: {model.confirmation.agreement_score:.0%} ({model.confirmation.strategy_count} strateji)")
    for fam, direction in model.confirmation.family_agreement.items():
        dir_str = ", ".join(direction) if isinstance(direction, list) else str(direction)
        lines.append(f"  - {fam}: {dir_str}")
    if model.confirmation.family_conflicts:
        lines.append("### ⚠️ Aile Çatışmaları")
        for c in model.confirmation.family_conflicts:
            lines.append(f"- {c['family']}: {', '.join(c['directions'])} ({c['severity']})")

    # Formation chain
    lines.append("")
    lines.append("### Setup Formation Zinciri")
    chain_links = []
    liq = model.liquidity
    if liq.buy_side_liquidity or liq.sell_side_liquidity:
        chain_links.append(f"Likidite: {liq.liquidity_side}-side sweep")
    else:
        chain_links.append("Likidite: sistematik")
    if model.structure.has_structure:
        chain_links.append(f"Yapı: {model.structure.structure_type}")
    else:
        chain_links.append("Yapı: tespit edilmedi")
    chain_links.append(f"Onay: {model.confirmation.agreement_score:.0%}")
    chain_links.append(f"Entry: {model.entry_zone.source}")
    if model.invalidation.price:
        chain_links.append(f"Invalidation: {model.invalidation.price:.4f}")
    if model.targets.primary and model.targets.primary.price:
        chain_links.append(f"Hedef: {model.targets.primary.price:.4f}")
    for link in chain_links:
        lines.append(f"- {link}")

    lines.append("")
    lines.append("### Kalite Skoru")
    q = model.quality
    lines.append(f"- Genel: {q.overall:.0%}")
    for k, v in q.breakdown.items():
        lines.append(f"  - {k}: {v:.0%}")

    # Regime filter status
    rf_status = getattr(model, "regime_filter_status", None)
    if rf_status:
        rf_compat = getattr(model, "regime_compatibility", 0.0)
        rf_reason = getattr(model, "regime_reason", "")
        lines.append("")
        lines.append("### Regime Filter")
        lines.append(f"- Durum: {rf_status}")
        lines.append(f"- Uyum: {rf_compat:.0%}")
        lines.append(f"- Sebep: {rf_reason}")

    lines.append("")
    lines.append("### Risk Metrikleri")
    rr = model.risk_reward
    lines.append(f"- Reward:Risk = {rr.reward_risk_ratio}:1" if rr.reward_risk_ratio else "- R:R hesaplanamadi")
    lines.append(f"- Breakeven: {rr.breakeven_age:.2f} ATR")

    lines.append("")
    lines.append("### ⚠️ Bayraklar")
    for flag in model.quality.flags:
        lines.append(f"- {flag}")

    if model.historical_validation.available:
        lines.append("")
        lines.append("### Tarihsel Doğrulama")
        hv = model.historical_validation
        lines.append(f"- Benzer setup: {hv.similar_count}")
        lines.append(f"- Win rate: {hv.win_rate:.0%}" if hv.win_rate else "- Win rate: yok")
        lines.append(f"- Ortalama getiri: {hv.avg_return:.1f}%" if hv.avg_return else "")

    lines.append("")
    lines.append(f"*Sonuç: {model.generated_at} — {model.engine} {model.version}*")

    return "\n".join(lines)