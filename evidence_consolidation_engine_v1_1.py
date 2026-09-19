# -*- coding: utf-8 -*-
"""
MarketHQ Evidence Consolidation Engine V1
=========================================

Amaç
-----
Aynı stratejiye ait farklı provenance/kanıt katmanlarını tek bir research
consolidation kaydında toplar:

    - V6 pipeline / ranking
    - Eski independent strategy evidence (knowledge item 693)
    - Fresh independent research (knowledge item 694)
    - Strategy-level evidence review (en güncel review)
    - Paper evidence (dosya/DB bulunursa)

Bu motor:
    - learned_rules değiştirmez
    - claims değiştirmez
    - validations değiştirmez
    - brain_observations değiştirmez
    - knowledge verification değiştirmez
    - broker / order / execution yapmaz
    - yalnızca research consolidation tablosu + JSON raporu üretir

ÖNEMLİ
-------
Bu bir "strategy verification" motoru değildir.
Kanıt katmanlarını birleştirir, fakat "verified/proven" statüsü üretmez.

Çalıştırma:
    .venv\\Scripts\\python.exe .\\evidence_consolidation_engine_v1.py
"""

from __future__ import annotations

import hashlib
import json
import math
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


# ============================================================================
# CONFIG
# ============================================================================

PROJECT_ROOT = Path(__file__).resolve().parent
DB_PATH = PROJECT_ROOT / "market_hq.db"

PIPELINE_DIR = PROJECT_ROOT / "strategy_pipeline_results"
INDEPENDENT_DIR = PROJECT_ROOT / "independent_strategy_evidence_results"
FRESH_DIR = PROJECT_ROOT / "fresh_independent_research_results"
FINAL_DECISION_DIR = PROJECT_ROOT / "final_research_decisions"
PAPER_DIR_CANDIDATES = (
    PROJECT_ROOT / "paper_evidence_results",
    PROJECT_ROOT / "paper_trading_results",
    PROJECT_ROOT / "paper_evidence",
    PROJECT_ROOT / "reports",
)

OUTPUT_DIR = PROJECT_ROOT / "evidence_consolidation_results"

ENGINE_NAME = "MARKETHQ_EVIDENCE_CONSOLIDATION"
ENGINE_VERSION = "V1"

TARGET_STRATEGY_ID = "STR-43839FA9C6"

RESEARCH_ONLY = True
EXECUTION_ENABLED = False


# ============================================================================
# HELPERS
# ============================================================================

def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def norm(value: Any) -> str:
    return "" if value is None else str(value).strip()


def safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
        if math.isfinite(number):
            return number
    except (TypeError, ValueError):
        pass
    return default


def clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


def normalize_ratio(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number):
        return None
    if number > 1.0:
        number /= 100.0
    return clamp01(number)


def parse_json(value: Any) -> Any:
    if isinstance(value, (dict, list)):
        return value
    text = norm(value)
    if not text:
        return {}
    try:
        return json.loads(text)
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}


def compact_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
        default=str,
    )


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def file_mtime_key(path: Path) -> float:
    try:
        return path.stat().st_mtime
    except OSError:
        return 0.0


def open_db() -> sqlite3.Connection:
    if not DB_PATH.exists():
        raise FileNotFoundError(f"Database bulunamadı: {DB_PATH}")
    conn = sqlite3.connect(str(DB_PATH), timeout=60)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout = 60000")
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
    row = conn.execute(
        """
        SELECT 1
        FROM sqlite_master
        WHERE type='table' AND name=?
        LIMIT 1
        """,
        (table_name,),
    ).fetchone()
    return row is not None


def table_columns(conn: sqlite3.Connection, table_name: str) -> set[str]:
    if not table_exists(conn, table_name):
        return set()
    rows = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
    return {norm(row["name"]) for row in rows}


def latest_matching_json(
    directories: tuple[Path, ...],
    patterns: tuple[str, ...],
) -> Path | None:
    candidates: list[Path] = []
    for directory in directories:
        if not directory.exists():
            continue
        for pattern in patterns:
            candidates.extend(directory.glob(pattern))
    candidates = [item for item in candidates if item.is_file()]
    if not candidates:
        return None
    candidates.sort(key=file_mtime_key, reverse=True)
    return candidates[0]


