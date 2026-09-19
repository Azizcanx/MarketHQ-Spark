# -*- coding: utf-8 -*-
"""
MarketHQ Adaptive Brain for Setup Intelligence V1
===================================================

Brain'in sadece sonuçları kaydetmesini değil:
"hangi setup tipi + hangi market regime + hangi confirmation kombinasyonu
daha anlamli sonuç verdi?" sorusunu ogrenir.

Bu öğrenme gelecekteki research priority ve setup generation kararlarını etkiler.

AKIŞ
----
1. SetupOutcomeTracker'tan tarihsel veri oku
2. Setup signature'leri analiz et (setup_type × regime × direction)
3. Performance metrics hesapla (win rate, avg return, quality correlation)
4. Learning recommendations üret
5. Brain research queue'onceligi guncelle
6. Strategy evolution hint'i üret

Research only. Canli islem yok.
"""

from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from setup_outcome_tracker import get_historical_stats, get_outcome_summary, ensure_table


ENGINE_NAME = "MARKETHQ_ADAPTIVE_BRAIN"
ENGINE_VERSION = "V1"

# Learning thresholds
MIN_SAMPLES_FOR_LEARNING = 5
MIN_WIN_RATE_FOR_PRIORITY = 0.55
MIN_QUALITY_FOR_PRIORITY = 0.5
PRIORITY_BOOST = 2.0
PRIORITY_PENALTY = 0.5


def _load_brain_queue_db() -> Any:
    """Access brain_research_queue table."""
    import sqlite3
    db_path = Path(__file__).resolve().parent / "market_hq.db"
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn


