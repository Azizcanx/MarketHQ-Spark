# -*- coding: utf-8 -*-
"""
Regime Filter — ties regime analysis to setup generation.

Computes regime x strategy performance matrix from backtest data,
assigns eligibility/penalty per regime-strategy combo, and integrates
with setup generation to modify quality scores based on data-driven
thresholds — no hardcoded regime blocking.

Rules:
  - sufficient sample (>=20) + positive expectancy → ALLOW
  - sufficient sample + negative expectancy → PENALTY (reduce quality score)
  - insufficient sample (< 20) → CONSERVATIVE (neutral, don't block)
"""

from __future__ import annotations

import sqlite3
import json
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

DB_PATH = Path(__file__).resolve().parent / "market_hq.db"

MIN_SAMPLE = 20  # minimum trades for data-driven decision
PENALTY_MULTIPLIER = 0.7  # quality score multiplier for PENALTY regimes


@dataclass
class RegimeStrategyStats:
    """Performance stats for a regime-strategy combo."""
    regime: str
    strategy: str
    sample: int = 0
    wins: int = 0
    losses: int = 0
    win_rate: float = 0.0
    avg_r: float = 0.0
    expectancy: float = 0.0


@dataclass
class RegimeFilterDecision:
    """Filter decision for a regime-strategy combo."""
    regime: str = ""
    strategy: str = ""
    status: str = "CONSERVATIVE"  # ALLOW | PENALTY | CONSERVATIVE
    compatibility: float = 0.5
    reason: str = ""
    sample: int = 0
    win_rate: float = 0.0
    avg_r: float = 0.0
    expectancy: float = 0.0


def _db():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def parse_meta(meta_json):
    if not meta_json:
        return None
    try:
        return json.loads(meta_json)
    except (json.JSONDecodeError, TypeError):
        return None


def compute_regime_strategy_matrix() -> dict[str, dict[str, RegimeStrategyStats]]:
    """Compute regime x strategy performance matrix from backtest data.

    Returns dict[regime][strategy] -> RegimeStrategyStats
    """
    conn = _db()
    rows = conn.execute("""
        SELECT
            regime, setup_type,
            outcome, quality_score,
            metadata_json
        FROM setup_outcomes
        WHERE metadata_json LIKE '%backtest_v1%'
           OR outcome IN ('hit_target', 'hit_invalidation')
    """).fetchall()
    conn.close()

    combos = defaultdict(list)
    for row in rows:
        regime = row["regime"] or "UNKNOWN"
        strategy = row["setup_type"] or "unknown"
        meta = parse_meta(row["metadata_json"])
        r_multiple = meta.get("r_multiple", 0.0) if meta else 0.0
        combos[(regime, strategy)].append({
            "outcome": row["outcome"],
            "r_multiple": r_multiple,
            "quality_score": row["quality_score"] or 0.0,
        })

    matrix = defaultdict(dict)
    for (regime, strategy), trades in combos.items():
        n = len(trades)
        wins = sum(1 for t in trades if t["outcome"] == "hit_target")
        losses = sum(1 for t in trades if t["outcome"] == "hit_invalidation")
        closed = wins + losses
        win_rate = wins / closed if closed else 0.0
        r_vals = [t["r_multiple"] for t in trades]
        avg_r = sum(r_vals) / len(r_vals) if r_vals else 0.0
        expectancy = win_rate * avg_r

        matrix[regime][strategy] = RegimeStrategyStats(
            regime=regime,
            strategy=strategy,
            sample=n,
            wins=wins,
            losses=losses,
            win_rate=round(win_rate, 3),
            avg_r=round(avg_r, 3),
            expectancy=round(expectancy, 3),
        )

    return dict(matrix)


