import csv
import json
import os
import sqlite3
import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

# =========================================================
# MARKET HQ — DASHBOARD BACKEND V1
# Read-only API layer for the frozen research/dashboard schema.
# Research-only: no broker calls, no order execution, no DB writes.
# =========================================================

BASE_DIR = Path(__file__).resolve().parent
DB_FILE = BASE_DIR / "market_hq.db"

# Optional JSON evidence/result folders created by the research loop.
PIPELINE_DIR = BASE_DIR / "strategy_pipeline_results"
FRESH_DIR = BASE_DIR / "fresh_independent_research_results"
BACKTEST_RESULTS_DIR = BASE_DIR / "backtest_results"
INDEPENDENT_DIR = BASE_DIR / "independent_strategy_evidence_results"
CONSOLIDATION_DIR = BASE_DIR / "evidence_consolidation_results"
RANKING_DIR = BASE_DIR / "learning_ranking_results"
DECISION_DIR = BASE_DIR / "final_research_decisions"
FREEZE_DIR = BASE_DIR / "schema_freeze_results"

HOST = "127.0.0.1"
PORT = 8010

TARGET_STRATEGY_ID = "STR-43839FA9C6"

SAFETY = {
    "research_only": True,
    "execution_enabled": False,
    "database_write_enabled": False,
    "broker_execution_enabled": False,
}


# =========================================================
# GENERIC SAFE HELPERS
# =========================================================

def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def json_load(path, fallback=None):
    if fallback is None:
        fallback = {}
    try:
        with path.open("r", encoding="utf-8") as handle:
            value = json.load(handle)
        return value
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return fallback


def latest_json(directory, pattern="*.json"):
    if not directory.exists():
        return None
    files = [p for p in directory.glob(pattern) if p.is_file()]
    if not files:
        return None
    try:
        return max(files, key=lambda p: p.stat().st_mtime)
    except OSError:
        return None


def connect_db():
    if not DB_FILE.exists():
        return None
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    # Read-only behavior at the API layer:
    # we never issue INSERT/UPDATE/DELETE/CREATE/ALTER statements.
    return conn


def table_exists(conn, table_name):
    if conn is None:
        return False
    try:
        row = conn.execute(
            "SELECT 1 FROM sqlite_master "
            "WHERE type='table' AND name=? LIMIT 1",
            (table_name,),
        ).fetchone()
        return row is not None
    except sqlite3.Error:
        return False


def table_columns(conn, table_name):
    if not table_exists(conn, table_name):
        return []
    try:
        return [
            str(row[1])
            for row in conn.execute(
                f'PRAGMA table_info("{table_name}")'
            ).fetchall()
        ]
    except sqlite3.Error:
        return []


def table_count(conn, table_name):
    if not table_exists(conn, table_name):
        return 0
    try:
        row = conn.execute(
            f'SELECT COUNT(*) AS n FROM "{table_name}"'
        ).fetchone()
        return int(row["n"] or 0)
    except sqlite3.Error:
        return 0


def first_existing_column(columns, candidates):
    for candidate in candidates:
        if candidate in columns:
            return candidate
    return None


def safe_rows(conn, table_name, columns, limit=10):
    if conn is None or not table_exists(conn, table_name):
        return []

    existing = table_columns(conn, table_name)
    selected = [c for c in columns if c in existing]
    if not selected:
        return []

    order_col = first_existing_column(
        existing,
        ("updated_at", "created_at", "finished_at", "started_at", "id"),
    )
    order_sql = f' ORDER BY "{order_col}" DESC' if order_col else ""

    try:
        rows = conn.execute(
            f'SELECT {", ".join(f"""\"{c}\"""" for c in selected)} '
            f'FROM "{table_name}"{order_sql} LIMIT ?',
            (max(1, min(int(limit), 100)),),
        ).fetchall()
        return [dict(row) for row in rows]
    except (sqlite3.Error, ValueError, TypeError):
        return []


def safe_query(conn, sql, params=()):
    if conn is None:
        return []
    try:
        return [dict(row) for row in conn.execute(sql, params).fetchall()]
    except sqlite3.Error:
        return []


def recursive_find(obj, key, value):
    if isinstance(obj, dict):
        if obj.get(key) == value:
            return obj
        for child in obj.values():
            found = recursive_find(child, key, value)
            if found is not None:
                return found
    elif isinstance(obj, list):
        for child in obj:
            found = recursive_find(child, key, value)
            if found is not None:
                return found
    return None


def nested_object(obj, key):
    if isinstance(obj, dict):
        candidate = obj.get(key)
        if isinstance(candidate, dict):
            return candidate
        for child in obj.values():
            found = nested_object(child, key)
            if found is not None:
                return found
    elif isinstance(obj, list):
        for child in obj:
            found = nested_object(child, key)
            if found is not None:
                return found
    return None


def latest_successful_freeze():
    conn = connect_db()
    if conn is None or not table_exists(conn, "brain_schema_freezes"):
        if conn is not None:
            conn.close()
        return None

    columns = table_columns(conn, "brain_schema_freezes")
    wanted = [
        "id",
        "engine_version",
        "contract_status",
        "contract_hash",
        "baseline_status",
        "created_at",
        "snapshot_path",
    ]
    selected = [c for c in wanted if c in columns]
    if not selected:
        conn.close()
        return None

    order_col = first_existing_column(
        columns, ("created_at", "updated_at", "id")
    )
    order_sql = f' ORDER BY "{order_col}" DESC' if order_col else ""

    try:
        row = conn.execute(
            f'SELECT {", ".join(f"""\"{c}\"""" for c in selected)} '
            f'FROM brain_schema_freezes '
            f'WHERE contract_status IN ("FREEZE_READY","SUCCESS")'
            f'{order_sql} LIMIT 1'
        ).fetchone()
        result = dict(row) if row else None
    except sqlite3.Error:
        result = None

    conn.close()
    return result


# =========================================================
# JSON EVIDENCE READERS
# =========================================================

def read_pipeline():
    path = latest_json(PIPELINE_DIR, "strategy_pipeline_v6_*.json")
    if path is None:
        return {
            "available": False,
            "file": None,
            "strategy": None,
        }

    data = json_load(path, {})
    strategy = recursive_find(data, "strategy_id", TARGET_STRATEGY_ID)
    if strategy is None:
        strategy = recursive_find(data, "id", TARGET_STRATEGY_ID)

    if isinstance(strategy, dict):
        ranking = strategy.get("ranking")
        if not isinstance(ranking, dict):
            ranking = strategy
    else:
        ranking = {}

    return {
        "available": bool(data),
        "file": str(path),
        "updated_at": datetime.fromtimestamp(
            path.stat().st_mtime, tz=timezone.utc
        ).isoformat(timespec="seconds"),
        "strategy": {
            "strategy_id": strategy.get("strategy_id", TARGET_STRATEGY_ID),
            "strategy_name": strategy.get(
                "strategy_name",
                strategy.get("name", "Kısa ve Uzun Vadeli Hareketli Ortalama Yukarı Kesişim Stratejisi"),
            ),
            "ranking": {
                "score": ranking.get("score"),
                "classification": ranking.get("classification"),
                "cross_symbol_positive_ratio": ranking.get(
                    "cross_symbol_positive_ratio"
                ),
                "average_return": ranking.get("average_return"),
                "cost_survival": ranking.get("cost_survival"),
                "parameter_stability": ranking.get("parameter_stability"),
                "regime_stability": ranking.get("regime_stability"),
                "wfo_positive_ratio": ranking.get("wfo_positive_ratio"),
            },
        },
    }


def read_latest_result(directory, glob_pattern):
    path = latest_json(directory, glob_pattern)
    if path is None:
        return {"available": False, "file": None, "data": None}

    data = json_load(path, {})
    return {
        "available": bool(data),
        "file": str(path),
        "updated_at": datetime.fromtimestamp(
            path.stat().st_mtime, tz=timezone.utc
        ).isoformat(timespec="seconds"),
        "data": data,
    }


def json_load_from_text(value):
    try:
        data = json.loads(str(value or "{}"))
        return data if isinstance(data, dict) else {}
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}


def read_consolidation():
    # Prefer the canonical consolidation record stored in SQLite.
    conn = connect_db()
    if conn is not None and table_exists(conn, "brain_evidence_consolidations"):
        columns = table_columns(conn, "brain_evidence_consolidations")
        if "consolidation_json" in columns:
            order_col = first_existing_column(
                columns, ("created_at", "updated_at", "id")
            )
            order_sql = f' ORDER BY "{order_col}" DESC' if order_col else ""
            try:
                row = conn.execute(
                    f"""
                    SELECT strategy_id, consolidation_json, created_at
                    FROM brain_evidence_consolidations
                    WHERE strategy_id=?
                    {order_sql}
                    LIMIT 1
                    """,
                    (TARGET_STRATEGY_ID,),
                ).fetchone()
            except sqlite3.Error:
                row = None

            if row is not None:
                data = json_load_from_text(row["consolidation_json"])
                independent = (
                    data.get("consolidated_independent")
                    if isinstance(data, dict) else {}
                )
                interpretation = (
                    data.get("interpretation")
                    if isinstance(data, dict) else {}
                )
                if not isinstance(independent, dict):
                    independent = {}
                if not isinstance(interpretation, dict):
                    interpretation = {}

                result = {
                    "available": True,
                    "source": "sqlite:brain_evidence_consolidations",
                    "file": None,
                    "updated_at": row["created_at"],
                    "summary": {
                        "evidence_records": independent.get("evidence_records"),
                        "symbol_runs_combined": independent.get(
                            "symbols_across_records"
                        ),
                        "positive_full_runs": independent.get(
                            "positive_full_runs"
                        ),
                        "negative_full_runs": independent.get(
                            "negative_full_runs"
                        ),
                        "pooled_positive_ratio": independent.get(
                            "pooled_positive_ratio"
                        ),
                        "holdout_positive": independent.get(
                            "holdout_positive_folds"
                        ),
                        "holdout_total": independent.get(
                            "holdout_total_folds"
                        ),
                        "holdout_positive_ratio": independent.get(
                            "holdout_positive_ratio"
                        ),
                        "cross_time_consistency": interpretation.get(
                            "independent_cross_time_consistency"
                        ),
                        "strategy_review_verdict": interpretation.get(
                            "strategy_review_verdict"
                        ),
                        "strategy_review_score": interpretation.get(
                            "strategy_review_score"
                        ),
                        "verified": data.get("verified"),
                        "next_research_question": data.get(
                            "next_research_question"
                        ),
                    },
                }
                conn.close()
                return result

    if conn is not None:
        conn.close()

    # Fallback to JSON artifact.
    result = read_latest_result(
        CONSOLIDATION_DIR,
        f"evidence_consolidation_{TARGET_STRATEGY_ID}_*.json",
    )
    if not result["available"]:
        return {
            "available": False,
            "file": None,
            "summary": None,
        }

    data = result["data"]
    independent = data.get("consolidated_independent", {})
    interpretation = data.get("interpretation", {})
    if not isinstance(independent, dict):
        independent = {}
    if not isinstance(interpretation, dict):
        interpretation = {}

    return {
        "available": True,
        "source": "json:evidence_consolidation",
        "file": result["file"],
        "updated_at": result["updated_at"],
        "summary": {
            "evidence_records": independent.get("evidence_records"),
            "symbol_runs_combined": independent.get("symbols_across_records"),
            "positive_full_runs": independent.get("positive_full_runs"),
            "negative_full_runs": independent.get("negative_full_runs"),
            "pooled_positive_ratio": independent.get("pooled_positive_ratio"),
            "holdout_positive": independent.get("holdout_positive_folds"),
            "holdout_total": independent.get("holdout_total_folds"),
            "holdout_positive_ratio": independent.get("holdout_positive_ratio"),
            "cross_time_consistency": interpretation.get(
                "independent_cross_time_consistency"
            ),
            "strategy_review_verdict": interpretation.get(
                "strategy_review_verdict"
            ),
            "strategy_review_score": interpretation.get(
                "strategy_review_score"
            ),
            "verified": data.get("verified"),
            "next_research_question": data.get("next_research_question"),
        },
    }



