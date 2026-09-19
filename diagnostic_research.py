# -*- coding: utf-8 -*-
"""
Diagnostic Research — Setup Engine V1
=======================================

Backtest_v1 sonuçlarıyla sistematik teşhis.
8 alan: strategy contribution, regime breakdown, evidence breakdown,
quality decomposition, strategy correlation, failure analysis,
exit vs entry, data quality.
"""

from __future__ import annotations

import json
import math
import sqlite3
from collections import defaultdict
from pathlib import Path

import numpy as np

DB_PATH = Path(__file__).resolve().parent / "market_hq.db"


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


def load_backtest_records():
    conn = _db()
    rows = conn.execute("""
        SELECT metadata_json, outcome, pnl_pct, quality_score,
               regime, direction, setup_signature
        FROM setup_outcomes
        WHERE metadata_json LIKE '%backtest_v1%'
    """).fetchall()
    conn.close()

    records = []
    for row in rows:
        meta = parse_meta(row["metadata_json"])
        if not meta:
            continue
        rec = dict(meta)
        rec["outcome"] = row["outcome"]
        rec["quality_score"] = row["quality_score"] or 0.0
        rec["regime"] = row["regime"] or "UNKNOWN"
        rec["direction"] = row["direction"] or "UNKNOWN"
        rec["setup_signature"] = row["setup_signature"] or ""
        records.append(rec)
    return records


# =====================================================================
# 1. STRATEGY CONTRIBUTION
# =====================================================================

def strategy_contribution(records):
    families = defaultdict(list)
    for r in records:
        stype = r.get("setup_type", "unknown")
        families[stype].append(r)

    result = {}
    for fam, trades in families.items():
        n = len(trades)
        wins = sum(1 for t in trades if t["outcome"] == "hit_target")
        losses = sum(1 for t in trades if t["outcome"] == "hit_invalidation")
        closed = wins + losses
        win_rate = wins / closed if closed else 0.0
        r_vals = [t.get("r_multiple", 0.0) or 0.0 for t in trades]
        avg_r = sum(r_vals) / len(r_vals) if r_vals else 0.0
        mfe = [t.get("mfe", 0.0) or 0.0 for t in trades]
        mae = [t.get("mae", 0.0) or 0.0 for t in trades]
        expectancy = win_rate * avg_r

        result[fam] = {
            "sample": n, "win_rate": round(win_rate, 3),
            "avg_r": round(avg_r, 3), "expectancy": round(expectancy, 3),
            "avg_mfe": round(np.mean(mfe), 4) if mfe else 0.0,
            "avg_mae": round(np.mean(mae), 4) if mae else 0.0,
        }
    return result


# =====================================================================
# 2. REGIME BREAKDOWN
# =====================================================================

def regime_breakdown(records):
    regimes = defaultdict(list)
    for r in records:
        regimes[r["regime"]].append(r)

    result = {}
    for reg, trades in regimes.items():
        n = len(trades)
        wins = sum(1 for t in trades if t["outcome"] == "hit_target")
        losses = sum(1 for t in trades if t["outcome"] == "hit_invalidation")
        closed = wins + losses
        win_rate = wins / closed if closed else 0.0
        r_vals = [t.get("r_multiple", 0.0) or 0.0 for t in trades]
        avg_r = sum(r_vals) / len(r_vals) if r_vals else 0.0
        avg_quality = np.mean([t.get("quality_score", 0.0) for t in trades])

        q_vals = [t.get("quality_score", 0.0) for t in trades]
        pearson = None
        if n >= 3 and np.std(q_vals) > 0 and np.std(r_vals) > 0:
            corr = np.corrcoef(q_vals, r_vals)
            pearson = round(float(corr[0, 1]), 4) if not np.isnan(corr[0, 1]) else 0.0

        result[reg] = {
            "sample": n, "win_rate": round(win_rate, 3),
            "avg_r": round(avg_r, 3), "avg_quality": round(avg_quality, 3),
            "quality_pearson": pearson,
        }
    return result


# =====================================================================
# 3. EVIDENCE BREAKDOWN
# =====================================================================

