# -*- coding: utf-8 -*-
"""Phase F — Research-Backed Setup Engine.

Bridges Phase E Opportunity → ResearchBackedSetup.

Flow:
  Opportunity (from Phase E)
      ↓
  Setup Geometry (reuse setup_engine_v1)
      ↓
  Entry Zone + Confirmation
      ↓
  Invalidation
      ↓
  Targets (T1/T2/T3)
      ↓
  Risk / Reward
      ↓
  WHY Panel
      ↓
  Uncertainty Flags
      ↓
  ResearchBackedSetup

Research-only. No broker, no orders, no trading.
No win probability. Confidence = research confidence.
"""

from __future__ import annotations

import dataclasses
import math
from datetime import datetime, timezone
from typing import Any

import pandas as pd

from agent_contract import AgentResult, AgentStatus
from opportunity_model import (
    ResearchBackedSetup, SetupStatus, UncertaintyFlag, UncertaintyType,
    EvidenceTrace, Direction,
)
from opportunity_engine import (
    detect_opportunity, validate_opportunity,
    generate_setup_candidate,
    classify_evidence, direction_weight,
    get_family, STRATEGY_FAMILY_MAP,
)
from opportunity_persistence import OpportunityPersistence


# ═══════════════════════════════════════════════════════════════
# REFERENCES TO EXISTING ENGINES (imported lazily)
# ═══════════════════════════════════════════════════════════════

def _get_setup_engine_v1():
    """Lazy import of setup_engine_v1 for geometry."""
    import importlib
    mod = importlib.import_module("setup_engine_v1")
    return mod


def _get_research_setup_engine():
    """Lazy import of research_setup_engine for WHY panel."""
    import importlib
    mod = importlib.import_module("research_setup_engine")
    return mod


# ═══════════════════════════════════════════════════════════════
# ENTRY ZONE ENGINE
# ═══════════════════════════════════════════════════════════════

def _compute_entry_zone(
    df: pd.DataFrame,
    direction: str,
    atr: float,
    method: str = "structure_atr",
) -> dict[str, Any]:
    """Compute entry zone from market structure + ATR."""
    # UNKNOWN direction — no entry zone
    if direction == "UNKNOWN":
        return {
            "low": None, "high": None, "reference": None,
            "method": "unavailable", "status": "UNAVAILABLE",
            "reason": "Unknown direction — no entry zone",
        }

    if df is None or len(df) < 20:
        return {
            "low": None, "high": None, "reference": None,
            "method": "unavailable", "status": "UNAVAILABLE",
            "reason": "Insufficient data for entry zone",
        }

    last = df.iloc[-1]
    close = float(last.get("Close", 0))
    atr_val = atr if atr and math.isfinite(atr) and atr > 0 else None

    # Structure levels from recent swings
    structure_support = None
    structure_resistance = None
    try:
        from smc_structure_v1 import find_swings
        swings = find_swings(df)
        if swings:
            swing_highs = [s["price"] for s in swings if s["kind"] == "H"][-5:]
            swing_lows = [s["price"] for s in swings if s["kind"] == "L"][-5:]
            if swing_highs:
                structure_resistance = max(swing_highs)
            if swing_lows:
                structure_support = min(swing_lows)
    except Exception:
        pass

    # ATR-based zone
    if atr_val:
        atr_zone_width = 0.5 * atr_val
        if direction == "LONG":
            atr_low = close - atr_zone_width
            atr_high = close + atr_zone_width * 0.3
        elif direction == "SHORT":
            atr_low = close - atr_zone_width * 0.3
            atr_high = close + atr_zone_width
        else:
            atr_low = close - atr_zone_width
            atr_high = close + atr_zone_width
    else:
        atr_low = None
        atr_high = None

    # Combine structure + ATR
    zone_low = None
    zone_high = None
    used_methods = []

    if direction == "LONG":
        # Entry near support for LONG
        if structure_support and close > structure_support:
            zone_low = structure_support
            used_methods.append("structure_support")
        elif atr_low:
            zone_low = atr_low
            used_methods.append("atr_support")

        if structure_support and atr_high:
            zone_high = min(structure_support * 1.02, atr_high)
        elif atr_high:
            zone_high = atr_high
        else:
            zone_high = close * 1.01

    elif direction == "SHORT":
        # Entry near resistance for SHORT
        if structure_resistance and close < structure_resistance:
            zone_low = structure_resistance * 0.98
            used_methods.append("structure_resistance")
        elif atr_low:
            zone_low = atr_low
            used_methods.append("atr_support")

        if structure_resistance and atr_low:
            zone_high = max(structure_resistance, atr_low)
        elif atr_high:
            zone_high = atr_high
        else:
            zone_high = close * 0.99

    else:
        # NEUTRAL/UNKNOWN — no directional entry
        if atr_low and atr_high:
            zone_low = atr_low
            zone_high = atr_high
            used_methods.append("atr_centered")
        else:
            return {
                "low": None, "high": None, "reference": close,
                "method": "unavailable", "status": "UNAVAILABLE",
                "reason": "No directional bias for entry zone",
            }

    if zone_low is not None and zone_high is not None:
        reference = (zone_low + zone_high) / 2
        return {
            "low": round(zone_low, 4),
            "high": round(zone_high, 4),
            "reference": round(reference, 4),
            "method": "+".join(used_methods) if used_methods else "atr_only",
            "status": "AVAILABLE",
            "reason": f"Entry zone from {' + '.join(used_methods)}",
        }

    return {
            "low": None, "high": None, "reference": close,
            "method": "unavailable", "status": "UNAVAILABLE",
            "reason": "Could not compute entry zone",
        }