def read_final_decision():
    # Final Research Decision V3 stores decision fields in a decision object.
    # Support both the current nested format and older top-level format.
    result = read_latest_result(
        DECISION_DIR,
        f"*{TARGET_STRATEGY_ID}*.json",
    )

    if not result["available"]:
        return {
            "available": False,
            "file": None,
            "decision": None,
        }

    data = result["data"]
    decision = nested_object(data, "decision")
    if not isinstance(decision, dict):
        decision = data if isinstance(data, dict) else {}

    payload = {
        "decision": decision.get("decision"),
        "action": decision.get("action"),
        "composite_score": decision.get("composite_score"),
        "decision_confidence": decision.get("decision_confidence"),
    }

    return {
        "available": any(value is not None for value in payload.values()),
        "file": result["file"],
        "updated_at": result["updated_at"],
        "decision": payload,
    }



def read_learning_ranking():
    result = read_latest_result(
        RANKING_DIR,
        f"learning_ranking_{TARGET_STRATEGY_ID}_*.json",
    )
    if not result["available"]:
        return {
            "available": False,
            "file": None,
            "ranking": None,
        }

    data = result["data"]
    ranking = data.get("ranking")
    if not isinstance(ranking, dict):
        ranking = data.get("learning_rank")
    if not isinstance(ranking, dict):
        ranking = nested_object(data, "learning_rank")
    if not isinstance(ranking, dict):
        ranking = {}

    learning = data.get("learning")
    if not isinstance(learning, dict):
        learning = {}

    return {
        "available": True,
        "file": result["file"],
        "updated_at": result["updated_at"],
        "ranking": {
            "learning_score": ranking.get(
                "learning_score",
                learning.get("learning_score", data.get("learning_score")),
            ),
            "learning_score_percent": ranking.get(
                "learning_score_percent",
                learning.get(
                    "learning_score_percent",
                    data.get("learning_score_percent"),
                ),
            ),
            "action": ranking.get(
                "action", learning.get("action", data.get("action"))
            ),
            "reason": ranking.get(
                "reason", learning.get("reason", data.get("reason"))
            ),
            "verification_status": ranking.get(
                "verification_status",
                learning.get(
                    "verification_status",
                    data.get("verification_status"),
                ),
            ),
            "candidate_status": ranking.get(
                "candidate_status",
                learning.get(
                    "candidate_status",
                    data.get("candidate_status"),
                ),
            ),
            "next_research_question": ranking.get(
                "next_research_question",
                learning.get(
                    "next_research_question",
                    data.get("next_research_question"),
                ),
            ),
        },
    }



def read_strategy_evidence_review():
    conn = connect_db()
    if conn is None:
        return {"available": False, "row": None}

    table = "brain_research_strategy_evidence_reviews"
    if not table_exists(conn, table):
        conn.close()
        return {"available": False, "row": None}

    columns = table_columns(conn, table)
    selected = [
        c for c in [
            "id",
            "knowledge_item_id",
            "strategy_id",
            "verdict",
            "score",
            "review_method",
            "reasoning",
            "review_text",
            "review_reasoning",
            "created_at",
            "updated_at",
        ] if c in columns
    ]

    if not selected:
        conn.close()
        return {"available": False, "row": None}

    filters = []
    params = []
    if "strategy_id" in columns:
        filters.append("strategy_id=?")
        params.append(TARGET_STRATEGY_ID)

    where_sql = f"WHERE {' AND '.join(filters)}" if filters else ""
    order_col = first_existing_column(
        columns, ("updated_at", "created_at", "id")
    )
    order_sql = f' ORDER BY "{order_col}" DESC' if order_col else ""

    try:
        row = conn.execute(
            f'SELECT {", ".join(f"""\"{c}\"""" for c in selected)} '
            f'FROM "{table}" {where_sql}{order_sql} LIMIT 1',
            tuple(params),
        ).fetchone()
        result = dict(row) if row else None
    except sqlite3.Error:
        result = None

    conn.close()

    if result is not None:
        # Normalize the review text for the UI without changing the DB.
        normalized_reasoning = (
            result.get("reasoning")
            or result.get("review_reasoning")
            or result.get("review_text")
        )
        result["normalized_reasoning"] = normalized_reasoning

    return {
        "available": result is not None,
        "row": result,
    }



def recursive_collect_symbol_records(obj, output=None):
    """
    Best-effort reader for V6 / independent JSON symbol-level results.
    It deliberately accepts multiple known/likely field names and returns
    only records that contain a symbol/ticker-like identifier.
    """
    if output is None:
        output = []

    if isinstance(obj, dict):
        symbol = (
            obj.get("symbol")
            or obj.get("ticker")
            or obj.get("Symbol")
            or obj.get("ticker_symbol")
        )
        if isinstance(symbol, str) and symbol.strip():
            record = {
                "symbol": symbol.strip(),
                "return_percent": first_numeric(
                    obj,
                    (
                        "return_percent",
                        "total_return_percent",
                        "strategy_return_percent",
                        "net_return_percent",
                        "return",
                    ),
                ),
                "profit_factor": first_numeric(
                    obj,
                    ("profit_factor", "pf", "profitFactor"),
                ),
                "trades": first_numeric(
                    obj,
                    ("total_trades", "trades", "trade_count"),
                ),
                "win_rate_percent": first_numeric(
                    obj,
                    ("win_rate_percent", "win_rate", "winRate"),
                ),
                "max_drawdown_percent": first_numeric(
                    obj,
                    ("max_drawdown_percent", "max_drawdown", "drawdown"),
                ),
                "positive": first_bool(
                    obj,
                    ("positive", "is_positive", "profitable"),
                ),
            }
            output.append(record)

        for child in obj.values():
            recursive_collect_symbol_records(child, output)

    elif isinstance(obj, list):
        for child in obj:
            recursive_collect_symbol_records(child, output)

    return dedupe_symbol_records(output)





def key_lookup(obj, *keys):
    if not isinstance(obj, dict):
        return None

    normalized = {
        str(key).strip().lower().replace(" ", "_"): value
        for key, value in obj.items()
    }

    for key in keys:
        normalized_key = str(key).strip().lower().replace(" ", "_")
        if normalized_key in normalized:
            return normalized[normalized_key]

    return None


def first_numeric(obj, keys):
    if not isinstance(obj, dict):
        return None

    for key in keys:
        value = key_lookup(obj, key)
        try:
            if value is None or value == "":
                continue
            if isinstance(value, str):
                value = value.strip().replace("%", "")
            return float(value)
        except (TypeError, ValueError):
            continue

    return None


def first_bool(obj, keys):
    if not isinstance(obj, dict):
        return None

    for key in keys:
        value = key_lookup(obj, key)
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return bool(value)
        if isinstance(value, str):
            s = value.strip().lower()
            if s in {
                "true", "yes", "positive", "profitable",
                "win", "winning", "done_positive"
            }:
                return True
            if s in {
                "false", "no", "negative", "loss",
                "losing", "done_negative"
            }:
                return False

    return None


def extract_metric_dict(obj):
    if not isinstance(obj, dict):
        return {}

    # Direct metric object.
    for key in (
        "metrics",
        "performance_metrics",
        "backtest_metrics",
    ):
        metrics = key_lookup(obj, key)
        if isinstance(metrics, dict):
            return metrics

    # Known parent containers.
    for parent_key in (
        "best_backtest",
        "best_result",
        "best",
        "full_backtest",
        "backtest",
        "result",
        "with_costs",
        "cost_adjusted",
        "selected_result",
    ):
        parent = key_lookup(obj, parent_key)
        if isinstance(parent, dict):
            metrics = key_lookup(parent, "metrics")
            if isinstance(metrics, dict):
                return metrics

            # Some versions put metrics directly in the parent.
            direct = {}
            for metric_key in (
                "trades",
                "total_trades",
                "wins",
                "winning_trades",
                "win_rate",
                "win_rate_percent",
                "profit_factor",
                "pf",
                "return",
                "return_percent",
                "total_return",
                "total_return_percent",
                "max_drawdown",
                "max_drawdown_percent",
            ):
                value = key_lookup(parent, metric_key)
                if value is not None:
                    direct[metric_key] = value
            if direct:
                return direct

            for nested_key in (
                "with_costs",
                "cost_adjusted",
                "result",
                "backtest",
            ):
                nested = key_lookup(parent, nested_key)
                if isinstance(nested, dict):
                    metrics = key_lookup(nested, "metrics")
                    if isinstance(metrics, dict):
                        return metrics

    return {}


def normalize_symbol_record(obj, source_hint=None):
    if not isinstance(obj, dict):
        return None

    symbol = (
        key_lookup(obj, "symbol")
        or key_lookup(obj, "ticker")
        or key_lookup(obj, "asset")
        or key_lookup(obj, "ticker_symbol")
        or key_lookup(obj, "tickerSymbol")
    )
    if not isinstance(symbol, str) or not symbol.strip():
        return None

    symbol = symbol.strip()
    metrics = extract_metric_dict(obj)

    status = (
        key_lookup(obj, "status")
        or key_lookup(obj, "classification")
        or key_lookup(obj, "result_status")
    )
    if isinstance(status, dict):
        status = (
            key_lookup(status, "status")
            or key_lookup(status, "classification")
        )
    status = str(status or "").strip().upper()

    aliases_return = (
        "return_percent",
        "total_return_percent",
        "strategy_return_percent",
        "net_return_percent",
        "return_pct",
        "total_return_pct",
        "strategy_return",
        "total_return",
        "return",
        "net_return",
        "pnl_percent",
    )

    return_percent = first_numeric(metrics, aliases_return)
    if return_percent is None:
        return_percent = first_numeric(obj, aliases_return)

    profit_factor = first_numeric(
        metrics, ("profit_factor", "pf", "profitFactor")
    )
    if profit_factor is None:
        profit_factor = first_numeric(
            obj, ("profit_factor", "pf", "profitFactor")
        )

    trades = first_numeric(
        metrics,
        (
            "total_trades",
            "trades",
            "trade_count",
            "number_of_trades",
        ),
    )
    if trades is None:
        trades = first_numeric(
            obj,
            (
                "total_trades",
                "trades",
                "trade_count",
                "number_of_trades",
            ),
        )

    win_rate_percent = first_numeric(
        metrics,
        ("win_rate_percent", "win_rate", "winRate"),
    )
    if win_rate_percent is None:
        win_rate_percent = first_numeric(
            obj,
            ("win_rate_percent", "win_rate", "winRate"),
        )

    max_drawdown_percent = first_numeric(
        metrics,
        ("max_drawdown_percent", "max_drawdown", "drawdown", "max_dd"),
    )
    if max_drawdown_percent is None:
        max_drawdown_percent = first_numeric(
            obj,
            ("max_drawdown_percent", "max_drawdown", "drawdown", "max_dd"),
        )

    # If the engine stored Return as a decimal fraction while labeling it as
    # percent, preserve it as-is rather than silently guessing. We only
    # normalize explicit percent strings through first_numeric.
    positive = first_bool(
        obj, ("positive", "is_positive", "profitable")
    )

    if positive is None:
        if status in {"POSITIVE", "PROFITABLE", "WIN", "WINNING"}:
            positive = True
        elif status in {"NEGATIVE", "LOSS", "LOSING"}:
            positive = False
        elif return_percent is not None:
            positive = return_percent > 0

    if not (
        metrics
        or return_percent is not None
        or profit_factor is not None
        or trades is not None
        or win_rate_percent is not None
        or max_drawdown_percent is not None
        or status
    ):
        return None

    return {
        "symbol": symbol,
        "source_hint": source_hint,
        "return_percent": return_percent,
        "profit_factor": profit_factor,
        "trades": trades,
        "win_rate_percent": win_rate_percent,
        "max_drawdown_percent": max_drawdown_percent,
        "positive": positive,
        "status_raw": status or None,
    }