def load_json_file(path: Path | None) -> Any:
    if path is None or not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def recursive_find_key(obj: Any, keys: tuple[str, ...]) -> Any:
    wanted = {norm(k).lower() for k in keys}
    if isinstance(obj, dict):
        for key, value in obj.items():
            if norm(key).lower() in wanted:
                return value
        for value in obj.values():
            found = recursive_find_key(value, keys)
            if found is not None:
                return found
    elif isinstance(obj, list):
        for value in obj:
            found = recursive_find_key(value, keys)
            if found is not None:
                return found
    return None


# ============================================================================
# SAFETY
# ============================================================================

def assert_research_only() -> None:
    if not RESEARCH_ONLY:
        raise RuntimeError("Safety gate: RESEARCH_ONLY=False")
    if EXECUTION_ENABLED:
        raise RuntimeError("Safety gate: EXECUTION_ENABLED=True")


# ============================================================================
# V6 PIPELINE
# ============================================================================

def load_v6_evidence(strategy_id: str) -> dict[str, Any]:
    path = latest_matching_json(
        (PIPELINE_DIR,),
        ("strategy_pipeline_v6_*.json",),
    )
    if path is None:
        return {
            "available": False,
            "file": None,
        }

    payload = load_json_file(path)
    record: dict[str, Any] | None = None

    def walk(obj: Any) -> None:
        nonlocal record
        if record is not None:
            return

        if isinstance(obj, dict):
            current_id = norm(
                obj.get("strategy_id")
                or obj.get("id")
            )
            ranking = obj.get("ranking")
            if (
                current_id.upper() == strategy_id.upper()
                and isinstance(ranking, dict)
            ):
                record = obj
                return

            for child in obj.values():
                if isinstance(child, (dict, list)):
                    walk(child)

        elif isinstance(obj, list):
            for child in obj:
                if isinstance(child, (dict, list)):
                    walk(child)
                if record is not None:
                    return

    walk(payload)

    if record is None:
        return {
            "available": False,
            "file": str(path),
            "error": "Strategy record not found",
        }

    ranking = record.get("ranking", {})
    if not isinstance(ranking, dict):
        ranking = {}

    def get_ratio(primary: str, *aliases: str) -> float | None:
        for key in (primary, *aliases):
            if key in ranking:
                return normalize_ratio(ranking.get(key))
        return None

    result = {
        "available": True,
        "file": str(path),
        "strategy_id": norm(record.get("strategy_id") or record.get("id")),
        "strategy_name": norm(
            record.get("strategy_name")
            or record.get("name")
            or record.get("title")
        ),
        "classification": norm(
            ranking.get("classification")
            or record.get("classification")
        ).upper(),
        "ranking_score": safe_float(
            ranking.get("score")
        ),
        "average_return": safe_float(
            ranking.get("average_return")
        ),
        "cross_symbol_ratio": get_ratio(
            "cross_symbol_positive_ratio",
            "cross_symbol_ratio",
        ),
        "cost_robustness": get_ratio(
            "cost_survival",
            "cost_survival_ratio",
            "cost_robustness",
        ),
        "parameter_stability": get_ratio(
            "parameter_stability",
            "parameter_stability_ratio",
        ),
        "regime_stability": get_ratio(
            "regime_stability",
            "regime_stability_ratio",
        ),
        "wfo_positive_ratio": get_ratio(
            "wfo_positive_ratio",
            "positive_wfo_ratio",
        ),
    }
    return result


# ============================================================================
# KNOWLEDGE ITEMS
# ============================================================================

def load_knowledge_item(
    conn: sqlite3.Connection,
    item_id: int,
) -> dict[str, Any]:
    if not table_exists(conn, "knowledge_items"):
        return {}

    row = conn.execute(
        "SELECT * FROM knowledge_items WHERE id=? LIMIT 1",
        (item_id,),
    ).fetchone()

    if row is None:
        return {}

    data = dict(row)
    data["metadata"] = parse_json(data.get("metadata_json"))
    data["tags"] = parse_json(data.get("tags_json"))
    return data