# ═══════════════════════════════════════════════════════════════
# ENTRY CONFIRMATION
# ═══════════════════════════════════════════════════════════════

def _compute_entry_confirmation(
    df: pd.DataFrame,
    direction: str,
    regime: str,
) -> list[str]:
    """Compute entry confirmation signals.

    Returns list of confirmation methods, or empty list if unavailable.
    """
    confirmations = []

    if df is None or len(df) < 20:
        return confirmations

    last = df.iloc[-1]

    # Volume confirmation
    vol_ratio = last.get("VOLUME_RATIO", 0)
    if vol_ratio and math.isfinite(vol_ratio) and vol_ratio > 1.0:
        confirmations.append("volume_surge")

    # Regime confirmation
    if regime and "DOWNTREND" in regime and direction == "SHORT":
        confirmations.append("regime_alignment")
    elif regime and "UPTREND" in regime and direction == "LONG":
        confirmations.append("regime_alignment")

    # Structure confirmation (BOS/CHoCH)
    try:
        from smc_structure_v1 import find_swings, structure_events
        from signal_engine import add_indicators, DEFAULT_CONFIG
        enriched = add_indicators(df, DEFAULT_CONFIG)
        atr = float(last.get("ATR", 0) or 0)
        swings = find_swings(df)
        events = structure_events(df, swings, atr) if atr > 0 else []
        for ev in events[-3:]:
            if direction == "LONG" and ev["type"] in ("BOS_UP", "CHoCH_UP"):
                confirmations.append("structure_break")
                break
            elif direction == "SHORT" and ev["type"] in ("BOS_DOWN", "CHoCH_DOWN"):
                confirmations.append("structure_break")
                break
    except Exception:
        pass

    return confirmations


# ═══════════════════════════════════════════════════════════════
# INVALIDATION ENGINE
# ═══════════════════════════════════════════════════════════════