def record_completeness(record):
    return sum(
        value is not None
        for value in (
            record.get("return_percent"),
            record.get("profit_factor"),
            record.get("trades"),
            record.get("win_rate_percent"),
            record.get("max_drawdown_percent"),
            record.get("positive"),
        )
    )


def dedupe_one_per_symbol(records):
    best = {}

    for record in records:
        symbol = record.get("symbol")
        if not symbol:
            continue

        key = str(symbol).strip().upper()
        current = best.get(key)

        if current is None:
            best[key] = record
            continue

        current_score = record_completeness(current)
        incoming_score = record_completeness(record)

        if incoming_score > current_score:
            best[key] = record

    return list(best.values())



def dedupe_symbol_records(records):
    """Backward-compatible alias for the canonical per-symbol deduper."""
    if not isinstance(records, list):
        return []
    return dedupe_one_per_symbol(records)





def collect_records_from_container(obj, source_hint=None):
    records = []

    if isinstance(obj, list):
        for child in obj:
            if isinstance(child, dict):
                record = normalize_symbol_record(
                    child,
                    source_hint=source_hint,
                )
                if record is not None:
                    records.append(record)

            if isinstance(child, (dict, list)):
                records.extend(
                    collect_records_from_container(
                        child,
                        source_hint=source_hint,
                    )
                )

    elif isinstance(obj, dict):
        # A very common MarketHQ layout is:
        # {
        #   "THYAO.IS": {"symbol": "THYAO.IS", "metrics": {...}},
        #   "ASELS.IS": {...}
        # }
        # In that layout the parent has no "symbol", while each value does.
        direct_record = normalize_symbol_record(
            obj,
            source_hint=source_hint,
        )
        if direct_record is not None:
            records.append(direct_record)

        for key, child in obj.items():
            if isinstance(child, dict):
                # If the child does not repeat the symbol, inherit the dict key
                # as a symbol only when the key looks like a market ticker.
                child_record = normalize_symbol_record(
                    child,
                    source_hint=source_hint,
                )

                if child_record is None:
                    key_text = str(key).strip()
                    looks_like_symbol = (
                        1 <= len(key_text) <= 16
                        and key_text.upper() == key_text
                        and any(ch.isalpha() for ch in key_text)
                        and all(
                            ch.isalnum() or ch in "._-"
                            for ch in key_text
                        )
                    )

                    if looks_like_symbol:
                        promoted = dict(child)
                        promoted["symbol"] = key_text
                        child_record = normalize_symbol_record(
                            promoted,
                            source_hint=source_hint,
                        )

                if child_record is not None:
                    records.append(child_record)
                    # Do not recursively traverse a complete symbol result;
                    # this prevents nested metrics/trades from being mistaken
                    # for additional symbol records.
                    continue

                records.extend(
                    collect_records_from_container(
                        child,
                        source_hint=source_hint,
                    )
                )

            elif isinstance(child, list):
                records.extend(
                    collect_records_from_container(
                        child,
                        source_hint=source_hint,
                    )
                )

    return dedupe_one_per_symbol(records)


def find_target_strategy_node(obj):
    if isinstance(obj, dict):
        current_id = str(
            key_lookup(
                obj,
                "strategy_id",
                "strategyId",
                "id",
            )
            or ""
        ).strip()

        if current_id.upper() == TARGET_STRATEGY_ID.upper():
            return obj

        for child in obj.values():
            found = find_target_strategy_node(child)
            if found is not None:
                return found

    elif isinstance(obj, list):
        for child in obj:
            found = find_target_strategy_node(child)
            if found is not None:
                return found

    return None



def collect_v6_symbol_records(payload):
    strategy = find_target_strategy_node(payload)
    if not isinstance(strategy, dict):
        return []

    candidates = []

    # Canonical V6 per-symbol results live under "backtests".
    for key in (
        "backtests",
        "symbol_results",
        "per_symbol_results",
        "backtest_results",
        "full_backtest_results",
        "results_by_symbol",
        "cross_symbol_results",
        "symbol_performance",
        "symbol_metrics",
    ):
        container = key_lookup(strategy, key)
        if isinstance(container, (dict, list)):
            candidates.extend(
                collect_records_from_container(
                    container,
                    source_hint="V6_PIPELINE",
                )
            )

        if candidates:
            # One canonical symbol result per ticker is enough.
            candidates = dedupe_one_per_symbol(candidates)

    if len(candidates) < 8:
        fallback = collect_records_from_container(
            strategy,
            source_hint="V6_PIPELINE",
        )

        merged = {}
        for record in candidates + fallback:
            key = record["symbol"].upper()
            previous = merged.get(key)
            if previous is None:
                merged[key] = record
                continue

            previous_rank = (
                previous.get("return_percent") is not None,
                record_completeness(previous),
            )
            current_rank = (
                record.get("return_percent") is not None,
                record_completeness(record),
            )

            if current_rank > previous_rank:
                merged[key] = record

        candidates = list(merged.values())

    return sorted(
        dedupe_one_per_symbol(candidates),
        key=lambda row: row["symbol"].upper(),
    )



def collect_fresh_symbol_records(payload):
    if not isinstance(payload, dict):
        return []

    direct_results = key_lookup(payload, "results")

    if isinstance(direct_results, list):
        records = []
        for item in direct_results:
            if not isinstance(item, dict):
                continue

            normalized = normalize_symbol_record(
                item,
                source_hint="INDEPENDENT_FRESH",
            )
            if normalized is not None:
                records.append(normalized)

        records = dedupe_one_per_symbol(records)
        if records:
            return sorted(
                records,
                key=lambda row: row["symbol"].upper(),
            )

    if isinstance(direct_results, dict):
        records = collect_records_from_container(
            direct_results,
            source_hint="INDEPENDENT_FRESH",
        )
        if records:
            return sorted(
                records,
                key=lambda row: row["symbol"].upper(),
            )

    return sorted(
        collect_records_from_container(
            payload,
            source_hint="INDEPENDENT_FRESH",
        ),
        key=lambda row: row["symbol"].upper(),
    )


def json_contains_strategy(payload):
    return (
        find_target_strategy_node(payload) is not None
        or str(
            key_lookup(payload, "strategy_id")
            or ""
        ).strip().upper() == TARGET_STRATEGY_ID.upper()
    )