def evidence_breakdown(records):
    dims = [
        "supporting_evidence", "conflicting_evidence",
        "regime_compatibility", "structure_quality", "entry_quality",
        "risk_reward_feasibility", "historical_validation",
        "strategy_agreement", "invalidation_clarity", "formation_chain",
    ]

    result = {}
    for dim in dims:
        vals = []
        for r in records:
            bd = r.get("quality_breakdown", {})
            val = bd.get(dim)
            if val is not None:
                vals.append((val, r["outcome"], r.get("r_multiple", 0.0) or 0.0))

        if not vals:
            result[dim] = {"error": "no data"}
            continue

        x = np.array([v[0] for v in vals])
        y = np.array([v[2] for v in vals])
        n = len(vals)

        if np.std(x) > 0 and np.std(y) > 0:
            pearson = round(float(np.corrcoef(x, y)[0, 1]), 4)
        else:
            pearson = 0.0

        mid = np.median(x)
        high = [v for v in vals if v[0] >= mid]
        low = [v for v in vals if v[0] < mid]
        high_wr = sum(1 for v in high if v[1] == "hit_target") / len(high) if high else 0.0
        low_wr = sum(1 for v in low if v[1] == "hit_target") / len(low) if low else 0.0
        val_range = (float(np.min(x)), float(np.max(x)))
        is_constant = val_range[0] == val_range[1]

        result[dim] = {
            "sample": n, "pearson_r": pearson,
            "high_evidence_wr": round(high_wr, 3),
            "low_evidence_wr": round(low_wr, 3),
            "median_value": round(float(mid), 3),
            "value_range": val_range,
            "is_constant": is_constant,
        }

    return result


# =====================================================================
# 4. QUALITY SCORE DECOMPOSITION
# =====================================================================

def quality_decomposition(records):
    breakdowns = defaultdict(list)
    for r in records:
        bd = r.get("quality_breakdown", {})
        for dim, val in bd.items():
            breakdowns[dim].append((val, r["outcome"], r.get("r_multiple", 0.0) or 0.0))

    result = {}
    for dim, vals in breakdowns.items():
        n = len(vals)
        x = np.array([v[0] for v in vals])
        y = np.array([v[2] for v in vals])

        if np.std(x) > 0 and np.std(y) > 0:
            pearson = round(float(np.corrcoef(x, y)[0, 1]), 4)
        else:
            pearson = 0.0

        sorted_vals = sorted(vals, key=lambda v: v[0])
        mid = n // 2
        high_q = sorted_vals[mid:]
        low_q = sorted_vals[:mid]
        high_wr = sum(1 for v in high_q if v[1] == "hit_target") / len(high_q) if high_q else 0.0
        low_wr = sum(1 for v in low_q if v[1] == "hit_target") / len(low_q) if low_q else 0.0
        val_range = (float(np.min(x)), float(np.max(x)))
        is_constant = val_range[0] == val_range[1]

        result[dim] = {
            "sample": n, "pearson_r": pearson,
            "high_quality_wr": round(high_wr, 3),
            "low_quality_wr": round(low_wr, 3),
            "value_range": val_range,
            "is_constant": is_constant,
        }

    return result


# =====================================================================
# 4A. AGREEMENT METADATA ANALYSIS — correlation-adjusted agreement
# =====================================================================