def _compute_invalidation(
    df: pd.DataFrame,
    direction: str,
    entry_reference: float | None,
    atr: float,
    regime: str,
) -> dict[str, Any]:
    """Compute invalidation level for a setup.

    Uses ATR-based invalidation as baseline, adds structure-based
    invalidation if available.
    """
    if entry_reference is None or not math.isfinite(entry_reference):
        return {
            "price": None, "type": "unavailable", "reason": "",
            "distance_atr": 0.0,
        }

    atr_val = atr if atr and math.isfinite(atr) and atr > 0 else None

    # ATR-based invalidation
    if atr_val:
        atr_distance = 2.0 * atr_val
        if direction == "LONG":
            atr_invalidation = entry_reference - atr_distance
        elif direction == "SHORT":
            atr_invalidation = entry_reference + atr_distance
        else:
            atr_invalidation = entry_reference - atr_distance
    else:
        atr_invalidation = None
        atr_distance = 0.0

    # Structure-based invalidation
    structure_invalidation = None
    structure_reason = ""
    try:
        from smc_structure_v1 import find_swings, structure_events
        from signal_engine import add_indicators, DEFAULT_CONFIG
        enriched = add_indicators(df, DEFAULT_CONFIG)
        last = enriched.iloc[-1]
        atr_s = float(last.get("ATR", 0) or 0)
        swings = find_swings(df)
        events = structure_events(df, swings, atr_s) if atr_s > 0 else []

        for ev in reversed(events[-10:]):
            if direction == "LONG" and ev["type"] in ("BOS_DOWN", "CHoCH_DOWN"):
                structure_invalidation = ev["price"]
                structure_reason = f"structure_{ev['type'].lower()}"
                break
            elif direction == "SHORT" and ev["type"] in ("BOS_UP", "CHoCH_UP"):
                structure_invalidation = ev["price"]
                structure_reason = f"structure_{ev['type'].lower()}"
                break
    except Exception:
        pass

    # Choose the tighter invalidation
    if atr_invalidation and structure_invalidation:
        if direction == "LONG":
            price = max(atr_invalidation, structure_invalidation)
        else:
            price = min(atr_invalidation, structure_invalidation)
        reason = f"ATR+structure ({structure_reason})"
        itype = "combined"
    elif atr_invalidation:
        price = atr_invalidation
        reason = f"ATR×2.0 stop-loss ({structure_reason})" if structure_reason else "ATR×2.0 stop-loss"
        itype = "atr"
    elif structure_invalidation:
        price = structure_invalidation
        reason = f"Structure: {structure_reason}"
        itype = "structure"
    else:
        return {
            "price": None, "type": "unavailable",
            "reason": "No invalidation data available",
            "distance_atr": 0.0,
        }

    distance = abs(entry_reference - price) if price else 0.0
    distance_atr = distance / atr_val if atr_val and distance else 0.0

    return {
        "price": round(price, 4) if price else None,
        "type": itype,
        "reason": reason,
        "distance_atr": round(distance_atr, 2),
    }


# ═══════════════════════════════════════════════════════════════
# TARGET ENGINE
# ═══════════════════════════════════════════════════════════════

def _compute_targets(
    df: pd.DataFrame,
    direction: str,
    entry_reference: float | None,
    atr: float,
    regime: str,
) -> dict[str, Any]:
    """Compute target levels (T1/T2/T3).

    Uses ATR-based targets as baseline, adds structure-based targets
    if available.
    """
    if entry_reference is None or not math.isfinite(entry_reference):
        return {"t1": None, "t2": None, "t3": None, "method": "unavailable"}

    atr_val = atr if atr and math.isfinite(atr) and atr > 0 else None

    # ATR-based targets
    targets = {}
    if atr_val:
        if direction == "LONG":
            targets["t1"] = entry_reference + atr_val
            targets["t2"] = entry_reference + 2 * atr_val
            targets["t3"] = entry_reference + 3 * atr_val
        elif direction == "SHORT":
            targets["t1"] = entry_reference - atr_val
            targets["t2"] = entry_reference - 2 * atr_val
            targets["t3"] = entry_reference - 3 * atr_val
        else:
            targets["t1"] = entry_reference + atr_val
            targets["t2"] = entry_reference + 2 * atr_val
            targets["t3"] = entry_reference + 3 * atr_val
    else:
        return {"t1": None, "t2": None, "t3": None, "method": "unavailable"}

    # Structure-based targets (swing points)
    structure_targets = []
    try:
        from smc_structure_v1 import find_swings
        swings = find_swings(df)
        if swings:
            swing_highs = sorted([s["price"] for s in swings if s["kind"] == "H"], reverse=True)
            swing_lows = sorted([s["price"] for s in swings if s["kind"] == "L"])
            if direction == "LONG":
                structure_targets = sorted([p for p in swing_highs if p > entry_reference])[:3]
            elif direction == "SHORT":
                structure_targets = sorted([p for p in swing_lows if p < entry_reference], reverse=True)[:3]
    except Exception:
        pass

    method = "atr"
    if structure_targets:
        # Use structure targets if available, fallback to ATR
        for i, t in enumerate(structure_targets[:3]):
            key = f"t{i+1}"
            if key in targets:
                targets[key] = round(t, 4)
        method = "structure+atr"

    return {
        "t1": round(targets.get("t1"), 4) if targets.get("t1") else None,
        "t2": round(targets.get("t2"), 4) if targets.get("t2") else None,
        "t3": round(targets.get("t3"), 4) if targets.get("t3") else None,
        "method": method,
    }


