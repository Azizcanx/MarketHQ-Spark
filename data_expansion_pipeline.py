# -*- coding: utf-8 -*-
"""
MarketHQ Data Expansion Pipeline — Phases 1-7
=================================================
Multi-asset / multi-timeframe OHLCV expansion + outcome tracking + feature coverage.

Phases:
  1. Multi-asset/multi-timeframe OHLCV fetch + store + validate
  2. Volume ratio pipeline (from signal_engine conventions)
  3. Outcome bar tracking (MFE/MAE, post-setup bars only, no lookahead)
  4. Structure engine integration (existing smc_structure_v1.py)
  5. ADX schema + calculation pipeline
  6. Feature availability matrix V2
  7. Dataset validation (PASS/WARNING/FAIL per dataset)

Research only. No live trading. No broker. No real money.
Reuses existing architecture: market_data_pipeline.py, signal_engine.py,
smc_structure_v1.py, setup_object_model.py, setup_outcome_tracker.py.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import sqlite3
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import yfinance as yf

DB_PATH = os.environ.get("MARKETHQ_DB", "/opt/markethq/market_hq.db")
DATA_DIR = Path("/opt/markethq/data")
OHLCV_DIR = DATA_DIR / "ohlcv"
ARTIFACT_DIR = DATA_DIR / "artifacts"

TIMEFRAME_MAP = {
    "5m": "5m", "15m": "15m", "1h": "60m", "4h": "4h", "1d": "1d",
}
TIMEFRAME_MINUTES = {"5m": 5, "15m": 15, "1h": 60, "4h": 240, "1d": 1440}
PERIOD = "60d"

# ─── Database helpers ───────────────────────────────────────────────────────

def get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def _dataset_key(symbol: str, timeframe: str) -> str:
    return f"{symbol}__{timeframe}"


# ─── Phase 1: OHLCV fetch + store + validate ────────────────────────────────

def fetch_symbol_timeframe(symbol: str, timeframe: str, period: str = PERIOD) -> pd.DataFrame | None:
    """Fetch OHLCV bars from yfinance. Returns DataFrame or None."""
    interval = TIMEFRAME_MAP.get(timeframe)
    if interval is None:
        raise ValueError(f"Unsupported timeframe: {timeframe}")
    try:
        ticker = yf.Ticker(symbol)
        df = ticker.history(period=period, interval=interval)
        if df.empty:
            return None
        df.columns = [str(c).split()[0] if not isinstance(c, str) else c for c in df.columns]
        cols = [c for c in ["Open", "High", "Low", "Close", "Volume"] if c in df.columns]
        df = df[cols]
        return df
    except Exception:
        return None


def validate_ohlcv_enhanced(df: pd.DataFrame, timeframe: str) -> dict[str, Any]:
    """Enhanced OHLCV validation. Returns quality dict."""
    issues = []
    warnings = []
    null_counts = {}

    if df is None or df.empty:
        return {"valid": False, "issues": ["empty dataframe"], "warnings": [], "null_counts": {}, "bar_count": 0}

    # Null checks per column
    for col in ["Open", "High", "Low", "Close", "Volume"]:
        if col in df.columns:
            nc = int(df[col].isnull().sum())
            if nc > 0:
                null_counts[col] = nc
                issues.append(f"nulls in {col}: {nc}")

    # Duplicate timestamps
    dupes = int(df.index.duplicated().sum())
    if dupes > 0:
        issues.append(f"duplicate timestamps: {dupes}")

    # Chronological ordering
    if len(df) > 1:
        sorted_idx = df.index.is_monotonic_increasing
        if not sorted_idx:
            issues.append("timestamps not sorted")

    # Missing bar detection (gaps > 1.5x expected interval)
    missing_bars = 0
    if len(df) > 1 and timeframe in TIMEFRAME_MINUTES:
        expected_min = TIMEFRAME_MINUTES[timeframe]
        diffs = df.index.to_series().diff().dropna()
        # Only check business-day hours for intraday; skip for 1d
        if timeframe != "1d":
            max_gap = timedelta(minutes=expected_min * 3)
            gaps = diffs[diffs > max_gap]
            missing_bars = sum(
                max(1, int(g.total_seconds() / 60 / expected_min) - 1)
                for g in gaps
            )

    # OHLC sanity checks
    ohlc_issues = 0
    if "High" in df.columns and "Low" in df.columns:
        bad_hl = int((df["High"] < df["Low"]).sum())
        if bad_hl > 0:
            issues.append(f"High < Low: {bad_hl} rows")
            ohlc_issues += bad_hl

    if "Open" in df.columns and "High" in df.columns and "Low" in df.columns and "Close" in df.columns:
        bad_oc = int(
            ((df["Open"] < df["Low"]) | (df["Open"] > df["High"]) |
             (df["Close"] < df["Low"]) | (df["Close"] > df["High"])).sum()
        )
        if bad_oc > 0:
            issues.append(f"Open/Close outside High-Low range: {bad_oc} rows")
            ohlc_issues += bad_oc

    # Impossible prices (negative or zero)
    neg_prices = 0
    for col in ["Open", "High", "Low", "Close"]:
        if col in df.columns:
            neg_prices += int((df[col] <= 0).sum())
    if neg_prices > 0:
        issues.append(f"non-positive prices: {neg_prices} rows")

    # Volume availability
    volume_available = "Volume" in df.columns and df["Volume"].notna().sum() > 0

    is_valid = len(issues) == 0
    status = "PASS" if is_valid else ("WARNING" if len(issues) <= 2 else "FAIL")

    return {
        "valid": is_valid,
        "status": status,
        "issues": issues,
        "warnings": warnings,
        "null_counts": null_counts,
        "bar_count": len(df),
        "duplicate_timestamps": dupes,
        "missing_bars": missing_bars,
        "ohlc_sanity_issues": ohlc_issues,
        "volume_available": volume_available,
        "data_start": df.index[0].isoformat() if hasattr(df.index[0], "isoformat") else str(df.index[0]),
        "data_end": df.index[-1].isoformat() if hasattr(df.index[-1], "isoformat") else str(df.index[-1]),
    }


def _to_native(val):
    """Convert numpy/pandas types to native Python for JSON serialization."""
    import numpy as np
    if val is None or (isinstance(val, float) and math.isnan(val)):
        return None
    try:
        if isinstance(val, (np.integer,)):
            return int(val)
        if isinstance(val, (np.floating,)):
            return float(val)
        if isinstance(val, (np.bool_,)):
            return bool(val)
        if isinstance(val, (np.ndarray,)):
            return val.tolist()
        return val
    except (TypeError, ValueError):
        return None


def _native_json(obj: Any) -> Any:
    """Recursively convert numpy types to native Python for JSON."""
    import numpy as np
    if isinstance(obj, dict):
        return {k: _native_json(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_native_json(v) for v in obj]
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating,)):
        return float(obj)
    if isinstance(obj, (np.bool_,)):
        return bool(obj)
    if isinstance(obj, (np.ndarray,)):
        return obj.tolist()
    return obj


def store_ohlcv_enhanced(df: pd.DataFrame, symbol: str, timeframe: str,
                         quality: dict[str, Any], provider: str = "yfinance") -> tuple[int | None, int | None]:
    """Store OHLCV with quality metadata. Returns (dataset_id, version_id)."""
    conn = get_db()
    cur = conn.cursor()
    now = datetime.now(timezone.utc).isoformat()
    dataset_key = _dataset_key(symbol, timeframe)

    if df is None or df.empty:
        q_json = json.dumps(_native_json({"quality": quality, "validated": False}))
        cur.execute("""
            INSERT OR IGNORE INTO market_datasets
            (dataset_key, symbol, market, timeframe, provider, source_uri, status,
             first_available_at, last_available_at, row_count, current_version_id,
             metadata_json, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, 'no_data', NULL, NULL, 0, NULL, ?, ?, ?)
        """, (dataset_key, symbol, None, timeframe, provider, None, q_json, now, now))
        conn.commit()
        conn.close()
        return None, None

    # Determine market
    market = "crypto" if "-" in symbol or symbol.endswith(".BTC") else "stock"
    if symbol.endswith(".IS"):
        market = "forex" if symbol == "EURUSD=X" else "index"

    first_at = df.index[0].isoformat() if hasattr(df.index[0], "isoformat") else str(df.index[0])
    last_at = df.index[-1].isoformat() if hasattr(df.index[-1], "isoformat") else str(df.index[-1])
    row_count = len(df)

    q_json = json.dumps(_native_json({"quality": quality, "validated": quality["valid"]}))

    # Upsert market_datasets with quality metadata
    cur.execute("""
        INSERT INTO market_datasets
        (dataset_key, symbol, market, timeframe, provider, source_uri, status,
         first_available_at, last_available_at, row_count, current_version_id,
         metadata_json, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, 'active', ?, ?, ?, NULL, ?, ?, ?)
        ON CONFLICT(dataset_key) DO UPDATE SET
            symbol=excluded.symbol, market=excluded.market, timeframe=excluded.timeframe,
            provider=excluded.provider, source_uri=excluded.source_uri, status='active',
            first_available_at=excluded.first_available_at, last_available_at=excluded.last_available_at,
            row_count=excluded.row_count, metadata_json=excluded.metadata_json,
            updated_at=excluded.updated_at
    """, (dataset_key, symbol, market, timeframe, provider, None,
          first_at, last_at, row_count, q_json, now, now))

    cur.execute("SELECT id FROM market_datasets WHERE dataset_key = ?", (dataset_key,))
    dataset_id = cur.fetchone()[0]

    # Store version
    version_key = f"v{dataset_id}_{int(time.time())}"
    content_hash = hashlib.sha256(
        json.dumps({"symbol": symbol, "timeframe": timeframe, "rows": row_count}, sort_keys=True).encode()
    ).hexdigest()[:16]

    # Store OHLCV artifact
    OHLCV_DIR.mkdir(parents=True, exist_ok=True)
    artifact_path = OHLCV_DIR / f"{dataset_key}.json"
    ohlcv_records = []
    for ts, row in df.iterrows():
        ts_str = ts.isoformat() if hasattr(ts, "isoformat") else str(ts)
        ohlcv_records.append({
            "timestamp": ts_str,
            "open": _to_native(row.get("Open", 0)),
            "high": _to_native(row.get("High", 0)),
            "low": _to_native(row.get("Low", 0)),
            "close": _to_native(row.get("Close", 0)),
            "volume": _to_native(row.get("Volume", 0)) if "Volume" in df.columns else 0,
        })
    with open(artifact_path, "w") as f:
        json.dump({"symbol": symbol, "timeframe": timeframe, "bars": ohlcv_records}, f)

    retrieval_params = json.dumps({"period": PERIOD, "interval": TIMEFRAME_MAP[timeframe], "symbol": symbol})

    cur.execute("""
        INSERT INTO market_dataset_versions
        (dataset_id, version_key, content_hash, schema_version,
         first_available_at, last_available_at, row_count, provider,
         retrieval_params_json, artifact_path, metadata_json, created_at)
        VALUES (?, ?, ?, '1.0', ?, ?, ?, ?, ?, ?, ?, ?)
    """, (dataset_id, version_key, content_hash,
          first_at, last_at, row_count, provider,
          retrieval_params, str(artifact_path),
          json.dumps(_native_json({"quality": quality}), default=str), now))

    cur.execute("SELECT id FROM market_dataset_versions WHERE version_key = ?", (version_key,))
    version_id = cur.fetchone()[0]
    cur.execute("UPDATE market_datasets SET current_version_id = ? WHERE id = ?", (version_id, dataset_id))

    conn.commit()
    conn.close()
    return dataset_id, version_id


def phase1_fetch_all() -> dict[str, Any]:
    """Phase 1: Fetch all symbol×timeframe combinations, validate, store.
    Returns summary dict."""
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT DISTINCT symbol FROM setup_outcomes ORDER BY symbol")
    symbols = [r[0] for r in cur.fetchall()]
    conn.close()

    timeframes = ["5m", "15m", "1h", "4h", "1d"]

    results = {"fetched": 0, "failed": 0, "empty": 0, "datasets": [], "summary": {}}
    total_checks = {"PASS": 0, "WARNING": 0, "FAIL": 0}

    for symbol in symbols:
        for tf in timeframes:
            print(f"  Fetching {symbol} {tf}...", end=" ")
            try:
                df = fetch_symbol_timeframe(symbol, tf)
                if df is None or df.empty:
                    print("NO DATA")
                    results["empty"] += 1
                    quality = {"valid": False, "status": "FAIL", "issues": ["no data from yfinance"], "bar_count": 0}
                    store_ohlcv_enhanced(None, symbol, tf, quality)
                    results["datasets"].append({"symbol": symbol, "timeframe": tf, "status": "no_data", "quality": quality})
                    total_checks["FAIL"] += 1
                    continue

                quality = validate_ohlcv_enhanced(df, tf)
                dataset_id, version_id = store_ohlcv_enhanced(df, symbol, tf, quality)
                status = quality["status"]
                total_checks[status] = total_checks.get(status, 0) + 1

                print(f"{status} ({quality['bar_count']} bars, issues={len(quality['issues'])})")
                results["datasets"].append({
                    "symbol": symbol, "timeframe": tf, "status": status,
                    "bar_count": quality["bar_count"], "quality": quality,
                    "dataset_id": dataset_id, "version_id": version_id,
                })
                results["fetched"] += 1
            except Exception as e:
                print(f"FAILED: {e}")
                results["failed"] += 1
                results["datasets"].append({"symbol": symbol, "timeframe": tf, "status": "error", "error": str(e)})

            time.sleep(0.1)  # rate-limit yfinance

    results["summary"] = {
        "total": len(symbols) * len(timeframes),
        "fetched": results["fetched"],
        "failed": results["failed"],
        "empty": results["empty"],
        "validation": total_checks,
        "symbols": len(symbols),
        "timeframes": len(timeframes),
    }
    return results


# ─── Phase 2: Volume ratio pipeline ─────────────────────────────────────────

def phase2_volume_ratio() -> dict[str, Any]:
    """Phase 2: Calculate volume_ratio for all stored OHLCV datasets.
    Uses signal_engine's calculate_volume_ratio convention."""
    conn = get_db()
    cur = conn.cursor()

    # Get all active datasets with their latest artifact path
    cur.execute("""
        SELECT d.dataset_key, d.symbol, d.timeframe, v.artifact_path
        FROM market_datasets d
        JOIN market_dataset_versions v ON d.current_version_id = v.id
        WHERE d.status = 'active'
    """)
    datasets = cur.fetchall()
    conn.close()

    results = {"processed": 0, "no_volume": 0, "feature_stats": []}

    for dataset_key, symbol, tf, artifact_path in datasets:
        try:
            with open(artifact_path) as f:
                data = json.load(f)
            bars = data.get("bars", [])
            if not bars:
                results["no_volume"] += 1
                continue

            df = pd.DataFrame(bars)
            df["timestamp"] = pd.to_datetime(df["timestamp"])
            df = df.set_index("timestamp")

            if "volume" not in df.columns or df["volume"].sum() == 0:
                results["no_volume"] += 1
                continue

            # Use signal_engine's calculate_volume_ratio convention
            from signal_engine import calculate_volume_ratio
            vol_series = pd.Series(df["volume"].values, index=df.index)
            vr = calculate_volume_ratio(vol_series, period=20)

            # Stats
            vr_clean = vr.dropna()
            if len(vr_clean) == 0:
                results["no_volume"] += 1
                continue

            stats = {
                "dataset_key": dataset_key,
                "symbol": symbol,
                "timeframe": tf,
                "coverage": f"{(vr.notna().sum() / len(vr) * 100):.1f}%",
                "null_rate": f"{(vr.isna().sum() / len(vr) * 100):.1f}%",
                "mean": float(vr_clean.mean()),
                "median": float(vr_clean.median()),
                "std": float(vr_clean.std()),
                "min": float(vr_clean.min()),
                "max": float(vr_clean.max()),
                "outlier_rate": f"{(vr_clean.abs() > 3.0).sum() / len(vr_clean) * 100:.1f}%",
                "bars": len(df),
            }
            results["feature_stats"].append(stats)
            results["processed"] += 1
        except Exception as e:
            results["feature_stats"].append({"dataset_key": dataset_key, "error": str(e)})

    return results


