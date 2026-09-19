# -*- coding: utf-8 -*-
"""
MarketHQ Setup Outcome Tracker V1
====================================

Setup çalıştırma sonuçlarını kaydeder (research-only).
Setup signature → outcome ilişkisini tutar.
Adaptive brain bu veriyi kullanır.

Schema (DB tablosu: setup_outcomes):
  - setup_signature: setup_type + regime + direction hash
  - symbol, timeframe
  - entry_price, invalidation, target
  - outcome: hit_target | hit_invalidation | open | abandoned
  - pnl_pct, duration_bars
  - quality_score: setup üretildiğinde ölçülmüş quality
  - created_at

Research only. Canli islem yok.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DB_PATH = Path(__file__).resolve().parent / "market_hq.db"
TABLE_NAME = "setup_outcomes"


def _db() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout = 60000")
    return conn


def ensure_table() -> None:
    """Create setup_outcomes table if not exists. Add new columns if missing."""
    conn = _db()
    conn.execute(f"""
        CREATE TABLE IF NOT EXISTS {TABLE_NAME} (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            setup_signature TEXT NOT NULL,
            symbol TEXT NOT NULL,
            timeframe TEXT NOT NULL,
            setup_type TEXT NOT NULL,
            regime TEXT NOT NULL,
            direction TEXT NOT NULL,
            entry_price REAL,
            invalidation_price REAL,
            target_price REAL,
            quality_score REAL,
            outcome TEXT DEFAULT 'open',
            pnl_pct REAL,
            duration_bars INTEGER,
            max_favorable REAL,
            max_adverse REAL,
            hit_target INTEGER DEFAULT 0,
            hit_invalidation INTEGER DEFAULT 0,
            atr_pct REAL,
            zone_width_atr REAL,
            touches INTEGER,
            structure_type TEXT,
            liquidity_side TEXT,
            metadata_json TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now')),
            -- Survivorship bias metadata (Task 2)
            dataset_version TEXT DEFAULT 'v1',
            universe TEXT DEFAULT 'crypto_spot',
            universe_method TEXT DEFAULT 'yfinance',
            universe_start_date TEXT,
            universe_end_date TEXT,
            survivorship_risk TEXT DEFAULT 'low'
        )
    """)
    # Add new columns for existing tables
    _add_column_if_missing(conn, "atr_pct", "REAL")
    _add_column_if_missing(conn, "zone_width_atr", "REAL")
    _add_column_if_missing(conn, "touches", "INTEGER")
    _add_column_if_missing(conn, "structure_type", "TEXT")
    _add_column_if_missing(conn, "liquidity_side", "TEXT")
    # Survivorship bias columns (Task 2)
    _add_column_if_missing(conn, "dataset_version", "TEXT")
    _add_column_if_missing(conn, "universe", "TEXT")
    _add_column_if_missing(conn, "universe_method", "TEXT")
    _add_column_if_missing(conn, "universe_start_date", "TEXT")
    _add_column_if_missing(conn, "universe_end_date", "TEXT")
    _add_column_if_missing(conn, "survivorship_risk", "TEXT")
    conn.execute(f"CREATE INDEX IF NOT EXISTS idx_{TABLE_NAME}_sig ON {TABLE_NAME}(setup_signature)")
    conn.execute(f"CREATE INDEX IF NOT EXISTS idx_{TABLE_NAME}_sym ON {TABLE_NAME}(symbol)")
    conn.execute(f"CREATE INDEX IF NOT EXISTS idx_{TABLE_NAME}_regime ON {TABLE_NAME}(regime)")
    conn.execute(f"CREATE INDEX IF NOT EXISTS idx_{TABLE_NAME}_outcome ON {TABLE_NAME}(outcome)")
    conn.execute(f"CREATE INDEX IF NOT EXISTS idx_{TABLE_NAME}_dataset ON {TABLE_NAME}(dataset_version)")
    conn.execute(f"CREATE INDEX IF NOT EXISTS idx_{TABLE_NAME}_universe ON {TABLE_NAME}(universe)")
    conn.commit()
    conn.close()


def _add_column_if_missing(conn: sqlite3.Connection, column: str, ctype: str) -> None:
    """Add a column if it doesn't already exist in the table."""
    cols = [r[1] for r in conn.execute(f"PRAGMA table_info({TABLE_NAME})").fetchall()]
    if column not in cols:
        conn.execute(f"ALTER TABLE {TABLE_NAME} ADD COLUMN {column} {ctype}")