# ═══════════════════════════════════════════════════════════════
# RISK / REWARD
# ═══════════════════════════════════════════════════════════════

def _compute_rr(
    direction: str,
    entry: float | None,
    invalidation: float | None,
    target: float | None,
) -> dict[str, Any]:
    """Compute risk/reward ratios."""
    if entry is None:
        return {"rr_t1": None, "rr_t2": None, "rr_t3": None, "risk": 0.0, "reward_t1": 0.0}
    if not math.isfinite(entry):
        return {"rr_t1": None, "rr_t2": None, "rr_t3": None, "risk": 0.0, "reward_t1": 0.0}

    risk = abs(entry - invalidation) if invalidation else 0.0

    rr = {}
    for i, t in enumerate([target], 1):
        if t and risk > 0:
            reward = abs(t - entry)
            rr[f"rr_t{i}"] = round(reward / risk, 2)
        else:
            rr[f"rr_t{i}"] = None

    return {
        "rr_t1": rr.get("rr_t1"),
        "rr_t2": rr.get("rr_t2"),
        "rr_t3": rr.get("rr_t3"),
        "risk": round(risk, 4),
        "reward_t1": round(abs(target - entry), 4) if target else 0.0,
    }


# ═══════════════════════════════════════════════════════════════
# UNCERTAINTY ENGINE
# ═══════════════════════════════════════════════════════════════

def _compute_uncertainty(
    opp_direction: str,
    supporting_count: int,
    conflicting_count: int,
    unavailable_count: int,
    total_agents: int,
    historical_available: bool,
    sample_size: int,
    data_availability: float,
    entry_status: str,
    target_status: str,
) -> list[UncertaintyFlag]:
    """Compute uncertainty flags for a setup.

    Automatically detects uncertainty from evidence gaps.
    """
    flags: list[UncertaintyFlag] = []

    # Conflicting agents
    if conflicting_count > 0:
        flags.append(UncertaintyFlag(
            type=UncertaintyType.CONFLICTING_AGENTS,
            description=f"{conflicting_count} agent(s) conflict with direction",
            severity="high" if conflicting_count >= 2 else "medium",
            feature="agent_conflict",
        ))

    # Unavailable evidence
    if unavailable_count > total_agents * 0.5:
        flags.append(UncertaintyFlag(
            type=UncertaintyType.FEATURE_UNAVAILABLE,
            description=f"{unavailable_count}/{total_agents} agents unavailable",
            severity="high",
            feature="agent_availability",
        ))
    elif unavailable_count > 0:
        flags.append(UncertaintyFlag(
            type=UncertaintyType.FEATURE_UNAVAILABLE,
            description=f"{unavailable_count} agent(s) evidence unavailable",
            severity="medium",
            feature="agent_availability",
        ))

    # Historical evidence
    if not historical_available:
        flags.append(UncertaintyFlag(
            type=UncertaintyType.INSUFFICIENT_HISTORY,
            description="No historical evidence available for this setup type",
            severity="medium",
            feature="historical_evidence",
        ))
    elif sample_size < 30:
        flags.append(UncertaintyFlag(
            type=UncertaintyType.LOW_SAMPLE,
            description=f"Low sample size: {sample_size} (< 30)",
            severity="high" if sample_size < 10 else "medium",
            feature="historical_sample",
        ))

    # Entry geometry
    if entry_status == "UNAVAILABLE":
        flags.append(UncertaintyFlag(
            type=UncertaintyType.WEAK_ENTRY_GEOMETRY,
            description="Entry zone unavailable — weak entry geometry",
            severity="high",
            feature="entry_zone",
        ))

    # Target geometry
    if target_status == "UNAVAILABLE":
        flags.append(UncertaintyFlag(
            type=UncertaintyType.WEAK_TARGET_GEOMETRY,
            description="Target levels unavailable — weak target geometry",
            severity="medium",
            feature="target_levels",
        ))

    # Data availability
    if data_availability < 0.5:
        flags.append(UncertaintyFlag(
            type=UncertaintyType.FEATURE_UNAVAILABLE,
            description=f"Low data availability: {data_availability:.0%}",
            severity="high",
            feature="data_availability",
        ))

    # Volume (check if volume data is present)
    flags.append(UncertaintyFlag(
        type=UncertaintyType.MISSING_VOLUME,
        description="Volume data may be incomplete for this timeframe",
        severity="low",
        feature="volume",
    ))

    # Regime instability
    flags.append(UncertaintyFlag(
        type=UncertaintyType.REGIME_INSTABILITY,
        description="Regime may shift before setup matures",
        severity="low",
        feature="regime",
    ))

    return flags


