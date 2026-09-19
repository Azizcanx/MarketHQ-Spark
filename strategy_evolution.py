# -*- coding: utf-8 -*-
"""
MarketHQ Strategy Evolution Engine V1
=======================================

Adaptive Brain öğrenmesini strategy evolution'a bağlar.

AKIŞ
----
1. Adaptive brain learning recommendations oku
2. Hangi setup tipi + regime + confirmation combo performans gösteriyor?
3. Strategy evolution önerisi üret:
   - Parametre adjust önerisi (e.g. ATR multiple, SMA periyot)
   - Ek strateji ekleme önerisi (e.g. trend'de momentum ekle)
   - Strateji çıkarma önerisi (yeterli örnek yok, düşük win rate)
4. Brain research queue'a evolution tasks ekle
5. Method specification güncelle

Research only. Canli islem yok.
"""

from __future__ import annotations

import json
import math
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DB_PATH = Path(__file__).resolve().parent / "market_hq.db"
ENGINE_NAME = "MARKETHQ_STRATEGY_EVOLUTION"
ENGINE_VERSION = "V1"


def _db() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout = 60000")
    return conn


def _get_learning_data(symbol: str = "") -> list[dict[str, Any]]:
    """Get setup performance data from outcome tracker."""
    conn = _db()
    where = "WHERE symbol = ?" if symbol else ""
    params = (symbol,) if symbol else ()

    rows = conn.execute(f"""
        SELECT
            setup_signature, setup_type, regime, direction, symbol, timeframe,
            quality_score, outcome, pnl_pct, hit_target, hit_invalidation,
            COUNT(*) OVER (PARTITION BY setup_signature) as signature_count
        FROM setup_outcomes
        {where}
        ORDER BY created_at DESC
    """, params).fetchall()

    conn.close()
    return [dict(r) for r in rows]


def _compute_deflated_sharpe(
    avg_return: float, std_return: float, n: int, trials: int = 1
) -> float | None:
    """
    Deflated Sharpe Ratio — penalizes for search intensity.

    From Gencay (2026) / White (2000):
    Deflated Sharpe = Sharpe / sqrt(1 + Sharpe² / (2 * N))

    Where N is the number of independent trials (not total backtests).
    """
    if std_return is None or std_return == 0 or n < 2:
        return None

    sharpe = (avg_return / std_return) * math.sqrt(252)  # annualized
    deflated = sharpe / math.sqrt(1 + (sharpe ** 2) / (2 * max(trials, 1)))
    return round(deflated, 4)


def _compute_pbo_proxy(
    win_rates: list[float],
    holdout_win_rate: float | None,
    train_win_rate: float | None,
) -> float:
    """
    Probability of Backtest Overfitting proxy.

    If holdout performance is significantly worse than training,
    overfitting is likely. Uses a simple ratio-based heuristic
    (full PBO requires combinatorially symmetric CV — too expensive
    for this implementation).
    """
    if holdout_win_rate is None or train_win_rate is None:
        return 0.5  # unknown — moderate risk

    if train_win_rate == 0:
        return 0.5

    ratio = holdout_win_rate / train_win_rate

    if ratio >= 0.9:
        return 0.05  # low overfitting risk
    elif ratio >= 0.7:
        return 0.2   # moderate
    elif ratio >= 0.5:
        return 0.5   # significant
    else:
        return 0.8   # high overfitting risk