def _classify_symbol_result(record: dict[str, Any]) -> str:
    """
    Fresh engine records can expose the result in multiple places.
    Prefer explicit classification, then return/net_pnl, then metrics.
    """
    for key in ("result", "classification", "status", "outcome"):
        value = norm(record.get(key)).upper()
        if value in {"POSITIVE", "NEGATIVE", "INCONCLUSIVE"}:
            return value

    nested = record.get("metrics")
    if isinstance(nested, dict):
        for key in ("total_return_percent", "return_percent", "net_pnl"):
            if key in nested and nested.get(key) is not None:
                value = safe_float(nested.get(key))
                if value > 0:
                    return "POSITIVE"
                if value < 0:
                    return "NEGATIVE"
                return "INCONCLUSIVE"

    for key in (
        "total_return_percent",
        "return_percent",
        "return",
        "net_pnl",
    ):
        if key in record and record.get(key) is not None:
            value = safe_float(record.get(key))
            if value > 0:
                return "POSITIVE"
            if value < 0:
                return "NEGATIVE"
            return "INCONCLUSIVE"

    # Some Fresh V1.1 records put the value in a human-readable field.
    text = " ".join(
        norm(record.get(key))
        for key in ("result_text", "summary_text", "outcome_text")
    ).upper()

    if "POSITIVE" in text:
        return "POSITIVE"
    if "NEGATIVE" in text:
        return "NEGATIVE"

    return "INCONCLUSIVE"


def _counts_from_results(results: Any) -> tuple[int, int, int]:
    positive = negative = inconclusive = 0

    if isinstance(results, dict):
        iterable = []
        for symbol, payload in results.items():
            if isinstance(payload, dict):
                item = dict(payload)
                item.setdefault("symbol", symbol)
                iterable.append(item)
    elif isinstance(results, list):
        iterable = [item for item in results if isinstance(item, dict)]
    else:
        iterable = []

    for item in iterable:
        classification = _classify_symbol_result(item)
        if classification == "POSITIVE":
            positive += 1
        elif classification == "NEGATIVE":
            negative += 1
        else:
            inconclusive += 1

    return positive, negative, inconclusive


def _latest_fresh_source_counts() -> tuple[int, int, int, str | None]:
    path = latest_matching_json(
        (FRESH_DIR,),
        ("fresh_independent_*.json",),
    )
    if path is None:
        return 0, 0, 0, None

    payload = load_json_file(path)
    if not isinstance(payload, dict):
        return 0, 0, 0, str(path)

    positive, negative, inconclusive = _counts_from_results(
        payload.get("results")
    )

    if positive + negative + inconclusive == 0:
        # Last-resort fallback: inspect common top-level summary fields.
        summary = payload.get("summary")
        if isinstance(summary, dict):
            positive = safe_int(
                summary.get("positive_full_runs")
                or summary.get("positive_runs")
            )
            negative = safe_int(
                summary.get("negative_full_runs")
                or summary.get("negative_runs")
            )
            symbols = safe_int(summary.get("symbols_tested"))
            inconclusive = max(0, symbols - positive - negative)

    return positive, negative, inconclusive, str(path)


def extract_knowledge_summary(
    knowledge: dict[str, Any],
    fallback_source: str,
) -> dict[str, Any]:
    metadata = knowledge.get("metadata", {})
    if not isinstance(metadata, dict):
        metadata = {}

    summary = metadata.get("summary", {})
    if not isinstance(summary, dict):
        summary = {}

    content = norm(knowledge.get("content"))
    item_id = safe_int(knowledge.get("id"))

    symbols_tested = safe_int(summary.get("symbols_tested"))
    positive_full = safe_int(summary.get("positive_full_runs"))
    negative_full = safe_int(summary.get("negative_full_runs"))

    # Fresh Knowledge item 694 may not carry the aggregate counts in its
    # metadata, even though the original Fresh JSON contains the symbol
    # records. Re-read the exact latest Fresh JSON and derive counts from the
    # actual symbol-level result/return fields.
    source_path = None
    if item_id == 694 or "FRESH_INDEPENDENT" in fallback_source.upper():
        fresh_positive, fresh_negative, fresh_inconclusive, source_path = (
            _latest_fresh_source_counts()
        )
        if fresh_positive + fresh_negative + fresh_inconclusive > 0:
            positive_full = fresh_positive
            negative_full = fresh_negative
            symbols_tested = (
                fresh_positive + fresh_negative + fresh_inconclusive
            )

    if symbols_tested <= 0:
        # Content fallback for older/alternate knowledge records.
        positive_count = 0
        negative_count = 0

        for line in content.splitlines():
            stripped = line.strip().upper()
            if "RESULT=POSITIVE" in stripped:
                positive_count += 1
            elif "RESULT=NEGATIVE" in stripped:
                negative_count += 1

        if positive_count or negative_count:
            positive_full = positive_count
            negative_full = negative_count
            symbols_tested = positive_count + negative_count

    total_holdout = safe_int(summary.get("total_holdout_folds"))
    positive_holdout = safe_int(summary.get("positive_holdout_folds"))

    return {
        "knowledge_item_id": item_id,
        "source": fallback_source,
        "source_path": source_path,
        "title": norm(knowledge.get("title")),
        "strategy_id": norm(metadata.get("strategy_id")),
        "strategy_name": norm(metadata.get("strategy_name")),
        "symbols_tested": symbols_tested,
        "positive_full_runs": positive_full,
        "negative_full_runs": negative_full,
        "positive_full_ratio": (
            clamp01(positive_full / symbols_tested)
            if symbols_tested > 0
            else None
        ),
        "cost_survivors": safe_int(summary.get("cost_survivors")),
        "total_holdout_folds": total_holdout,
        "positive_holdout_folds": positive_holdout,
        "holdout_available": total_holdout > 0,
        "holdout_ratio": (
            clamp01(positive_holdout / total_holdout)
            if total_holdout > 0
            else None
        ),
        "verified": bool(metadata.get("verified", False)),
        "research_derived": bool(metadata.get("research_derived", False)),
        "content_hash": sha256_text(content),
    }