def _bucket_atr_pct(atr_pct: float | None) -> str:
    """Bucket ATR % into volatility categories."""
    if atr_pct is None:
        return "unknown"
    if atr_pct < 0.5:
        return "vl0_05"
    elif atr_pct < 1.0:
        return "vl0_5_1"
    elif atr_pct < 2.0:
        return "vl1_2"
    elif atr_pct < 3.0:
        return "vl2_3"
    else:
        return "vl3_up"


def _bucket_zone_width(width_atr: float) -> str:
    """Bucket zone width in ATR multiples."""
    if width_atr <= 0:
        return "unk"
    elif width_atr < 0.3:
        return "zn_narrow"
    elif width_atr < 0.7:
        return "zn_medium"
    elif width_atr < 1.5:
        return "zn_wide"
    else:
        return "zn_vwide"


def _bucket_touches(touches: int) -> str:
    """Bucket touch count."""
    if touches <= 0:
        return "t0"
    elif touches == 1:
        return "t1"
    elif touches == 2:
        return "t2"
    elif touches == 3:
        return "t3"
    else:
        return "t4+"


def _signature(
    setup_type: str,
    regime: str,
    direction: str,
    symbol: str,
    timeframe: str = "",
    atr_pct: float | None = None,
    zone_width_atr: float = 0,
    structure_type: str = "",
    liquidity_side: str = "",
    touches: int = 0,
) -> str:
    """Rich setup signature hash — groups similar setups for learning.

    Includes meaningful features: timeframe, volatility state (ATR %),
    entry formation (zone width, touches), market structure, liquidity context.
    """
    atr_bkt = _bucket_atr_pct(atr_pct)
    zwid_bkt = _bucket_zone_width(zone_width_atr)
    tch_bkt = _bucket_touches(touches)
    raw = (
        f"{setup_type}|{regime}|{direction}|{symbol}|"
        f"{timeframe}|{atr_bkt}|{zwid_bkt}|{tch_bkt}|"
        f"{structure_type}|{liquidity_side}"
    )
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def signature_components(sig: str) -> dict[str, str]:
    """Decompose a signature into its bucket components for near-dup comparison."""
    # Signatures are hashes, so we can't decompose them directly.
    # Instead, near-dup detection works on the raw component level.
    return {}


def is_near_duplicate(
    atr_pct_a: float | None, atr_pct_b: float | None,
    zone_width_a: float, zone_width_b: float,
    touches_a: int, touches_b: int,
    setup_type_a: str, setup_type_b: str,
    regime_a: str, regime_b: str,
    direction_a: str, direction_b: str,
    atr_tolerance: float = 0.3,
    zone_tolerance: float = 0.2,
) -> bool:
    """Check if two setups are near-duplicates within tolerance.

    Two setups are near-duplicates if they have the same setup_type, regime,
    direction, and their atr_pct, zone_width, and touches are within tolerance.
    """
    if setup_type_a != setup_type_b or regime_a != regime_b or direction_a != direction_b:
        return False
    if atr_pct_a is not None and atr_pct_b is not None:
        if abs(atr_pct_a - atr_pct_b) > atr_tolerance:
            return False
    elif (atr_pct_a is None) != (atr_pct_b is None):
        return False
    if abs(zone_width_a - zone_width_b) > zone_tolerance:
        return False
    if touches_a != touches_b:
        return False
    return True