def analyze_strategy_evolution(
    symbol: str = "",
    min_samples: int = 5,
) -> dict[str, Any]:
    """
    Analyze setup performance and generate strategy evolution recommendations.

    Returns:
        {
            "setup_signatures": [...performance by signature...],
            "evolution_recommendations": [...actionable suggestions...],
            "overfitting_warnings": [...],
            "strategy_evolution": {
                "add_strategies": [...],
                "remove_strategies": [...],
                "adjust_params": [...],
                "keep_strategies": [...]
            }
        }
    """
    data = _get_learning_data(symbol=symbol)

    if not data:
        return {
            "setup_signatures": [],
            "evolution_recommendations": [],
            "overfitting_warnings": [],
            "strategy_evolution": {
                "add_strategies": [],
                "remove_strategies": [],
                "adjust_params": [],
                "keep_strategies": [],
            },
        }

    # Group by setup signature
    signatures: dict[str, dict[str, Any]] = {}
    for row in data:
        sig = row["setup_signature"]
        if sig not in signatures:
            signatures[sig] = {
                "setup_signature": sig,
                "setup_type": row["setup_type"],
                "regime": row["regime"],
                "direction": row["direction"],
                "symbol": row["symbol"],
                "timeframe": row["timeframe"],
                "samples": 0,
                "targets": 0,
                "invalidations": 0,
                "open": 0,
                "pnl_sum": 0.0,
                "pnl_sq_sum": 0.0,
                "quality_sum": 0.0,
                "quality_count": 0,
            }
        s = signatures[sig]
        s["samples"] += 1
        if row["outcome"] == "hit_target":
            s["targets"] += 1
        elif row["outcome"] == "hit_invalidation":
            s["invalidations"] += 1
        elif row["outcome"] == "open":
            s["open"] += 1
        if row["pnl_pct"] is not None:
            s["pnl_sum"] += row["pnl_pct"]
            s["pnl_sq_sum"] += (row["pnl_pct"] or 0) ** 2
        if row["quality_score"] is not None:
            s["quality_sum"] += row["quality_score"]
            s["quality_count"] += 1

    # Analyze each signature
    results = []
    overfitting_warnings = []
    for sig, s in signatures.items():
        if s["samples"] < min_samples:
            continue

        closed = s["targets"] + s["invalidations"]
        win_rate = s["targets"] / closed if closed > 0 else None
        avg_pnl = s["pnl_sum"] / closed if closed > 0 else None
        std_pnl = math.sqrt(
            max(0, s["pnl_sq_sum"] / closed - avg_pnl ** 2)
        ) if closed > 1 else None
        deflated = _compute_deflated_sharpe(avg_pnl or 0, std_pnl or 0, closed)
        avg_quality = s["quality_sum"] / s["quality_count"] if s["quality_count"] > 0 else None

        # Overfitting warning
        if win_rate and win_rate > 0.7 and s["samples"] < 20:
            overfitting_warnings.append({
                "setup_signature": sig,
                "setup_type": s["setup_type"],
                "win_rate": win_rate,
                "samples": s["samples"],
                "reason": "Yuksek win rate az sample'da — overfitting riski",
                "severity": "medium",
            })

        # Performance classification
        if win_rate and avg_pnl:
            if win_rate >= 0.6 and avg_pnl > 0:
                performance = "STRONG"
            elif win_rate >= 0.5 and avg_pnl > 0:
                performance = "MODERATE"
            elif win_rate < 0.4 and avg_pnl < 0:
                performance = "WEAK"
            else:
                performance = "MIXED"
        else:
            performance = "INSUFFICIENT_DATA"

        results.append({
            "setup_signature": sig,
            "setup_type": s["setup_type"],
            "regime": s["regime"],
            "direction": s["direction"],
            "symbol": s["symbol"],
            "timeframe": s["timeframe"],
            "samples": s["samples"],
            "win_rate": round(win_rate, 3) if win_rate else None,
            "avg_pnl": round(avg_pnl, 2) if avg_pnl else None,
            "std_pnl": round(std_pnl, 2) if std_pnl else None,
            "deflated_sharpe": deflated,
            "avg_quality": round(avg_quality, 3) if avg_quality else None,
            "performance": performance,
        })

    # Sort by performance
    perf_order = {"STRONG": 0, "MODERATE": 1, "MIXED": 2, "WEAK": 3, "INSUFFICIENT_DATA": 4}
    results.sort(key=lambda r: perf_order.get(r["performance"], 5))

    # Generate evolution recommendations
    recommendations = []
    add_strategies = []
    remove_strategies = []
    adjust_params = []
    keep_strategies = []

    for r in results:
        if r["performance"] == "STRONG":
            keep_strategies.append({
                "setup_type": r["setup_type"],
                "regime": r["regime"],
                "direction": r["direction"],
                "win_rate": r["win_rate"],
                "avg_pnl": r["avg_pnl"],
                "deflated_sharpe": r["deflated_sharpe"],
                "action": "KEEP — strong performer, increase allocation",
            })
            # Also suggest adding similar strategies
            add_strategies.append({
                "suggestion": f"Add {r['setup_type']} variants for {r['regime']} regime",
                "reason": f"Win rate {r['win_rate']:.0%}, avg PnL {r['avg_pnl']:.1f}%",
                "priority": "high",
            })
        elif r["performance"] == "MODERATE":
            keep_strategies.append({
                "setup_type": r["setup_type"],
                "regime": r["regime"],
                "direction": r["direction"],
                "win_rate": r["win_rate"],
                "avg_pnl": r["avg_pnl"],
                "deflated_sharpe": r["deflated_sharpe"],
                "action": "KEEP — monitor, consider parameter tuning",
            })
            adjust_params.append({
                "setup_type": r["setup_type"],
                "regime": r["regime"],
                "current_params": "default",
                "suggested_adjustment": "Tune ATR multiples or SMA periods",
                "reason": f"Moderate performance — {r['win_rate']:.0%} win rate",
            })
        elif r["performance"] == "WEAK":
            remove_strategies.append({
                "setup_type": r["setup_type"],
                "regime": r["regime"],
                "direction": r["direction"],
                "win_rate": r["win_rate"],
                "avg_pnl": r["avg_pnl"],
                "action": "DEPRIORITIZE — weak performer, reduce or remove",
            })
        elif r["performance"] == "INSUFFICIENT_DATA":
            recommendations.append({
                "setup_type": r["setup_type"],
                "regime": r["regime"],
                "direction": r["direction"],
                "samples": r["samples"],
                "action": "GATHER_MORE_DATA",
                "reason": f"Only {r['samples']} samples — need more data",
            })

    # Add overfitting warnings to recommendations
    for warning in overfitting_warnings:
        recommendations.append({
            "type": "OVERFITTING_WARNING",
            "setup_signature": warning["setup_signature"],
            "setup_type": warning["setup_type"],
            "severity": warning["severity"],
            "reason": warning["reason"],
            "action": "REDUCE_COMPLEXITY — fewer parameters, simpler model",
        })

    evolution = {
        "add_strategies": add_strategies,
        "remove_strategies": remove_strategies,
        "adjust_params": adjust_params,
        "keep_strategies": keep_strategies,
    }

    return {
        "setup_signatures": results,
        "evolution_recommendations": recommendations,
        "overfitting_warnings": overfitting_warnings,
        "strategy_evolution": evolution,
        "engine": ENGINE_NAME,
        "version": ENGINE_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


def update_brain_with_evolution(
    symbol: str = "",
    analysis: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Update brain research queue based on strategy evolution analysis.

    Adds research questions for:
    - Strong performers: expand to other symbols/timeframes
    - Weak performers: investigate why, possible removal
    - Overfitting warnings: reduce complexity
    """
    if analysis is None:
        analysis = analyze_strategy_evolution(symbol=symbol)

    conn = _db()
    updates = 0
    questions_added = 0

    for rec in analysis.get("evolution_recommendations", []):
        if rec.get("type") == "OVERFITTING_WARNING":
            # Add research question about reducing complexity
            question = f"Overfitting detected in {rec.get('setup_type', 'unknown')} — reduce parameters?"
            conn.execute("""
                INSERT INTO brain_research_queue
                    (question, reason, priority, status, metadata_json, created_at, updated_at)
                VALUES (?, ?, ?, 'active', ?, ?, ?)
            """, (
                question,
                rec.get("reason", ""),
                5,  # medium priority
                json.dumps({"source": "strategy_evolution", "severity": rec.get("severity", "medium")}, ensure_ascii=False),
                datetime.now(timezone.utc).isoformat(timespec="seconds"),
                datetime.now(timezone.utc).isoformat(timespec="seconds"),
            ))
            questions_added += 1

    # Add questions for strong performers
    for keep in analysis.get("strategy_evolution", {}).get("keep_strategies", []):
        if keep.get("deflated_sharpe") and keep["deflated_sharpe"] > 1.0:
            question = f"Expand {keep['setup_type']} ({keep['regime']}) to other symbols — deflated Sharpe {keep['deflated_sharpe']:.2f}"
            conn.execute("""
                INSERT INTO brain_research_queue
                    (question, reason, priority, status, metadata_json, created_at, updated_at)
                VALUES (?, ?, ?, 'active', ?, ?, ?)
            """, (
                question,
                f"Strong performer: win_rate={keep.get('win_rate')}, avg_pnl={keep.get('avg_pnl')}",
                7,  # high priority
                json.dumps({"source": "strategy_evolution", "action": "EXPAND"}, ensure_ascii=False),
                datetime.now(timezone.utc).isoformat(timespec="seconds"),
                datetime.now(timezone.utc).isoformat(timespec="seconds"),
            ))
            questions_added += 1

    # Add questions for strategies to deprioritize
    for remove in analysis.get("strategy_evolution", {}).get("remove_strategies", []):
        question = f"Deprioritize {remove.get('setup_type', 'unknown')} ({remove.get('regime', '?')}) — weak performer"
        conn.execute("""
            INSERT INTO brain_research_queue
                (question, reason, priority, status, metadata_json, created_at, updated_at)
            VALUES (?, ?, ?, 'active', ?, ?, ?)
        """, (
            question,
            f"Weak: win_rate={remove.get('win_rate')}, avg_pnl={remove.get('avg_pnl')}",
            3,  # low priority
            json.dumps({"source": "strategy_evolution", "action": "DEPRIORITIZE"}, ensure_ascii=False),
            datetime.now(timezone.utc).isoformat(timespec="seconds"),
            datetime.now(timezone.utc).isoformat(timespec="seconds"),
        ))
        questions_added += 1

    conn.commit()
    conn.close()

    return {
        "updates": updates,
        "questions_added": questions_added,
        "analysis_summary": {
            "total_signatures": len(analysis.get("setup_signatures", [])),
            "overfitting_warnings": len(analysis.get("overfitting_warnings", [])),
            "strong_performers": len(analysis.get("strategy_evolution", {}).get("keep_strategies", [])),
            "weak_performers": len(analysis.get("strategy_evolution", {}).get("remove_strategies", [])),
            "param_adjustments": len(analysis.get("strategy_evolution", {}).get("adjust_params", [])),
        },
    }


def get_evolution_dashboard(symbol: str = "") -> dict[str, Any]:
    """Full evolution dashboard."""
    analysis = analyze_strategy_evolution(symbol=symbol)

    return {
        "engine": ENGINE_NAME,
        "version": ENGINE_VERSION,
        "analysis": analysis,
        "brain_queue_update": update_brain_with_evolution(symbol=symbol, analysis=analysis),
    }