# ============================================================================
# STRATEGY REVIEW
# ============================================================================

def latest_strategy_review(
    conn: sqlite3.Connection,
    strategy_id: str,
) -> dict[str, Any]:
    table = "brain_research_strategy_evidence_reviews"
    if not table_exists(conn, table):
        return {}

    cols = table_columns(conn, table)
    if not {"id", "knowledge_item_id", "verdict", "score"}.issubset(cols):
        return {}

    rows = conn.execute(
        f"SELECT * FROM {table} ORDER BY id DESC"
    ).fetchall()

    for row in rows:
        data = dict(row)
        metadata = parse_json(data.get("metadata_json"))
        row_strategy = norm(
            data.get("strategy_id")
            or (metadata.get("strategy_id") if isinstance(metadata, dict) else "")
        )

        if row_strategy.upper() == strategy_id.upper():
            data["metadata"] = metadata
            return data

        knowledge_id = safe_int(data.get("knowledge_item_id"))
        if knowledge_id:
            ki = load_knowledge_item(conn, knowledge_id)
            ki_meta = ki.get("metadata", {})
            if (
                isinstance(ki_meta, dict)
                and norm(ki_meta.get("strategy_id")).upper()
                == strategy_id.upper()
            ):
                data["metadata"] = metadata
                return data

    return {}


# ============================================================================
# PAPER EVIDENCE DISCOVERY
# ============================================================================

def normalize_paper_record(
    raw: Any,
    origin: str,
) -> dict[str, Any]:
    if not isinstance(raw, dict):
        return {
            "available": False,
            "origin": origin,
            "reason": "JSON root is not an object",
        }

    strategy_id = norm(
        raw.get("strategy_id")
        or recursive_find_key(raw, ("strategy_id",))
    )

    summary = raw.get("summary")
    if not isinstance(summary, dict):
        summary = recursive_find_key(raw, ("summary",))
    if not isinstance(summary, dict):
        summary = {}

    # Support several naming conventions used by previous MarketHQ versions.
    symbols = safe_int(
        summary.get("symbols_tested")
        or summary.get("unique_symbols")
        or summary.get("symbols")
    )
    trades = safe_int(
        summary.get("total_trades")
        or summary.get("trades")
    )
    wins = safe_int(
        summary.get("winning_trades")
        or summary.get("wins")
    )
    losses = safe_int(
        summary.get("losing_trades")
        or summary.get("losses")
    )

    win_rate = summary.get("win_rate_percent")
    if win_rate is None:
        win_rate = summary.get("win_rate")

    aggregate_return = summary.get("aggregate_return_percent")
    if aggregate_return is None:
        aggregate_return = summary.get("return_percent")
    if aggregate_return is None:
        aggregate_return = summary.get("aggregate_return")

    aggregate_pnl = summary.get("aggregate_net_pnl")
    if aggregate_pnl is None:
        aggregate_pnl = summary.get("net_pnl")

    avg_pf = summary.get("average_profit_factor")
    if avg_pf is None:
        avg_pf = summary.get("avg_profit_factor")

    if not strategy_id:
        strategy_id = norm(
            raw.get("strategy")
            or raw.get("strategy_name")
        )

    if strategy_id.upper() != TARGET_STRATEGY_ID.upper():
        return {
            "available": False,
            "origin": origin,
            "reason": "Different or missing strategy_id",
        }

    return {
        "available": True,
        "origin": origin,
        "file": origin,
        "strategy_id": strategy_id,
        "symbols_tested": symbols,
        "total_trades": trades,
        "wins": wins,
        "losses": losses,
        "win_rate_percent": safe_float(win_rate),
        "aggregate_return_percent": safe_float(aggregate_return),
        "aggregate_net_pnl": safe_float(aggregate_pnl),
        "average_profit_factor": safe_float(avg_pf),
        "classification": norm(
            raw.get("classification")
            or summary.get("classification")
        ).upper(),
    }


