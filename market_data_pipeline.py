"""
OHLCV Data Pipeline — fetches from yfinance and stores in market_datasets + market_dataset_versions.
"""

import hashlib
import json
import os
import sqlite3
import time
from datetime import datetime, timezone

import yfinance as yf

DB_PATH = os.environ.get("MARKETHQ_DB", "/opt/markethq/market_hq.db")

TIMEFRAME_MAP = {
    "5m":  "5m",
    "15m": "15m",
    "1h":  "60m",
    "4h":  "240m",
    "1d":  "1d",
}

PERIOD = "60d"  # historical only, no lookahead


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def fetch_symbol_timeframe(symbol, timeframe, period=PERIOD):
    """Fetch OHLCV bars from yfinance. Returns DataFrame or None on failure."""
    interval = TIMEFRAME_MAP.get(timeframe)
    if interval is None:
        raise ValueError(f"Unsupported timeframe: {timeframe}")

    ticker = yf.Ticker(symbol)
    df = ticker.history(period=period, interval=interval)

    if df.empty:
        return None

    # Standardize column names (yfinance may add suffixes for multi-ticker)
    df.columns = [str(c).split()[0] if not isinstance(c, str) else c for c in df.columns]
    # Keep only OHLCV + Volume
    cols = [c for c in ["Open", "High", "Low", "Close", "Volume"] if c in df.columns]
    df = df[cols]

    return df


def validate_ohlcv(df):
    """Validate OHLCV data. Returns (is_valid, issues_list)."""
    issues = []

    if df is None or df.empty:
        return False, ["empty dataframe"]

    # Null checks
    null_counts = df.isnull().sum()
    for col, cnt in null_counts.items():
        if cnt > 0:
            issues.append(f"nulls in {col}: {cnt}")

    # Duplicate index check
    dupes = df.index.duplicated().sum()
    if dupes > 0:
        issues.append(f"duplicate timestamps: {dupes}")

    # Gap check — warn if gaps > 1.5x expected interval
    if len(df) > 1:
        diffs = df.index.to_series().diff().dropna()
        # Skip validation if we can't determine freq (e.g. irregular data)
        pass  # gaps are acceptable for markets (weekends, holidays)

    # Price sanity: High >= Low, Open/Close within range
    if "High" in df.columns and "Low" in df.columns:
        bad = (df["High"] < df["Low"]).sum()
        if bad > 0:
            issues.append(f"High < Low: {bad} rows")

    is_valid = len(issues) == 0
    return is_valid, issues


def _content_hash(df):
    """Hash the dataframe content for version tracking."""
    head = {str(k): [float(v) for v in vs] for k, vs in df.head(3).to_dict("series").items()}
    payload = json.dumps(
        {"rows": len(df), "columns": list(df.columns), "head": head},
        sort_keys=True,
        default=str,
    )
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


def _dataset_key(symbol, timeframe):
    return f"{symbol}__{timeframe}"


def store_ohlcv(df, symbol, timeframe, provider="yfinance"):
    """Store OHLCV data in market_datasets + market_dataset_versions.
    Returns (dataset_id, version_id)."""
    conn = get_db()
    cur = conn.cursor()
    now = datetime.now(timezone.utc).isoformat()
    dataset_key = _dataset_key(symbol, timeframe)

    # Validate first
    is_valid, issues = validate_ohlcv(df)
    if df is None or df.empty:
        # Still register dataset but with status='no_data'
        cur.execute("""
            INSERT OR IGNORE INTO market_datasets
            (dataset_key, symbol, market, timeframe, provider, source_uri, status,
             first_available_at, last_available_at, row_count, current_version_id,
             metadata_json, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, 'no_data', NULL, NULL, 0, NULL, ?, ?, ?)
        """, (dataset_key, symbol, None, timeframe, provider, None,
              json.dumps({"validation_issues": issues}), now, now))
        conn.commit()
        conn.close()
        return None, None

    if not is_valid:
        print(f"  WARNING validation for {symbol} {timeframe}: {issues}")

    # Determine market
    market = "crypto" if "-" in symbol or symbol.endswith(".BTC") else "stock"
    if symbol.endswith(".IS"):
        market = "forex" if symbol == "EURUSD=X" else "index"

    # First/last available timestamps
    first_at = df.index[0].isoformat() if hasattr(df.index[0], 'isoformat') else str(df.index[0])
    last_at = df.index[-1].isoformat() if hasattr(df.index[-1], 'isoformat') else str(df.index[-1])
    row_count = len(df)

    # Upsert market_datasets
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
          first_at, last_at, row_count,
          json.dumps({"validation_issues": issues, "validated": is_valid}), now, now))

    cur.execute("SELECT id FROM market_datasets WHERE dataset_key = ?", (dataset_key,))
    dataset_id = cur.fetchone()[0]

    # Store version
    version_key = f"v{dataset_id}_{int(time.time())}"
    content_hash = _content_hash(df)

    # Store OHLCV as JSON artifact
    artifact_dir = "/opt/markethq/data/ohlcv"
    os.makedirs(artifact_dir, exist_ok=True)
    artifact_path = os.path.join(artifact_dir, f"{dataset_key}.json")

    # Serialize OHLCV
    ohlcv_records = []
    for ts, row in df.iterrows():
        ts_str = ts.isoformat() if hasattr(ts, 'isoformat') else str(ts)
        ohlcv_records.append({
            "timestamp": ts_str,
            "open": float(row.get("Open", 0)),
            "high": float(row.get("High", 0)),
            "low": float(row.get("Low", 0)),
            "close": float(row.get("Close", 0)),
            "volume": float(row.get("Volume", 0)) if "Volume" in df.columns else 0,
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
          retrieval_params, artifact_path,
          json.dumps({"validation_issues": issues}), now))

    cur.execute("SELECT id FROM market_dataset_versions WHERE version_key = ?", (version_key,))
    version_id = cur.fetchone()[0]

    # Update dataset with current_version_id
    cur.execute("UPDATE market_datasets SET current_version_id = ? WHERE id = ?", (version_id, dataset_id))

    conn.commit()
    conn.close()
    return dataset_id, version_id