def agreement_metadata_analysis(records):
    """Analyze correlation-adjusted agreement vs raw agreement.

    Compares agreement_raw, agreement_adjusted, family_diversity,
    conflict_count against outcomes to verify the fix.
    """
    dims = ["agreement_raw", "agreement_adjusted", "family_diversity"]
    result = {}

    for dim in dims:
        vals = []
        for r in records:
            # Check quality_breakdown first (stored scores)
            bd = r.get("quality_breakdown", {})
            val = bd.get(dim)
            if val is None:
                # Check confirmation metadata
                conf = r.get("confirmation", {})
                val = conf.get(dim)
            if val is not None and r.get("outcome"):
                vals.append((float(val), r["outcome"], r.get("r_multiple", 0.0) or 0.0))

        if not vals:
            result[dim] = {"error": "no data"}
            continue

        x = np.array([v[0] for v in vals])
        y = np.array([v[2] for v in vals])
        n = len(vals)

        if np.std(x) > 0 and np.std(y) > 0:
            pearson = round(float(np.corrcoef(x, y)[0, 1]), 4)
        else:
            pearson = 0.0

        mid = np.median(x)
        high = [v for v in vals if v[0] >= mid]
        low = [v for v in vals if v[0] < mid]
        high_wr = sum(1 for v in high if v[1] == "hit_target") / len(high) if high else 0.0
        low_wr = sum(1 for v in low if v[1] == "hit_target") / len(low) if low else 0.0
        val_range = (float(np.min(x)), float(np.max(x)))
        is_constant = val_range[0] == val_range[1]

        result[dim] = {
            "sample": n, "pearson_r": pearson,
            "high_evidence_wr": round(high_wr, 3),
            "low_evidence_wr": round(low_wr, 3),
            "median_value": round(float(mid), 3),
            "value_range": val_range,
            "is_constant": is_constant,
        }

    # Conflict count analysis
    conflict_vals = []
    for r in records:
        conf = r.get("confirmation", {})
        cc = conf.get("conflict_count")
        if cc is not None and r.get("outcome"):
            conflict_vals.append((int(cc), r["outcome"], r.get("r_multiple", 0.0) or 0.0))

    if conflict_vals:
        x = np.array([v[0] for v in conflict_vals])
        y = np.array([v[2] for v in conflict_vals])
        n = len(conflict_vals)
        if np.std(x) > 0 and np.std(y) > 0:
            pearson = round(float(np.corrcoef(x, y)[0, 1]), 4)
        else:
            pearson = 0.0
        no_conflict = [v for v in conflict_vals if v[0] == 0]
        with_conflict = [v for v in conflict_vals if v[0] > 0]
        result["conflict_count"] = {
            "sample": n, "pearson_r": pearson,
            "no_conflict_wr": round(
                sum(1 for v in no_conflict if v[1] == "hit_target") / len(no_conflict), 3
            ) if no_conflict else 0.0,
            "with_conflict_wr": round(
                sum(1 for v in with_conflict if v[1] == "hit_target") / len(with_conflict), 3
            ) if with_conflict else 0.0,
        }

    return result


# =====================================================================
# 5. STRATEGY CORRELATION
# =====================================================================

def strategy_correlation(records):
    combos = defaultdict(list)
    for r in records:
        key = f"{r.get('setup_type', 'unknown')}|{r['regime']}"
        combos[key].append(r)

    result = {}
    for combo, trades in combos.items():
        n = len(trades)
        wins = sum(1 for t in trades if t["outcome"] == "hit_target")
        win_rate = wins / n if n else 0.0
        r_vals = [t.get("r_multiple", 0.0) or 0.0 for t in trades]
        avg_r = sum(r_vals) / len(r_vals) if r_vals else 0.0
        result[combo] = {"sample": n, "win_rate": round(win_rate, 3), "avg_r": round(avg_r, 3)}

    return result


# =====================================================================
# 6. FAILURE ANALYSIS
# =====================================================================

def failure_analysis(records):
    losses = [r for r in records if r["outcome"] == "hit_invalidation"]
    categories = defaultdict(list)

    for r in losses:
        bd = r.get("quality_breakdown", {})
        weakest_dim = min(bd, key=bd.get) if bd else "unknown"
        weakest_val = bd.get(weakest_dim, 1.0) if bd else 0.0

        if weakest_val < 0.4:
            cat = f"weak_{weakest_dim}"
        elif r.get("regime", "").startswith("RANGE") or r.get("regime") == "EXPANDING_VOLATILITY":
            cat = "range_regime"
        elif r.get("regime") == "UNKNOWN":
            cat = "unknown_regime"
        else:
            cat = f"weak_{weakest_dim}"

        categories[cat].append(r)

    result = {}
    total_losses = len(losses)
    for cat, trades in sorted(categories.items(), key=lambda x: -len(x[1])):
        n = len(trades)
        r_vals = [t.get("r_multiple", 0.0) or 0.0 for t in trades]
        avg_r = sum(r_vals) / len(r_vals) if r_vals else 0.0
        result[cat] = {
            "count": n,
            "pct": round(n / total_losses * 100, 1) if total_losses else 0.0,
            "avg_r": round(avg_r, 3),
        }

    return result, total_losses