def discover_paper_evidence() -> dict[str, Any]:
    candidates: list[Path] = []

    patterns = (
        "*paper*.json",
        "*evidence*.json",
        "*aggregat*.json",
    )

    for directory in PAPER_DIR_CANDIDATES:
        if not directory.exists():
            continue
        for pattern in patterns:
            candidates.extend(directory.glob(pattern))

    # Keep likely candidates, newest first.
    candidates = list(
        {
            str(path.resolve()): path
            for path in candidates
            if path.is_file()
        }.values()
    )
    candidates.sort(key=file_mtime_key, reverse=True)

    for path in candidates[:50]:
        payload = load_json_file(path)
        normalized = normalize_paper_record(payload, str(path))
        if normalized.get("available"):
            return normalized

    # Also inspect DB tables whose name contains paper.
    try:
        conn = open_db()
    except Exception:
        return {
            "available": False,
            "reason": "No paper evidence file/DB record found",
        }

    try:
        rows = conn.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type='table'
              AND lower(name) LIKE '%paper%'
            ORDER BY name
            """
        ).fetchall()

        for row in rows:
            table_name = norm(row["name"])
            cols = table_columns(conn, table_name)
            if not cols:
                continue

            select_cols = []
            for col in (
                "strategy_id",
                "strategy_name",
                "classification",
                "symbols_tested",
                "total_trades",
                "winning_trades",
                "losing_trades",
                "win_rate_percent",
                "aggregate_return_percent",
                "aggregate_net_pnl",
                "average_profit_factor",
            ):
                if col in cols:
                    select_cols.append(col)

            if not select_cols:
                continue

            data_rows = conn.execute(
                f"""
                SELECT {", ".join(select_cols)}
                FROM {table_name}
                ORDER BY rowid DESC
                LIMIT 50
                """
            ).fetchall()

            for data_row in data_rows:
                raw = dict(data_row)
                normalized = normalize_paper_record(
                    {"summary": raw, **raw},
                    f"db:{table_name}",
                )
                if normalized.get("available"):
                    return normalized
    finally:
        conn.close()

    return {
        "available": False,
        "reason": "No matching paper evidence discovered",
    }


# ============================================================================
# CONSOLIDATION
# ============================================================================

def find_latest_final_decision() -> dict[str, Any]:
    path = latest_matching_json(
        (FINAL_DECISION_DIR,),
        (f"final_decision_{TARGET_STRATEGY_ID}_*.json",),
    )

    if path is None:
        return {
            "available": False,
        }

    payload = load_json_file(path)
    return {
        "available": True,
        "file": str(path),
        "payload": payload,
    }


def build_consolidation(
    conn: sqlite3.Connection,
    strategy_id: str,
) -> dict[str, Any]:
    v6 = load_v6_evidence(strategy_id)

    old_knowledge = load_knowledge_item(conn, 693)
    fresh_knowledge = load_knowledge_item(conn, 694)

    old = extract_knowledge_summary(
        old_knowledge,
        "OLD_INDEPENDENT_KNOWLEDGE_693",
    )
    fresh = extract_knowledge_summary(
        fresh_knowledge,
        "FRESH_INDEPENDENT_KNOWLEDGE_694",
    )

    review = latest_strategy_review(conn, strategy_id)

    paper = discover_paper_evidence()
    final_decision = find_latest_final_decision()

    sources = {
        "v6_pipeline": v6,
        "old_independent": old,
        "fresh_independent": fresh,
        "strategy_review": {
            "available": bool(review),
            "review_id": safe_int(review.get("id")),
            "knowledge_item_id": safe_int(review.get("knowledge_item_id")),
            "verdict": norm(review.get("verdict")).upper(),
            "score": safe_float(review.get("score")),
            "review_method": norm(review.get("review_method")),
        },
        "paper_evidence": paper,
        "latest_final_decision": final_decision,
    }

    # Independent full-run coverage across two separate evidence records.
    independent_records = [
        item for item in (old, fresh)
        if item.get("symbols_tested", 0) > 0
    ]

    total_tested = sum(
        safe_int(item.get("symbols_tested"))
        for item in independent_records
    )
    total_positive = sum(
        safe_int(item.get("positive_full_runs"))
        for item in independent_records
    )
    total_negative = sum(
        safe_int(item.get("negative_full_runs"))
        for item in independent_records
    )

    pooled_positive_ratio = (
        total_positive / (total_positive + total_negative)
        if (total_positive + total_negative) > 0
        else None
    )

    holdout_records = [
        item for item in independent_records
        if item.get("holdout_available")
    ]
    holdout_total = sum(
        safe_int(item.get("total_holdout_folds"))
        for item in holdout_records
    )
    holdout_positive = sum(
        safe_int(item.get("positive_holdout_folds"))
        for item in holdout_records
    )

    holdout_ratio = (
        holdout_positive / holdout_total
        if holdout_total > 0
        else None
    )

    return {
        "engine": ENGINE_NAME,
        "engine_version": ENGINE_VERSION,
        "created_at": utc_now(),
        "strategy_id": strategy_id,
        "research_only": True,
        "execution_enabled": False,
        "verified": False,
        "sources": sources,
        "consolidated_independent": {
            "evidence_records": len(independent_records),
            "symbols_across_records": total_tested,
            "positive_full_runs": total_positive,
            "negative_full_runs": total_negative,
            "pooled_positive_ratio": pooled_positive_ratio,
            "holdout_available": holdout_total > 0,
            "holdout_positive_folds": holdout_positive,
            "holdout_total_folds": holdout_total,
            "holdout_positive_ratio": holdout_ratio,
        },
        "interpretation": {
            "independent_cross_time_consistency": (
                "SUPPORTIVE"
                if (
                    old.get("positive_full_ratio") is not None
                    and fresh.get("positive_full_ratio") is not None
                    and old["positive_full_ratio"] >= 0.50
                    and fresh["positive_full_ratio"] >= 0.50
                )
                else "MIXED"
            ),
            "strategy_review_verdict": norm(
                review.get("verdict")
            ).upper(),
            "strategy_review_score": safe_float(
                review.get("score")
            ),
            "fresh_holdout_status": (
                "AVAILABLE" if fresh.get("holdout_available")
                else "NOT_AVAILABLE"
            ),
            "verified_status": "NOT_VERIFIED",
        },
        "next_research_question": (
            "Can the strategy reproduce its edge on another genuinely "
            "independent time slice with the same fixed parameters while "
            "showing stronger cost, parameter and regime stability?"
        ),
    }


# ============================================================================
# DB OUTPUT
# ============================================================================

def ensure_tables(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS brain_evidence_consolidations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            strategy_id TEXT NOT NULL,
            pooled_positive_ratio REAL,
            holdout_positive_ratio REAL,
            strategy_review_score REAL,
            verified INTEGER NOT NULL DEFAULT 0,
            consolidation_json TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS
        idx_brain_evidence_consolidations_strategy
        ON brain_evidence_consolidations(strategy_id)
        """
    )


