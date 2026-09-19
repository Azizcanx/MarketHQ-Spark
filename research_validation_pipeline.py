# -*- coding: utf-8 -*-
"""Phase G — Research Validation Pipeline + Historical Backtest.

Orchestrates the full Phase G validation flow on real historical data:

1. Fetch OHLCV data (yfinance)
2. Generate setups at historical cutoff points (Phase D/E/F logic)
3. Replay each setup against future bars (Phase G replay)
4. Compute validation metrics
5. Walk-forward validation
6. Failure analysis
7. Claim validation
8. Machine-readable JSON output

Research-only. No trading, no broker, no live execution.
"""

from __future__ import annotations

import json, os, sys, uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
os.chdir(str(Path(__file__).parent))

from market_data_pipeline import fetch_symbol_timeframe, validate_ohlcv
from opportunity_model import ResearchBackedSetup, Direction
from research_setup_phase_f import build_research_backed_setup
from research_validation_engine import (
    analyze_failures,
    audit_lookahead,
    compute_validation_metrics,
    replay_setup,
    validate_claims,
    validate_setups,
    walk_forward_validation,
)
from research_validation_model import (
    HistoricalOutcome,
    ResearchClaim,
    ValidationMetrics,
)

BACKTEST_DIR = Path(__file__).parent / "backtest_results"


# ═══════════════════════════════════════════════════════════════
# SETUP GENERATOR (historical cutoff)
# ═══════════════════════════════════════════════════════════════

def generate_setups_at_cutoff(
    df: pd.DataFrame,
    cutoff_idx: int,
    symbol: str = "THYAO.IS",
    timeframe: str = "1h",
) -> list[ResearchBackedSetup]:
    """Generate ResearchBackedSetups at a historical cutoff point.

    Uses bars up to cutoff_idx for setup generation,
    bars after cutoff_idx for outcome replay.
    """
    setup_df = df.iloc[: cutoff_idx + 1].copy()
    if len(setup_df) < 50:
        return []

    try:
        from signal_engine import add_indicators, DEFAULT_CONFIG
        setup_df = add_indicators(setup_df, DEFAULT_CONFIG)
    except Exception:
        pass

    regime = "TRENDING_UP"
    sma_20 = setup_df["Close"].rolling(20).mean().iloc[-1] if len(setup_df) >= 20 else np.nan
    sma_50 = setup_df["Close"].rolling(50).mean().iloc[-1] if len(setup_df) >= 50 else np.nan
    if not np.isnan(sma_20) and not np.isnan(sma_50):
        regime = "TRENDING_UP" if sma_20 > sma_50 else "TRENDING_DOWN"
    elif setup_df["Close"].iloc[-1] > setup_df["Close"].iloc[max(0, len(setup_df) - 20)]:
        regime = "TRENDING_UP"
    else:
        regime = "TRENDING_DOWN"

    last_row = setup_df.iloc[-1]
    opp = type(
        "Opportunity",
        (),
        {
            "opportunity_id": f"OPP-HIST-{cutoff_idx}",
            "symbol": symbol,
            "timeframe": timeframe,
            "direction": "LONG" if regime == "TRENDING_UP" else "SHORT",
            "regime": regime,
            "confidence": 0.65,
            "uncertainty": 0.35,
            "thesis": "Phase G historical backtest",
            "supporting_evidence": ["trend", "momentum"],
            "conflicting_evidence": [],
            "unavailable_evidence": [],
            "strategy_families": ["trend_following"],
            "strategy_count": 1,
            "independent_families": 1,
            "correlated_families": 0,
            "source_agents": [{"agent_id": "trend_agent", "direction": "LONG" if regime == "TRENDING_UP" else "SHORT", "confidence": 0.65}],
            "feature_snapshot_id": f"FS-{symbol}-{timeframe}-{cutoff_idx}",
            "entry_zone_low": float(last_row.get("Close", 0)) * 0.998,
            "entry_zone_high": float(last_row.get("Close", 0)) * 1.002,
            "entry_reference": float(last_row.get("Close", 0)),
            "detected_at": datetime.now(timezone.utc).isoformat(),
            "status": "DETECTED",
            "metadata": {},
        },
    )()

    snap_id = f"FS-{symbol}-{timeframe}-{cutoff_idx}"
    setup = build_research_backed_setup(opp, df=setup_df, cutoff_idx=cutoff_idx, feature_snapshot_id=snap_id)
    return [setup]