def classify_regime_eligibility(
    regime: str,
    strategy: str,
    matrix: dict[str, dict[str, RegimeStrategyStats]] | None = None,
) -> RegimeFilterDecision:
    """Classify regime-strategy combo eligibility.

    Rules:
      - sufficient sample (>=20) + positive expectancy → ALLOW
      - sufficient sample + negative expectancy → PENALTY
      - insufficient sample (< 20) → CONSERVATIVE

    If no data available for the combo, falls back to regime-level data.
    """
    if matrix is None:
        matrix = compute_regime_strategy_matrix()

    combo_stats = None
    if regime in matrix and strategy in matrix[regime]:
        combo_stats = matrix[regime][strategy]

    if combo_stats is None or combo_stats.sample < MIN_SAMPLE:
        regime_stats = _aggregate_regime_stats(regime, matrix)
        if regime_stats is not None:
            stats = regime_stats
        else:
            return RegimeFilterDecision(
                regime=regime,
                strategy=strategy,
                status="CONSERVATIVE",
                compatibility=0.5,
                reason="no_data: conservative fallback, no historical data",
                sample=0,
                win_rate=0.0,
                avg_r=0.0,
                expectancy=0.0,
            )
    else:
        stats = combo_stats

    n = stats.sample
    expectancy = stats.expectancy

    if n >= MIN_SAMPLE and expectancy > 0:
        compat = 0.85 + 0.15 * min(max(stats.avg_r, 0.0) / 2.0, 1.0)
        return RegimeFilterDecision(
            regime=regime,
            strategy=strategy,
            status="ALLOW",
            compatibility=round(min(compat, 1.0), 3),
            reason=f"data_driven: n={n} exp={expectancy:+.3f} avgR={stats.avg_r:+.3f}",
            sample=n,
            win_rate=stats.win_rate,
            avg_r=stats.avg_r,
            expectancy=expectancy,
        )
    elif n >= MIN_SAMPLE and expectancy <= 0:
        severity = min(abs(expectancy) / 2.0, 1.0)
        compat = max(0.15 - severity * 0.5, 0.05)
        return RegimeFilterDecision(
            regime=regime,
            strategy=strategy,
            status="PENALTY",
            compatibility=round(compat, 3),
            reason=f"negative_expectancy: n={n} exp={expectancy:+.3f} avgR={stats.avg_r:+.3f}",
            sample=n,
            win_rate=stats.win_rate,
            avg_r=stats.avg_r,
            expectancy=expectancy,
        )
    else:
        return RegimeFilterDecision(
            regime=regime,
            strategy=strategy,
            status="CONSERVATIVE",
            compatibility=0.5,
            reason=f"insufficient_data: n={n} < {MIN_SAMPLE}, conservative fallback",
            sample=n,
            win_rate=stats.win_rate,
            avg_r=stats.avg_r,
            expectancy=expectancy,
        )


def _aggregate_regime_stats(
    regime: str,
    matrix: dict[str, dict[str, RegimeStrategyStats]],
) -> RegimeStrategyStats | None:
    """Aggregate stats across all strategies for a regime."""
    if regime not in matrix:
        return None

    all_stats = list(matrix[regime].values())
    total_sample = sum(s.sample for s in all_stats)
    if total_sample == 0:
        return None

    total_wins = sum(s.wins for s in all_stats)
    total_losses = sum(s.losses for s in all_stats)
    closed = total_wins + total_losses
    win_rate = total_wins / closed if closed else 0.0
    avg_r = sum(s.avg_r * s.sample for s in all_stats) / total_sample
    expectancy = win_rate * avg_r

    return RegimeStrategyStats(
        regime=regime,
        strategy="AGGREGATE",
        sample=total_sample,
        wins=total_wins,
        losses=total_losses,
        win_rate=round(win_rate, 3),
        avg_r=round(avg_r, 3),
        expectancy=round(expectancy, 3),
    )


def apply_regime_filter(
    setup: dict[str, Any] | Any,
    matrix: dict[str, dict[str, RegimeStrategyStats]] | None = None,
) -> RegimeFilterDecision:
    """Apply regime filter to a setup.

    Modifies the setup dict/object with regime filter metadata and adjusts
    quality score if PENALTY.

    Returns the RegimeFilterDecision for reference.
    """
    if matrix is None:
        matrix = compute_regime_strategy_matrix()

    # Extract regime and strategy from setup
    if isinstance(setup, dict):
        regime = setup.get("regime", "UNKNOWN")
        strategy = setup.get("setup_type", "unknown")
        old_score = setup.get("quality_score", 0.0)
    else:
        regime_obj = getattr(setup, "regime", None)
        regime = regime_obj.regime if regime_obj else "UNKNOWN"
        strategy = getattr(setup, "setup_type", "unknown") or "unknown"
        # Extract quality score from model.quality.overall or fallback
        quality_obj = getattr(setup, "quality", None)
        if quality_obj is not None:
            old_score = getattr(quality_obj, "overall", 0.0)
        elif hasattr(setup, "quality_score"):
            old_score = setup.quality_score
        else:
            old_score = 0.0

    decision = classify_regime_eligibility(regime, strategy, matrix)

    # Store filter decision in setup metadata
    if isinstance(setup, dict):
        setup["regime_filter_status"] = decision.status
        setup["regime_compatibility"] = decision.compatibility
        setup["regime_reason"] = decision.reason
        setup["regime_filter_sample"] = decision.sample
        setup["regime_filter_expectancy"] = decision.expectancy

        if decision.status == "PENALTY":
            setup["quality_score"] = round(old_score * PENALTY_MULTIPLIER, 3)
            setup["regime_penalty_applied"] = True
            setup["regime_penalty_factor"] = PENALTY_MULTIPLIER
        elif decision.status == "CONSERVATIVE":
            setup["regime_low_confidence"] = True
    else:
        setup.regime_filter_status = decision.status
        setup.regime_compatibility = decision.compatibility
        setup.regime_reason = decision.reason

        if decision.status == "PENALTY":
            if hasattr(setup, "quality") and hasattr(setup.quality, "overall"):
                setup.quality.overall = round(old_score * PENALTY_MULTIPLIER, 3)
            if hasattr(setup, "quality") and hasattr(setup.quality, "flags"):
                setup.quality.flags.append(f"REGIME_PENALTY: {decision.reason}")
        elif decision.status == "CONSERVATIVE":
            if hasattr(setup, "quality") and hasattr(setup.quality, "flags"):
                setup.quality.flags.append(f"REGIME_CONSERVATIVE: {decision.reason}")

    return decision