# ─── Phase 3: Outcome bar tracking ──────────────────────────────────────────

def phase3_outcome_tracking() -> dict[str, Any]:
    """Phase 3: Add bar-based MFE/MAE tracking to setup_outcomes.
    Uses ONLY post-setup bars (no lookahead)."""
    conn = get_db()
    cur = conn.cursor()

    # Get setups with entry/invalidation/target + symbol/timeframe
    cur.execute("""
        SELECT id, symbol, timeframe, entry_price, invalidation_price, target_price, created_at
        FROM setup_outcomes
        WHERE entry_price IS NOT NULL
        AND outcome = 'open'
        ORDER BY created_at
    """)
    setups = cur.fetchall()

    results = {"tracked": 0, "skipped": 0, "mfe_mae_calculated": 0}

    for setup_id, symbol, tf, entry, invalidation, target, created_at in setups:
        try:
            # Get OHLCV data for this symbol/timeframe
            dataset_key = f"{symbol}__{tf}"
            cur.execute("""
                SELECT v.artifact_path FROM market_datasets d
                JOIN market_dataset_versions v ON d.current_version_id = v.id
                WHERE d.dataset_key = ?
            """, (dataset_key,))
            row = cur.fetchone()
            if not row or not row[0]:
                results["skipped"] += 1
                continue

            artifact_path = row[0]
            if not os.path.exists(artifact_path):
                results["skipped"] += 1
                continue

            with open(artifact_path) as f:
                data = json.load(f)
            bars = data.get("bars", [])
            if len(bars) < 2:
                results["skipped"] += 1
                continue

            df = pd.DataFrame(bars)
            df["timestamp"] = pd.to_datetime(df["timestamp"])
            df = df.set_index("timestamp").sort_index()

            # Find the bar index where the setup was created
            setup_time = pd.to_datetime(created_at)
            # Handle timezone mismatch: make setup_time tz-aware if data is
            try:
                if setup_time.tzinfo is None and df.index.tz is not None:
                    setup_time = setup_time.tz_localize(str(df.index.tz))
            except Exception:
                pass
            # Only use bars AFTER the setup timestamp
            post_bars = df[df.index > setup_time]
            if len(post_bars) < 1:
                results["skipped"] += 1
                continue

            # Calculate MFE/MAE from post-setup bars only
            if invalidation and entry and invalidation != 0:
                rr_distance = abs(entry - invalidation)
            else:
                rr_distance = None

            max_favorable = 0.0
            max_adverse = 0.0
            bars_to_mfe = None
            bars_to_mae = None

            for i, (_, bar) in enumerate(post_bars.iterrows(), 1):
                high = float(bar.get("high", 0))
                low = float(bar.get("low", 0))
                close = float(bar.get("close", 0))

                # For LONG setups (entry < target): favorable = high above entry
                # For SHORT setups (entry > target): favorable = low below entry
                if target and entry and target > entry:
                    # LONG
                    f = high - entry
                    a = entry - low
                elif target and entry and target < entry:
                    # SHORT
                    f = entry - low
                    a = high - entry
                else:
                    # Unknown direction: use max excursion from entry
                    f = max(high - entry, entry - low)
                    a = max(entry - low, high - entry)

                if f > max_favorable:
                    max_favorable = f
                    bars_to_mfe = i
                if a > max_adverse:
                    max_adverse = a
                    bars_to_mae = i

            # Convert to R multiples
            mfe_r = None
            mae_r = None
            if rr_distance and rr_distance > 0:
                mfe_r = round(max_favorable / rr_distance, 2) if max_favorable > 0 else 0.0
                mae_r = round(max_adverse / rr_distance, 2) if max_adverse > 0 else 0.0

            # Update setup_outcomes
            cur.execute("""
                UPDATE setup_outcomes SET
                    max_favorable = ?, max_adverse = ?,
                    metadata_json = json_set(
                        COALESCE(metadata_json, '{}'),
                        '$.mfe_bars', ?,
                        '$.mae_bars', ?,
                        '$.mfe_r', ?,
                        '$.mae_r', ?,
                        '$.bars_tracked', ?
                    ),
                    updated_at = ?
                WHERE id = ?
            """, (
                round(max_favorable, 4) if max_favorable > 0 else None,
                round(max_adverse, 4) if max_adverse > 0 else None,
                bars_to_mfe, bars_to_mae,
                mfe_r, mae_r,
                len(post_bars),
                datetime.now(timezone.utc).isoformat(),
                setup_id,
            ))
            results["tracked"] += 1
            if mfe_r is not None:
                results["mfe_mae_calculated"] += 1

        except Exception as e:
            results["skipped"] += 1

    conn.commit()
    conn.close()
    return results