# ═══════════════════════════════════════════════════════════════
# HISTORICAL BACKTEST
# ═══════════════════════════════════════════════════════════════

def run_historical_backtest(
    symbol: str = "THYAO.IS",
    timeframe: str = "1h",
    period: str = "60d",
    stride: int = 24,
) -> dict[str, Any]:
    """Run full historical backtest: generate setups at cutoffs, replay, validate.

    Args:
        symbol: Asset symbol (yfinance format)
        timeframe: TF string
        period: yfinance period
        stride: bars between cutoff points

    Returns:
        Full backtest result dict
    """
    now = datetime.now(timezone.utc).isoformat()
    print(f"  Simge: {symbol} | TF: {timeframe} | Periyot: {period}")

    # 1. Fetch data
    df = fetch_symbol_timeframe(symbol, timeframe, period=period)
    if df is None or df.empty:
        return {"error": f"No data for {symbol} {timeframe}", "outcomes": []}

    valid, issues = validate_ohlcv(df)
    if issues:
        print(f"  Veri uyari: {issues}")

    # 2. Generate setups at stride intervals
    cutoffs = list(range(50, len(df) - 10, stride))
    all_setups: list[ResearchBackedSetup] = []
    for ci in cutoffs:
        setups = generate_setups_at_cutoff(df, ci, symbol=symbol, timeframe=timeframe)
        all_setups.extend(setups)

    print(f"  {len(all_setups)} setup uretildi ({len(cutoffs)} cutoff)")

    # 3. Replay each setup
    outcomes: list[HistoricalOutcome] = []
    for setup in all_setups:
        cutoff_idx = min(
            max(0, int(setup.feature_snapshot_id.split("-")[-1]) if setup.feature_snapshot_id.split("-")[-1].isdigit() else 50),
            len(df) - 2,
        )
        outcome = replay_setup(setup, df, cutoff_idx)
        outcomes.append(outcome)

    # 4. Validation metrics
    metrics = compute_validation_metrics(outcomes)

    # 5. Walk-forward
    wf_results = walk_forward_validation(all_setups, df)

    # 6. Failure analysis
    failures = analyze_failures(outcomes)

    # 7. Lookahead audit
    lookahead = audit_lookahead(all_setups, df, cutoffs[0] if cutoffs else 50)

    # 8. Claims
    claims = _build_claims()
    claim_results = validate_claims(claims, outcomes)
    claim_results = [c.to_dict() for c in claim_results]

    # 9. Assemble
    result = {
        "pipeline": "Phase G — Research Validation + Historical Backtest",
        "run_at": now,
        "symbol": symbol,
        "timeframe": timeframe,
        "period": period,
        "data_bars": len(df),
        "cutoffs_used": len(cutoffs),
        "setups_generated": len(all_setups),
        "outcomes": _outcomes_to_list(outcomes),
        "metrics": _metrics_to_dict(metrics),
        "walk_forward": _wf_to_dict(wf_results),
        "failures": failures,
        "lookahead_audit": lookahead,
        "claims": claim_results,
        "data_sufficiency": metrics.data_sufficiency if hasattr(metrics, 'data_sufficiency') else "UNAVAILABLE",
    }
    return result


# ═══════════════════════════════════════════════════════════════
# CLAIMS
# ═══════════════════════════════════════════════════════════════

