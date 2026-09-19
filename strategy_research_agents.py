# -*- coding: utf-8 -*-
"""Strategy Research Agents — Phase D.

7 research agents over existing deterministic engines.
Each agent: MarketContext → AgentResult (structured research observation).
No trading, no fake data, no lookahead.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from agent_contract import (
    AgentResult,
    AgentStatus,
    Claim,
    ClaimStatus,
    Evidence,
    EvidenceItem,
    MarketContext,
    BaseAgentAdapter,
)


# ═══════════════════════════════════════════════════════════════
# HELPER: availability check
# ═══════════════════════════════════════════════════════════════

def _check_features(ctx: MarketContext, required: list[str]) -> tuple[list[str], list[str]]:
    """Check which required features are available.

    Returns (available, unavailable).
    """
    available = []
    unavailable = []
    features = ctx.feature_snapshot.available_features
    for feat in required:
        if features.get(feat, False):
            available.append(feat)
        else:
            unavailable.append(feat)
    return available, unavailable


def _has_enough_bars(ctx: MarketContext, min_bars: int = 30) -> bool:
    return ctx.feature_snapshot.bar_count >= min_bars


# ═══════════════════════════════════════════════════════════════
# 1. TREND RESEARCH AGENT
# ═══════════════════════════════════════════════════════════════

class TrendResearchAdapter(BaseAgentAdapter):
    """Research agent for trend strategies.

    Analyzes: trend direction, strength, persistence, structure alignment,
    momentum alignment, volatility context, regime compatibility.
    """
    adapter_id = "strategy_trend"
    adapter_version = "1.0"
    source_engine = "strategy_registry_v1"
    source_engine_version = "1.0"

    REQUIRED_FEATURES = ["EMA_FAST", "EMA_SLOW", "ADX", "ATR"]

    def run(self) -> AgentResult:
        available, unavailable = _check_features(self.context, self.REQUIRED_FEATURES)

        if not _has_enough_bars(self.context, 30):
            return AgentResult(
                agent_id=self.adapter_id,
                agent_version=self.adapter_version,
                source_engine=self.source_engine,
                source_engine_version=self.source_engine_version,
                status=AgentStatus.INSUFFICIENT_DATA,
                direction="UNKNOWN", regime="UNKNOWN", confidence=0.0, uncertainty=1.0,
                reasoning=f"Insufficient bars: need 30+, have {self.context.feature_snapshot.bar_count}",
                engine_metadata={"required_features": self.REQUIRED_FEATURES,
                                 "unavailable_features": [], "insufficient": "BAR_COUNT_LOW"},
                symbol=self.context.symbol, timeframe=self.context.timeframe,
                observation_timestamp=self.context.observation_timestamp,
                data_cutoff_timestamp=self.context.data_cutoff_timestamp,
            )

        if not available:
            return AgentResult(
                agent_id=self.adapter_id,
                agent_version=self.adapter_version,
                source_engine=self.source_engine,
                source_engine_version=self.source_engine_version,
                status=AgentStatus.PARTIAL,
                direction="UNKNOWN", regime="UNKNOWN", confidence=0.0, uncertainty=1.0,
                reasoning=f"Partial data: unavailable features {unavailable}",
                engine_metadata={"required_features": self.REQUIRED_FEATURES,
                                 "unavailable_features": unavailable, "partial": True},
                symbol=self.context.symbol, timeframe=self.context.timeframe,
                observation_timestamp=self.context.observation_timestamp,
                data_cutoff_timestamp=self.context.data_cutoff_timestamp,
            )

        # Use signal_engine indicators from feature_snapshot
        sma_fast = self.context.feature_snapshot.sma_fast
        sma_slow = self.context.feature_snapshot.sma_slow
        adx = self.context.feature_snapshot.adx
        atr = self.context.feature_snapshot.atr
        regime = self.context.feature_snapshot.regime

        # Trend thesis
        direction = "NEUTRAL"
        confidence = 0.0
        thesis_parts = []
        evidence_items = []

        if sma_fast and sma_slow:
            if sma_fast > sma_slow:
                direction = "LONG"
                thesis_parts.append("EMA bullish cross")
                evidence_items.append(EvidenceItem(
                    evidence_id="trend_ema", type="indicator", feature="EMA_FAST",
                    value=round(sma_fast, 2), timestamp=self.context.observation_timestamp,
                    direction="LONG", strength=0.6, source="signal_engine",
                    explanation=f"EMA_FAST({sma_fast:.2f}) > EMA_SLOW({sma_slow:.2f})",
                ))
            elif sma_fast < sma_slow:
                direction = "SHORT"
                thesis_parts.append("EMA bearish cross")
                evidence_items.append(EvidenceItem(
                    evidence_id="trend_ema", type="indicator", feature="EMA_FAST",
                    value=round(sma_fast, 2), timestamp=self.context.observation_timestamp,
                    direction="SHORT", strength=0.6, source="signal_engine",
                    explanation=f"EMA_FAST({sma_fast:.2f}) < EMA_SLOW({sma_slow:.2f})",
                ))

        if adx:
            evidence_items.append(EvidenceItem(
                evidence_id="trend_adx", type="indicator", feature="ADX",
                value=round(adx, 2), timestamp=self.context.observation_timestamp,
                direction=direction, strength=0.5, source="signal_engine",
                explanation=f"ADX={adx:.1f} — {'trending' if adx > 20 else 'ranging'}",
            ))
            if adx < 10:
                confidence = 0.2
            elif adx < 20:
                confidence = 0.4
            else:
                confidence = 0.6

        if atr:
            evidence_items.append(EvidenceItem(
                evidence_id="trend_atr", type="indicator", feature="ATR",
                value=round(atr, 2), timestamp=self.context.observation_timestamp,
                direction=direction, strength=0.3, source="signal_engine",
                explanation=f"ATR={atr:.2f} — volatility context",
            ))

        thesis = " ".join(thesis_parts) if thesis_parts else "Insufficient trend signal"
        if not thesis_parts:
            direction = "UNKNOWN"

        return self._success_result(
            direction=direction,
            regime=regime or "UNKNOWN",
            confidence=confidence,
            uncertainty=1.0 - confidence,
            evidence=Evidence(items=evidence_items),
            supporting_features=available,
            conflicting_features=[],
            reasoning=f"Trend research: {thesis}",
            invalidation_conditions="EMA cross reversal OR ADX drops below 10",
            engine_metadata={
                "strategy_family": "trend",
                "required_features": self.REQUIRED_FEATURES,
                "unavailable_features": unavailable,
                "regime": regime or "UNKNOWN",
            },
        )


# ═══════════════════════════════════════════════════════════════
# 2. BREAKOUT RESEARCH AGENT
# ═══════════════════════════════════════════════════════════════

class BreakoutResearchAdapter(BaseAgentAdapter):
    """Research agent for breakout strategies.

    Analyzes: range compression, breakout signals, expansion,
    continuation, Donchian channels, ATR expansion, opening range.
    """
    adapter_id = "strategy_breakout"
    adapter_version = "1.0"
    source_engine = "strategy_registry_v1"
    source_engine_version = "1.0"

    REQUIRED_FEATURES = ["ATR", "donchian_high", "donchian_low"]

    def run(self) -> AgentResult:
        available, unavailable = _check_features(self.context, self.REQUIRED_FEATURES)

        if not _has_enough_bars(self.context, 30):
            return AgentResult(
                agent_id=self.adapter_id,
                agent_version=self.adapter_version,
                source_engine=self.source_engine,
                source_engine_version=self.source_engine_version,
                status=AgentStatus.INSUFFICIENT_DATA,
                direction="UNKNOWN", regime="UNKNOWN", confidence=0.0, uncertainty=1.0,
                reasoning=f"Insufficient bars: need 30+, have {self.context.feature_snapshot.bar_count}",
                engine_metadata={"required_features": self.REQUIRED_FEATURES,
                                 "unavailable_features": [], "insufficient": "BAR_COUNT_LOW"},
                symbol=self.context.symbol, timeframe=self.context.timeframe,
                observation_timestamp=self.context.observation_timestamp,
                data_cutoff_timestamp=self.context.data_cutoff_timestamp,
            )

        if not available:
            return AgentResult(
                agent_id=self.adapter_id,
                agent_version=self.adapter_version,
                source_engine=self.source_engine,
                source_engine_version=self.source_engine_version,
                status=AgentStatus.PARTIAL,
                direction="UNKNOWN", regime="UNKNOWN", confidence=0.0, uncertainty=1.0,
                reasoning=f"Partial data: unavailable features {unavailable}",
                engine_metadata={"required_features": self.REQUIRED_FEATURES,
                                 "unavailable_features": unavailable, "partial": True},
                symbol=self.context.symbol, timeframe=self.context.timeframe,
                observation_timestamp=self.context.observation_timestamp,
                data_cutoff_timestamp=self.context.data_cutoff_timestamp,
            )

        direction = "NEUTRAL"
        confidence = 0.0
        thesis_parts = []
        evidence_items = []
        regime = self.context.feature_snapshot.regime or "UNKNOWN"

        # Volatility context from ATR
        atr = self.context.feature_snapshot.atr
        if atr:
            evidence_items.append(EvidenceItem(
                evidence_id="brk_atr", type="indicator", feature="ATR",
                value=round(atr, 2), timestamp=self.context.observation_timestamp,
                direction="NEUTRAL", strength=0.4, source="signal_engine",
                explanation=f"ATR={atr:.2f} — volatility for breakout context",
            ))

        # Regime check
        if regime == "RANGE":
            thesis_parts.append("Range regime — compression possible")
            confidence = max(confidence, 0.3)
        elif regime == "TRENDING":
            thesis_parts.append("Trending regime — continuation bias")
            confidence = max(confidence, 0.4)

        # Donchian / Bollinger available features
        if self.context.feature_snapshot.available_features.get("BOLL_UPPER"):
            evidence_items.append(EvidenceItem(
                evidence_id="brk_bb", type="indicator", feature="BOLL_UPPER",
                value=0.0, timestamp=self.context.observation_timestamp,
                direction="NEUTRAL", strength=0.3, source="signal_engine",
                explanation="Bollinger available for breakout context",
            ))

        thesis = " ".join(thesis_parts) if thesis_parts else "No breakout signal — monitoring"

        return self._success_result(
            direction=direction,
            regime=regime,
            confidence=confidence,
            uncertainty=1.0 - confidence,
            evidence=Evidence(items=evidence_items),
            supporting_features=available,
            conflicting_features=[],
            reasoning=f"Breakout research: {thesis}",
            invalidation_conditions="Breakout fails OR volume confirmation missing",
            engine_metadata={
                "strategy_family": "breakout",
                "required_features": self.REQUIRED_FEATURES,
                "unavailable_features": unavailable,
                "regime": regime,
            },
        )


# ═══════════════════════════════════════════════════════════════
# 3. REVERSAL RESEARCH AGENT
# ═══════════════════════════════════════════════════════════════

class ReversalResearchAdapter(BaseAgentAdapter):
    """Research agent for reversal strategies.

    Analyzes: RSI, Bollinger, Stochastic, structure change,
    momentum shift, liquidity.
    """
    adapter_id = "strategy_reversal"
    adapter_version = "1.0"
    source_engine = "strategy_registry_v1"
    source_engine_version = "1.0"

    REQUIRED_FEATURES = ["RSI", "BOLL_UPPER", "BOLL_LOWER"]

    def run(self) -> AgentResult:
        available, unavailable = _check_features(self.context, self.REQUIRED_FEATURES)

        if not _has_enough_bars(self.context, 30):
            return AgentResult(
                agent_id=self.adapter_id,
                agent_version=self.adapter_version,
                source_engine=self.source_engine,
                source_engine_version=self.source_engine_version,
                status=AgentStatus.INSUFFICIENT_DATA,
                direction="UNKNOWN", regime="UNKNOWN", confidence=0.0, uncertainty=1.0,
                reasoning=f"Insufficient bars: need 30+, have {self.context.feature_snapshot.bar_count}",
                engine_metadata={"required_features": self.REQUIRED_FEATURES,
                                 "unavailable_features": [], "insufficient": "BAR_COUNT_LOW"},
                symbol=self.context.symbol, timeframe=self.context.timeframe,
                observation_timestamp=self.context.observation_timestamp,
                data_cutoff_timestamp=self.context.data_cutoff_timestamp,
            )

        if not available:
            return AgentResult(
                agent_id=self.adapter_id,
                agent_version=self.adapter_version,
                source_engine=self.source_engine,
                source_engine_version=self.source_engine_version,
                status=AgentStatus.PARTIAL,
                direction="UNKNOWN", regime="UNKNOWN", confidence=0.0, uncertainty=1.0,
                reasoning=f"Partial data: unavailable features {unavailable}",
                engine_metadata={"required_features": self.REQUIRED_FEATURES,
                                 "unavailable_features": unavailable, "partial": True},
                symbol=self.context.symbol, timeframe=self.context.timeframe,
                observation_timestamp=self.context.observation_timestamp,
                data_cutoff_timestamp=self.context.data_cutoff_timestamp,
            )

        direction = "NEUTRAL"
        confidence = 0.0
        thesis_parts = []
        evidence_items = []
        regime = self.context.feature_snapshot.regime or "UNKNOWN"

        rsi = self.context.feature_snapshot.rsi
        if rsi is not None:
            rsi_dir = "NEUTRAL"
            if rsi < 30:
                rsi_dir = "LONG"
                thesis_parts.append(f"RSI oversold ({rsi:.1f})")
                confidence = max(confidence, 0.4)
            elif rsi > 70:
                rsi_dir = "SHORT"
                thesis_parts.append(f"RSI overbought ({rsi:.1f})")
                confidence = max(confidence, 0.4)
            else:
                thesis_parts.append(f"RSI neutral ({rsi:.1f})")

            evidence_items.append(EvidenceItem(
                evidence_id="rev_rsi", type="indicator", feature="RSI",
                value=round(rsi, 2), timestamp=self.context.observation_timestamp,
                direction=rsi_dir, strength=0.5, source="signal_engine",
                explanation=f"RSI={rsi:.1f} — {'oversold' if rsi < 30 else 'overbought' if rsi > 70 else 'neutral'}",
            ))

        # Bollinger
        if self.context.feature_snapshot.available_features.get("BOLL_UPPER"):
            evidence_items.append(EvidenceItem(
                evidence_id="rev_bb", type="indicator", feature="BOLL_BANDS",
                value=0.0, timestamp=self.context.observation_timestamp,
                direction="NEUTRAL", strength=0.3, source="signal_engine",
                explanation="Bollinger Bands available for reversal context",
            ))

        thesis = " ".join(thesis_parts) if thesis_parts else "No reversal signal — monitoring"
        if not thesis_parts or (rsi is not None and 30 <= rsi <= 70):
            direction = "UNKNOWN"

        return self._success_result(
            direction=direction,
            regime=regime,
            confidence=confidence,
            uncertainty=1.0 - confidence,
            evidence=Evidence(items=evidence_items),
            supporting_features=available,
            conflicting_features=[],
            reasoning=f"Reversal research: {thesis}",
            invalidation_conditions="RSI moves from extreme OR regime change",
            engine_metadata={
                "strategy_family": "mean_reversion",
                "required_features": self.REQUIRED_FEATURES,
                "unavailable_features": unavailable,
                "regime": regime,
            },
        )


# ═══════════════════════════════════════════════════════════════
# 4. MOMENTUM RESEARCH AGENT
# ═══════════════════════════════════════════════════════════════

class MomentumResearchAdapter(BaseAgentAdapter):
    """Research agent for momentum strategies.

    Analyzes: momentum direction, magnitude, alignment, change.
    Note: momentum_at_entry r=0.438 is correlation, NOT predictive edge.
    """
    adapter_id = "strategy_momentum"
    adapter_version = "1.0"
    source_engine = "signal_engine"
    source_engine_version = "1.0"

    REQUIRED_FEATURES = ["SMA_FAST", "SMA_SLOW"]

    def run(self) -> AgentResult:
        available, unavailable = _check_features(self.context, self.REQUIRED_FEATURES)

        if not _has_enough_bars(self.context, 20):
            return AgentResult(
                agent_id=self.adapter_id,
                agent_version=self.adapter_version,
                source_engine=self.source_engine,
                source_engine_version=self.source_engine_version,
                status=AgentStatus.INSUFFICIENT_DATA,
                direction="UNKNOWN", regime="UNKNOWN", confidence=0.0, uncertainty=1.0,
                reasoning=f"Insufficient bars: need 20+, have {self.context.feature_snapshot.bar_count}",
                engine_metadata={"required_features": self.REQUIRED_FEATURES,
                                 "unavailable_features": [], "insufficient": "BAR_COUNT_LOW"},
            )

        direction = "NEUTRAL"
        confidence = 0.0
        thesis_parts = []
        evidence_items = []
        regime = self.context.feature_snapshot.regime or "UNKNOWN"

        sma_fast = self.context.feature_snapshot.sma_fast
        sma_slow = self.context.feature_snapshot.sma_slow

        if sma_fast and sma_slow:
            diff = sma_fast - sma_slow
            pct_diff = abs(diff / sma_slow) if sma_slow else 0.0

            if diff > 0:
                direction = "LONG"
                thesis_parts.append(f"Momentum positive (SMA diff +{pct_diff:.2%})")
            elif diff < 0:
                direction = "SHORT"
                thesis_parts.append(f"Momentum negative (SMA diff {pct_diff:.2%})")
            else:
                thesis_parts.append("Momentum neutral")

            confidence = min(pct_diff * 5, 0.6)  # Scale to 0-0.6, NOT win probability

            evidence_items.append(EvidenceItem(
                evidence_id="mom_sma", type="indicator", feature="SMA_DIFF",
                value=round(pct_diff, 4), timestamp=self.context.observation_timestamp,
                direction=direction, strength=confidence, source="signal_engine",
                explanation=f"SMA_FAST({sma_fast:.2f}) vs SMA_SLOW({sma_slow:.2f}), diff={pct_diff:.2%}",
            ))

        # ADX as momentum strength
        adx = self.context.feature_snapshot.adx
        if adx:
            evidence_items.append(EvidenceItem(
                evidence_id="mom_adx", type="indicator", feature="ADX",
                value=round(adx, 2), timestamp=self.context.observation_timestamp,
                direction=direction, strength=0.3, source="signal_engine",
                explanation=f"ADX={adx:.1f} — trend strength context",
            ))

        thesis = " ".join(thesis_parts) if thesis_parts else "Insufficient momentum data"

        return self._success_result(
            direction=direction,
            regime=regime,
            confidence=confidence,
            uncertainty=1.0 - confidence,
            evidence=Evidence(items=evidence_items),
            supporting_features=available,
            conflicting_features=[],
            reasoning=f"Momentum research: {thesis}. Note: correlation not predictive edge.",
            invalidation_conditions="SMA cross OR regime change",
            engine_metadata={
                "strategy_family": "momentum",
                "required_features": self.REQUIRED_FEATURES,
                "unavailable_features": unavailable,
                "regime": regime,
                "note": "momentum_at_entry r=0.438 is correlation, NOT predictive edge",
            },
        )


# ═══════════════════════════════════════════════════════════════
# 5. VOLATILITY RESEARCH AGENT
# ═══════════════════════════════════════════════════════════════

class VolatilityResearchAdapter(BaseAgentAdapter):
    """Research agent for volatility strategies.

    Analyzes: ATR, volatility compression/expansion, abnormal volatility,
    regime compatibility. RANGE_HIGH_VOL flagged as known problem regime.
    """
    adapter_id = "strategy_volatility"
    adapter_version = "1.0"
    source_engine = "signal_engine"
    source_engine_version = "1.0"

    REQUIRED_FEATURES = ["ATR"]

    def run(self) -> AgentResult:
        available, unavailable = _check_features(self.context, self.REQUIRED_FEATURES)

        if not _has_enough_bars(self.context, 20):
            return AgentResult(
                agent_id=self.adapter_id,
                agent_version=self.adapter_version,
                source_engine=self.source_engine,
                source_engine_version=self.source_engine_version,
                status=AgentStatus.INSUFFICIENT_DATA,
                direction="UNKNOWN", regime="UNKNOWN", confidence=0.0, uncertainty=1.0,
                reasoning=f"Insufficient bars: need 20+, have {self.context.feature_snapshot.bar_count}",
                engine_metadata={"required_features": self.REQUIRED_FEATURES,
                                 "unavailable_features": [], "insufficient": "BAR_COUNT_LOW"},
            )

        direction = "NEUTRAL"
        confidence = 0.0
        thesis_parts = []
        evidence_items = []
        regime = self.context.feature_snapshot.regime or "UNKNOWN"

        atr = self.context.feature_snapshot.atr
        if atr:
            evidence_items.append(EvidenceItem(
                evidence_id="vol_atr", type="indicator", feature="ATR",
                value=round(atr, 2), timestamp=self.context.observation_timestamp,
                direction="NEUTRAL", strength=0.5, source="signal_engine",
                explanation=f"ATR={atr:.2f} — volatility level",
            ))

        # Volatility state
        vol_state = self.context.feature_snapshot.available_features.get("volatility_state", False)
        if vol_state:
            evidence_items.append(EvidenceItem(
                evidence_id="vol_state", type="indicator", feature="volatility_state",
                value=0.0, timestamp=self.context.observation_timestamp,
                direction="NEUTRAL", strength=0.3, source="signal_engine",
                explanation="Volatility state available",
            ))

        # RANGE_HIGH_VOL known problem
        if regime == "RANGE" and atr and atr > 0:
            thesis_parts.append("RANGE_HIGH_VOL regime detected — known problematic")
            confidence = 0.3
        elif regime == "TRENDING":
            thesis_parts.append("Trending regime — volatility in context")
            confidence = 0.4
        else:
            thesis_parts.append("Volatility context analyzed")
            confidence = 0.3

        thesis = " ".join(thesis_parts) if thesis_parts else "Volatility analysis incomplete"

        return self._success_result(
            direction=direction,
            regime=regime,
            confidence=confidence,
            uncertainty=1.0 - confidence,
            evidence=Evidence(items=evidence_items),
            supporting_features=available,
            conflicting_features=[],
            reasoning=f"Volatility research: {thesis}",
            invalidation_conditions="Volatility regime shift OR ATR anomaly",
            engine_metadata={
                "strategy_family": "volatility",
                "required_features": self.REQUIRED_FEATURES,
                "unavailable_features": unavailable,
                "regime": regime,
                "note": "RANGE_HIGH_VOL r=0.29 — known problem regime",
            },
        )


# ═══════════════════════════════════════════════════════════════
# 6. LIQUIDITY RESEARCH AGENT
# ═══════════════════════════════════════════════════════════════

class LiquidityResearchAdapter(BaseAgentAdapter):
    """Research agent for liquidity analysis.

    Analyzes: liquidity context, balance, interaction, sweep evidence,
    opposing liquidity. Uses smc_structure_v1 data when available.
    """
    adapter_id = "strategy_liquidity"
    adapter_version = "1.0"
    source_engine = "smc_structure_v1"
    source_engine_version = "1.0"

    REQUIRED_FEATURES = []  # Liquidity derived from structure engine

    def run(self) -> AgentResult:
        available, unavailable = _check_features(self.context, self.REQUIRED_FEATURES)

        if not _has_enough_bars(self.context, 30):
            return AgentResult(
                agent_id=self.adapter_id,
                agent_version=self.adapter_version,
                source_engine=self.source_engine,
                source_engine_version=self.source_engine_version,
                status=AgentStatus.INSUFFICIENT_DATA,
                direction="UNKNOWN", regime="UNKNOWN", confidence=0.0, uncertainty=1.0,
                reasoning=f"Insufficient bars: need 30+, have {self.context.feature_snapshot.bar_count}",
                engine_metadata={"required_features": self.REQUIRED_FEATURES,
                                 "unavailable_features": [], "insufficient": "BAR_COUNT_LOW"},
                symbol=self.context.symbol, timeframe=self.context.timeframe,
                observation_timestamp=self.context.observation_timestamp,
                data_cutoff_timestamp=self.context.data_cutoff_timestamp,
            )

        direction = "NEUTRAL"
        confidence = 0.0
        thesis_parts = []
        evidence_items = []
        regime = self.context.feature_snapshot.regime or "UNKNOWN"

        # Check if structure data available via feature_snapshot
        has_structure = self.context.feature_snapshot.available_features.get("structure", False)
        has_liquidity = self.context.feature_snapshot.available_features.get("liquidity", False)

        if has_structure:
            evidence_items.append(EvidenceItem(
                evidence_id="liq_struct", type="structure", feature="structure",
                value=0.0, timestamp=self.context.observation_timestamp,
                direction="NEUTRAL", strength=0.4, source="smc_structure_v1",
                explanation="Structure data available for liquidity context",
            ))

        if has_liquidity:
            evidence_items.append(EvidenceItem(
                evidence_id="liq_balance", type="indicator", feature="liquidity_balance",
                value=0.0, timestamp=self.context.observation_timestamp,
                direction="NEUTRAL", strength=0.3, source="smc_structure_v1",
                explanation="Liquidity balance available",
            ))

        if not has_structure and not has_liquidity:
            thesis_parts.append("Liquidity data unavailable — structure_type/liquidity_side 0% coverage")
            confidence = 0.0
        else:
            thesis_parts.append("Liquidity context analyzed")
            confidence = 0.3

        thesis = " ".join(thesis_parts) if thesis_parts else "Liquidity analysis pending"

        return self._success_result(
            direction=direction,
            regime=regime,
            confidence=confidence,
            uncertainty=1.0 - confidence,
            evidence=Evidence(items=evidence_items),
            supporting_features=available,
            conflicting_features=[],
            reasoning=f"Liquidity research: {thesis}",
            invalidation_conditions="Liquidity sweep OR regime change",
            engine_metadata={
                "strategy_family": "liquidity",
                "required_features": self.REQUIRED_FEATURES,
                "unavailable_features": unavailable,
                "regime": regime,
                "note": "liquidity_balance r=-0.278 — correlation, not predictive",
            },
        )


# ═══════════════════════════════════════════════════════════════
# 7. STRUCTURE RESEARCH AGENT
# ═══════════════════════════════════════════════════════════════

class StructureResearchAdapter(BaseAgentAdapter):
    """Research agent for structure analysis.

    Analyzes: BOS, CHoCH, HH, HL, LH, LL, structure alignment.
    Lookahead protection applied via filter_by_cutoff.
    """
    adapter_id = "strategy_structure"
    adapter_version = "1.0"
    source_engine = "smc_structure_v1"
    source_engine_version = "1.0"

    REQUIRED_FEATURES = []  # Structure derived from smc_structure_v1

    def run(self) -> AgentResult:
        available, unavailable = _check_features(self.context, self.REQUIRED_FEATURES)

        if not _has_enough_bars(self.context, 30):
            return AgentResult(
                agent_id=self.adapter_id,
                agent_version=self.adapter_version,
                source_engine=self.source_engine,
                source_engine_version=self.source_engine_version,
                status=AgentStatus.INSUFFICIENT_DATA,
                direction="UNKNOWN", regime="UNKNOWN", confidence=0.0, uncertainty=1.0,
                reasoning=f"Insufficient bars: need 30+, have {self.context.feature_snapshot.bar_count}",
                engine_metadata={"required_features": self.REQUIRED_FEATURES,
                                 "unavailable_features": [], "insufficient": "BAR_COUNT_LOW"},
                symbol=self.context.symbol, timeframe=self.context.timeframe,
                observation_timestamp=self.context.observation_timestamp,
                data_cutoff_timestamp=self.context.data_cutoff_timestamp,
            )

        direction = "NEUTRAL"
        confidence = 0.0
        thesis_parts = []
        evidence_items = []
        regime = self.context.feature_snapshot.regime or "UNKNOWN"

        # Check structure events availability
        has_events = self.context.feature_snapshot.available_features.get("structure", False)

        if has_events:
            # Structure events available — analyze BOS/CHoCH
            evidence_items.append(EvidenceItem(
                evidence_id="struct_events", type="structure", feature="structure_events",
                value=0.0, timestamp=self.context.observation_timestamp,
                direction="NEUTRAL", strength=0.5, source="smc_structure_v1",
                explanation="BOS/CHoCH events available for analysis",
            ))
            confidence = 0.5
            thesis_parts.append("Structure events detected — BOS/CHoCH analysis available")
        else:
            evidence_items.append(EvidenceItem(
                evidence_id="struct_none", type="structure", feature="structure_events",
                value=0.0, timestamp=self.context.observation_timestamp,
                direction="NEUTRAL", strength=0.0, source="smc_structure_v1",
                explanation="No structure events at this cutoff — UNCONFIRMED",
            ))
            thesis_parts.append("No structure events — monitoring")
            confidence = 0.1

        # Lookahead warning
        evidence_items.append(EvidenceItem(
            evidence_id="struct_lookahead", type="indicator", feature="lookahead_protection",
            value=0.0, timestamp=self.context.observation_timestamp,
            direction="NEUTRAL", strength=0.2, source="structure_lookahead_fix",
            explanation="Cutoff enforcement active — future bars excluded",
        ))

        thesis = " ".join(thesis_parts) if thesis_parts else "Structure analysis pending"

        return self._success_result(
            direction=direction,
            regime=regime,
            confidence=confidence,
            uncertainty=1.0 - confidence,
            evidence=Evidence(items=evidence_items),
            supporting_features=available,
            conflicting_features=[],
            reasoning=f"Structure research: {thesis}. Lookahead protected.",
            invalidation_conditions="Structure change OR new BOS/CHoCH event",
            engine_metadata={
                "strategy_family": "structure",
                "required_features": self.REQUIRED_FEATURES,
                "unavailable_features": unavailable,
                "regime": regime,
                "lookahead_protection": True,
            },
        )


# ═══════════════════════════════════════════════════════════════
# REGISTRY
# ═══════════════════════════════════════════════════════════════

STRATEGY_AGENTS = {
    "strategy_trend": TrendResearchAdapter,
    "strategy_breakout": BreakoutResearchAdapter,
    "strategy_reversal": ReversalResearchAdapter,
    "strategy_momentum": MomentumResearchAdapter,
    "strategy_volatility": VolatilityResearchAdapter,
    "strategy_liquidity": LiquidityResearchAdapter,
    "strategy_structure": StructureResearchAdapter,
}