def save_consolidation(
    conn: sqlite3.Connection,
    consolidation: dict[str, Any],
) -> int:
    pooled = consolidation["consolidated_independent"].get(
        "pooled_positive_ratio"
    )
    holdout = consolidation["consolidated_independent"].get(
        "holdout_positive_ratio"
    )
    review_score = consolidation["interpretation"].get(
        "strategy_review_score"
    )

    cur = conn.execute(
        """
        INSERT INTO brain_evidence_consolidations (
            strategy_id,
            pooled_positive_ratio,
            holdout_positive_ratio,
            strategy_review_score,
            verified,
            consolidation_json,
            created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            consolidation["strategy_id"],
            pooled,
            holdout,
            review_score,
            0,
            compact_json(consolidation),
            consolidation["created_at"],
        ),
    )
    return safe_int(cur.lastrowid)


# ============================================================================
# REPORT
# ============================================================================

def print_report(
    consolidation: dict[str, Any],
    record_id: int,
) -> None:
    sources = consolidation["sources"]
    independent = consolidation["consolidated_independent"]
    interpretation = consolidation["interpretation"]

    print("=" * 78)
    print("MARKETHQ EVIDENCE CONSOLIDATION ENGINE V1")
    print("=" * 78)
    print()
    print(f"Strategy        : {consolidation['strategy_id']}")
    print()
    print("EVIDENCE SOURCES")
    print("-" * 78)

    v6 = sources["v6_pipeline"]
    print(
        f"V6 Pipeline     : "
        f"{'AVAILABLE' if v6.get('available') else 'MISSING'}"
    )

    old = sources["old_independent"]
    print(
        f"Old Independent : "
        f"{old.get('positive_full_runs', 0)}/"
        f"{old.get('symbols_tested', 0)} positive"
    )

    fresh = sources["fresh_independent"]
    print(
        f"Fresh Independent : "
        f"{fresh.get('positive_full_runs', 0)}/"
        f"{fresh.get('symbols_tested', 0)} positive"
    )

    review = sources["strategy_review"]
    print(
        f"Strategy Review : "
        f"{review.get('verdict', 'MISSING')} | "
        f"score={review.get('score', 0.0):.3f} | "
        f"id={review.get('review_id', 0)}"
    )

    paper = sources["paper_evidence"]
    print(
        f"Paper Evidence  : "
        f"{'AVAILABLE' if paper.get('available') else 'NOT_FOUND'}"
    )

    print()
    print("CONSOLIDATED INDEPENDENT EVIDENCE")
    print("-" * 78)
    print(
        f"Evidence records       : {independent['evidence_records']}"
    )
    print(
        f"Symbol runs combined   : {independent['symbols_across_records']}"
    )
    print(
        f"Positive full runs     : {independent['positive_full_runs']}"
    )
    print(
        f"Negative full runs     : {independent['negative_full_runs']}"
    )
    pooled = independent.get("pooled_positive_ratio")
    print(
        "Pooled positive ratio  : "
        + ("N/A" if pooled is None else f"{pooled:.2%}")
    )
    print(
        f"Holdout                : "
        f"{independent['holdout_positive_folds']}/"
        f"{independent['holdout_total_folds']}"
        if independent["holdout_available"]
        else "Holdout                : NOT_AVAILABLE"
    )

    print()
    print("INTERPRETATION")
    print("-" * 78)
    print(
        "Cross-time independent consistency : "
        f"{interpretation['independent_cross_time_consistency']}"
    )
    print(
        "Strategy review                     : "
        f"{interpretation['strategy_review_verdict']}"
    )
    print(
        "Verified                            : "
        f"{interpretation['verified_status']}"
    )

    print()
    print("SAFETY")
    print("-" * 78)
    print("Research Only       : True")
    print("Execution Enabled   : False")
    print("learned_rules       : unchanged")
    print("claims              : unchanged")
    print("validations         : unchanged")
    print("observations        : unchanged")
    print("Knowledge Verified  : unchanged")

    print()
    print(
        f"Consolidation record: {record_id}"
    )
    print(
        "Next research question: "
        + consolidation["next_research_question"]
    )


# ============================================================================
# MAIN
# ============================================================================

def main() -> int:
    assert_research_only()

    conn = open_db()
    try:
        consolidation = build_consolidation(
            conn,
            TARGET_STRATEGY_ID,
        )

        ensure_tables(conn)
        record_id = save_consolidation(
            conn,
            consolidation,
        )
        conn.commit()

        OUTPUT_DIR.mkdir(
            parents=True,
            exist_ok=True,
        )

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = (
            OUTPUT_DIR
            / f"evidence_consolidation_{TARGET_STRATEGY_ID}_{timestamp}.json"
        )

        payload = dict(consolidation)
        payload["consolidation_record_id"] = record_id

        output_path.write_text(
            json.dumps(
                payload,
                ensure_ascii=False,
                indent=2,
                default=str,
            ),
            encoding="utf-8",
        )

        print_report(
            consolidation,
            record_id,
        )

        print()
        print(
            f"Saved consolidation JSON : {output_path}"
        )
        print("RUN STATUS               : SUCCESS")
        return 0

    except Exception as exc:
        conn.rollback()
        print()
        print("=" * 78)
        print("RUN STATUS               : ERROR")
        print("=" * 78)
        print(f"{type(exc).__name__}: {exc}")
        return 1
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())