def get_regime_filter_status(
    regime: str,
    strategy: str = "unknown",
    matrix: dict[str, dict[str, RegimeStrategyStats]] | None = None,
) -> dict[str, Any]:
    """Get the regime filter status for a given regime-strategy combo.

    Returns a simple dict for quick checks.
    """
    decision = classify_regime_eligibility(regime, strategy, matrix)
    return {
        "regime_filter_status": decision.status,
        "regime_compatibility": decision.compatibility,
        "regime_reason": decision.reason,
        "regime_filter_sample": decision.sample,
        "regime_filter_expectancy": decision.expectancy,
    }


def compute_performance_report() -> dict[str, Any]:
    """Generate a full regime-strategy performance report.

    Returns matrix + summary stats per regime.
    """
    matrix = compute_regime_strategy_matrix()

    report = {}
    for regime, strategies in matrix.items():
        total_sample = sum(s.sample for s in strategies.values())
        total_wins = sum(s.wins for s in strategies.values())
        total_losses = sum(s.losses for s in strategies.values())
        closed = total_wins + total_losses
        wr = total_wins / closed if closed else 0.0
        avg_r = sum(s.avg_r * s.sample for s in strategies.values()) / total_sample if total_sample else 0.0
        expectancy = wr * avg_r

        # Get filter classification for this regime (aggregate)
        agg_stats = _aggregate_regime_stats(regime, matrix)
        if agg_stats:
            decision = classify_regime_eligibility(regime, "AGGREGATE", matrix)
            filter_status = decision.status
            filter_reason = decision.reason
        else:
            filter_status = "CONSERVATIVE"
            filter_reason = "no_data"

        report[regime] = {
            "total_sample": total_sample,
            "win_rate": round(wr, 3),
            "avg_r": round(avg_r, 3),
            "expectancy": round(expectancy, 3),
            "filter_status": filter_status,
            "filter_reason": filter_reason,
            "strategies": {
                s: {
                    "sample": st.sample,
                    "win_rate": st.win_rate,
                    "avg_r": st.avg_r,
                    "expectancy": st.expectancy,
                }
                for s, st in strategies.items()
            },
        }

    return report


if __name__ == "__main__":
    print("=== Regime Filter — Performance Report ===\n")

    report = compute_performance_report()
    for regime, data in sorted(report.items(), key=lambda x: x[1].get("avg_r", 0), reverse=True):
        print(f"  {regime:20s}: n={data['total_sample']:4d}  "
              f"wr={data['win_rate']:.0%}  avgR={data['avg_r']:+.3f}  "
              f"exp={data['expectancy']:+.3f}  "
              f"filter={data['filter_status']}")
        for strat, sdata in data["strategies"].items():
            print(f"    {strat:20s}: n={sdata['sample']:3d}  "
                  f"wr={sdata['win_rate']:.0%}  avgR={sdata['avg_r']:+.3f}")

    print("\n=== Filter Decision Test ===\n")
    for regime in sorted(report.keys()):
        decision = classify_regime_eligibility(regime, "unknown")
        print(f"  {regime:20s} → {decision.status:12s} "
              f"(compat={decision.compatibility:.3f}, reason={decision.reason})")