# -*- coding: utf-8 -*-
"""
MarketHQ Setup Backtest Engine V1
===================================

Rolling-window setup generation + bar-by-bar execution simulation.
Research-only — no live trading, no broker orders.

Flow:
  1. For each bar i (from lookback to end-1):
     a. Generate setup using df.iloc[:i+1]   ← NO future data
     b. If LONG/SHORT: simulate execution on future bars i+1..end
     c. Record outcome in setup_outcomes DB
  2. Compute portfolio metrics
  3. Compute quality correlation

Look-ahead bias prevention:
  - Setup at bar i uses ONLY bars 0..i
  - Execution simulation uses bars i+1..end
  - Indicators computed on rolling window (no forward fill)

Entry / Exit rules:
  - Entry: future bar's Close enters entry_zone [low, high]
  - Stop:  LONG → Low <= invalidation | SHORT → High >= invalidation
  - Target: LONG → High >= target | SHORT → Low <= target
  - Same bar: stop AND target hit → outcome = "ambiguous"
  - Entry never triggered → outcome = "open" (unresolved)

Quality correlation:
  - quality bucket → sample count → win rate → expectancy → avg R
  - Pearson correlation quality vs R

Monte Carlo:
  - NOT implemented (synthetic OHLC avoided — see TODO)
  - Real historical block bootstrap → TODO for Phase 2
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from signal_engine import DEFAULT_CONFIG
from research_setup_engine import build_research_setup, detect_regime
from setup_quality_engine_v2 import score_setup_quality_v2 as score_setup_quality
from setup_object_model import (
    SetupModel, MarketInfo, TimeframeInfo, RegimeInfo, BiasInfo,
    StructureInfo, LiquidityInfo, EntryZone, Confirmation,
    InvalidationLevel, TargetLevel, Targets, RiskReward,
    Evidence, HistoricalValidation, QualityScore, Reasoning,
    InvalidationConditions, LearningMetadata,
)
from setup_outcome_tracker import record_outcome, ensure_table


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

BACKTEST_DEFAULTS = {
    "min_bars": 60,
    "step": 4,               # generate setup every N bars
    "max_wait_bars": 0,      # 0 = wait until end of data for entry
    "data_source": "yfinance",
}


# ---------------------------------------------------------------------------
# Result dataclasses
# ---------------------------------------------------------------------------

@dataclass
class TradeResult:
    setup_id: str = ""
    symbol: str = ""
    timeframe: str = ""
    setup_type: str = ""
    regime: str = ""
    direction: str = ""
    entry_price: float = 0.0
    invalidation: float = 0.0
    target: float = 0.0
    atr: float = 0.0
    atr_pct: float = 0.0
    quality_score: float = 0.0
    quality_breakdown: dict[str, float] = field(default_factory=dict)
    outcome: str = "open"
    exit_price: float = 0.0
    exit_reason: str = ""
    pnl_pct: float = 0.0
    r_multiple: float = 0.0
    bars_to_entry: int = 0
    bars_to_exit: int = 0
    mfe: float = 0.0
    mae: float = 0.0
    target_reached: bool = False
    invalidated: bool = False
    unresolved: bool = False
    generated_at_idx: int = 0
    entry_idx: int = 0
    exit_idx: int = 0
    # Regime filter fields
    regime_filter_status: str = ""
    regime_compatibility: float = 0.0
    regime_reason: str = ""
    zone_width_atr: float = 0.0
    touches: int = 0
    structure_type: str = ""
    liquidity_side: str = ""


@dataclass
class PortfolioMetrics:
    total_trades: int = 0
    hit_target: int = 0
    hit_invalidation: int = 0
    open_unresolved: int = 0
    ambiguous: int = 0
    win_rate: float = 0.0
    avg_r: float = 0.0
    expectancy: float = 0.0
    profit_factor: float = 0.0
    cumulative_r: float = 0.0
    max_drawdown: float = 0.0
    sharpe_ratio: float = 0.0
    consecutive_wins: int = 0
    consecutive_losses: int = 0
    max_consecutive_wins: int = 0
    max_consecutive_losses: int = 0
    avg_bars_to_entry: float = 0.0
    avg_bars_to_exit: float = 0.0
    quality_correlation: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Core helpers
# ---------------------------------------------------------------------------

def _entry_zone(setup: dict[str, Any]) -> tuple[float, float]:
    zone = setup.get("entry_zone", [0, 0])
    if isinstance(zone, list) and len(zone) == 2:
        return float(zone[0]), float(zone[1])
    entry = float(setup.get("entry_price", 0))
    atr_v = float(setup.get("atr", 0)) or 1.0
    return entry - 0.25 * atr_v, entry + 0.25 * atr_v


def _check_entry(direction: str, close: float, z_low: float, z_high: float) -> bool:
    return z_low <= close <= z_high


def _check_exit(
    direction: str,
    high: float, low: float,
    invalidation: float, target: float,
) -> tuple[str, bool]:
    if direction == "LONG":
        stop_hit = low <= invalidation
        tgt_hit = high >= target
    else:
        stop_hit = high >= invalidation
        tgt_hit = low <= target

    if stop_hit and tgt_hit:
        return "ambiguous", True
    if stop_hit:
        return "stop_hit", False
    if tgt_hit:
        return "target_hit", False
    return "", False


def _compute_excursion(
    direction: str,
    entry_price: float,
    invalidation: float,
    target: float,
    bars_high: list[float],
    bars_low: list[float],
) -> tuple[float, float]:
    if direction == "LONG":
        dist = abs(target - invalidation)
        if dist == 0:
            return 0.0, 0.0
        moves = [(h - entry_price) / dist for h in bars_high]
        adverse = [(entry_price - l) / dist for l in bars_low]
    else:
        dist = abs(invalidation - target)
        if dist == 0:
            return 0.0, 0.0
        moves = [(entry_price - l) / dist for l in bars_low]
        adverse = [(h - entry_price) / dist for h in bars_high]

    mfe = max(moves) if moves else 0.0
    mae = max(adverse) if adverse else 0.0
    return round(mfe, 4), round(mae, 4)


# ---------------------------------------------------------------------------
# Single trade simulation
# ---------------------------------------------------------------------------

def _simulate_trade(
    setup: dict[str, Any],
    future_df: pd.DataFrame,
    generated_at_idx: int,
    max_wait_bars: int = 0,
) -> TradeResult:
    direction = setup.get("direction", "NO_CONSENSUS")
    if direction not in ("LONG", "SHORT"):
        return TradeResult(
            setup_id=setup.get("setup_id", ""),
            outcome="open",
            exit_reason="no_direction",
            unresolved=True,
            generated_at_idx=generated_at_idx,
        )

    entry_price = float(setup.get("entry_price", 0))
    invalidation = float(setup.get("invalidation", 0))
    target = float(setup.get("target", 0))
    atr = float(setup.get("atr", 0)) or 1.0
    zone_low, zone_high = _entry_zone(setup)

    rr_dist = abs(target - entry_price)
    risk_dist = abs(entry_price - invalidation)

    result = TradeResult(
        setup_id=setup.get("setup_id", ""),
        symbol=setup.get("symbol", ""),
        timeframe=setup.get("timeframe", ""),
        setup_type=setup.get("setup_type", "manual"),
        regime=setup.get("regime", ""),
        direction=direction,
        entry_price=entry_price,
        invalidation=invalidation,
        target=target,
        atr=atr,
        atr_pct=setup.get("atr_pct", 0.0),
        quality_score=setup.get("quality_score", 0.0),
        quality_breakdown=setup.get("quality_breakdown", {}),
        generated_at_idx=generated_at_idx,
        zone_width_atr=setup.get("zone_width_atr", 0.0),
        touches=setup.get("touches", 0),
        structure_type=setup.get("structure_type", ""),
        liquidity_side=setup.get("liquidity_side", ""),
        regime_filter_status=setup.get("regime_filter_status", ""),
        regime_compatibility=setup.get("regime_compatibility", 0.0),
        regime_reason=setup.get("regime_reason", ""),
    )

    # --- Wait for entry ---
    entry_bar_idx = -1
    for i, (_, bar) in enumerate(future_df.iterrows()):
        if max_wait_bars and i >= max_wait_bars:
            break
        close = float(bar.get("Close", 0))
        if _check_entry(direction, close, zone_low, zone_high):
            entry_bar_idx = i
            result.entry_price = close
            result.bars_to_entry = i + 1
            break

    if entry_bar_idx == -1:
        result.outcome = "open"
        result.exit_reason = "expired"
        result.unresolved = True
        result.bars_to_exit = len(future_df)
        return result

    result.entry_idx = generated_at_idx + entry_bar_idx + 1

    # --- After entry: track stop/target ---
    post_entry = future_df.iloc[entry_bar_idx + 1:]
    bars_high: list[float] = []
    bars_low: list[float] = []

    for j, (_, bar) in enumerate(post_entry.iterrows()):
        high = float(bar.get("High", 0))
        low = float(bar.get("Low", 0))
        bars_high.append(high)
        bars_low.append(low)

        exit_reason, ambiguous = _check_exit(
            direction, high, low, invalidation, target,
        )

        if exit_reason:
            result.bars_to_exit = j + 1
            result.exit_idx = generated_at_idx + entry_bar_idx + 1 + j

            if ambiguous:
                result.outcome = "ambiguous"
                result.exit_reason = "ambiguous"
                result.unresolved = True
                mid = (invalidation + target) / 2
                if direction == "LONG":
                    result.pnl_pct = ((mid - result.entry_price) / result.entry_price) * 100
                else:
                    result.pnl_pct = ((result.entry_price - mid) / result.entry_price) * 100
                result.r_multiple = 0.0
            elif exit_reason == "target_hit":
                result.outcome = "hit_target"
                result.exit_reason = "target_hit"
                result.target_reached = True
                result.pnl_pct = ((target - result.entry_price) / result.entry_price) * 100 if direction == "LONG" else ((result.entry_price - target) / result.entry_price) * 100
                result.r_multiple = rr_dist / risk_dist if risk_dist else 0.0
            else:
                result.outcome = "hit_invalidation"
                result.exit_reason = "stop_hit"
                result.invalidated = True
                result.pnl_pct = ((invalidation - result.entry_price) / result.entry_price) * 100 if direction == "LONG" else ((result.entry_price - invalidation) / result.entry_price) * 100
                result.r_multiple = -1.0

            result.mfe, result.mae = _compute_excursion(
                direction, result.entry_price, invalidation, target,
                bars_high, bars_low,
            )
            return result

    # --- Expired ---
    result.outcome = "open"
    result.exit_reason = "expired"
    result.unresolved = True
    result.bars_to_exit = len(post_entry)
    result.mfe, result.mae = _compute_excursion(
        direction, result.entry_price, invalidation, target,
        bars_high, bars_low,
    )
    return result


# ---------------------------------------------------------------------------
# Quality correlation
# ---------------------------------------------------------------------------

def _quality_correlation(results: list[TradeResult]) -> dict[str, Any]:
    closed = [r for r in results if r.outcome in ("hit_target", "hit_invalidation")]
    if not closed:
        return {"note": "No closed trades — correlation unavailable"}

    buckets = [
        (0.0, 0.2, "0-20%"),
        (0.2, 0.4, "20-40%"),
        (0.4, 0.6, "40-60%"),
        (0.6, 0.8, "60-80%"),
        (0.8, 1.0, "80-100%"),
    ]

    bucket_stats = []
    for lo, hi, label in buckets:
        bucket = [r for r in closed if lo <= r.quality_score < hi]
        if not bucket:
            continue
        wins = sum(1 for r in bucket if r.outcome == "hit_target")
        win_rate = wins / len(bucket)
        avg_r = sum(r.r_multiple for r in bucket) / len(bucket)
        win_rs = [r.r_multiple for r in bucket if r.outcome == "hit_target"]
        loss_rs = [r.r_multiple for r in bucket if r.outcome == "hit_invalidation"]
        avg_win_r = sum(win_rs) / len(win_rs) if win_rs else 0.0
        avg_loss_r = sum(loss_rs) / len(loss_rs) if loss_rs else 0.0
        expectancy = (win_rate * avg_win_r) - ((1 - win_rate) * avg_loss_r)

        bucket_stats.append({
            "quality_bucket": label,
            "min_quality": lo,
            "max_quality": hi,
            "sample_count": len(bucket),
            "win_rate": round(win_rate, 3),
            "avg_r": round(avg_r, 3),
            "expectancy": round(expectancy, 3),
            "avg_win_r": round(avg_win_r, 3),
            "avg_loss_r": round(avg_loss_r, 3),
        })

    n = len(closed)
    pearson = None
    if n >= 3:
        q_vals = [r.quality_score for r in closed]
        r_vals = [r.r_multiple for r in closed]
        mean_q = sum(q_vals) / n
        mean_r = sum(r_vals) / n
        num = sum((q - mean_q) * (r - mean_r) for q, r in zip(q_vals, r_vals))
        den_q = math.sqrt(sum((q - mean_q) ** 2 for q in q_vals))
        den_r = math.sqrt(sum((r - mean_r) ** 2 for r in r_vals))
        if den_q > 0 and den_r > 0:
            pearson = num / (den_q * den_r)

    return {
        "buckets": bucket_stats,
        "pearson_quality_vs_r": round(pearson, 4) if pearson is not None else None,
        "total_closed": len(closed),
    }


# ---------------------------------------------------------------------------
# Portfolio metrics
# ---------------------------------------------------------------------------

def _compute_portfolio_metrics(results: list[TradeResult]) -> PortfolioMetrics:
    m = PortfolioMetrics()
    closed = [r for r in results if r.outcome in ("hit_target", "hit_invalidation")]

    m.total_trades = len(results)
    m.hit_target = sum(1 for r in results if r.outcome == "hit_target")
    m.hit_invalidation = sum(1 for r in results if r.outcome == "hit_invalidation")
    m.open_unresolved = sum(1 for r in results if r.outcome == "open")
    m.ambiguous = sum(1 for r in results if r.outcome == "ambiguous")

    if closed:
        m.win_rate = sum(1 for r in closed if r.outcome == "hit_target") / len(closed)
        m.avg_r = sum(r.r_multiple for r in closed) / len(closed)
        total_r = sum(r.r_multiple for r in closed)
        m.expectancy = total_r / len(closed)

        gross_profit = sum(r.r_multiple for r in closed if r.r_multiple > 0)
        gross_loss = abs(sum(r.r_multiple for r in closed if r.r_multiple < 0))
        m.profit_factor = round(gross_profit / gross_loss, 3) if gross_loss > 0 else float("inf")

        cur_w = cur_l = 0
        for r in closed:
            if r.outcome == "hit_target":
                cur_w += 1
                cur_l = 0
            else:
                cur_l += 1
                cur_w = 0
            m.max_consecutive_wins = max(m.max_consecutive_wins, cur_w)
            m.max_consecutive_losses = max(m.max_consecutive_losses, cur_l)

    # Equity curve & drawdown
    cumulative = 0.0
    equity_curve = []
    running_max = 0.0
    for r in results:
        cumulative += r.r_multiple
        equity_curve.append(cumulative)
        if cumulative > running_max:
            running_max = cumulative
        dd = running_max - cumulative
        m.max_drawdown = max(m.max_drawdown, dd)

    m.cumulative_r = round(cumulative, 3)

    # Sharpe (simplified — per-bar, not annualized)
    if len(equity_curve) >= 2:
        rets = [equity_curve[i] - equity_curve[i - 1] for i in range(1, len(equity_curve))]
        if rets:
            mean_ret = sum(rets) / len(rets)
            var = sum((r - mean_ret) ** 2 for r in rets) / len(rets)
            std = math.sqrt(var) if var > 0 else 0.0001
            m.sharpe_ratio = round(mean_ret / std, 3) if std > 0 else 0.0

    entry_bars = [r.bars_to_entry for r in results if r.bars_to_entry > 0]
    exit_bars = [r.bars_to_exit for r in results if r.bars_to_exit > 0]
    m.avg_bars_to_entry = round(sum(entry_bars) / len(entry_bars), 1) if entry_bars else 0.0
    m.avg_bars_to_exit = round(sum(exit_bars) / len(exit_bars), 1) if exit_bars else 0.0

    # Current streak
    for r in reversed(closed):
        if r.outcome == "hit_target":
            m.consecutive_wins += 1
        else:
            m.consecutive_losses += 1
        break

    return m


# ---------------------------------------------------------------------------
# Setup model builder (kept for future use)
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Main engine
# ---------------------------------------------------------------------------

class BacktestEngine:
    """Rolling-window backtest engine for setups."""

    def __init__(
        self,
        symbol: str = "UNKNOWN",
        timeframe: str = "1h",
        config: dict[str, Any] | None = None,
        step: int = 4,
        max_wait_bars: int = 0,
    ):
        self.symbol = symbol
        self.timeframe = timeframe
        self.config = {**DEFAULT_CONFIG, **(config or {})}
        self.step = step
        self.max_wait_bars = max_wait_bars
        self.results: list[TradeResult] = []

    def load_data(self, df: pd.DataFrame | None = None) -> pd.DataFrame:
        if df is not None:
            return df
        try:
            import yfinance as yf
            ticker = yf.Ticker(self.symbol)
            data = ticker.history(period="6mo", interval=self._yf_interval())
            data = data[["Open", "High", "Low", "Close", "Volume"]]
            data.columns = [c.capitalize() if c.lower() == "volume" else c for c in data.columns]
            return data
        except Exception as e:
            raise RuntimeError(f"Failed to load data for {self.symbol}: {e}")

    def _yf_interval(self) -> str:
        mapping = {"1m": "1m", "5m": "5m", "15m": "15m", "30m": "30m",
                   "1h": "60m", "4h": "240m", "1d": "1d", "1w": "1wk"}
        return mapping.get(self.timeframe, "60m")

    def run(self, df: pd.DataFrame | None = None) -> dict[str, Any]:
        df = self.load_data(df)
        df = df.sort_index().reset_index(drop=True)

        n = len(df)
        min_bars = self.config.get("min_bars", 60)
        if n < min_bars:
            raise ValueError(f"Not enough data: {n} bars (need {min_bars})")

        print(f"Backtest: {self.symbol} {self.timeframe}")
        print(f"  Bars: {n}, Step: {self.step}")
        print(f"  Date range: {df.index[0]} → {df.index[-1]}")

        self.results = []
        t0 = time.time()

        for i in range(min_bars, n - 1, self.step):
            window_df = df.iloc[:i + 1].copy()

            try:
                research = build_research_setup(
                    window_df,
                    symbol=self.symbol,
                    timeframe=self.timeframe,
                    config=self.config,
                )
            except Exception:
                continue

            raw_setup = research.get("setup", {})
            model = research.get("model")
            if raw_setup.get("direction") not in ("LONG", "SHORT"):
                continue
            if model is None:
                continue

            quality = research.get("quality", {})
            raw_setup["quality_score"] = quality.get("overall", 0.0)
            raw_setup["quality_breakdown"] = quality.get("breakdown", {})

            raw_setup["setup_type"] = research["model"].setup_type

            # Regime filter fields from research engine
            raw_setup["regime_filter_status"] = research.get("regime_filter_status", "")
            raw_setup["regime_compatibility"] = research.get("regime_compatibility", 0.0)
            raw_setup["regime_reason"] = research.get("regime_reason", "")

            # Enrich signature context from SetupModel
            raw_setup["atr_pct"] = model.regime.atr_pct
            raw_setup["zone_width_atr"] = model.entry_zone.width_atr
            raw_setup["touches"] = model.entry_zone.touches
            raw_setup["structure_type"] = model.structure.structure_type
            raw_setup["liquidity_side"] = model.liquidity.liquidity_side

            future_df = df.iloc[i + 1:].copy()
            if future_df.empty:
                continue

            result = _simulate_trade(
                raw_setup, future_df, generated_at_idx=i,
                max_wait_bars=self.max_wait_bars,
            )
            self.results.append(result)

        elapsed = time.time() - t0
        print(f"  Generated {len(self.results)} setups in {elapsed:.1f}s")

        pm = _compute_portfolio_metrics(self.results)
        qc = _quality_correlation(self.results)
        pm.quality_correlation = qc

        self._save_to_db()

        return {
            "results": self.results,
            "portfolio_metrics": pm,
            "quality_correlation": qc,
            "total_setups": len(self.results),
            "elapsed_seconds": round(elapsed, 2),
        }

    def _save_to_db(self):
        ensure_table()
        saved = 0
        for r in self.results:
            if r.outcome == "open":
                continue
            try:
                record_outcome(
                    setup_type=r.setup_type,
                    regime=r.regime,
                    direction=r.direction,
                    symbol=r.symbol,
                    timeframe=r.timeframe,
                    entry_price=r.entry_price,
                    invalidation_price=r.invalidation,
                    target_price=r.target,
                    quality_score=r.quality_score,
                    outcome=r.outcome,
                    pnl_pct=r.pnl_pct,
                    duration_bars=r.bars_to_exit,
                    atr_pct=r.atr_pct,
                    zone_width_atr=r.zone_width_atr,
                    touches=r.touches,
                    structure_type=r.structure_type,
                    liquidity_side=r.liquidity_side,
                    metadata={
                        "source": "backtest_v1",
                        "setup_type": r.setup_type,
                        "r_multiple": r.r_multiple,
                        "bars_to_entry": r.bars_to_entry,
                        "exit_reason": r.exit_reason,
                        "mfe": r.mfe,
                        "mae": r.mae,
                        "quality_breakdown": r.quality_breakdown,
                        "regime_filter_status": r.regime_filter_status if hasattr(r, "regime_filter_status") else "",
                        "regime_compatibility": r.regime_compatibility if hasattr(r, "regime_compatibility") else 0.0,
                        "regime_reason": r.regime_reason if hasattr(r, "regime_reason") else "",
                    },
                    dataset_version="backtest_v1",
                    universe=r.symbol,
                    universe_method="yfinance",
                    survivorship_risk="medium",
                )
                saved += 1
            except Exception:
                pass
        print(f"  Saved {saved}/{len(self.results)} outcomes to DB")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    import sys
    if len(sys.argv) < 2:
        print("Kullanim: python3 setup_backtest_engine.py SYMBOL [TIMEFRAME]")
        print("Ornek:  python3 setup_backtest_engine.py THYAO.IS 1h")
        sys.exit(1)

    symbol = sys.argv[1]
    timeframe = sys.argv[2] if len(sys.argv) > 2 else "1h"

    engine = BacktestEngine(
        symbol=symbol,
        timeframe=timeframe,
        step=4,
        max_wait_bars=0,
    )

    try:
        output = engine.run()
        pm = output["portfolio_metrics"]

        print("\n" + "=" * 60)
        print(f"  BACKTEST SONUC — {symbol} {timeframe}")
        print("=" * 60)
        print(f"  Total setups:      {pm.total_trades}")
        print(f"  Hit target:        {pm.hit_target}")
        print(f"  Hit invalidation:  {pm.hit_invalidation}")
        print(f"  Open (unresolved): {pm.open_unresolved}")
        print(f"  Ambiguous:         {pm.ambiguous}")
        print(f"  Win rate:          {pm.win_rate:.1%}")
        print(f"  Avg R:             {pm.avg_r:.3f}")
        print(f"  Expectancy:        {pm.expectancy:.3f}")
        print(f"  Profit factor:     {pm.profit_factor:.3f}")
        print(f"  Cumulative R:      {pm.cumulative_r:.3f}")
        print(f"  Max drawdown:      {pm.max_drawdown:.3f}")
        print(f"  Sharpe (raw):      {pm.sharpe_ratio:.3f}")
        print(f"  Max consec wins:   {pm.max_consecutive_wins}")
        print(f"  Max consec losses: {pm.max_consecutive_losses}")
        print(f"  Avg bars to entry: {pm.avg_bars_to_entry}")
        print(f"  Avg bars to exit:  {pm.avg_bars_to_exit}")

        qc = pm.quality_correlation
        if "buckets" in qc:
            print(f"\n  Quality Correlation:")
            print(f"  Pearson quality vs R: {qc.get('pearson_quality_vs_r', 'N/A')}")
            for b in qc["buckets"]:
                print(f"    {b['quality_bucket']:>8s}: n={b['sample_count']:3d}  "
                      f"win={b['win_rate']:.0%}  avgR={b['avg_r']:.2f}  exp={b['expectancy']:.2f}")

        print("=" * 60)

    except Exception as e:
        print(f"Hata: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()