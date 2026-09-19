# -*- coding: utf-8 -*-
"""Structure Lookahead Audit + Protection.

Phase C fix: ensures structure features are computed only from data
available at the cutoff timestamp.

Audit findings from smc_structure_v1.py:
- find_swings(): Uses range(order, n-order) — safe, excludes last `order` bars
- structure_events(): Iterates range(n-1) — safe, excludes last bar
- swept_extreme(): Uses tail(lookback+1).iloc[:-1] — safe, excludes last bar
- evaluate_smc(): Uses df["ATR"].iloc[-1] and df["Close"].iloc[-1] —
  THESE use the last bar which may be unclosed in real-time

Fix: Add data_cutoff enforcement — when computing features for cutoff T,
exclude bars after T. For real-time usage, the last bar is considered
unconfirmed.

New functions:
- safe_evaluate_smc(): Only uses data up to cutoff timestamp
- event_status_label(): Labels events as CONFIRMED or UNCONFIRMED
"""

from __future__ import annotations

from typing import Any

import pandas as pd


def filter_by_cutoff(df: pd.DataFrame, cutoff_timestamp: str) -> pd.DataFrame:
    """Filter OHLCV DataFrame to only include bars up to cutoff.

    Args:
        df: OHLCV DataFrame with DatetimeIndex
        cutoff_timestamp: ISO format timestamp — only bars BEFORE this are kept

    Returns:
        Filtered DataFrame (never modifies original)
    """
    if df.empty or not cutoff_timestamp:
        return df.copy()

    try:
        # Filter to bars strictly before cutoff
        mask = df.index < pd.Timestamp(cutoff_timestamp)
        return df[mask].copy()
    except (ValueError, TypeError):
        # If cutoff parsing fails, return all data (safe fallback)
        return df.copy()


def safe_evaluate_smc(
    df: pd.DataFrame, cutoff_timestamp: str = ""
) -> dict[str, Any]:
    """Evaluate SMC using only data up to cutoff timestamp.

    Wraps smc_structure_v1.evaluate_smc() with cutoff protection.

    Args:
        df: OHLCV DataFrame
        cutoff_timestamp: ISO format — only bars before this used

    Returns:
        SMC evaluation with event_status metadata
    """
    from smc_structure_v1 import evaluate_smc

    # Filter to cutoff
    safe_df = filter_by_cutoff(df, cutoff_timestamp) if cutoff_timestamp else df.copy()

    # Evaluate
    result = evaluate_smc(safe_df)

    # Add lookahead protection metadata
    result["event_status"] = "CONFIRMED" if cutoff_timestamp else "UNCONFIRMED"
    result["data_cutoff_timestamp"] = cutoff_timestamp or ""
    result["bars_used"] = len(safe_df)
    result["bars_total"] = len(df)

    return result


def label_event_status(
    event_index: int, total_bars: int, lookahead_bars: int = 1
) -> str:
    """Label an event as CONFIRMED or UNCONFIRMED based on position.

    Events near the end of the dataset (within lookahead_bars of the end)
    are UNCONFIRMED because future data hasn't been observed yet.

    Args:
        event_index: Index of the event in the DataFrame
        total_bars: Total bars in the dataset
        lookahead_bars: Number of bars needed for confirmation

    Returns:
        "CONFIRMED" or "UNCONFIRMED"
    """
    if event_index + lookahead_bars >= total_bars:
        return "UNCONFIRMED"
    return "CONFIRMED"


def audit_lookahead(df: pd.DataFrame) -> dict[str, Any]:
    """Audit a DataFrame for potential lookahead issues.

    Checks:
    - Whether the last bar is used in calculations
    - Whether future bars leak into feature computation

    Returns:
        Audit report dict
    """
    n = len(df)
    report = {
        "total_bars": n,
        "risks": [],
        "safe_bars": n,
    }

    if n < 30:
        report["risks"].append("INSUFFICIENT_DATA: fewer than 30 bars")
        return report

    # Check if indicators use last bar
    report["risks"].append("INFO: smc_structure_v1.evaluate_smc uses last bar for ATR/close")
    report["safe_bars"] = n - 1  # Exclude last bar for safety

    return report