# ═══════════════════════════════════════════════════════════════
# WHY PANEL
# ═══════════════════════════════════════════════════════════════

def _generate_why_panel(
    setup: ResearchBackedSetup,
    opp_direction: str,
    supporting_agents: list[dict],
    conflicting_agents: list[dict],
    regime: str,
) -> dict[str, Any]:
    """Generate WHY panel for research-backed setup."""
    panel: dict[str, Any] = {}

    # Market context
    panel["market_context"] = {
        "symbol": setup.symbol,
        "timeframe": setup.timeframe,
        "regime": regime,
    }

    # Direction
    panel["direction"] = setup.direction

    # Supporting evidence
    panel["supporting_evidence"] = []
    for sa in supporting_agents:
        panel["supporting_evidence"].append({
            "agent": sa.get("agent_id", ""),
            "direction": sa.get("direction", ""),
            "confidence": sa.get("confidence", 0),
            "strategy_family": sa.get("strategy_family", ""),
        })

    # Conflicting evidence
    panel["conflicting_evidence"] = []
    for ca in conflicting_agents:
        panel["conflicting_evidence"].append({
            "agent": ca.get("agent_id", ""),
            "direction": ca.get("direction", ""),
            "confidence": ca.get("confidence", 0),
            "strategy_family": ca.get("strategy_family", ""),
        })

    # Entry rationale
    entry_parts = []
    if setup.entry_method:
        entry_parts.append(f"Entry zone method: {setup.entry_method}")
    if setup.entry_zone_low and setup.entry_zone_high:
        entry_parts.append(f"Zone: [{setup.entry_zone_low:.4f}, {setup.entry_zone_high:.4f}]")
    panel["entry_rationale"] = entry_parts

    # Invalidation rationale
    inv_parts = []
    if setup.invalidation_price:
        inv_parts.append(f"Invalidation at {setup.invalidation_price:.4f}")
    if setup.invalidation_reason:
        inv_parts.append(f"Reason: {setup.invalidation_reason}")
    panel["invalidation_rationale"] = inv_parts

    # Target rationale
    tgt_parts = []
    if setup.target_1:
        tgt_parts.append(f"T1: {setup.target_1:.4f}")
    if setup.target_2:
        tgt_parts.append(f"T2: {setup.target_2:.4f}")
    if setup.target_3:
        tgt_parts.append(f"T3: {setup.target_3:.4f}")
    if setup.target_method:
        tgt_parts.append(f"Method: {setup.target_method}")
    panel["target_rationale"] = tgt_parts

    # Regime context
    panel["regime_context"] = regime

    # Agreement analysis
    panel["agreement_analysis"] = {
        "supporting_agents": len(supporting_agents),
        "conflicting_agents": len(conflicting_agents),
        "direction_counts": {
            opp_direction: len(supporting_agents),
            "conflicting": len(conflicting_agents),
        },
    }

    # Risk/Reward
    panel["reward_risk"] = {
        "rr_t1": setup.rr_to_t1,
        "rr_t2": setup.rr_to_t2,
        "rr_t3": setup.rr_to_t3,
        "risk": setup.stop_distance,
    }

    # Uncertainty
    panel["uncertainty"] = {
        "flags": [uf.to_dict() for uf in setup.uncertainty_flags],
        "overall": setup.overall_uncertainty,
    }

    # Research flags
    flags = []
    if setup.confidence < 0.3:
        flags.append("DUSUK_GUVENLILIK: setup bilincli olarak kullanilmali")
    elif setup.confidence < 0.55:
        flags.append("ORTA_GUVENLILIK: ek onay oneren setup")
    if setup.invalidation_price is None:
        flags.append("INVALIDATION_YOK: invalidation belirlenemedi")
    if setup.target_1 is None:
        flags.append("HEDEF_YOK: target belirlenemedi")
    if setup.uncertainty_flags:
        high_severity = [f for f in setup.uncertainty_flags if f.severity in ("high", "critical")]
        if high_severity:
            flags.append(f"YUKSEK_UNSUR: {len(high_severity)} high-severity uncertainty flag")
    flags.append("RESEARCH_ONLY: canli islem yok")
    panel["research_flags"] = flags

    # Research-only warning
    panel["research_only"] = True
    panel["not_a_trade_recommendation"] = True

    return panel