def count_unique_signatures(records: list[dict]) -> dict[str, int]:
    """Count unique signatures with near-duplicate detection.

    Returns dict with 'total', 'unique', 'unique_no_near_dup', 'max_repetition'.
    """
    from collections import Counter

    # Exact signature counts
    sigs = [r.get("setup_signature", "") for r in records]
    sig_counts = Counter(sigs)

    # Near-duplicate detection: group records by (setup_type, regime, direction)
    # then check numeric closeness
    groups: dict[tuple, list[dict]] = {}
    for r in records:
        key = (r.get("setup_type", ""), r.get("regime", ""), r.get("direction", ""))
        groups.setdefault(key, []).append(r)

    near_dup_count = 0
    for key, group in groups.items():
        if len(group) <= 1:
            continue
        # Sort by atr_pct for efficient grouping
        sorted_group = sorted(group, key=lambda x: x.get("atr_pct") or 0)
        used = set()
        for i, rec in enumerate(sorted_group):
            if i in used:
                continue
            # Count this as a unique signature start, mark near-dups
            used.add(i)
            for j in range(i + 1, len(sorted_group)):
                if j in used:
                    continue
                if is_near_duplicate(
                    rec.get("atr_pct"), sorted_group[j].get("atr_pct"),
                    rec.get("zone_width_atr", 0), sorted_group[j].get("zone_width_atr", 0),
                    rec.get("touches", 0), sorted_group[j].get("touches", 0),
                    rec.get("setup_type", ""), sorted_group[j].get("setup_type", ""),
                    rec.get("regime", ""), sorted_group[j].get("regime", ""),
                    rec.get("direction", ""), sorted_group[j].get("direction", ""),
                ):
                    used.add(j)
                    near_dup_count += 1

    return {
        "total": len(records),
        "unique_exact": len(sig_counts),
        "unique_no_near_dup": len(sig_counts) - near_dup_count,
        "max_repetition": max(sig_counts.values()) if sig_counts else 0,
        "near_dup_count": near_dup_count,
    }


