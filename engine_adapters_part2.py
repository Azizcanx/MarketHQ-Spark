# -*- coding: utf-8 -*-
"""
MarketHQ Engine Adapters V1 — Part 2
=======================================

Additional adapters:
  E. StrategyAdapter         — strategy_registry_v1.py → AgentResult
  F. SetupAdapter            — setup_engine_v1.py → AgentResult
  G. QualityAdapter          — setup_quality_engine_v4.py → AgentResult
  H. HistoricalEvidenceAdapter — setup_outcome_tracker.py → AgentResult
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from agent_contract import (
    AgentResult, AgentStatus, Claim, ClaimStatus,
    Evidence, EvidenceItem, MarketContext, BaseAgentAdapter,
)


# =========================================================
# E. STRATEGY ADAPTER
# =========================================================

class StrategyAdapter(BaseAgentAdapter):
    """Adapter: strategy_registry_v1.py → AgentResult.

    Runs all strategies and returns agreement summary.
    Same feature → not independent evidence (correlation warning).
    """

    adapter_id = "strategy"
    adapter_version = "v1"
    source_engine = "strategy_registry_v1"
    source_engine_version = "v1"

    def run(self) -> AgentResult:
        ctx = self.context
        ohlcv = ctx.ohlcv_ref

        if ohlcv is None or ohlcv.empty:
            return self._error_result("NO_DATA", "No OHLCV data for strategy analysis")

        try:
            from strategy_registry_v1 import run_all_strategies_df, agreement_summary
            from signal_engine import DEFAULT_CONFIG

            enriched = ohlcv.copy()
            strategies = run_all_strategies_df(enriched, DEFAULT_CONFIG)
            agreement = agreement_summary(strategies)

            # Collect evidence
            items = []
            supporting = []
            conflicting = []

            for sdata in strategies:
                sid = sdata.get("strategy_id", "unknown")
                direction = sdata.get("direction", "NEUTRAL")
                confidence = float(sdata.get("confidence", 0.0))
                items.append(EvidenceItem(
                    evidence_id=f"strategy_{sid}",
                    type="strategy",
                    feature=f"strategy_{sid}",
                    value=confidence,
                    timestamp=ctx.observation_timestamp,
                    data_cutoff_timestamp=ctx.data_cutoff_timestamp,
                    direction=direction,
                    strength=min(confidence, 1.0),
                    source="strategy_registry_v1",
                    explanation=f"{sid}: {direction} (conf={confidence:.2f})",
                ))
                if direction != "NEUTRAL":
                    supporting.append(f"{sid}:{direction}")

            # Check for conflicts
            directions = [s.get("direction", "NEUTRAL") for s in strategies.values()]
            long_count = sum(1 for d in directions if d == "LONG")
            short_count = sum(1 for d in directions if d == "SHORT")
            if long_count > 0 and short_count > 0:
                conflicting.append(f"conflict:{long_count}LONG vs {short_count}SHORT")

            # Claims
            claims = [Claim(
                claim_id=f"strategy_agreement_{ctx.symbol}_{ctx.timeframe}",
                statement=f"Strategy agreement: {agreement.get('agreement', 'unknown')}",
                source_agent=self.adapter_id,
                source_agent_version=self.adapter_version,
                observation_timestamp=ctx.observation_timestamp,
                data_cutoff_timestamp=ctx.data_cutoff_timestamp,
                evidence_refs=[f"agreement:{agreement.get('agreement', 'unknown')}"],
                validation_status=ClaimStatus.UNTESTED,
                feature="strategy_agreement",
                timeframe=ctx.timeframe,
                symbol=ctx.symbol,
            )]

            return self._success_result(
                direction=agreement.get("dominant_direction", "NEUTRAL"),
                regime="",
                confidence=float(agreement.get("agreement_score", 0.0)),
                uncertainty=round(1.0 - float(agreement.get("agreement_score", 0.0)), 2),
                evidence=Evidence(items=items, observation_timestamp=ctx.observation_timestamp,
                                  data_cutoff_timestamp=ctx.data_cutoff_timestamp),
                supporting_features=supporting,
                conflicting_features=conflicting,
                claims=claims,
                reasoning=f"Strategies: {len(strategies)}, agreement={agreement.get('agreement', 'unknown')}, "
                          f"dominant={agreement.get('dominant_direction', 'NEUTRAL')}",
                engine_metadata={
                    "strategy_count": len(strategies),
                    "agreement": agreement,
                    "long_count": long_count,
                    "short_count": short_count,
                },
            )
        except Exception as exc:
            return self._error_result("STRATEGY_ERROR", str(exc))


# =========================================================
# F. SETUP ADAPTER
# =========================================================

class SetupAdapter(BaseAgentAdapter):
    """Adapter: setup_engine_v1.py / research_setup_engine.py → AgentResult.

    Generates a setup from the current OHLCV data.
    Wraps build_setup() / build_research_setup().
    """

    adapter_id = "setup"
    adapter_version = "v1"
    source_engine = "setup_engine_v1"
    source_engine_version = "v1"

    def run(self) -> AgentResult:
        ctx = self.context
        ohlcv = ctx.ohlcv_ref

        if ohlcv is None or ohlcv.empty:
            return self._error_result("NO_DATA", "No OHLCV data for setup generation")

        try:
            from setup_engine_v1 import build_setup, detect_regime

            last = ohlcv.iloc[-1]
            regime_result = detect_regime(last, ohlcv)
            setup = build_setup(ohlcv)

            regime = regime_result.get("regime", "UNKNOWN")
            confidence = float(regime_result.get("confidence", 0.0))

            # Claims
            claims = []
            if setup and setup.get("setup_type"):
                claims.append(Claim(
                    claim_id=f"setup_type_{ctx.symbol}_{ctx.timeframe}",
                    statement=f"Setup type: {setup['setup_type']}, regime={regime}",
                    source_agent=self.adapter_id,
                    source_agent_version=self.adapter_version,
                    observation_timestamp=ctx.observation_timestamp,
                    data_cutoff_timestamp=ctx.data_cutoff_timestamp,
                    evidence_refs=[f"setup:{setup.get('setup_type','')}"],
                    validation_status=ClaimStatus.UNTESTED,
                    feature="setup_type",
                    regime=regime,
                    timeframe=ctx.timeframe,
                    symbol=ctx.symbol,
                ))

            return self._success_result(
                direction=setup.get("direction", "NEUTRAL") if setup else "NEUTRAL",
                regime=regime,
                confidence=confidence,
                uncertainty=round(1.0 - confidence, 2),
                claims=claims,
                reasoning=f"Setup: {setup.get('setup_type', 'unknown') if setup else 'none'}, "
                          f"regime={regime}, entry={setup.get('entry_zone', {}).get('center', 'N/A') if setup else 'N/A'}",
                invalidation_conditions=(
                    f"Invalidation: {setup['invalidation']}" if setup and setup.get("invalidation") else ""
                ),
                engine_metadata={
                    "setup_type": setup.get("setup_type", "") if setup else "",
                    "regime_detail": regime_result.get("detail", ""),
                    "entry_zone": str(setup.get("entry_zone", {})) if setup else "",
                    "target": str(setup.get("target", {})) if setup else "",
                },
            )
        except Exception as exc:
            return self._error_result("SETUP_ERROR", str(exc))


# =========================================================
# G. QUALITY ADAPTER
# =========================================================

class QualityAdapter(BaseAgentAdapter):
    """Adapter: setup_quality_engine_v4.py → AgentResult.

    Computes quality score for a setup.
    Does NOT interpret quality as win probability.
    """

    adapter_id = "quality"
    adapter_version = "v1"
    source_engine = "setup_quality_engine_v4"
    source_engine_version = "v1"

    def run(self) -> AgentResult:
        ctx = self.context
        ohlcv = ctx.ohlcv_ref

        if ohlcv is None or ohlcv.empty:
            return self._error_result("NO_DATA", "No OHLCV data for quality scoring")

        try:
            from setup_engine_v1 import build_setup, detect_regime
            from setup_quality_engine_v4 import score_setup_quality_v4 as score_setup_quality
            from setup_object_model import SetupModel, MarketInfo, TimeframeInfo, RegimeInfo
            from setup_object_model import BiasInfo, StructureInfo, LiquidityInfo
            from setup_object_model import EntryZone, Confirmation, InvalidationLevel, TargetLevel, Targets
            from setup_object_model import RiskReward, Evidence as ModelEvidence, HistoricalValidation
            from setup_object_model import InvalidationConditions, LearningMetadata

            # Build minimal SetupModel for quality scoring
            last = ohlcv.iloc[-1]
            regime_result = detect_regime(last, ohlcv)
            raw_setup = build_setup(ohlcv)

            if raw_setup is None:
                return self._error_result("NO_SETUP", "No setup generated for quality scoring")

            # Convert raw setup to SetupModel (minimal)
            setup_model = SetupModel(
                market=MarketInfo(symbol=ctx.symbol, market="BIST"),
                timeframe=TimeframeInfo(timeframe=ctx.timeframe),
                regime=RegimeInfo(regime=regime_result.get("regime", "UNKNOWN")),
                bias=BiasInfo(),
                structure=StructureInfo(),
                liquidity=LiquidityInfo(),
                setup_type=raw_setup.get("setup_type", "unknown"),
                entry_zone=EntryZone(
                    center=float(raw_setup.get("entry_price", 0) or 0),
                    low=float(raw_setup.get("entry_zone", {}).get("low", 0) or 0),
                    high=float(raw_setup.get("entry_zone", {}).get("high", 0) or 0),
                ) if raw_setup.get("entry_zone") else EntryZone(),
                confirmation=Confirmation(),
                invalidation=InvalidationLevel(
                    price=float(raw_setup.get("invalidation_price", 0) or 0),
                ) if raw_setup.get("invalidation_price") else InvalidationLevel(),
                targets=Targets(primary=TargetLevel(
                    price=float(raw_setup.get("target_price", 0) or 0),
                ) if raw_setup.get("target_price") else None),
                risk_reward=RiskReward(),
                evidence=ModelEvidence(),
                historical_validation=HistoricalValidation(),
                quality=score_setup_quality(SetupModel()),  # placeholder
                reasoning=Reasoning() if False else None,  # will be set below
                invalidation_conditions=InvalidationConditions(),
                learning_metadata=LearningMetadata(),
                generated_at=ctx.observation_timestamp,
                engine="setup_engine_v1",
                version="v1",
            )

            quality_score = score_setup_quality(setup_model)

            # Claims
            claims = [Claim(
                claim_id=f"quality_{ctx.symbol}_{ctx.timeframe}",
                statement=f"Quality score: {quality_score.overall:.2f}",
                source_agent=self.adapter_id,
                source_agent_version=self.adapter_version,
                observation_timestamp=ctx.observation_timestamp,
                data_cutoff_timestamp=ctx.data_cutoff_timestamp,
                evidence_refs=[f"quality:{quality_score.overall:.2f}"],
                validation_status=ClaimStatus.UNTESTED,
                feature="quality_score",
                regime=regime_result.get("regime", "UNKNOWN"),
                timeframe=ctx.timeframe,
                symbol=ctx.symbol,
            )]

            return self._success_result(
                direction=setup_model.bias.direction if setup_model.bias else "NEUTRAL",
                regime=regime_result.get("regime", "UNKNOWN"),
                confidence=quality_score.overall,
                uncertainty=round(1.0 - quality_score.overall, 2),
                claims=claims,
                reasoning=f"Quality V4 score: {quality_score.overall:.2f}, "
                          f"breakdown: {quality_score.breakdown}",
                engine_metadata={
                    "quality_score": quality_score.overall,
                    "breakdown": quality_score.breakdown,
                    "confidence": quality_score.sample_size_confidence_score,
                    "flags": quality_score.flags,
                    "feature_usage": quality_score.feature_usage,
                },
            )
        except Exception as exc:
            return self._error_result("QUALITY_ERROR", str(exc))


# =========================================================
# H. HISTORICAL EVIDENCE ADAPTER
# =========================================================

class HistoricalEvidenceAdapter(BaseAgentAdapter):
    """Adapter: setup_outcome_tracker.py → AgentResult.

    Queries historical setup outcomes for similar setups.
    Never fabricates — returns what the DB has.
    """

    adapter_id = "historical_evidence"
    adapter_version = "v1"
    source_engine = "setup_outcome_tracker"
    source_engine_version = "v1"

    def run(self) -> AgentResult:
        ctx = self.context

        try:
            from setup_outcome_tracker import get_historical_stats

            stats = get_historical_stats(ctx.symbol, ctx.timeframe)

            items = []
            if stats:
                items.append(EvidenceItem(
                    evidence_id=f"hist_{ctx.symbol}_{ctx.timeframe}",
                    type="historical",
                    feature="historical_stats",
                    value=float(stats.get("win_rate", 0) or 0),
                    timestamp=ctx.observation_timestamp,
                    data_cutoff_timestamp=ctx.data_cutoff_timestamp,
                    direction="NEUTRAL",
                    strength=min(float(stats.get("win_rate", 0) or 0) * 2, 1.0),
                    source="setup_outcome_tracker",
                    explanation=f"Win rate: {stats.get('win_rate', 0):.1%}, "
                                f"avg R: {stats.get('avg_r', 0):.2f}, "
                                f"sample: {stats.get('sample_size', 0)}",
                ))

            evidence = Evidence(
                items=items,
                observation_timestamp=ctx.observation_timestamp,
                data_cutoff_timestamp=ctx.data_cutoff_timestamp,
            )

            # Claims
            claims = []
            if stats and stats.get("sample_size", 0) >= 10:
                claims.append(Claim(
                    claim_id=f"hist_evidence_{ctx.symbol}_{ctx.timeframe}",
                    statement=f"Historical win rate: {stats.get('win_rate', 0):.1%} "
                              f"(n={stats.get('sample_size', 0)})",
                    source_agent=self.adapter_id,
                    source_agent_version=self.adapter_version,
                    observation_timestamp=ctx.observation_timestamp,
                    data_cutoff_timestamp=ctx.data_cutoff_timestamp,
                    evidence_refs=[f"historical:{ctx.symbol}:{ctx.timeframe}"],
                    validation_status=ClaimStatus.UNTESTED,
                    feature="historical_win_rate",
                    timeframe=ctx.timeframe,
                    symbol=ctx.symbol,
                    sample_size=stats.get("sample_size", 0),
                ))

            return self._success_result(
                direction="NEUTRAL",
                regime="",
                confidence=float(stats.get("win_rate", 0) or 0) if stats else 0.0,
                uncertainty=0.5 if (stats and stats.get("sample_size", 0) < 30) else 0.3,
                evidence=evidence,
                reasoning=f"Historical: sample={stats.get('sample_size', 0) if stats else 0}, "
                          f"win_rate={stats.get('win_rate', 0) if stats else 0:.1%}, "
                          f"avg_r={stats.get('avg_r', 0) if stats else 0:.2f}" if stats else "No historical data",
                engine_metadata={
                    "stats": stats or {},
                    "sample_size": stats.get("sample_size", 0) if stats else 0,
                    "win_rate": stats.get("win_rate", 0) if stats else 0,
                    "avg_r": stats.get("avg_r", 0) if stats else 0,
                },
                claims=claims,
            )
        except Exception as exc:
            return self._error_result("HISTORICAL_ERROR", str(exc))