# ═══════════════════════════════════════════════════════════════
# MAIN: BUILD RESEARCH-BACKED SETUP
# ═══════════════════════════════════════════════════════════════

def build_research_backed_setup(
    opportunity: Any,
    df: pd.DataFrame | None = None,
    feature_snapshot_id: str = "",
    cutoff_idx: int | None = None,
) -> ResearchBackedSetup:
    """Build a ResearchBackedSetup from an Opportunity.

    Args:
        opportunity: Opportunity object (from Phase E)
        df: OHLCV DataFrame (optional — for geometry calculation)
        feature_snapshot_id: FeatureSnapshot cache reference (optional)
        cutoff_idx: If provided, only bars up to this index are used
            for geometry calculation. Future bars are excluded to prevent
            lookahead leakage.

    Returns:
        ResearchBackedSetup with full traceability
    """
    now = datetime.now(timezone.utc).isoformat()

    # Truncate df to cutoff_idx to prevent lookahead leakage
    if cutoff_idx is not None and df is not None and len(df) > cutoff_idx + 1:
        df = df.iloc[: cutoff_idx + 1].copy()

    # Generate feature_snapshot_id if not provided

    # Generate feature_snapshot_id if not provided
    if not feature_snapshot_id:
        feature_snapshot_id = f"FS-{opportunity.symbol}-{opportunity.timeframe}-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M')}"

    # --- Extract opportunity data ---
    opp_direction = opportunity.direction
    opp_regime = opportunity.regime
    opp_confidence = opportunity.confidence
    opp_uncertainty = opportunity.uncertainty
    opp_supporting = opportunity.supporting_evidence
    opp_conflicting = opportunity.conflicting_evidence
    opp_unavailable = opportunity.unavailable_evidence
    opp_strategy_families = opportunity.strategy_families
    opp_feature_snapshot_id = opportunity.feature_snapshot_id
    opp_source_agents_raw = opportunity.source_agents
    opp_source_agents = []
    for sa in opp_source_agents_raw:
        if dataclasses.is_dataclass(sa) and not isinstance(sa, type):
            opp_source_agents.append(dataclasses.asdict(sa))
        elif isinstance(sa, dict):
            opp_source_agents.append(sa)
        else:
            opp_source_agents.append({"agent_id": str(sa), "direction": "NEUTRAL", "confidence": 0})

    # --- Compute data availability ---
    total_evidence = len(opp_supporting) + len(opp_conflicting) + len(opp_unavailable)
    available_evidence = len(opp_supporting) + len(opp_conflicting)
    data_availability = available_evidence / max(total_evidence, 1)

    # --- Compute indicators if df provided ---
    if df is not None and len(df) > 0:
        try:
            # Flatten MultiIndex columns if present
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
            from signal_engine import add_indicators, DEFAULT_CONFIG
            df = add_indicators(df, DEFAULT_CONFIG)
        except Exception:
            pass

    atr_val = 0.0
    if df is not None and len(df) > 0:
        last = df.iloc[-1]
        atr_val = float(last.get("ATR", 0) or 0)

    entry_result = _compute_entry_zone(df, opp_direction, atr_val if atr_val > 0 else None)
    entry_zone_low = entry_result.get("low")
    entry_zone_high = entry_result.get("high")
    entry_reference = entry_result.get("reference")
    entry_method = entry_result.get("method", "unavailable")
    entry_status = entry_result.get("status", "UNAVAILABLE")

    # --- Entry confirmation ---
    entry_confirmation = _compute_entry_confirmation(df, opp_direction, opp_regime)

    # --- Invalidation ---
    inv_result = _compute_invalidation(df, opp_direction, entry_reference, atr_val if atr_val > 0 else None, opp_regime)
    invalidation_price = inv_result.get("price")
    invalidation_type = inv_result.get("type", "unavailable")
    invalidation_reason = inv_result.get("reason", "")
    invalidation_distance_atr = inv_result.get("distance_atr", 0.0)

    # --- Targets ---
    tgt_result = _compute_targets(df, opp_direction, entry_reference, atr_val if atr_val > 0 else None, opp_regime)
    target_1 = tgt_result.get("t1")
    target_2 = tgt_result.get("t2")
    target_3 = tgt_result.get("t3")
    target_method = tgt_result.get("method", "unavailable")

    # --- Risk / Reward ---
    rr = _compute_rr(opp_direction, entry_reference, invalidation_price, target_1)

    # --- Compute distances (handle None) ---
    _e = entry_reference if entry_reference is not None else 0.0
    _i = invalidation_price if invalidation_price is not None else 0.0
    _t1 = target_1 if target_1 is not None else 0.0
    _t2 = target_2 if target_2 is not None else 0.0
    _t3 = target_3 if target_3 is not None else 0.0

    # --- Historical evidence ---
    historical_evidence: dict[str, Any] = {"available": False, "sample_size": 0}
    try:
        from setup_outcome_tracker import get_historical_stats
        stats = get_historical_stats(
            symbol=opportunity.symbol,
            regime=opp_regime,
            direction=opp_direction,
            setup_type="research_backed",
            min_samples=0,
        )
        historical_evidence = {
            "available": stats.get("available", False),
            "sample_size": stats.get("similar_count", 0),
            "win_rate": stats.get("win_rate"),
            "avg_return": stats.get("avg_return"),
            "lookup_method": "setup_signature",
        }
    except Exception:
        pass

    # --- Uncertainty ---
    supporting_count = len(opp_supporting)
    conflicting_count = len(opp_conflicting)
    unavailable_count = len(opp_unavailable)
    total_agents = opportunity.strategy_count or 1

    uncertainty_flags = _compute_uncertainty(
        opp_direction,
        supporting_count,
        conflicting_count,
        unavailable_count,
        total_agents,
        historical_evidence.get("available", False),
        historical_evidence.get("sample_size", 0),
        data_availability,
        entry_status,
        "AVAILABLE" if target_1 else "UNAVAILABLE",
    )

    # --- Overall uncertainty ---
    high_count = sum(1 for f in uncertainty_flags if f.severity == "high")
    critical_count = sum(1 for f in uncertainty_flags if f.severity == "critical")
    medium_count = sum(1 for f in uncertainty_flags if f.severity == "medium")
    overall_uncertainty = min(1.0, (high_count * 0.25 + critical_count * 0.4 + medium_count * 0.1 + len(uncertainty_flags) * 0.05))

    # --- Thesis ---
    thesis = opportunity.thesis if opportunity.thesis else ""

    # --- Evidence traces ---
    evidence_traces: list[EvidenceTrace] = []
    for sa in opp_source_agents:
        if sa.get("direction") == opp_direction:
            evidence_traces.append(EvidenceTrace(
                assertion=f"{sa.get('agent_id', '')} supports {opp_direction}",
                source_agent=sa.get("agent_id", ""),
                agent_run_id=sa.get("agent_id", ""),
                feature_snapshot_id=feature_snapshot_id or opp_feature_snapshot_id or f"FS-{opportunity.symbol}-{opportunity.timeframe}",
                timestamp=now,
                evidence_feature="strategy_direction",
                evidence_value=sa.get("confidence", 0),
                evidence_direction=sa.get("direction", "NEUTRAL"),
            ))

    # --- Supporting/Conflicting evidence for setup ---
    supporting_evidence = [
        {"agent_id": sa.get("agent_id", ""), "direction": sa.get("direction", ""), "confidence": sa.get("confidence", 0)}
        for sa in opp_source_agents if sa.get("direction") == opp_direction
    ]
    conflicting_evidence = [
        {"agent_id": sa.get("agent_id", ""), "direction": sa.get("direction", ""), "confidence": sa.get("confidence", 0)}
        for sa in opp_source_agents if sa.get("direction") != opp_direction and sa.get("direction") in ("LONG", "SHORT")
    ]

    # --- Evidence breakdown ---
    structure_evidence = {"structure_type": "", "swing_points": 0}
    regime_evidence = {"regime": opp_regime, "compatibility": "unknown"}
    momentum_evidence = {}
    liquidity_evidence = {}
    volatility_evidence = {}

    # --- Quality reference ---
    quality_reference = "setup_quality_engine_v4_experimental"

    # --- Determine status ---
    status = SetupStatus.CANDIDATE
    if opp_direction == "UNKNOWN":
        status = SetupStatus.CANDIDATE
    elif conflicting_count > supporting_count:
        status = SetupStatus.CANDIDATE
    elif data_availability < 0.3:
        status = SetupStatus.UNDER_REVIEW

    # --- Determine setup type ---
    setup_type = f"research_{opp_direction.lower()}"
    if opp_direction == "UNKNOWN":
        setup_type = "research_unknown"

    # --- Strategy family ---
    strategy_family = ""
    if opp_source_agents:
        first_agent = opp_source_agents[0]
        strategy_family = first_agent.get("strategy_family", "")

    # --- Build ResearchBackedSetup ---
    setup = ResearchBackedSetup(
        opportunity_id=opportunity.opportunity_id,
        symbol=opportunity.symbol,
        timeframe=opportunity.timeframe,
        detected_at=now,
        direction=opp_direction,
        regime=opp_regime,
        setup_type=setup_type,
        strategy_family=strategy_family,
        thesis=thesis,
        entry_zone_low=entry_zone_low,
        entry_zone_high=entry_zone_high,
        entry_reference=entry_reference,
        entry_method=entry_method,
        entry_confirmation=entry_confirmation,
        entry_status=entry_status,
        invalidation_price=invalidation_price,
        invalidation_type=invalidation_type,
        invalidation_reason=invalidation_reason,
        invalidation_distance_atr=invalidation_distance_atr,
        target_1=target_1,
        target_2=target_2,
        target_3=target_3,
        target_method=target_method,
        stop_distance=rr.get("risk", 0.0),
        target_distance_1=abs(_t1 - _e),
        target_distance_2=abs(_t2 - _e),
        target_distance_3=abs(_t3 - _e),
        rr_to_t1=rr.get("rr_t1"),
        rr_to_t2=rr.get("rr_t2"),
        rr_to_t3=rr.get("rr_t3"),
        supporting_evidence=supporting_evidence,
        conflicting_evidence=conflicting_evidence,
        historical_evidence=historical_evidence,
        structure_evidence=structure_evidence,
        regime_evidence=regime_evidence,
        momentum_evidence=momentum_evidence,
        liquidity_evidence=liquidity_evidence,
        volatility_evidence=volatility_evidence,
        uncertainty_flags=uncertainty_flags,
        overall_uncertainty=round(overall_uncertainty, 3),
        quality_reference=quality_reference,
        confidence=opp_confidence,
        uncertainty=opp_uncertainty,
        data_availability=round(data_availability, 3),
        source_agents=opp_source_agents,
        evidence_traces=evidence_traces,
        feature_snapshot_id=feature_snapshot_id or opp_feature_snapshot_id or f"FS-{opportunity.symbol}-{opportunity.timeframe}",
        status=status,
    )

    # --- Generate WHY panel ---
    setup.why_panel = _generate_why_panel(
        setup, opp_direction,
        supporting_evidence, conflicting_evidence,
        opp_regime,
    )

    return setup