# =====================================================================
# 7. EXIT vs ENTRY
# =====================================================================

def exit_vs_entry(records):
    winners = []
    losers = []
    for r in records:
        if r["outcome"] not in ("hit_target", "hit_invalidation"):
            continue
        bd = r.get("quality_breakdown", {})
        entry = {
            "r": r.get("r_multiple", 0.0) or 0.0,
            "bars_to_entry": r.get("bars_to_entry", 0) or 0,
            "quality": r.get("quality_score", 0.0),
            "entry_quality": bd.get("entry_quality", 0.0),
            "invalidation_clarity": bd.get("invalidation_clarity", 0.0),
        }
        if r["outcome"] == "hit_target":
            winners.append(entry)
        else:
            losers.append(entry)

    w_entry = np.mean([w["entry_quality"] for w in winners]) if winners else 0.0
    l_entry = np.mean([l["entry_quality"] for l in losers]) if losers else 0.0
    w_inv = np.mean([w["invalidation_clarity"] for w in winners]) if winners else 0.0
    l_inv = np.mean([l["invalidation_clarity"] for l in losers]) if losers else 0.0

    return {
        "winners_n": len(winners),
        "losers_n": len(losers),
        "win_entry_quality": round(w_entry, 3),
        "lose_entry_quality": round(l_entry, 3),
        "win_inv_clarity": round(w_inv, 3),
        "lose_inv_clarity": round(l_inv, 3),
        "entry_diff": round(w_entry - l_entry, 3),
        "inv_diff": round(w_inv - l_inv, 3),
        "entry_problem": l_entry < w_entry,
        "invalidation_problem": l_inv < w_inv,
    }


# =====================================================================
# 8. DATA QUALITY
# =====================================================================

def data_quality(records):
    issues = {}

    sigs = defaultdict(int)
    for r in records:
        sigs[r.get("setup_signature", "")] += 1
    issues["unique_signatures"] = len(sigs)
    issues["max_same_sig"] = max(sigs.values()) if sigs else 0
    issues["avg_same_sig"] = round(np.mean(list(sigs.values())), 1) if sigs else 0.0

    # Near-duplicate detection
    try:
        from setup_outcome_tracker import count_unique_signatures
        nd = count_unique_signatures(records)
        issues["unique_signatures_rich"] = nd.get("unique_exact", len(sigs))
        issues["unique_signatures_no_near_dup"] = nd.get("unique_no_near_dup", len(sigs))
        issues["max_repetition_rich"] = nd.get("max_repetition", issues["max_same_sig"])
        issues["near_dup_count"] = nd.get("near_dup_count", 0)
    except Exception:
        issues["unique_signatures_rich"] = len(sigs)
        issues["unique_signatures_no_near_dup"] = len(sigs)
        issues["max_repetition_rich"] = issues["max_same_sig"]
        issues["near_dup_count"] = 0

    outcomes = defaultdict(int)
    for r in records:
        outcomes[r["outcome"]] += 1
    issues["outcome_distribution"] = dict(outcomes)

    ambiguous = sum(1 for r in records if r.get("exit_reason") == "ambiguous")
    issues["ambiguous_same_bar"] = ambiguous

    eb = evidence_breakdown(records)
    constant_dims = [d for d, s in eb.items() if s.get("is_constant")]
    issues["constant_evidence_dims"] = constant_dims

    return issues


# =====================================================================
# MAIN DIAGNOSTIC
# =====================================================================