def record_outcome(
    setup_type: str,
    regime: str,
    direction: str,
    symbol: str,
    timeframe: str,
    entry_price: float | None = None,
    invalidation_price: float | None = None,
    target_price: float | None = None,
    quality_score: float | None = None,
    outcome: str = "open",
    pnl_pct: float | None = None,
    duration_bars: int = 0,
    max_favorable: float | None = None,
    max_adverse: float | None = None,
    metadata: dict[str, Any] | None = None,
    # Rich signature fields
    atr_pct: float | None = None,
    zone_width_atr: float = 0,
    touches: int = 0,
    structure_type: str = "",
    liquidity_side: str = "",
    # Survivorship bias metadata (Task 2)
    dataset_version: str = "v1",
    universe: str = "crypto_spot",
    universe_method: str = "yfinance",
    universe_start_date: str = "",
    universe_end_date: str = "",
    survivorship_risk: str = "low",
) -> str:
    """
    Record a setup outcome.

    Returns the setup_signature for reference.
    """
    ensure_table()
    conn = _db()
    sig = _signature(
        setup_type, regime, direction, symbol,
        timeframe=timeframe,
        atr_pct=atr_pct,
        zone_width_atr=zone_width_atr,
        structure_type=structure_type,
        liquidity_side=liquidity_side,
        touches=touches,
    )

    conn.execute(f"""
        INSERT INTO {TABLE_NAME}
            (setup_signature, symbol, timeframe, setup_type, regime, direction,
             entry_price, invalidation_price, target_price, quality_score,
             outcome, pnl_pct, duration_bars, max_favorable, max_adverse,
             hit_target, hit_invalidation,
             atr_pct, zone_width_atr, touches, structure_type, liquidity_side,
             metadata_json,
             dataset_version, universe, universe_method,
             universe_start_date, universe_end_date, survivorship_risk)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        sig, symbol, timeframe, setup_type, regime, direction,
        entry_price, invalidation_price, target_price, quality_score,
        outcome, pnl_pct, duration_bars, max_favorable, max_adverse,
        1 if outcome == "hit_target" else 0,
        1 if outcome == "hit_invalidation" else 0,
        atr_pct, zone_width_atr, touches, structure_type, liquidity_side,
        json.dumps(metadata or {}, ensure_ascii=False) if metadata else None,
        dataset_version, universe, universe_method,
        universe_start_date, universe_end_date, survivorship_risk,
    ))
    conn.commit()
    conn.close()
    return sig


def get_historical_stats(
    symbol: str = "",
    regime: str = "",
    direction: str = "",
    setup_type: str = "",
    min_samples: int = 3,
) -> dict[str, Any]:
    """
    Get historical performance for similar setups.

    Used by research setup engine for historical validation scoring.
    """
    ensure_table()
    conn = _db()

    conditions = []
    params = []
    if symbol:
        conditions.append("symbol = ?")
        params.append(symbol)
    if regime:
        conditions.append("regime = ?")
        params.append(regime)
    if direction:
        conditions.append("direction = ?")
        params.append(direction)
    if setup_type:
        conditions.append("setup_type = ?")
        params.append(setup_type)

    where = "WHERE " + " AND ".join(conditions) if conditions else ""

    # Total count
    total = conn.execute(
        f"SELECT COUNT(*) as c FROM {TABLE_NAME} {where}", params
    ).fetchone()["c"]

    if total < min_samples:
        conn.close()
        return {
            "available": total >= 1,
            "similar_count": total,
            "win_rate": None,
            "avg_return": None,
            "avg_return_20d": None,
            "best_return": None,
            "worst_return": None,
            "regime_match": regime,
            "lookup_method": "setup_signature",
            "notes": f"Yetersiz veri ({total}/{min_samples} örnek)",
        }

    # Win rate (closed outcomes only)
    closed = conn.execute(f"""
        SELECT
            COUNT(*) as total,
            SUM(CASE WHEN outcome = 'hit_target' THEN 1 ELSE 0 END) as wins,
            SUM(CASE WHEN outcome = 'hit_invalidation' THEN 1 ELSE 0 END) as losses,
            AVG(pnl_pct) as avg_pnl,
            MAX(pnl_pct) as best_pnl,
            MIN(pnl_pct) as worst_pnl
        FROM {TABLE_NAME}
        {where} AND outcome IN ('hit_target', 'hit_invalidation')
    """, params).fetchone()

    win_rate = closed["wins"] / closed["total"] if closed and closed["total"] > 0 else None
    avg_return = closed["avg_pnl"] if closed and closed["avg_pnl"] is not None else None

    # Open setups
    open_count = conn.execute(
        f"SELECT COUNT(*) as c FROM {TABLE_NAME} {where} AND outcome = 'open'",
        params,
    ).fetchone()["c"]

    conn.close()

    return {
        "available": True,
        "similar_count": total,
        "closed_count": closed["total"] if closed else 0,
        "open_count": open_count,
        "win_rate": round(win_rate, 3) if win_rate else None,
        "avg_return": round(avg_return, 2) if avg_return else None,
        "avg_return_20d": None,  # Would need time-based filtering
        "best_return": round(closed["best_pnl"], 2) if closed and closed["best_pnl"] else None,
        "worst_return": round(closed["worst_pnl"], 2) if closed and closed["worst_pnl"] else None,
        "regime_match": regime,
        "lookup_method": "setup_signature",
        "notes": f"{total} benzer setup, {closed['total'] if closed else 0} kapali",
    }


def get_outcome_summary(symbol: str = "") -> dict[str, Any]:
    """Overall outcome summary for monitoring."""
    ensure_table()
    conn = _db()
    where = "WHERE symbol = ?" if symbol else ""
    params = (symbol,) if symbol else ()

    row = conn.execute(f"""
        SELECT
            COUNT(*) as total,
            SUM(CASE WHEN outcome = 'hit_target' THEN 1 ELSE 0 END) as targets,
            SUM(CASE WHEN outcome = 'hit_invalidation' THEN 1 ELSE 0 END) as invalidations,
            SUM(CASE WHEN outcome = 'open' THEN 1 ELSE 0 END) as open,
            AVG(pnl_pct) as avg_pnl,
            AVG(quality_score) as avg_quality
        FROM {TABLE_NAME}
        {where}
    """, params).fetchone()

    conn.close()

    return {
        "total": row["total"],
        "hit_target": row["targets"],
        "hit_invalidation": row["invalidations"],
        "open": row["open"],
        "win_rate": round(row["targets"] / row["total"], 3) if row["total"] > 0 else None,
        "avg_pnl": round(row["avg_pnl"], 2) if row["avg_pnl"] else None,
        "avg_quality": round(row["avg_quality"], 3) if row["avg_quality"] else None,
    }