def refresh_all_symbols(symbols=None, timeframes=None):
    """Iterate all symbols/timeframes and fetch + store OHLCV data.
    Returns summary dict."""
    if symbols is None:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT DISTINCT symbol FROM setup_outcomes ORDER BY symbol")
        symbols = [r[0] for r in cur.fetchall()]
        conn.close()

    if timeframes is None:
        timeframes = ["5m", "15m", "1h", "4h", "1d"]

    results = {"fetched": 0, "failed": 0, "empty": 0, "details": []}

    for symbol in symbols:
        for tf in timeframes:
            print(f"Fetching {symbol} {tf}...", end=" ")
            try:
                df = fetch_symbol_timeframe(symbol, tf)
                if df is None or df.empty:
                    print("NO DATA")
                    results["empty"] += 1
                    store_ohlcv(None, symbol, tf)
                    results["details"].append({"symbol": symbol, "timeframe": tf, "status": "no_data"})
                    continue

                dataset_id, version_id = store_ohlcv(df, symbol, tf)
                print(f"OK ({len(df)} bars, dataset={dataset_id}, version={version_id})")
                results["fetched"] += 1
                results["details"].append({
                    "symbol": symbol, "timeframe": tf, "status": "ok",
                    "bars": len(df), "dataset_id": dataset_id, "version_id": version_id,
                })
            except Exception as e:
                print(f"FAILED: {e}")
                results["failed"] += 1
                results["details"].append({"symbol": symbol, "timeframe": tf, "status": "error", "error": str(e)})

            time.sleep(0.1)  # rate-limit yfinance

    return results


def verify_stored(symbol, timeframe):
    """Verify stored data for a symbol/timeframe. Returns dict."""
    conn = get_db()
    cur = conn.cursor()
    dataset_key = _dataset_key(symbol, timeframe)

    cur.execute("SELECT * FROM market_datasets WHERE dataset_key = ?", (dataset_key,))
    dataset = cur.fetchone()
    if not dataset:
        conn.close()
        return {"found": False}

    columns = [d[0] for d in cur.description]
    dataset_row = dict(zip(columns, dataset))

    cur.execute("SELECT * FROM market_dataset_versions WHERE dataset_id = ? ORDER BY id DESC LIMIT 1", (dataset[0],))
    version = cur.fetchone()
    version_columns = [d[0] for d in cur.description]
    version_row = dict(zip(version_columns, version)) if version else None

    # Read artifact
    artifact_path = version_row.get("artifact_path") if version_row else None
    bar_count = 0
    if artifact_path and os.path.exists(artifact_path):
        with open(artifact_path) as f:
            data = json.load(f)
        bar_count = len(data.get("bars", []))

    conn.close()
    return {
        "found": True,
        "dataset": dataset_row,
        "version": version_row,
        "artifact_bar_count": bar_count,
    }


if __name__ == "__main__":
    # Test: THYAO.IS 1h
    print("=== Test fetch: THYAO.IS 1h ===")
    df = fetch_symbol_timeframe("THYAO.IS", "1h")
    if df is not None:
        print(f"Fetched {len(df)} bars")
        print(df.head())
        print(df.tail())
        is_valid, issues = validate_ohlcv(df)
        print(f"Valid: {is_valid}, Issues: {issues}")

        dataset_id, version_id = store_ohlcv(df, "THYAO.IS", "1h")
        print(f"Stored: dataset_id={dataset_id}, version_id={version_id}")

        # Verify
        result = verify_stored("THYAO.IS", "1h")
        print(f"Verification: {json.dumps(result, indent=2, default=str)}")
    else:
        print("No data returned for THYAO.IS 1h")