def find_latest_strategy_json(directory, patterns):
    if not directory.exists():
        return None

    candidates = []
    for pattern in patterns:
        candidates.extend(
            p for p in directory.glob(pattern)
            if p.is_file()
        )

    candidates = sorted(
        set(candidates),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )

    for path in candidates:
        data = json_load(path, {})
        if json_contains_strategy(data):
            return path

    # Last fallback: inspect all JSON files in the directory.
    for path in sorted(
        directory.glob("*.json"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    ):
        data = json_load(path, {})
        if json_contains_strategy(data):
            return path

    return None



def collect_old_independent_records(path):
    if path is None:
        return []

    payload = json_load(path, {})
    results = key_lookup(payload, "results")

    if isinstance(results, (dict, list)):
        records = collect_records_from_container(
            results,
            source_hint="INDEPENDENT_OLD",
        )
        if records:
            return sorted(
                records,
                key=lambda row: row["symbol"].upper(),
            )

    return sorted(
        collect_records_from_container(
            payload,
            source_hint="INDEPENDENT_OLD",
        ),
        key=lambda row: row["symbol"].upper(),
    )


def read_knowledge_item_symbol_evidence(knowledge_item_id):
    """Read symbol-level evidence from a knowledge item without writing to the DB."""
    conn = connect_db()
    if conn is None or not table_exists(conn, "knowledge_items"):
        if conn is not None:
            conn.close()
        return []

    columns = table_columns(conn, "knowledge_items")
    selected = [
        c for c in (
            "id",
            "title",
            "summary",
            "content",
            "body",
            "metadata_json",
            "observation",
            "method_name",
        )
        if c in columns
    ]

    if not selected:
        conn.close()
        return []

    try:
        row = conn.execute(
            f'SELECT {", ".join(f"\"{c}\"" for c in selected)} '
            f'FROM "knowledge_items" WHERE id=? LIMIT 1',
            (int(knowledge_item_id),),
        ).fetchone()
    except (sqlite3.Error, TypeError, ValueError):
        row = None

    conn.close()
    if row is None:
        return []

    row_dict = dict(row)
    payloads = [row_dict]
    for key in ("metadata_json", "content", "body", "summary", "observation"):
        value = row_dict.get(key)
        if not value:
            continue
        if isinstance(value, str):
            parsed = json_load_from_text(value)
            if parsed:
                payloads.append(parsed)

    records = []
    for payload in payloads:
        records.extend(collect_records_from_container(
            payload,
            source_hint=f"KNOWLEDGE_ITEM:{int(knowledge_item_id)}",
        ))

    return sorted(
        dedupe_one_per_symbol(records),
        key=lambda row: row["symbol"].upper(),
    )





def evidence_symbol_snapshot():
    datasets = []

    # ---------------------------------------------------------
    # V6
    # ---------------------------------------------------------
    v6_path = latest_json(
        PIPELINE_DIR,
        "strategy_pipeline_v6_*.json",
    )
    if v6_path is not None:
        payload = json_load(v6_path, {})
        v6_records = collect_v6_symbol_records(payload)

        if v6_records:
            datasets.append(
                {
                    "source": "V6_PIPELINE",
                    "file": str(v6_path),
                    "records": v6_records,
                }
            )

    # ---------------------------------------------------------
    # OLD INDEPENDENT
    # ---------------------------------------------------------
    old_path = find_latest_strategy_json(
        INDEPENDENT_DIR,
        (
            f"independent_evidence_{TARGET_STRATEGY_ID}_*.json",
            f"independent_strategy_evidence_{TARGET_STRATEGY_ID}_*.json",
            "*independent*.json",
        ),
    )

    old_records = collect_old_independent_records(old_path)

    # Knowledge item 693 is only a fallback when no usable raw file exists.
    if not old_records:
        old_records = read_knowledge_item_symbol_evidence(693)

    if old_records:
        datasets.append(
            {
                "source": "INDEPENDENT_OLD",
                "file": str(old_path) if old_path else "knowledge_items:693",
                "records": old_records,
            }
        )

    # ---------------------------------------------------------
    # FRESH INDEPENDENT
    # ---------------------------------------------------------
    fresh_path = find_latest_strategy_json(
        FRESH_DIR,
        (
            f"fresh_independent_{TARGET_STRATEGY_ID}_*.json",
            "*fresh_independent*.json",
        ),
    )

    if fresh_path is not None:
        fresh_payload = json_load(fresh_path, {})
        fresh_records = collect_fresh_symbol_records(
            fresh_payload
        )

        if fresh_records:
            datasets.append(
                {
                    "source": "INDEPENDENT_FRESH",
                    "file": str(fresh_path),
                    "records": fresh_records,
                }
            )

    return {
        "available": bool(datasets),
        "datasets": datasets,
        "diagnostics": {
            "dataset_counts": {
                item["source"]: len(item["records"])
                for item in datasets
            },
            "dataset_symbols": {
                item["source"]: [
                    record["symbol"] for record in item["records"]
                ]
                for item in datasets
            },
        },
    }



def _normalize_chart_symbol(symbol):
    value = str(symbol or "").strip().upper()
    if not value:
        return ""
    return value


def _chart_symbol_candidates(symbol):
    value = _normalize_chart_symbol(symbol)
    if not value:
        return []

    candidates = [value]
    if "." not in value and "=" not in value and "^" not in value:
        candidates.append(f"{value}.IS")

    return list(dict.fromkeys(candidates))


def _parse_trade_datetime(value):
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(
            str(value).replace("Z", "+00:00")
        )
        return parsed.replace(tzinfo=None)
    except (TypeError, ValueError):
        return None


def _indicator_series(close):
    ema20 = close.ewm(span=20, adjust=False).mean()
    ema50 = close.ewm(span=50, adjust=False).mean()

    delta = close.diff()
    gain = delta.clip(lower=0).rolling(14).mean()
    loss = (-delta.clip(upper=0)).rolling(14).mean()
    rs = gain / loss.replace(0, float("nan"))
    rsi14 = 100 - (100 / (1 + rs))

    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    macd = ema12 - ema26
    signal = macd.ewm(span=9, adjust=False).mean()

    return ema20, ema50, rsi14, macd, signal


def research_historical_data(symbol, start_date, end_date, interval="1d", limit=5000):
    """
    Read-only historical OHLCV endpoint for MarketHQ research experiments.
    No database writes, broker calls, or order execution.
    """
    symbol = _normalize_chart_symbol(symbol)
    if not symbol:
        return {"available": False, "error": "symbol is required"}

    if interval != "1d":
        return {
            "available": False,
            "error": "Only interval=1d is supported by the research data adapter.",
            "symbol": symbol,
            "interval": interval,
        }

    try:
        start_dt = datetime.fromisoformat(str(start_date)).replace(tzinfo=None)
        end_dt = datetime.fromisoformat(str(end_date)).replace(tzinfo=None)
    except (TypeError, ValueError):
        return {
            "available": False,
            "error": "start and end must be ISO dates, e.g. 2024-01-01 and 2024-12-31.",
            "symbol": symbol,
            "interval": interval,
        }

    if end_dt <= start_dt:
        return {
            "available": False,
            "error": "end must be later than start.",
            "symbol": symbol,
            "interval": interval,
        }

    resolved_symbol = None
    frame = None
    fetch_errors = []

    for candidate in _chart_symbol_candidates(symbol):
        try:
            candidate_frame = yf.download(
                candidate,
                start=start_dt.strftime("%Y-%m-%d"),
                end=(end_dt + timedelta(days=1)).strftime("%Y-%m-%d"),
                interval=interval,
                auto_adjust=False,
                progress=False,
                threads=False,
            )
        except Exception as exc:
            fetch_errors.append({"symbol": candidate, "error": str(exc)})
            continue

        if candidate_frame is None or candidate_frame.empty:
            fetch_errors.append({
                "symbol": candidate,
                "error": "No historical OHLCV data returned.",
            })
            continue

        frame = candidate_frame
        resolved_symbol = candidate
        break

    if frame is None or frame.empty or resolved_symbol is None:
        return {
            "available": False,
            "error": "No historical OHLCV data returned for the requested window.",
            "symbol": symbol,
            "interval": interval,
            "fetch_errors": fetch_errors,
        }

    if hasattr(frame.columns, "levels"):
        try:
            if len(frame.columns.levels) == 2:
                frame.columns = [str(col[0]) for col in frame.columns]
        except Exception:
            pass

    required = ["Open", "High", "Low", "Close", "Volume"]
    missing = [column for column in required if column not in frame.columns]
    if missing:
        return {
            "available": False,
            "error": f"Missing OHLCV columns: {missing}",
            "symbol": symbol,
            "interval": interval,
        }

    frame = frame[required].copy()
    for column in required:
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    frame = frame.dropna(subset=required).sort_index()

    if limit > 0 and len(frame) > limit:
        frame = frame.iloc[-limit:]

    rows = []
    for index, row in frame.iterrows():
        timestamp = index.to_pydatetime() if hasattr(index, "to_pydatetime") else index
        rows.append({
            "timestamp": timestamp.isoformat(),
            "open": float(row["Open"]),
            "high": float(row["High"]),
            "low": float(row["Low"]),
            "close": float(row["Close"]),
            "volume": float(row["Volume"]),
        })

    return {
        "available": bool(rows),
        "symbol": resolved_symbol,
        "requested_symbol": symbol,
        "interval": interval,
        "requested_start": start_dt.strftime("%Y-%m-%d"),
        "requested_end": end_dt.strftime("%Y-%m-%d"),
        "bars": len(rows),
        "start": rows[0]["timestamp"] if rows else None,
        "end": rows[-1]["timestamp"] if rows else None,
        "rows": rows,
        "source": "yfinance",
        "read_only": True,
        "research_only": True,
    }


def trade_chart_snapshot(symbol, entry_time=None, exit_time=None, period_bars=90):
    """
    Read-only historical OHLCV chart data for a selected backtest trade.
    It never writes to the DB or sends broker orders.
    """
    symbol = _normalize_chart_symbol(symbol)
    if not symbol:
        return {
            "available": False,
            "error": "symbol is required",
        }

    entry_dt = _parse_trade_datetime(entry_time)
    exit_dt = _parse_trade_datetime(exit_time)

    # Fetch a bounded historical window around the selected trade.
    if entry_dt is not None:
        start_dt = entry_dt - timedelta(days=90)
    else:
        start_dt = datetime.utcnow() - timedelta(days=365)

    if exit_dt is not None:
        end_dt = exit_dt + timedelta(days=15)
    else:
        end_dt = datetime.utcnow()

    try:
        frame = yf.download(
            symbol,
            start=start_dt.strftime("%Y-%m-%d"),
            end=(end_dt + timedelta(days=1)).strftime("%Y-%m-%d"),
            interval="1d",
            auto_adjust=False,
            progress=False,
            threads=False,
        )
    except Exception as exc:
        return {
            "available": False,
            "error": f"Historical data fetch failed: {exc}",
            "symbol": symbol,
        }

    if frame is None or frame.empty:
        return {
            "available": False,
            "error": "No historical OHLCV data returned.",
            "symbol": symbol,
        }

    # yfinance may return MultiIndex columns for a single ticker.
    if hasattr(frame.columns, "levels"):
        try:
            if len(frame.columns.levels) == 2:
                frame.columns = [
                    str(col[0])
                    for col in frame.columns
                ]
        except Exception:
            pass

    required = ["Open", "High", "Low", "Close", "Volume"]
    missing = [c for c in required if c not in frame.columns]
    if missing:
        return {
            "available": False,
            "error": f"Missing OHLCV columns: {missing}",
            "symbol": symbol,
        }

    frame = frame[required].copy()
    for column in required:
        frame[column] = pd.to_numeric(
            frame[column],
            errors="coerce",
        )
    frame = frame.dropna(subset=required)
    frame = frame.sort_index()

    if frame.empty:
        return {
            "available": False,
            "error": "Historical OHLCV data became empty after normalization.",
            "symbol": symbol,
        }

    ema20, ema50, rsi14, macd, macd_signal = _indicator_series(
        frame["Close"]
    )
    frame["EMA20"] = ema20
    frame["EMA50"] = ema50
    frame["RSI14"] = rsi14
    frame["MACD"] = macd
    frame["MACD_SIGNAL"] = macd_signal

    # Focus the chart around the selected trade if possible.
    if entry_dt is not None:
        center = entry_dt
        distances = [
            abs((idx.to_pydatetime().replace(tzinfo=None) - center).days)
            for idx in frame.index
        ]
        nearest_index = min(
            range(len(distances)),
            key=distances.__getitem__,
        )
        left = max(0, nearest_index - int(period_bars * 0.65))
        right = min(
            len(frame),
            nearest_index + int(period_bars * 0.35) + 1,
        )
        frame = frame.iloc[left:right]

    if len(frame) > period_bars:
        frame = frame.iloc[-period_bars:]

    rows = []
    for index, row in frame.iterrows():
        timestamp = index.to_pydatetime() if hasattr(index, "to_pydatetime") else index
        rows.append(
            {
                "timestamp": timestamp.isoformat(),
                "open": float(row["Open"]),
                "high": float(row["High"]),
                "low": float(row["Low"]),
                "close": float(row["Close"]),
                "volume": float(row["Volume"]),
                "ema20": (
                    float(row["EMA20"])
                    if pd.notna(row["EMA20"]) else None
                ),
                "ema50": (
                    float(row["EMA50"])
                    if pd.notna(row["EMA50"]) else None
                ),
                "rsi14": (
                    float(row["RSI14"])
                    if pd.notna(row["RSI14"]) else None
                ),
                "macd": (
                    float(row["MACD"])
                    if pd.notna(row["MACD"]) else None
                ),
                "macd_signal": (
                    float(row["MACD_SIGNAL"])
                    if pd.notna(row["MACD_SIGNAL"]) else None
                ),
            }
        )

    return {
        "available": bool(rows),
        "symbol": symbol,
        "interval": "1d",
        "bars": len(rows),
        "start": rows[0]["timestamp"] if rows else None,
        "end": rows[-1]["timestamp"] if rows else None,
        "rows": rows,
        "read_only": True,
    }


def _read_trade_csv(path, symbol_hint=None, limit=500):
    rows = []
    if path is None or not path.exists():
        return rows

    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            for index, raw in enumerate(reader):
                if index >= limit:
                    break

                row = {
                    str(key).strip(): value
                    for key, value in raw.items()
                    if key is not None
                }

                def number(key):
                    value = row.get(key)
                    if value in (None, ""):
                        return None
                    try:
                        return float(value)
                    except (TypeError, ValueError):
                        return None

                rows.append({
                    "trade_id": index + 1,
                    "symbol": (
                        row.get("symbol")
                        or symbol_hint
                        or ""
                    ),
                    "side": row.get("side") or "",
                    "entry_time": row.get("entry_time") or "",
                    "exit_time": row.get("exit_time") or "",
                    "entry_price": number("entry_price"),
                    "exit_price": number("exit_price"),
                    "quantity": number("quantity"),
                    "notional": number("notional"),
                    "stop_price": number("stop_price"),
                    "target_price": number("target_price"),
                    "gross_pnl": number("gross_pnl"),
                    "commission": number("commission"),
                    "net_pnl": number("net_pnl"),
                    "return_percent": number("return_percent"),
                    "bars_held": (
                        int(number("bars_held"))
                        if number("bars_held") is not None
                        else None
                    ),
                    "exit_reason": row.get("exit_reason") or "",
                    "entry_signal": row.get("entry_signal") or "",
                    "entry_score": number("entry_score"),
                    "entry_reason": row.get("entry_reason") or "",
                })
    except (OSError, UnicodeError, csv.Error):
        return []

    return rows


def trade_viewer_snapshot():
    datasets = []
    directory = BACKTEST_RESULTS_DIR

    if directory.exists():
        # The Backtest Engine exports <symbol>_trades.csv.
        for path in sorted(
            directory.glob("*_trades.csv"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        ):
            safe_name = path.stem[:-6] if path.stem.endswith("_trades") else path.stem
            rows = _read_trade_csv(path, symbol_hint=safe_name)
            if rows:
                datasets.append({
                    "source": "BACKTEST_CSV",
                    "file": str(path),
                    "symbol": rows[0].get("symbol") or safe_name,
                    "trades": rows,
                })

    total_trades = sum(len(item["trades"]) for item in datasets)

    return {
        "available": bool(datasets),
        "directory": str(directory),
        "dataset_count": len(datasets),
        "total_trades": total_trades,
        "datasets": datasets,
        "read_only": True,
    }



def _normalize_symbol_for_match(symbol):
    value = str(symbol or "").strip().upper()
    if not value:
        return ""
    return value.replace(".IS", "")


def _research_json(value):
    if isinstance(value, dict):
        return value
    return json_load_from_text(value)


def _latest_research_lineage(symbol=None, strategy_id=None):
    """
    Read-only lineage lookup for the TradingView Research Terminal.
    It links a chart event to the durable Research Storage experiment/result
    without changing the existing research loop.
    """
    conn = connect_db()
    if conn is None or not table_exists(conn, "research_experiments"):
        if conn is not None:
            conn.close()
        return {
            "available": False,
            "reason": "Research Storage tables are unavailable.",
        }

    columns = table_columns(conn, "research_experiments")
    required = {
        "id", "experiment_id", "run_id", "strategy_id", "strategy_name",
        "symbol", "timeframe", "scope_train_start", "scope_train_end",
        "scope_validation_start", "scope_validation_end",
        "scope_independent_start", "scope_independent_end",
        "research_question", "hypothesis", "rule_definition",
        "parameters_json", "cost_model_json", "feedback_json",
        "provenance_json", "status", "created_at", "updated_at",
    }
    if not required.issubset(set(columns)):
        conn.close()
        return {
            "available": False,
            "reason": "Research experiment schema is incomplete.",
        }

    clauses = []
    params = []
    normalized = _normalize_symbol_for_match(symbol)
    if normalized:
        clauses.append(
            "REPLACE(UPPER(symbol), '.IS', '') = ?"
        )
        params.append(normalized)
    if strategy_id:
        clauses.append("strategy_id = ?")
        params.append(str(strategy_id))

    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    try:
        row = conn.execute(
            f"""
            SELECT *
            FROM research_experiments
            {where}
            ORDER BY COALESCE(updated_at, created_at) DESC, id DESC
            LIMIT 1
            """,
            tuple(params),
        ).fetchone()
    except sqlite3.Error:
        row = None

    if row is None:
        conn.close()
        return {
            "available": False,
            "reason": "No research experiment lineage found for this symbol.",
        }

    experiment = dict(row)
    result = None
    result_id = None
    if table_exists(conn, "research_results"):
        result_columns = table_columns(conn, "research_results")
        wanted = [
            "id", "result_id", "run_id", "execution_status", "validation_status",
            "started_at", "completed_at", "duration_ms", "metrics_json",
            "validation_json", "summary_json", "provenance_json", "result_hash",
            "created_at",
        ]
        selected = [c for c in wanted if c in result_columns]
        if selected:
            try:
                result_row = conn.execute(
                    f'SELECT {", ".join(selected)} FROM research_results '
                    'WHERE experiment_id=? ORDER BY COALESCE(created_at, completed_at) DESC, id DESC LIMIT 1',
                    (experiment["id"],),
                ).fetchone()
                if result_row is not None:
                    result = dict(result_row)
                    result_id = result.get("result_id")
            except sqlite3.Error:
                result = None

    conn.close()

    validation = _research_json((result or {}).get("validation_json"))
    metrics = _research_json((result or {}).get("metrics_json"))
    summary = _research_json((result or {}).get("summary_json"))
    result_provenance = _research_json((result or {}).get("provenance_json"))
    experiment_provenance = _research_json(experiment.get("provenance_json"))
    parameters = _research_json(experiment.get("parameters_json"))
    cost_model = _research_json(experiment.get("cost_model_json"))
    feedback = _research_json(experiment.get("feedback_json"))

    return {
        "available": True,
        "experiment": {
            "id": experiment.get("experiment_id"),
            "runId": experiment.get("run_id"),
            "strategyId": experiment.get("strategy_id"),
            "strategyName": experiment.get("strategy_name"),
            "symbol": experiment.get("symbol"),
            "timeframe": experiment.get("timeframe"),
            "researchQuestion": experiment.get("research_question"),
            "hypothesis": experiment.get("hypothesis"),
            "ruleDefinition": experiment.get("rule_definition"),
            "status": experiment.get("status"),
            "scope": {
                "trainStart": experiment.get("scope_train_start"),
                "trainEnd": experiment.get("scope_train_end"),
                "validationStart": experiment.get("scope_validation_start"),
                "validationEnd": experiment.get("scope_validation_end"),
                "independentStart": experiment.get("scope_independent_start"),
                "independentEnd": experiment.get("scope_independent_end"),
            },
            "parameters": parameters,
            "costModel": cost_model,
            "feedback": feedback,
            "provenance": experiment_provenance,
        },
        "result": {
            "resultId": result_id,
            "runId": (result or {}).get("run_id"),
            "executionStatus": (result or {}).get("execution_status"),
            "validationStatus": (result or {}).get("validation_status"),
            "startedAt": (result or {}).get("started_at"),
            "completedAt": (result or {}).get("completed_at"),
            "durationMs": (result or {}).get("duration_ms"),
            "metrics": metrics,
            "validation": validation,
            "summary": summary,
            "provenance": result_provenance,
            "resultHash": (result or {}).get("result_hash"),
        },
    }


def research_signals_snapshot(symbol=None, limit=250, strategy_id=None):
    """
    Read-only research events for the TradingView Research Terminal.

    Trade entries/exits are exposed as chart events and enriched with the
    durable experiment/result lineage. No writes, order routing, or pipeline
    mutation occur here.
    """
    limit = max(1, min(int(limit or 250), 500))
    normalized_symbol = str(symbol or "").strip().upper()
    lineage = _latest_research_lineage(
        symbol=normalized_symbol,
        strategy_id=strategy_id,
    )

    trades = []
    trade_snapshot = trade_viewer_snapshot()
    for dataset in trade_snapshot.get("datasets", []):
        for trade in dataset.get("trades", []):
            trade_symbol = str(trade.get("symbol") or "").strip().upper()
            if normalized_symbol:
                if (
                    trade_symbol != normalized_symbol
                    and _normalize_symbol_for_match(trade_symbol)
                    != _normalize_symbol_for_match(normalized_symbol)
                ):
                    continue
            trades.append({
                **trade,
                "source": dataset.get("source"),
                "file": dataset.get("file"),
            })

    events = []
    final_decision = read_final_decision().get("decision") or {}
    learning_ranking = read_learning_ranking().get("ranking") or {}
    for trade in trades:
        base = {
            "symbol": trade.get("symbol") or normalized_symbol,
            "source": "BACKTEST_TRADE",
            "tradeId": trade.get("trade_id"),
            "strategyId": (lineage.get("experiment") or {}).get("strategyId"),
            "strategyName": (lineage.get("experiment") or {}).get("strategyName"),
            "experimentId": (lineage.get("experiment") or {}).get("id"),
            "runId": (lineage.get("experiment") or {}).get("runId") or (lineage.get("result") or {}).get("runId"),
            "resultId": (lineage.get("result") or {}).get("resultId"),
            "researchQuestion": (lineage.get("experiment") or {}).get("researchQuestion"),
            "ruleDefinition": (lineage.get("experiment") or {}).get("ruleDefinition"),
            "scope": (lineage.get("experiment") or {}).get("scope") or {},
            "validation": (lineage.get("result") or {}).get("validation") or {},
            "validationStatus": (lineage.get("result") or {}).get("validationStatus"),
            "decision": final_decision,
            "learning": learning_ranking,
            "lineageAvailable": bool(lineage.get("available")),
        }

        provenance = {
            "experiment": lineage.get("experiment"),
            "result": lineage.get("result"),
            "decision": final_decision,
            "learning": learning_ranking,
        }

        entry_signal = trade.get("entry_signal") or "BUY"
        entry_type = str(entry_signal).upper()
        events.append({
            **base,
            "provenance": provenance,
            "eventType": "BUY" if any(x in entry_type for x in ("BUY", "LONG", "ENTRY")) else "ENTRY",
            "signalId": f"TRADE-{trade.get('trade_id')}-ENTRY",
            "timestamp": trade.get("entry_time"),
            "price": trade.get("entry_price"),
            "score": trade.get("entry_score"),
            "signal": entry_signal,
            "reason": trade.get("entry_reason"),
        })

        events.append({
            **base,
            "provenance": provenance,
            "eventType": "EXIT",
            "signalId": f"TRADE-{trade.get('trade_id')}-EXIT",
            "timestamp": trade.get("exit_time"),
            "price": trade.get("exit_price"),
            "score": None,
            "signal": "EXIT",
            "reason": trade.get("exit_reason"),
            "netPnl": trade.get("net_pnl"),
            "returnPercent": trade.get("return_percent"),
            "side": trade.get("side"),
        })

    events.sort(key=lambda item: str(item.get("timestamp") or ""))
    events = events[-limit:]

    return {
        "available": bool(events),
        "symbol": normalized_symbol or None,
        "source": "BACKTEST_CSV_WITH_RESEARCH_LINEAGE",
        "events": events,
        "eventCount": len(events),
        "lineage": lineage,
        "read_only": True,
        "research_only": True,
        "execution_enabled": False,
        "database_write_enabled": False,
        "broker_execution_enabled": False,
    }


def trade_viewer_trade_detail(symbol=None, trade_id=None):
    snapshot = trade_viewer_snapshot()

    symbol_text = str(symbol or "").strip().upper()
    try:
        target_id = int(trade_id) if trade_id is not None else None
    except (TypeError, ValueError):
        target_id = None

    for dataset in snapshot["datasets"]:
        for trade in dataset["trades"]:
            trade_symbol = str(trade.get("symbol") or "").strip().upper()
            if symbol_text and trade_symbol != symbol_text:
                continue
            if target_id is not None and int(trade.get("trade_id", -1)) != target_id:
                continue

            return {
                "available": True,
                "source": dataset["source"],
                "file": dataset["file"],
                "trade": trade,
            }

    return {
        "available": False,
        "source": None,
        "file": None,
        "trade": None,
    }


# =========================================================
# DATABASE SNAPSHOT
# =========================================================

CORE_TABLES = [
    "knowledge_sources",
    "knowledge_items",
    "learning_experiments",
    "experiment_results",
    "learned_rules",
    "brain_nodes",
    "brain_edges",
    "brain_episodes",
    "brain_evidence",
    "brain_node_evidence",
    "brain_edge_evidence",
    "brain_claims",
    "brain_claim_evidence",
    "brain_learning_events",
    "brain_contradictions",
    "brain_research_queue",
    "brain_research_evidence_reviews",
    "brain_research_strategy_evidence_reviews",
    "brain_evidence_consolidations",
    "brain_strategy_learning_rankings",
    "brain_schema_freezes",
]


def db_snapshot():
    conn = connect_db()
    if conn is None:
        return {
            "available": False,
            "path": str(DB_FILE),
            "table_counts": {},
            "missing_core_tables": CORE_TABLES[:],
        }

    counts = {}
    missing = []
    for table in CORE_TABLES:
        if table_exists(conn, table):
            counts[table] = table_count(conn, table)
        else:
            missing.append(table)

    result = {
        "available": True,
        "path": str(DB_FILE),
        "table_counts": counts,
        "missing_core_tables": missing,
        "schema_freeze": latest_successful_freeze(),
    }

    conn.close()
    return result


def knowledge_snapshot(limit=10):
    conn = connect_db()
    if conn is None:
        return {
            "items": 0,
            "sources": 0,
            "recent_items": [],
            "recent_sources": [],
        }

    result = {
        "items": table_count(conn, "knowledge_items"),
        "sources": table_count(conn, "knowledge_sources"),
        "recent_items": safe_rows(
            conn,
            "knowledge_items",
            [
                "id",
                "title",
                "summary",
                "method_name",
                "confidence",
                "item_type",
                "created_at",
                "updated_at",
            ],
            limit,
        ),
        "recent_sources": safe_rows(
            conn,
            "knowledge_sources",
            [
                "id",
                "title",
                "name",
                "url",
                "source_type",
                "status",
                "created_at",
                "updated_at",
            ],
            limit,
        ),
    }
    conn.close()
    return result


def brain_snapshot(limit=10):
    conn = connect_db()
    if conn is None:
        return {
            "nodes": 0,
            "edges": 0,
            "episodes": 0,
            "claims": 0,
            "learning_events": 0,
            "contradictions_open": 0,
            "research_queue_active": 0,
            "recent_reviews": [],
            "recent_strategy_reviews": [],
            "recent_queue": [],
        }

    open_contradictions = safe_query(
        conn,
        """
        SELECT COUNT(*) AS n
        FROM brain_contradictions
        WHERE status IN ('open','OPEN')
        """,
    )
    active_queue = safe_query(
        conn,
        """
        SELECT COUNT(*) AS n
        FROM brain_research_queue
        WHERE status IN ('queued','working')
        """,
    )

    result = {
        "nodes": table_count(conn, "brain_nodes"),
        "edges": table_count(conn, "brain_edges"),
        "episodes": table_count(conn, "brain_episodes"),
        "claims": table_count(conn, "brain_claims"),
        "learning_events": table_count(conn, "brain_learning_events"),
        "contradictions_open": int(
            open_contradictions[0]["n"] if open_contradictions else 0
        ),
        "research_queue_active": int(
            active_queue[0]["n"] if active_queue else 0
        ),
        "recent_reviews": safe_rows(
            conn,
            "brain_research_evidence_reviews",
            [
                "id",
                "knowledge_item_id",
                "observation_id",
                "verdict",
                "score",
                "contradiction_flag",
                "review_method",
                "created_at",
            ],
            limit,
        ),
        "recent_strategy_reviews": safe_rows(
            conn,
            "brain_research_strategy_evidence_reviews",
            [
                "id",
                "knowledge_item_id",
                "strategy_id",
                "verdict",
                "score",
                "review_method",
                "reasoning",
                "review_text",
                "review_reasoning",
                "created_at",
                "updated_at",
            ],
            limit,
        ),
        "recent_queue": safe_rows(
            conn,
            "brain_research_queue",
            [
                "id",
                "question",
                "priority",
                "status",
                "created_at",
                "updated_at",
                "metadata_json",
            ],
            limit,
        ),
    }

    conn.close()
    return result


def learning_snapshot(limit=10):
    conn = connect_db()
    if conn is None:
        return {
            "experiments": 0,
            "experiment_results": 0,
            "learned_rules": 0,
            "strategy_rankings": [],
            "recent_rules": [],
        }

    result = {
        "experiments": table_count(conn, "learning_experiments"),
        "experiment_results": table_count(conn, "experiment_results"),
        "learned_rules": table_count(conn, "learned_rules"),
        "recent_rules": safe_rows(
            conn,
            "learned_rules",
            [
                "id",
                "method_name",
                "symbol",
                "timeframe",
                "condition_name",
                "sample_size",
                "success_rate",
                "average_return",
                "confidence",
                "observation",
                "created_at",
                "updated_at",
            ],
            limit,
        ),
        "strategy_rankings": safe_rows(
            conn,
            "brain_strategy_learning_rankings",
            [
                "id",
                "strategy_id",
                "strategy_name",
                "learning_score",
                "learning_score_percent",
                "action",
                "reason",
                "verification_status",
                "candidate_status",
                "created_at",
                "updated_at",
            ],
            limit,
        ),
    }

    conn.close()
    return result



def _decision_number(value):
    """Best-effort numeric normalization for heterogeneous research artifacts."""
    try:
        if value is None or value == "":
            return None
        number = float(value)
        if number != number:  # NaN
            return None
        return number
    except (TypeError, ValueError):
        return None


def _decision_ratio(value):
    """Normalize ratios/percentages to the 0..1 interval when possible."""
    number = _decision_number(value)
    if number is None:
        return None
    if number > 1.0:
        number /= 100.0
    return max(0.0, min(1.0, number))


def _decision_nested(payload, *keys):
    """Find the first useful value among direct/nested keys."""
    if not isinstance(payload, dict):
        return None
    for key in keys:
        value = payload.get(key)
        if value is not None:
            return value
    for child in payload.values():
        if isinstance(child, dict):
            value = _decision_nested(child, *keys)
            if value is not None:
                return value
        elif isinstance(child, list):
            for item in child:
                value = _decision_nested(item, *keys)
                if value is not None:
                    return value
    return None


def _decision_posture(value, good=0.67, weak=0.45):
    """Map a normalized metric to a research posture."""
    number = _decision_ratio(value)
    if number is None:
        return "UNKNOWN"
    if number >= good:
        return "STRONG"
    if number >= weak:
        return "MIXED"
    return "WEAK"


def research_decision_snapshot():
    """
    Read-only Research Decision Engine.

    This is intentionally an in-memory synthesis layer: it does not write the
    existing final-decision artifact and never creates an execution signal.
    Existing artifact values remain visible as provenance/legacy context.
    """
    pipeline = read_pipeline()
    consolidation = read_consolidation()
    learning = read_learning_ranking()
    review = read_strategy_evidence_review()
    legacy = read_final_decision()

    ranking = (pipeline.get("strategy") or {}).get("ranking") or {}
    evidence = consolidation.get("summary") or {}
    learning_data = learning.get("ranking") or {}
    review_row = review.get("row") or {}

    # Evidence / validation posture.  Prefer normalized fields, then fall back
    # to nested source data so schema variants do not silently erase evidence.
    holdout_ratio = _decision_ratio(
        evidence.get("holdout_positive_ratio")
        if evidence.get("holdout_positive_ratio") is not None
        else _decision_nested(consolidation, "holdout_positive_ratio")
    )
    cross_time = _decision_ratio(
        evidence.get("cross_time_consistency")
        if evidence.get("cross_time_consistency") is not None
        else _decision_nested(consolidation, "cross_time_consistency", "independent_cross_time_consistency")
    )
    review_score_source = review_row.get("score")
    if review_score_source is None:
        review_score_source = evidence.get("strategy_review_score")
    if review_score_source is None:
        review_score_source = _decision_nested(review, "score", "strategy_review_score")
    review_score = _decision_ratio(review_score_source)
    pooled_positive = _decision_ratio(
        evidence.get("pooled_positive_ratio")
        if evidence.get("pooled_positive_ratio") is not None
        else _decision_nested(consolidation, "pooled_positive_ratio")
    )

    wfo = _decision_ratio(
        ranking.get("wfo_positive_ratio")
        if ranking.get("wfo_positive_ratio") is not None
        else _decision_nested(pipeline, "wfo_positive_ratio")
    )
    cross_symbol = _decision_ratio(
        ranking.get("cross_symbol_positive_ratio")
        if ranking.get("cross_symbol_positive_ratio") is not None
        else _decision_nested(pipeline, "cross_symbol_positive_ratio")
    )
    cost_survival = _decision_ratio(
        ranking.get("cost_survival")
        if ranking.get("cost_survival") is not None
        else _decision_nested(pipeline, "cost_survival")
    )
    parameter_stability = _decision_ratio(
        ranking.get("parameter_stability")
        if ranking.get("parameter_stability") is not None
        else _decision_nested(pipeline, "parameter_stability")
    )
    regime_stability = _decision_ratio(
        ranking.get("regime_stability")
        if ranking.get("regime_stability") is not None
        else _decision_nested(pipeline, "regime_stability")
    )

    verification = evidence.get("verified")
    if verification is None:
        verification = learning_data.get("verification_status")
    if verification is None:
        verification = _decision_nested(consolidation, "verified", "verification_status")
    if verification is None:
        verification = _decision_nested(learning, "verification_status")
    verification_text = str(verification or "UNKNOWN").upper()
    verification_ok = verification_text in {
        "TRUE", "VERIFIED", "PASS", "PASSED", "READY", "SUCCESS", "VALID"
    }

    # Sequence posture uses the durable backtest trade stream when available.
    trade_snapshot = trade_viewer_snapshot()
    pnls = []
    for dataset in trade_snapshot.get("datasets", []):
        for trade in dataset.get("trades", []):
            pnl = _decision_number(
                trade.get("net_pnl")
                if trade.get("net_pnl") is not None
                else trade.get("pnl")
            )
            if pnl is not None:
                pnls.append(pnl)
    wins = sum(1 for pnl in pnls if pnl > 0)
    losses = sum(1 for pnl in pnls if pnl < 0)
    sequence_positive = (wins / len(pnls)) if pnls else pooled_positive
    longest_loss = 0
    current_loss = 0
    for pnl in pnls:
        if pnl < 0:
            current_loss += 1
            longest_loss = max(longest_loss, current_loss)
        else:
            current_loss = 0
    sequence_posture = "UNKNOWN"
    if sequence_positive is not None:
        sequence_posture = (
            "STRONG" if sequence_positive >= 0.60 and longest_loss <= 4
            else "WEAK" if sequence_positive < 0.45 or longest_loss >= 8
            else "MIXED"
        )

    robustness_values = [v for v in (wfo, cross_symbol, cost_survival,
                                     parameter_stability, regime_stability) if v is not None]
    validation_values = [v for v in (holdout_ratio, cross_time, pooled_positive) if v is not None]
    evidence_values = [v for v in (review_score, pooled_positive, cross_time) if v is not None]

    robustness_score = sum(robustness_values) / len(robustness_values) if robustness_values else None
    validation_score = sum(validation_values) / len(validation_values) if validation_values else None
    evidence_score = sum(evidence_values) / len(evidence_values) if evidence_values else None

    strengths = []
    blockers = []
    reasons = []

    if wfo is not None and wfo >= 0.67:
        strengths.append("WFO consistency is strong.")
    elif wfo is not None and wfo < 0.45:
        blockers.append("WFO consistency is weak.")
    if cross_symbol is not None and cross_symbol >= 0.67:
        strengths.append("Cross-symbol evidence is supportive.")
    elif cross_symbol is not None and cross_symbol < 0.45:
        blockers.append("Cross-symbol evidence is weak.")
    if cost_survival is not None and cost_survival < 0.50:
        blockers.append("Cost survival is not sufficiently robust.")
    if parameter_stability is not None and parameter_stability < 0.50:
        blockers.append("Parameter stability is weak.")
    if regime_stability is not None and regime_stability < 0.50:
        blockers.append("Regime stability is weak.")
    if holdout_ratio is not None and holdout_ratio >= 0.67:
        strengths.append("Holdout evidence is supportive.")
    elif holdout_ratio is not None and holdout_ratio < 0.50:
        blockers.append("Holdout evidence is weak.")
    if not verification_ok:
        blockers.append("Evidence verification is not confirmed.")
    if sequence_posture == "WEAK":
        blockers.append("Sequence risk is elevated in the available trade sample.")

    score_components = [x for x in (validation_score, robustness_score, evidence_score) if x is not None]
    composite = sum(score_components) / len(score_components) if score_components else None
    if composite is None:
        state = "INSUFFICIENT_EVIDENCE"
    elif blockers and composite < 0.67:
        state = "FRAGILE"
    elif composite >= 0.67 and not blockers:
        state = "PROMISING"
    elif composite >= 0.50:
        state = "CONDITIONAL"
    else:
        state = "REJECTED"

    if state == "PROMISING":
        research_action = "DEEPEN_VALIDATION"
    elif state == "CONDITIONAL":
        research_action = "TARGET_WEAK_EVIDENCE"
    elif state == "FRAGILE":
        research_action = "STRESS_TEST"
    elif state == "REJECTED":
        research_action = "RESEARCH_ALTERNATIVE"
    else:
        research_action = "COLLECT_EVIDENCE"

    next_question = (
        evidence.get("next_research_question")
        or learning_data.get("next_research_question")
        or "Which weak evidence dimension most limits confidence in this strategy?"
    )

    if blockers:
        reasons.extend(blockers[:3])
    if strengths:
        reasons.extend(strengths[:3])
    if not reasons:
        reasons.append("No sufficient evidence dimension is currently available for a stronger conclusion.")

    confidence = None
    if composite is not None:
        completeness = len(score_components) / 3.0
        confidence = max(0.0, min(1.0, composite * (0.75 + 0.25 * completeness)))

    return {
        "available": bool(
            pipeline.get("available") or consolidation.get("available")
            or learning.get("available") or legacy.get("available")
        ),
        "strategy_id": TARGET_STRATEGY_ID,
        "engine_version": "RESEARCH_DECISION_ENGINE_V1",
        "state": state,
        "decision": state,
        "research_action": research_action,
        "composite_score": composite,
        "confidence": confidence,
        "evidence_posture": _decision_posture(evidence_score),
        "validation_posture": _decision_posture(validation_score),
        "robustness_posture": _decision_posture(robustness_score),
        "regime_posture": _decision_posture(regime_stability),
        "sequence_posture": sequence_posture,
        "verification_posture": "VERIFIED" if verification_ok else verification_text,
        "metrics": {
            "holdout_positive_ratio": holdout_ratio,
            "cross_time_consistency": cross_time,
            "pooled_positive_ratio": pooled_positive,
            "wfo_positive_ratio": wfo,
            "cross_symbol_positive_ratio": cross_symbol,
            "cost_survival": cost_survival,
            "parameter_stability": parameter_stability,
            "regime_stability": regime_stability,
            "sequence_positive_ratio": sequence_positive,
            "trade_count": len(pnls),
            "wins": wins,
            "losses": losses,
            "longest_loss_streak": longest_loss,
        },
        "reasons": reasons,
        "strengths": strengths,
        "blockers": blockers,
        "next_research_question": next_question,
        "legacy_final_decision": legacy.get("decision"),
        "sources": {
            "pipeline": pipeline.get("file"),
            "consolidation": consolidation.get("file"),
            "learning": learning.get("file"),
            "strategy_review": review.get("row"),
            "legacy_decision": legacy.get("file"),
        },
        "research_only": True,
        "execution_enabled": False,
        "database_write_enabled": False,
        "broker_execution_enabled": False,
    }

def research_experiment_request_snapshot():
    """
    Build a deterministic, read-only experiment request from the current
    Research Decision.  This is a contract for the Experiment Generator;
    it does not persist, queue, execute, or mutate anything.
    """
    decision = research_decision_snapshot()
    state = str(decision.get("state") or "INSUFFICIENT_EVIDENCE")
    action = str(decision.get("research_action") or "COLLECT_EVIDENCE")
    metrics = decision.get("metrics") or {}
    blockers = list(decision.get("blockers") or [])
    next_question = str(
        decision.get("next_research_question")
        or "Which weak evidence dimension most limits confidence in this strategy?"
    )

    blocker_text = " ".join(blockers).lower()
    dimensions = []
    if "cost" in blocker_text:
        dimensions.append({
            "name": "cost_robustness",
            "instruction": "Re-test with explicit conservative transaction-cost assumptions and compare cost-free vs cost-adjusted results.",
        })
    if "parameter" in blocker_text:
        dimensions.append({
            "name": "parameter_stability",
            "instruction": "Perturb the fixed strategy parameters around the current baseline and measure performance degradation and consistency.",
        })
    if "regime" in blocker_text:
        dimensions.append({
            "name": "regime_stability",
            "instruction": "Split results by market regime and test whether the observed edge survives outside the dominant regime.",
        })
    if "holdout" in blocker_text or "verification" in blocker_text:
        dimensions.append({
            "name": "independent_time_slice",
            "instruction": "Use a genuinely independent time slice with the same fixed rules and parameters.",
        })
    if "sequence" in blocker_text:
        dimensions.append({
            "name": "sequence_risk",
            "instruction": "Stress the observed trade sequence and loss-streak profile; report drawdown and streak sensitivity.",
        })

    if not dimensions:
        dimensions = [{
            "name": "independent_validation",
            "instruction": "Re-test the strategy on an independent sample with unchanged rules, parameters, and explicit costs.",
        }]

    experiment_type = {
        "STRESS_TEST": "RESEARCH_STRESS_TEST",
        "TARGET_WEAK_EVIDENCE": "TARGETED_VALIDATION",
        "DEEPEN_VALIDATION": "DEEP_VALIDATION",
        "RESEARCH_ALTERNATIVE": "ALTERNATIVE_STRATEGY_RESEARCH",
        "COLLECT_EVIDENCE": "EVIDENCE_COLLECTION",
    }.get(action, "RESEARCH_VALIDATION")

    priority = 9 if state == "FRAGILE" else 8 if state == "CONDITIONAL" else 7

    return {
        "available": bool(decision.get("available")),
        "contract_version": "RESEARCH_EXPERIMENT_REQUEST_V1",
        "strategy_id": TARGET_STRATEGY_ID,
        "state": state,
        "research_action": action,
        "experiment_type": experiment_type,
        "priority": priority,
        "research_question": next_question,
        "hypothesis": "The identified weak evidence dimension can be improved or rejected under an independent, explicitly controlled research test.",
        "design": {
            "same_strategy_id": TARGET_STRATEGY_ID,
            "keep_rules_fixed": True,
            "keep_parameters_fixed_for_primary_test": True,
            "execution_enabled": False,
            "database_write_enabled": False,
            "broker_execution_enabled": False,
            "dimensions": dimensions,
            "required_outputs": [
                "full_run_result",
                "holdout_result",
                "cost_adjusted_result",
                "parameter_sensitivity",
                "regime_breakdown",
                "sequence_risk_summary",
            ],
        },
        "decision_metrics": metrics,
        "source": {
            "decision_engine": decision.get("engine_version"),
            "legacy_decision": decision.get("legacy_final_decision"),
            "next_research_question_source": "research_decision",
        },
        "safety": SAFETY,
    }



def adaptive_research_plan_snapshot():
    """
    Adaptive Research Planner V1.

    Read-only planning layer:
    - derives the current Research Decision,
    - ranks weak research dimensions from available metrics,
    - checks whether the same research question is already active,
    - returns the next recommended research focus without queue mutation,
      database writes, execution, or broker calls.
    """
    decision = research_decision_snapshot()
    metrics = decision.get("metrics") or {}
    blockers = [str(item) for item in (decision.get("blockers") or [])]
    next_question = str(
        decision.get("next_research_question")
        or "Which weak evidence dimension most limits confidence in this strategy?"
    )

    dimensions = [
        {
            "name": "holdout_validation",
            "metric": "holdout_positive_ratio",
            "score": _decision_ratio(metrics.get("holdout_positive_ratio")),
            "question": "Can the strategy reproduce its edge on an independent holdout slice with fixed rules and parameters?",
            "reason": "Holdout validation is below the desired evidence threshold.",
        },
        {
            "name": "cost_robustness",
            "metric": "cost_survival",
            "score": _decision_ratio(metrics.get("cost_survival")),
            "question": "Does the strategy retain its edge after conservative transaction costs and slippage?",
            "reason": "Cost survival is weak.",
        },
        {
            "name": "parameter_stability",
            "metric": "parameter_stability",
            "score": _decision_ratio(metrics.get("parameter_stability")),
            "question": "Does the edge remain stable when fixed parameters are perturbed around the baseline?",
            "reason": "Parameter stability is weak.",
        },
        {
            "name": "regime_stability",
            "metric": "regime_stability",
            "score": _decision_ratio(metrics.get("regime_stability")),
            "question": "Does the strategy remain viable across distinct market regimes?",
            "reason": "Regime stability is weak.",
        },
        {
            "name": "cross_symbol_validation",
            "metric": "cross_symbol_positive_ratio",
            "score": _decision_ratio(metrics.get("cross_symbol_positive_ratio")),
            "question": "Does the strategy reproduce positive results across independent symbols?",
            "reason": "Cross-symbol evidence is comparatively weak.",
        },
        {
            "name": "wfo_validation",
            "metric": "wfo_positive_ratio",
            "score": _decision_ratio(metrics.get("wfo_positive_ratio")),
            "question": "Does the strategy remain consistent across walk-forward validation folds?",
            "reason": "Walk-forward consistency is comparatively weak.",
        },
        {
            "name": "sequence_risk",
            "metric": "sequence_positive_ratio",
            "score": _decision_ratio(metrics.get("sequence_positive_ratio")),
            "question": "Does the observed trade sequence remain acceptable under streak and drawdown stress?",
            "reason": "Sequence performance is comparatively weak.",
        },
    ]

    available = [item for item in dimensions if item["score"] is not None]
    available.sort(key=lambda item: (item["score"], item["name"]))

    aliases = {
        "holdout_validation": ("holdout", "verification", "independent time"),
        "cost_robustness": ("cost",),
        "parameter_stability": ("parameter",),
        "regime_stability": ("regime",),
        "cross_symbol_validation": ("cross-symbol", "cross symbol"),
        "wfo_validation": ("wfo", "walk-forward"),
        "sequence_risk": ("sequence", "streak"),
    }

    def blocker_match(item):
        haystack = (" ".join(blockers) + " " + item["name"]).lower()
        return any(token in haystack for token in aliases.get(item["name"], ()))

    blocked_available = [item for item in available if blocker_match(item)]
    selected = blocked_available[0] if blocked_available else (available[0] if available else None)

    if selected is None:
        selected = {
            "name": "evidence_collection",
            "metric": None,
            "score": None,
            "question": next_question,
            "reason": "No measurable research dimension is currently available.",
        }

    active_queue_rows = []
    queue_active = False
    same_question_active = False

    conn = connect_db()
    if conn is not None and table_exists(conn, "brain_research_queue"):
        columns = table_columns(conn, "brain_research_queue")
        status_col = first_existing_column(columns, ("status",))
        selected_cols = [
            c for c in
            ("id", "question", "research_question", "status", "priority", "created_at", "updated_at")
            if c in columns
        ]

        if status_col and selected_cols:
            order_col = first_existing_column(columns, ("updated_at", "created_at", "id")) or status_col
            query = (
                f'SELECT {", ".join(f"""\"{c}\"""" for c in selected_cols)} '
                f'FROM "brain_research_queue" '
                f'WHERE "{status_col}" IN (\'queued\', \'working\') '
                f'ORDER BY "{order_col}" DESC LIMIT 25'
            )
            active_queue_rows = safe_query(conn, query)
            queue_active = bool(active_queue_rows)

            normalized_target = " ".join(next_question.lower().split())
            selected_question = str(selected.get("question") or "").strip()
            normalized_selected = " ".join(selected_question.lower().split())

            for row in active_queue_rows:
                candidate = row.get("question") or row.get("research_question") or ""
                normalized_candidate = " ".join(str(candidate).lower().split())
                if (
                    normalized_target
                    and normalized_candidate == normalized_target
                ) or (
                    normalized_selected
                    and normalized_candidate == normalized_selected
                ):
                    same_question_active = True
                    break

    if conn is not None:
        conn.close()

    if same_question_active:
        plan_status = "ACTIVE_QUESTION_ALREADY_QUEUED"
        planner_action = "WAIT_FOR_ACTIVE_RESEARCH"
    elif selected["score"] is None:
        plan_status = "INSUFFICIENT_MEASURABLE_EVIDENCE"
        planner_action = "COLLECT_EVIDENCE"
    else:
        plan_status = "READY"
        planner_action = "TARGET_WEAK_DIMENSION"

    return {
        "available": bool(decision.get("available")),
        "planner_version": "ADAPTIVE_RESEARCH_PLANNER_V1",
        "strategy_id": TARGET_STRATEGY_ID,
        "decision_state": decision.get("state"),
        "decision_action": decision.get("research_action"),
        "plan_status": plan_status,
        "planner_action": planner_action,
        "selected_dimension": selected["name"],
        "selected_metric": selected["metric"],
        "selected_score": selected["score"],
        "selected_question": selected["question"],
        "selected_reason": selected["reason"],
        "decision_next_research_question": next_question,
        "ranked_dimensions": [
            {
                "name": item["name"],
                "metric": item["metric"],
                "score": item["score"],
                "priority_rank": index + 1,
            }
            for index, item in enumerate(available)
        ],
        "active_queue_count": len(active_queue_rows),
        "same_question_active": same_question_active,
        "research_queue_status": "ACTIVE" if queue_active else "EMPTY",
        "research_only": True,
        "execution_enabled": False,
        "database_write_enabled": False,
        "broker_execution_enabled": False,
    }


def strategy_snapshot():
    pipeline = read_pipeline()
    consolidation = read_consolidation()
    learning = read_learning_ranking()
    review = read_strategy_evidence_review()
    final_decision = read_final_decision()
    research_decision = research_decision_snapshot()

    return {
        "strategy_id": TARGET_STRATEGY_ID,
        "pipeline": pipeline,
        "consolidation": consolidation,
        "learning": learning,
        "strategy_review": review,
        "final_decision": final_decision,
        "research_decision": research_decision,
        "research_experiment_request": research_experiment_request_snapshot(),
        "adaptive_research_plan": adaptive_research_plan_snapshot(),
    }


# =========================================================
# DASHBOARD CONTRACT
# =========================================================

def dashboard_snapshot():
    db = db_snapshot()
    knowledge = knowledge_snapshot(limit=8)
    brain = brain_snapshot(limit=8)
    learning = learning_snapshot(limit=8)
    strategy = strategy_snapshot()

    return {
        "api_version": "DASHBOARD_BACKEND_V2.5",
        "generated_at": utc_now(),
        "system": {
            "name": "MarketHQ",
            "role": "Research Intelligence Dashboard Backend",
            "target_strategy_id": TARGET_STRATEGY_ID,
        },
        "safety": SAFETY,
        "schema": {
            "status": (
                "READY"
                if db["available"] and not db["missing_core_tables"]
                else "DEGRADED"
            ),
            "missing_core_tables": db["missing_core_tables"],
            "latest_freeze": db["schema_freeze"],
        },
        "database": db,
        "knowledge": knowledge,
        "brain": brain,
        "learning": learning,
        "strategy": strategy,
        "symbol_explorer": evidence_symbol_snapshot(),
    }


# =========================================================
# HTTP API
# =========================================================

def parse_limit(query):
    raw = query.get("limit", ["10"])[0]
    try:
        return max(1, min(int(raw), 100))
    except (TypeError, ValueError):
        return 10


def source_debug_snapshot():
    """Return a read-only diagnostic snapshot of configured research sources."""
    directories = {
        "pipeline": PIPELINE_DIR,
        "fresh_independent": FRESH_DIR,
        "backtest_results": BACKTEST_RESULTS_DIR,
        "independent": INDEPENDENT_DIR,
        "consolidation": CONSOLIDATION_DIR,
        "ranking": RANKING_DIR,
        "decision": DECISION_DIR,
        "freeze": FREEZE_DIR,
    }

    directory_snapshot = {}
    for name, directory in directories.items():
        try:
            files = sorted(
                [p.name for p in directory.glob("*.json") if p.is_file()],
                reverse=True,
            ) if directory.exists() else []
        except OSError:
            files = []
        directory_snapshot[name] = {
            "path": str(directory),
            "exists": directory.exists(),
            "json_count": len(files),
            "latest": files[0] if files else None,
        }

    return {
        "strategy_id": TARGET_STRATEGY_ID,
        "database": db_snapshot(),
        "directories": directory_snapshot,
        "latest": {
            "pipeline": str(latest_json(PIPELINE_DIR, "strategy_pipeline_v6_*.json") or ""),
            "fresh_independent": str(latest_json(FRESH_DIR, "fresh_independent_*.json") or ""),
            "decision": str(latest_json(DECISION_DIR, "final_decision_*.json") or ""),
            "learning": str(latest_json(RANKING_DIR, "learning_ranking_*.json") or ""),
        },
        "safety": SAFETY,
        "read_only": True,
    }





class DashboardBackendHandler(BaseHTTPRequestHandler):
    server_version = "MarketHQDashboardBackend/2.3"

    def _send_json(self, payload, status=200):
        body = json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
            default=str,
        ).encode("utf-8")

        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        # UI :8000 -> API :8010 requires explicit CORS permission.
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("X-MarketHQ-Research-Only", "true")
        self.send_header("X-MarketHQ-Execution-Enabled", "false")
        self.end_headers()
        self.wfile.write(body)

    def _send_error(self, message, status=404):
        self._send_json(
            {
                "success": False,
                "error": message,
                "api_version": "DASHBOARD_BACKEND_V2.5",
                "generated_at": utc_now(),
                "safety": SAFETY,
            },
            status,
        )

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Max-Age", "600")
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"
        query = parse_qs(parsed.query)

        try:
            if path == "/":
                self._send_json(
                    {
                        "service": "MarketHQ Dashboard Backend V1",
                        "status": "ok",
                        "api_version": "DASHBOARD_BACKEND_V2.5",
                        "read_only": True,
                        "research_only": True,
                        "execution_enabled": False,
                        "endpoints": [
                            "/api/health",
                            "/api/snapshot",
                            "/api/schema",
                            "/api/knowledge",
                            "/api/brain",
                            "/api/learning",
                            "/api/strategy",
                            "/api/pipeline",
                            "/api/evidence",
                            "/api/research-data",
                            "/api/research-signals",
                            "/api/research-experiment",
                            "/api/research-plan",
                        ],
                    }
                )
                return

            if path == "/api/health":
                db = db_snapshot()
                self._send_json(
                    {
                        "success": True,
                        "status": (
                            "READY"
                            if db["available"] and not db["missing_core_tables"]
                            else "DEGRADED"
                        ),
                        "api_version": "DASHBOARD_BACKEND_V2.5",
                        "generated_at": utc_now(),
                        "database_available": db["available"],
                        "missing_core_tables": db["missing_core_tables"],
                        "safety": SAFETY,
                    }
                )
                return

            if path == "/api/schema":
                db = db_snapshot()
                self._send_json(
                    {
                        "success": True,
                        "schema_status": (
                            "READY"
                            if db["available"] and not db["missing_core_tables"]
                            else "DEGRADED"
                        ),
                        "missing_core_tables": db["missing_core_tables"],
                        "latest_freeze": db["schema_freeze"],
                        "contract_source": (
                            "brain_schema_freezes"
                            if db["schema_freeze"] is not None
                            else "unavailable"
                        ),
                        "safety": SAFETY,
                    }
                )
                return

            if path == "/api/snapshot":
                self._send_json(
                    {
                        "success": True,
                        "data": dashboard_snapshot(),
                    }
                )
                return

            if path == "/api/knowledge":
                self._send_json(
                    {
                        "success": True,
                        "data": knowledge_snapshot(parse_limit(query)),
                    }
                )
                return

            if path == "/api/brain":
                self._send_json(
                    {
                        "success": True,
                        "data": brain_snapshot(parse_limit(query)),
                    }
                )
                return

            if path == "/api/learning":
                self._send_json(
                    {
                        "success": True,
                        "data": learning_snapshot(parse_limit(query)),
                    }
                )
                return

            if path == "/api/strategy":
                self._send_json(
                    {
                        "success": True,
                        "data": strategy_snapshot(),
                    }
                )
                return

            if path == "/api/pipeline":
                self._send_json(
                    {
                        "success": True,
                        "data": read_pipeline(),
                    }
                )
                return



            if path == "/api/trade-chart":
                params = parse_qs(parsed.query)
                symbol = (
                    params.get("symbol", [""])[0]
                    if params else ""
                )
                entry_time = (
                    params.get("entry_time", [""])[0]
                    if params else None
                )
                exit_time = (
                    params.get("exit_time", [""])[0]
                    if params else None
                )
                self._send_json(
                    {
                        "success": True,
                        "data": trade_chart_snapshot(
                            symbol=symbol,
                            entry_time=entry_time,
                            exit_time=exit_time,
                        ),
                        "read_only": True,
                    }
                )
                return

            if path == "/api/research-data":
                symbol = query.get("symbol", [""])[0]
                start_date = query.get("start", [""])[0]
                end_date = query.get("end", [""])[0]
                interval = query.get("interval", ["1d"])[0]
                try:
                    limit = max(1, min(int(query.get("limit", ["5000"])[0]), 5000))
                except (TypeError, ValueError):
                    limit = 5000

                data = research_historical_data(
                    symbol=symbol,
                    start_date=start_date,
                    end_date=end_date,
                    interval=interval,
                    limit=limit,
                )
                self._send_json(
                    {
                        "success": bool(data.get("available")),
                        "data": data,
                        "read_only": True,
                        "safety": SAFETY,
                    },
                    200 if data.get("available") else 400,
                )
                return

            if path == "/api/research-experiment":
                self._send_json(
                    {
                        "success": True,
                        "data": research_experiment_request_snapshot(),
                        "read_only": True,
                        "safety": SAFETY,
                    }
                )
                return

            if path == "/api/research-plan":
                self._send_json(
                    {
                        "success": True,
                        "data": adaptive_research_plan_snapshot(),
                        "read_only": True,
                        "safety": SAFETY,
                    }
                )
                return

            if path == "/api/research-signals":
                limit = parse_limit(query)
                symbol = query.get("symbol", [""])[0] if query else ""
                strategy_id = query.get("strategy_id", [None])[0] if query else None
                self._send_json(
                    {
                        "success": True,
                        "data": research_signals_snapshot(
                            symbol=symbol,
                            limit=limit,
                            strategy_id=strategy_id,
                        ),
                        "read_only": True,
                    }
                )
                return

            if path == "/api/trades":
                self._send_json(
                    {
                        "success": True,
                        "data": trade_viewer_snapshot(),
                        "read_only": True,
                    }
                )
                return

            if path == "/api/trade":
                params = parse_qs(parsed.query)
                symbol = (
                    params.get("symbol", [""])[0]
                    if params else ""
                )
                trade_id = (
                    params.get("trade_id", [None])[0]
                    if params else None
                )
                self._send_json(
                    {
                        "success": True,
                        "data": trade_viewer_trade_detail(
                            symbol=symbol,
                            trade_id=trade_id,
                        ),
                        "read_only": True,
                    }
                )
                return

            if path == "/api/source-debug":
                self._send_json(
                    {
                        "success": True,
                        "data": source_debug_snapshot(),
                        "read_only": True,
                    }
                )
                return

            if path == "/api/symbols":
                self._send_json(
                    {
                        "success": True,
                        "data": evidence_symbol_snapshot(),
                    }
                )
                return

            if path == "/api/evidence":
                self._send_json(
                    {
                        "success": True,
                        "data": {
                            "independent_old": read_latest_result(
                                INDEPENDENT_DIR,
                                f"independent_evidence_{TARGET_STRATEGY_ID}_*.json",
                            ),
                            "fresh_independent": read_latest_result(
                                FRESH_DIR,
                                f"fresh_independent_{TARGET_STRATEGY_ID}_*.json",
                            ),
                            "consolidation": read_consolidation(),
                            "strategy_review": read_strategy_evidence_review(),
                            "final_decision": read_final_decision(),
                            "learning_ranking": read_learning_ranking(),
                        },
                    }
                )
                return

            self._send_error("Not found.", 404)

        except Exception as exc:
            self._send_error(f"Backend error: {exc}", 500)

    def do_POST(self):
        # V1 is deliberately read-only.
        self._send_error(
            "Dashboard Backend V1 read-only'dir; POST mutation endpoint yok.",
            405,
        )

    def do_PUT(self):
        self._send_error(
            "Dashboard Backend V1 read-only'dir; PUT mutation endpoint yok.",
            405,
        )

    def do_DELETE(self):
        self._send_error(
            "Dashboard Backend V1 read-only'dir; DELETE mutation endpoint yok.",
            405,
        )

    def log_message(self, format_string, *args):
        return


def main():
    print()
    print("=" * 76)
    print("MARKETHQ DASHBOARD BACKEND V1")
    print("=" * 76)
    print(f"Database          : {DB_FILE}")
    print(f"Server             : http://{HOST}:{PORT}")
    print("API Mode           : READ-ONLY")
    print("Research Only      : True")
    print("Execution Enabled  : False")
    print()
    print("Endpoints:")
    print("  /api/health")
    print("  /api/snapshot")
    print("  /api/schema")
    print("  /api/knowledge")
    print("  /api/brain")
    print("  /api/learning")
    print("  /api/strategy")
    print("  /api/pipeline")
    print("  /api/evidence")
    print("  /api/research-signals")
    print("  /api/research-experiment")
    print("  /api/research-plan")
    print()
    print("CTRL+C ile durdur.")
    print()

    server = ThreadingHTTPServer((HOST, PORT), DashboardBackendHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nBackend kapatıldı.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()