# ─── Phase 4: Structure engine integration ──────────────────────────────────

def phase4_structure_integration() -> dict[str, Any]:
    """Phase 4: Verify structure engine integration.
    Checks that smc_structure_v1 produces aligned timestamps."""
    conn = get_db()
    cur = conn.cursor()

    # Get distinct symbol/timeframe combos with data
    cur.execute("""
        SELECT d.dataset_key, d.symbol, d.timeframe, v.artifact_path
        FROM market_datasets d
        JOIN market_dataset_versions v ON d.current_version_id = v.id
    """)
    datasets = cur.fetchall()
    conn.close()

    results = {"checked": 0, "structure_events": 0, "alignment_issues": 0}

    from smc_structure_v1 import find_swings, structure_events, SWING_ORDER, evaluate_smc
    from signal_engine import add_indicators, DEFAULT_CONFIG

    for dataset_key, symbol, tf, artifact_path in datasets:
        try:
            dataset_key = f"{symbol}__{tf}"
            artifact_path = OHLCV_DIR / f"{dataset_key}.json"
            if not artifact_path.exists():
                continue

            with open(artifact_path) as f:
                data = json.load(f)
            bars = data.get("bars", [])
            if len(bars) < 30:
                continue

            df = pd.DataFrame(bars)
            df["timestamp"] = pd.to_datetime(df["timestamp"])
            df = df.set_index("timestamp")
            # Rename lowercase columns to match signal_engine convention
            df = df.rename(columns={"open": "Open", "high": "High", "low": "Low", "close": "Close", "volume": "Volume"})
            df = add_indicators(df, DEFAULT_CONFIG)

            # Check structure events
            swings = find_swings(df, order=SWING_ORDER)
            atr = float(df["ATR"].iloc[-1]) if "ATR" in df.columns else 0
            events = structure_events(df, swings, atr) if atr > 0 else []

            results["checked"] += 1
            results["structure_events"] += len(events)

            # Check timestamp alignment — all events must be at or before the last bar
            for ev in events:
                ev_idx = ev.get("idx", -1)
                if ev_idx >= len(df):
                    results["alignment_issues"] += 1

        except Exception:
            results["skipped"] = results.get("skipped", 0) + 1

    return results