def run_diagnostic():
    records = load_backtest_records()
    print(f"Loaded {len(records)} backtest records\n")

    print("--- 1. STRATEGY CONTRIBUTION ---")
    sc = strategy_contribution(records)
    for fam, s in sorted(sc.items(), key=lambda x: x[1].get("avg_r", 0), reverse=True):
        print(f"  {fam:30s}: n={s['sample']:4d}  wr={s['win_rate']:.0%}  avgR={s['avg_r']:.3f}")

    print("\n--- 2. REGIME BREAKDOWN ---")
    rb = regime_breakdown(records)
    for reg, s in sorted(rb.items(), key=lambda x: x[1].get("avg_r", 0), reverse=True):
        print(f"  {reg:15s}: n={s['sample']:4d}  wr={s['win_rate']:.0%}  "
              f"avgR={s['avg_r']:.3f}  qual={s['avg_quality']:.3f}  q_pearson={s['quality_pearson']}")

    print("\n--- 3. EVIDENCE BREAKDOWN ---")
    eb = evidence_breakdown(records)
    for dim, s in sorted(eb.items(), key=lambda x: abs(x[1].get("pearson_r", 0)), reverse=True):
        if "error" in s:
            continue
        const_flag = " [CONSTANT]" if s.get("is_constant") else ""
        print(f"  {dim:30s}: pearson={s['pearson_r']:+.4f}  "
              f"high_wr={s['high_evidence_wr']:.0%}  low_wr={s['low_evidence_wr']:.0%}  "
              f"range={s['value_range']}{const_flag}")

    print("\n--- 4. QUALITY DECOMPOSITION ---")
    qd = quality_decomposition(records)
    for dim, s in sorted(qd.items(), key=lambda x: abs(x[1].get("pearson_r", 0)), reverse=True):
        const_flag = " [CONSTANT]" if s.get("is_constant") else ""
        print(f"  {dim:30s}: pearson={s['pearson_r']:+.4f}  "
              f"high_wr={s['high_quality_wr']:.0%}  low_wr={s['low_quality_wr']:.0%}  "
              f"range={s['value_range']}{const_flag}")

    print("\n--- 4A. AGREEMENT METADATA (CORRELATION-ADJUSTED) ---")
    amd = agreement_metadata_analysis(records)
    for dim, s in sorted(amd.items(), key=lambda x: abs(x[1].get("pearson_r", 0)), reverse=True):
        if "error" in s:
            continue
        const_flag = " [CONSTANT]" if s.get("is_constant") else ""
        if dim == "conflict_count":
            print(f"  {dim:30s}: pearson={s['pearson_r']:+.4f}  "
                  f"no_conflict_wr={s['no_conflict_wr']:.0%}  with_conflict_wr={s['with_conflict_wr']:.0%}")
        else:
            print(f"  {dim:30s}: pearson={s['pearson_r']:+.4f}  "
                  f"high_wr={s['high_evidence_wr']:.0%}  low_wr={s['low_evidence_wr']:.0%}  "
                  f"range={s['value_range']}{const_flag}")

    print("\n--- 5. STRATEGY CORRELATION ---")
    scr = strategy_correlation(records)
    for combo, s in sorted(scr.items(), key=lambda x: x[1].get("avg_r", 0), reverse=True)[:10]:
        print(f"  {combo:40s}: n={s['sample']:3d}  wr={s['win_rate']:.0%}  avgR={s['avg_r']:.3f}")

    print("\n--- 6. FAILURE ANALYSIS ---")
    fa, total_losses = failure_analysis(records)
    for cat, s in sorted(fa.items(), key=lambda x: -x[1]["count"])[:10]:
        print(f"  {cat:30s}: n={s['count']:3d}  ({s['pct']:.1f}%)  avgR={s['avg_r']:.3f}")

    print("\n--- 7. EXIT vs ENTRY ---")
    ev = exit_vs_entry(records)
    print(f"  Winners (n={ev['winners_n']}): entry_q={ev['win_entry_quality']:.3f}  inv_clarity={ev['win_inv_clarity']:.3f}")
    print(f"  Losers  (n={ev['losers_n']}): entry_q={ev['lose_entry_quality']:.3f}  inv_clarity={ev['lose_inv_clarity']:.3f}")
    print(f"  Entry problem:      {ev['entry_problem']} (diff={ev['entry_diff']:+.3f})")
    print(f"  Invalidation prob:  {ev['invalidation_problem']} (diff={ev['inv_diff']:+.3f})")

    print("\n--- 8. DATA QUALITY ---")
    dq = data_quality(records)
    for k, v in dq.items():
        print(f"  {k}: {v}")

    return records, sc, rb, eb, qd, amd, scr, fa, ev, dq


if __name__ == "__main__":
    records, sc, rb, eb, qd, amd, scr, fa, ev, dq = run_diagnostic()