def analyze_setup_performance(
    symbol: str = "",
    min_samples: int = MIN_SAMPLES_FOR_LEARNING,
) -> list[dict[str, Any]]:
    """
    Analyze all setup signatures and their performance.

    Returns sorted list of learning recommendations.
    """
    conn = _load_brain_queue_db()

    # Get all distinct setup signatures with outcomes
    where = "WHERE symbol = ?" if symbol else ""
    params = (symbol,) if symbol else ()

    rows = conn.execute(f"""
        SELECT
            setup_signature,
            symbol,
            timeframe,
            setup_type,
            regime,
            direction,
            quality_score,
            outcome,
            pnl_pct,
            created_at
        FROM setup_outcomes
        {where}
        ORDER BY created_at DESC
    """, params).fetchall()

    conn.close()

    if not rows:
        return []

    # Group by signature
    signatures: dict[str, dict[str, Any]] = {}
    for row in rows:
        sig = row["setup_signature"]
        if sig not in signatures:
            signatures[sig] = {
                "setup_signature": sig,
                "symbol": row["symbol"],
                "timeframe": row["timeframe"],
                "setup_type": row["setup_type"],
                "regime": row["regime"],
                "direction": row["direction"],
                "samples": 0,
                "targets": 0,
                "invalidations": 0,
                "open": 0,
                "pnl_sum": 0.0,
                "quality_sum": 0.0,
                "quality_count": 0,
                "first_seen": row["created_at"],
                "last_seen": row["created_at"],
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
        if row["quality_score"] is not None:
            s["quality_sum"] += row["quality_score"]
            s["quality_count"] += 1
        s["last_seen"] = row["created_at"]

    # Calculate metrics and learning priority
    recommendations = []
    for sig, data in signatures.items():
        if data["samples"] < min_samples:
            continue

        closed = data["targets"] + data["invalidations"]
        win_rate = data["targets"] / closed if closed > 0 else None
        avg_pnl = data["pnl_sum"] / closed if closed > 0 else None
        avg_quality = data["quality_sum"] / data["quality_count"] if data["quality_count"] > 0 else None

        # Learning priority score
        priority = 0.0

        # Win rate contribution
        if win_rate and win_rate >= MIN_WIN_RATE_FOR_PRIORITY:
            priority += (win_rate - 0.5) * 2.0  # 0..1
        elif win_rate and win_rate < 0.4:
            priority -= (0.4 - win_rate) * 2.0  # negative

        # Quality correlation
        if avg_quality and avg_quality >= MIN_QUALITY_FOR_PRIORITY:
            priority += (avg_quality - 0.5) * 1.0

        # Sample size bonus (more data = more reliable)
        if data["samples"] >= 10:
            priority += 0.1
        elif data["samples"] >= 5:
            priority += 0.05

        # PnL contribution
        if avg_pnl and avg_pnl > 0:
            priority += min(avg_pnl / 10, 0.2)  # cap at 0.2

        priority = max(0.0, min(1.0, priority))

        # Determine action
        if priority >= 0.6:
            action = "PROMOTE_RESEARCH"
            reason = f"Yuksek performans: win_rate={win_rate:.0%}, avg_pnl={avg_pnl:.1f}%, quality={avg_quality:.0%}"
        elif priority >= 0.3:
            action = "MONITOR"
            reason = f"Orta performans: win_rate={win_rate:.0% if win_rate else 0}, samples={data['samples']}"
        elif priority < 0.1 and data["samples"] >= 7:
            action = "DEPRIORITIZE"
            reason = f"Dusuk performans: win_rate={win_rate:.0% if win_rate else 0}, avg_pnl={avg_pnl:.1f}%"
        else:
            action = "INSUFFICIENT_DATA"
            reason = f"Beklemek: {data['samples']} sample (min {min_samples})"

        # Next research question
        next_question = f"{data['setup_type']} + {data['regime']} + {data['direction']}: win_rate={win_rate:.0% if win_rate else '?'}, avg_pnl={avg_pnl:.1f if avg_pnl else '?'}%"

        recommendations.append({
            "setup_signature": sig,
            "setup_type": data["setup_type"],
            "regime": data["regime"],
            "direction": data["direction"],
            "symbol": data["symbol"],
            "samples": data["samples"],
            "win_rate": win_rate,
            "avg_pnl": avg_pnl,
            "avg_quality": avg_quality,
            "priority_score": round(priority, 3),
            "action": action,
            "reason": reason,
            "next_research_question": next_question,
            "strategy_evolution_hint": f"Bu kombinasyonu {data['timeframe']} timeframe'de {data['regime']} ortaminda test et",
        })

    # Sort by priority descending
    recommendations.sort(key=lambda r: r["priority_score"], reverse=True)

    return recommendations


def update_brain_research_queue(
    symbol: str = "",
    recommendations: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """
    Update brain research queue priorities based on learning.

    If recommendations not provided, analyze from outcome data.
    """
    if recommendations is None:
        recommendations = analyze_setup_performance(symbol=symbol)

    conn = _load_brain_queue_db()
    updated = 0

    for rec in recommendations:
        if rec["priority_score"] < 0.3:
            continue  # Only boost high-priority items

        # Find existing queue items for this setup type
        existing = conn.execute("""
            SELECT id, priority, metadata_json
            FROM brain_research_queue
            WHERE status = 'active'
            AND metadata_json LIKE ?
        """, (f"%{rec['setup_type']}%",)).fetchall()

        for row in existing:
            meta = {}
            try:
                meta = json.loads(row["metadata_json"]) if row["metadata_json"] else {}
            except (json.JSONDecodeError, TypeError):
                pass

            # Boost priority
            old_priority = row["priority"]
            new_priority = min(10.0, old_priority + PRIORITY_BOOST * rec["priority_score"])

            meta["adaptive_priority"] = rec["priority_score"]
            meta["learning_action"] = rec["action"]
            meta["next_research_question"] = rec["next_research_question"]

            conn.execute("""
                UPDATE brain_research_queue
                SET priority = ?, metadata_json = ?, updated_at = ?
                WHERE id = ?
            """, (round(new_priority, 1), json.dumps(meta, ensure_ascii=False),
                  datetime.now(timezone.utc).isoformat(timespec="seconds"), row["id"]))
            updated += 1

    conn.commit()
    conn.close()

    return {
        "updated_count": updated,
        "recommendations": len(recommendations),
        "top_recommendation": recommendations[0] if recommendations else None,
    }


def generate_research_questions(
    symbol: str = "",
    max_questions: int = 5,
) -> list[dict[str, Any]]:
    """
    Generate research questions based on adaptive learning.

    These questions guide the brain research queue toward
    the most promising setup-type × regime × confirmation combos.
    """
    recommendations = analyze_setup_performance(symbol=symbol)
    questions = []

    for rec in recommendations[:max_questions]:
        questions.append({
            "question": rec["next_research_question"],
            "reason": rec["reason"],
            "priority": rec["priority_score"],
            "action": rec["action"],
            "setup_signature": rec["setup_signature"],
            "strategy_evolution_hint": rec["strategy_evolution_hint"],
            "source": "adaptive_brain_v1",
        })

    return questions


def get_learning_dashboard(symbol: str = "") -> dict[str, Any]:
    """Full learning dashboard for monitoring."""
    ensure_table()

    outcome_summary = get_outcome_summary(symbol=symbol)
    recommendations = analyze_setup_performance(symbol=symbol)

    return {
        "engine": ENGINE_NAME,
        "version": ENGINE_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "outcome_summary": outcome_summary,
        "learning_recommendations": recommendations,
        "research_questions": generate_research_questions(symbol=symbol),
        "top_setup": recommendations[0] if recommendations else None,
    }


# CLI entry point
def main() -> None:
    import sys

    if len(sys.argv) < 2:
        print(f"Kullanim: python3 {sys.argv[0]} SYMBOL [TIMEFRAME]")
        print("Ornek: python3 setup_adaptive_brain.py THYAO.IS")
        sys.exit(1)

    symbol = sys.argv[1]

    print(f"🧠 Adaptive Brain — {symbol}")
    print("-" * 60)

    dashboard = get_learning_dashboard(symbol=symbol)

    print(f"\n📊 Outcome Summary:")
    for k, v in dashboard["outcome_summary"].items():
        print(f"  {k}: {v}")

    print(f"\n📋 Learning Recommendations:")
    for rec in dashboard["learning_recommendations"]:
        print(f"  [{rec['priority_score']:.0%}] {rec['setup_type']} + {rec['regime']} + {rec['direction']}")
        print(f"      Action: {rec['action']} — {rec['reason']}")
        print(f"      Soru: {rec['next_research_question']}")

    if dashboard["research_questions"]:
        print(f"\n❓ Research Queue Questions:")
        for q in dashboard["research_questions"][:3]:
            print(f"  - {q['question']} (priority: {q['priority']:.0%})")

    # Update brain queue
    update_result = update_brain_research_queue(symbol=symbol, recommendations=dashboard["learning_recommendations"])
    print(f"\n🔄 Brain Queue: {update_result['updated_count']} guncellendi")

    # Save dashboard
    output_dir = Path(__file__).resolve().parent / "agentspace" / "evidence"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_file = output_dir / f"adaptive_brain_{symbol}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(output_file, "w") as f:
        json.dump(dashboard, f, indent=2, ensure_ascii=False, default=str)
    print(f"\n📋 Dashboard: {output_file}")


if __name__ == "__main__":
    main()