# ─── Phase 5: ADX schema + calculation ──────────────────────────────────────

def add_adx_schema() -> dict[str, Any]:
    """Phase 5: Add ADX to setup_outcomes schema if missing."""
    conn = get_db()
    cur = conn.cursor()

    # Check if column exists
    cols = [r[1] for r in cur.execute("PRAGMA table_info(setup_outcomes)").fetchall()]
    added = []

    if "adx_value" not in cols:
        cur.execute("ALTER TABLE setup_outcomes ADD COLUMN adx_value REAL")
        added.append("adx_value")
    if "adx_trend" not in cols:
        cur.execute("ALTER TABLE setup_outcomes ADD COLUMN adx_trend TEXT")
        added.append("adx_trend")

    # Also add to market_datasets for per-dataset ADX tracking
    ds_cols = [r[1] for r in cur.execute("PRAGMA table_info(market_datasets)").fetchall()]
    if "adx_value" not in ds_cols:
        cur.execute("ALTER TABLE market_datasets ADD COLUMN adx_value REAL")
        added.append("market_datasets.adx_value")

    conn.commit()
    conn.close()
    return {"added_columns": added}


def calculate_adx(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """Calculate ADX from OHLCV data. Returns ADX series."""
    high = pd.Series(df["High"].values, index=df.index)
    low = pd.Series(df["Low"].values, index=df.index)
    close = pd.Series(df["Close"].values, index=df.index)

    # True Range
    tr1 = high - low
    tr2 = (high - close.shift(1)).abs()
    tr3 = (low - close.shift(1)).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

    # DM+ and DM-
    up_move = high - high.shift(1)
    down_move = low.shift(1) - low

    dm_plus = up_move.where((up_move > down_move) & (up_move > 0), 0.0)
    dm_minus = down_move.where((down_move > up_move) & (down_move > 0), 0.0)

    # Smoothed averages
    atr = tr.ewm(alpha=1/period, adjust=False).mean()
    dm_plus_smooth = dm_plus.ewm(alpha=1/period, adjust=False).mean()
    dm_minus_smooth = dm_minus.ewm(alpha=1/period, adjust=False).mean()

    # DI+ and DI-
    di_plus = 100 * (dm_plus_smooth / atr)
    di_minus = 100 * (dm_minus_smooth / atr)

    # DX
    dx = 100 * ((di_plus - di_minus).abs() / (di_plus + di_minus)).replace([np.inf, -np.inf], np.nan)

    # ADX = smoothed DX
    adx = dx.ewm(alpha=1/period, adjust=False).mean()

    return adx


def phase5_adx_pipeline() -> dict[str, Any]:
    """Phase 5: Calculate ADX for all active datasets."""
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        SELECT d.dataset_key, d.symbol, d.timeframe, v.artifact_path
        FROM market_datasets d
        JOIN market_dataset_versions v ON d.current_version_id = v.id
    """)
    datasets = cur.fetchall()
    conn.close()

    results = {"calculated": 0, "missing_volume": 0, "stats": []}

    for dataset_key, symbol, tf, artifact_path in datasets:
        try:
            path = Path(artifact_path) if artifact_path else OHLCV_DIR / f"{dataset_key}.json"
            if not path.exists():
                continue

            with open(path) as f:
                data = json.load(f)
            bars = data.get("bars", [])
            if len(bars) < 30:
                continue

            df = pd.DataFrame(bars)
            df["timestamp"] = pd.to_datetime(df["timestamp"])
            df = df.set_index("timestamp")
            # Rename lowercase columns to match calculation conventions
            df = df.rename(columns={"open": "Open", "high": "High", "low": "Low", "close": "Close", "volume": "Volume"})

            adx = calculate_adx(df)
            adx_clean = adx.dropna()

            if len(adx_clean) == 0:
                continue

            stats = {
                "dataset_key": dataset_key,
                "symbol": symbol,
                "timeframe": tf,
                "coverage": f"{(adx.notna().sum() / len(adx) * 100):.1f}%",
                "null_rate": f"{(adx.isna().sum() / len(adx) * 100):.1f}%",
                "mean": float(adx_clean.mean()),
                "median": float(adx_clean.median()),
                "min": float(adx_clean.min()),
                "max": float(adx_clean.max()),
                "regime_strong_trend": f"{((adx_clean > 25).sum() / len(adx_clean) * 100):.1f}%",
            }
            results["stats"].append(stats)
            results["calculated"] += 1

            # Store latest ADX value in market_datasets
            latest_adx = float(adx_clean.iloc[-1]) if len(adx_clean) > 0 else None
            if latest_adx is not None:
                try:
                    conn2 = get_db()
                    cur2 = conn2.cursor()
                    adx_trend = "strong" if latest_adx > 25 else ("weak" if latest_adx > 20 else "no_trend")
                    cur2.execute("UPDATE market_datasets SET adx_value = ?, adx_trend = ? WHERE dataset_key = ?",
                                 (latest_adx, adx_trend, dataset_key))
                    # Also update setup_outcomes for this symbol/timeframe
                    cur2.execute("""
                        UPDATE setup_outcomes SET adx_value = ?, adx_trend = ?
                        WHERE symbol = ? AND timeframe = ? AND adx_value IS NULL
                    """, (latest_adx, adx_trend, symbol, tf))
                    conn2.commit()
                    conn2.close()
                except Exception:
                    pass
        except Exception as e:
            results["stats"].append({"dataset_key": dataset_key, "error": str(e)})

    return results


# ─── Phase 6: Feature availability matrix V2 ────────────────────────────────

def phase6_feature_matrix_v2() -> dict[str, Any]:
    """Phase 6: Generate feature availability matrix V2."""
    conn = get_db()
    cur = conn.cursor()

    # Count total setups
    cur.execute("SELECT COUNT(*) FROM setup_outcomes")
    total_setups = cur.fetchone()[0]

    # Count non-null per feature column
    features = [
        "atr_pct", "zone_width_atr", "touches", "structure_type", "liquidity_side",
        "max_favorable", "max_adverse", "adx_value", "hit_target", "hit_invalidation",
        "pnl_pct", "quality_score",
    ]

    feature_stats = {}
    for feat in features:
        cur.execute(f"""
            SELECT COUNT(*) as total,
                   SUM(CASE WHEN {feat} IS NOT NULL THEN 1 ELSE 0 END) as non_null,
                   SUM(CASE WHEN {feat} IS NULL THEN 1 ELSE 0 END) as null_count
            FROM setup_outcomes
        """)
        row = cur.fetchone()
        total, non_null, null_count = row[0], row[1], row[2]
        coverage = (non_null / total * 100) if total > 0 else 0
        null_rate = (null_count / total * 100) if total > 0 else 0
        feature_stats[feat] = {
            "total": total, "non_null": non_null, "null_count": null_count,
            "coverage": f"{coverage:.1f}%", "null_rate": f"{null_rate:.1f}%",
        }

    # Dataset coverage
    cur.execute("SELECT COUNT(*) FROM market_datasets WHERE status = 'active'")
    active_datasets = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM market_datasets")
    total_datasets = cur.fetchone()[0]

    conn.close()

    return {
        "total_setups": total_setups,
        "active_datasets": active_datasets,
        "total_datasets": total_datasets,
        "features": feature_stats,
    }


# ─── Phase 7: Dataset validation ────────────────────────────────────────────

def phase7_dataset_validation() -> dict[str, Any]:
    """Phase 7: Validate all datasets with PASS/WARNING/FAIL."""
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        SELECT d.dataset_key, d.symbol, d.timeframe, v.artifact_path, d.row_count
        FROM market_datasets d
        JOIN market_dataset_versions v ON d.current_version_id = v.id
    """)
    datasets = cur.fetchall()
    conn.close()

    results = {"validated": 0, "pass": 0, "warning": 0, "fail": 0, "details": []}

    for dataset_key, symbol, tf, artifact_path, row_count in datasets:
        checks = {
            "ohlc_valid": True,
            "timestamps_sorted": True,
            "no_duplicates": True,
            "expected_spacing": True,
            "volume_available": False,
            "sufficient_bars": row_count >= 20,
            "no_impossible_prices": True,
            "no_future_leakage": True,
        }

        if not artifact_path:
            results["fail"] += 1
            results["details"].append({"dataset_key": dataset_key, "status": "FAIL", "issues": ["no artifact"]})
            continue

        path = Path(artifact_path)
        if not path.exists():
            results["fail"] += 1
            results["details"].append({"dataset_key": dataset_key, "status": "FAIL", "issues": ["artifact missing"]})
            continue

        try:
            with open(path) as f:
                data = json.load(f)
            bars = data.get("bars", [])
            if len(bars) < 20:
                checks["sufficient_bars"] = False

            df = pd.DataFrame(bars)
            df["timestamp"] = pd.to_datetime(df["timestamp"])
            df = df.set_index("timestamp").sort_index()
            df = df.rename(columns={"open": "Open", "high": "High", "low": "Low", "close": "Close", "volume": "Volume"})

            # OHLC valid
            for col in ["Open", "High", "Low", "Close"]:
                if col not in df.columns or df[col].isnull().any():
                    checks["ohlc_valid"] = False

            # Timestamps sorted
            if not df.index.is_monotonic_increasing:
                checks["timestamps_sorted"] = False

            # No duplicates
            if df.index.duplicated().any():
                checks["no_duplicates"] = False

            # Volume available
            if "Volume" in df.columns and df["Volume"].notna().sum() > 0:
                checks["volume_available"] = True

            # Impossible prices
            if ((df["High"] < df["Low"]) | (df["Open"] <= 0) | (df["Close"] <= 0)).any():
                checks["no_impossible_prices"] = False

            # Future leakage check
            if df.index.max() > pd.Timestamp.now(tz="UTC"):
                checks["no_future_leakage"] = False

            # Overall status
            failed = sum(1 for v in checks.values() if not v)
            if failed == 0:
                status = "PASS"
            elif failed <= 2:
                status = "WARNING"
            else:
                status = "FAIL"

            results[status.lower()] += 1
            results["validated"] += 1
            results["details"].append({
                "dataset_key": dataset_key, "symbol": symbol, "timeframe": tf,
                "status": status, "checks": checks, "bar_count": len(df),
            })

        except Exception as e:
            results["fail"] += 1
            results["details"].append({"dataset_key": dataset_key, "status": "FAIL", "issues": [str(e)]})

    return results