def _build_claims() -> list[ResearchClaim]:
    return [
        ResearchClaim(
            claim_id="CLAIM-001-G",
            claim_text="High-quality setups had higher T1 hit rate.",
            claim_type="hypothesis",
            status="UNTESTED",
            evidence=[],
            sample_size=0,
            validation_window="",
            confidence=0.0,
            uncertainty=1.0,
        ),
        ResearchClaim(
            claim_id="CLAIM-002-G",
            claim_text="Agent direction confidence correlates with outcome.",
            claim_type="hypothesis",
            status="UNTESTED",
            evidence=[],
            sample_size=0,
            validation_window="",
            confidence=0.0,
            uncertainty=1.0,
        ),
        ResearchClaim(
            claim_id="CLAIM-003-G",
            claim_text="T1 hit rate exceeds T2+T3 combined rate.",
            claim_type="hypothesis",
            status="UNTESTED",
            evidence=[],
            sample_size=0,
            validation_window="",
            confidence=0.0,
            uncertainty=1.0,
        ),
        ResearchClaim(
            claim_id="CLAIM-004-G",
            claim_text="Invalidation hit rate is below 40%.",
            claim_type="hypothesis",
            status="UNTESTED",
            evidence=[],
            sample_size=0,
            validation_window="",
            confidence=0.0,
            uncertainty=1.0,
        ),
        ResearchClaim(
            claim_id="CLAIM-005-G",
            claim_text="Walk-forward metrics are stable across windows.",
            claim_type="hypothesis",
            status="UNTESTED",
            evidence=[],
            sample_size=0,
            validation_window="",
            confidence=0.0,
            uncertainty=1.0,
        ),
    ]


# ═══════════════════════════════════════════════════════════════
# SERIALIZERS
# ═══════════════════════════════════════════════════════════════

def _outcomes_to_list(outcomes: list[HistoricalOutcome]) -> list[dict[str, Any]]:
    return [o.to_dict() for o in outcomes]


def _metrics_to_dict(metrics: ValidationMetrics) -> dict[str, Any]:
    return metrics.to_dict()


def _wf_to_dict(wf_results: list[dict[str, Any]]) -> dict[str, Any]:
    if not wf_results:
        return {"windows": 0, "stable": False, "drift_detected": False}
    return {
        "windows": len(wf_results),
        "stable": all(w.get("stable", False) for w in wf_results),
        "drift_detected": any(w.get("drift_detected", False) for w in wf_results),
        "per_window": [
            {"window": w.get("window", i), "entry_rate": w.get("entry_rate"), "t1_hit_rate": w.get("t1_hit_rate")}
            for i, w in enumerate(wf_results)
        ],
    }


# ═══════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════

def main() -> None:
    print("=" * 60)
    print("Phase G — Research Validation Pipeline + Historical Backtest")
    print("=" * 60)

    symbol = os.environ.get("MHQ_SYMBOL", "THYAO.IS")
    tf = os.environ.get("MHQ_TIMEFRAME", "1h")
    period = os.environ.get("MHQ_PERIOD", "60d")
    stride = int(os.environ.get("MHQ_STRIDE", "24"))

    result = run_historical_backtest(symbol=symbol, timeframe=tf, period=period, stride=stride)

    # Save JSON
    BACKTEST_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    json_path = BACKTEST_DIR / f"backtest_{symbol.replace('.', '_')}_{tf}_{ts}.json"
    with open(json_path, "w") as f:
        json.dump(result, f, indent=2, default=str, ensure_ascii=False)

    # Summary
    metrics = result.get("metrics", {})
    print(f"\n  Sonuc: {json_path}")
    print(f"  Setup: {result.get('setups_generated', 0)}")
    print(f"  Outcome: {result.get('outcomes', []) and len(result['outcomes'])}")
    print(f"  T1 hit rate: {metrics.get('target_1_hit_rate', 'N/A')}")
    print(f"  T2 hit rate: {metrics.get('target_2_hit_rate', 'N/A')}")
    print(f"  T3 hit rate: {metrics.get('target_3_hit_rate', 'N/A')}")
    print(f"  Entry rate: {metrics.get('entry_rate', 'N/A')}")
    print(f"  Realized R: {metrics.get('realized_r_mean', 'N/A')}")
    print(f"  Data sufficiency: {result.get('data_sufficiency', 'N/A')}")
    print(f"  Claims validated: {len(result.get('claims', []))}")
    print(f"  Walk-forward windows: {result.get('walk_forward', {}).get('windows', 0)}")
    print("=" * 60)


if __name__ == "__main__":
    main()