# ─── Main runner ────────────────────────────────────────────────────────────

def run_all_phases() -> dict[str, Any]:
    """Run all phases 1-7 and return summary."""
    print("=" * 60)
    print("MARKETHQ DATA EXPANSION PIPELINE — Phases 1-7")
    print("=" * 60)

    # Phase 1
    print("\n>>> Phase 1: Multi-asset OHLCV fetch + store + validate")
    p1 = phase1_fetch_all()

    # Phase 2
    print("\n>>> Phase 2: Volume ratio pipeline")
    p2 = phase2_volume_ratio()

    # Phase 3
    print("\n>>> Phase 3: Outcome bar tracking (MFE/MAE)")
    p3 = phase3_outcome_tracking()

    # Phase 4
    print("\n>>> Phase 4: Structure engine integration")
    p4 = phase4_structure_integration()

    # Phase 5
    print("\n>>> Phase 5: ADX schema + calculation")
    p5_schema = add_adx_schema()
    p5_adx = phase5_adx_pipeline()

    # Phase 6
    print("\n>>> Phase 6: Feature availability matrix V2")
    p6 = phase6_feature_matrix_v2()

    # Phase 7
    print("\n>>> Phase 7: Dataset validation")
    p7 = phase7_dataset_validation()

    summary = {
        "phase1_ohlcv": p1,
        "phase2_volume": p2,
        "phase3_outcome": p3,
        "phase4_structure": p4,
        "phase5_adx": {"schema": p5_schema, "pipeline": p5_adx},
        "phase6_feature_matrix": p6,
        "phase7_validation": p7,
    }

    # Write summary to file
    report_path = ARTIFACT_DIR / "data_expansion_report.json"
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    with open(report_path, "w") as f:
        json.dump(summary, f, indent=2, default=str)

    print(f"\nReport saved to {report_path}")
    return summary


if __name__ == "__main__":
    result = run_all_phases()
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(json.dumps(result, indent=2, default=str))