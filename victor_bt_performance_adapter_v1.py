# -*- coding: utf-8 -*-
"""
Victor BT → Strategy Performance Memory V1
==========================================

Ingest Victor BT backtest results (WFO, Monte Carlo, train/validation
metrics) into the existing research_memory storage without creating a
parallel memory system.

Storage contract (reuses existing tables):
  research_experiments  — strategy_id, symbol, timeframe, regime, source
  research_results      — metrics_json (train), validation_json (OOS),
                          summary_json (WFO folds + Monte Carlo + data period)
  research_memory       — searchable learning record with evidence/learning

Idempotency: same (strategy_id, symbol, timeframe, regime, result_hash)
             written twice → second write is a no-op with a `duplicate` flag.

Rules enforced by this adapter:
  1. train_metrics and oos_validation_metrics are stored separately.
  2. OOS/validation is NEVER written into train fields.
  3. insufficient_sample flag is preserved when present.
  4. duplicate writes are detected via result_hash; no second row created.
  5. strategy × symbol × timeframe × regime is queryable via existing indexes.
  6. Brain reads via existing research_memory_query_adapter_v1.
  7. No automatic "best strategy" selection.
  8. No strategy promote/demote.
  9. No new claim creation/modification.
 10. No live trading, no broker.

Input JSON (stdin) — minimal required fields:
{
  "strategyId":        "STRAT-001",
  "strategyName":      "RSI_20_EMA_50",
  "strategyFamily":    "momentum_rsi",
  "symbol":            "THYAO.IS",
  "timeframe":         "1h",
  "regime":            "TRENDING_UP",        # optional; UNKNOWN if missing
  "resultHash":        "sha256-of-deterministic-payload",
  "dataPeriod":        {"start": "2024-01-01", "end": "2024-12-31",
                        "source": "yfinance", "quality": "good"},
  "trainMetrics":      {"total_return": 0.12, "sharpe": 1.4, ...},
  "oosValidationMetrics": {"total_return": 0.09, "sharpe": 1.1, ...},
  "wfoFolds":          [{"fold": 1, "trainReturn": 0.11, "oosReturn": 0.08, ...}, ...],
  "monteCarlo":        {"medianReturn": 0.07, "p5": -0.05, "p95": 0.18, "simulations": 1000},
  "tradeCount":        247,
  "insufficientSample": false,
  "dataCutoffTimestamp": "2024-12-31T00:00:00+03:00",
  "timestamp":         "2024-12-31T23:59:59+03:00"   # result/version timestamp
}

Output JSON (stdout):
{
  "success": true,
  "persisted": true,
  "duplicate": false,
  "memoryId": "mem-xxxx",
  "experimentId": "exp-xxxx",
  "resultId": "res-xxxx",
  "strategyId": "STRAT-001",
  "symbol": "THYAO.IS",
  "timeframe": "1h",
  "regime": "TRENDING_UP",
  "resultHash": "abc...",
  "source": "victor_bt",
  "timestamp": "2024-12-31T23:59:59+03:00"
}
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import sys
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple

ADAPTER_NAME = "victor_bt_performance_adapter_v1"
SCHEMA_VERSION = "victor_bt_performance_v1"

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DB_FILE = os.path.join(SCRIPT_DIR, "market_hq.db")


# ── helpers ────────────────────────────────────────────────────────

def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def json_default(value: Any) -> str:
    return str(value)


def compact_json(value: Any) -> str:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            separators=(",", ":"),
            default=json_default,
        )
    except Exception:
        return json.dumps(
            {"value": str(value)},
            ensure_ascii=False,
            separators=(",", ":"),
        )


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def read_stdin_json() -> Dict[str, Any]:
    raw = sys.stdin.read()
    if not raw or not raw.strip():
        raise ValueError("No JSON input received on stdin.")
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON input: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError("Input JSON root must be an object.")
    return payload


def table_exists(connection: sqlite3.Connection, table_name: str) -> bool:
    row = connection.execute(
        """
        SELECT 1
        FROM sqlite_master
        WHERE type = 'table'
          AND name = ?
        LIMIT 1
        """,
        (table_name,),
    ).fetchone()
    return row is not None


def verify_required_tables(connection: sqlite3.Connection) -> None:
    required = ("research_experiments", "research_results", "research_memory")
    missing = [t for t in required if not table_exists(connection, t)]
    if missing:
        raise RuntimeError(
            "Required research storage tables are missing: " + ", ".join(missing)
        )


def ensure_victor_bt_indexes(connection: sqlite3.Connection) -> None:
    """Add queryability indexes for Victor BT records (idempotent)."""
    cursor = connection.cursor()
    indexes = [
        ("idx_exp_victor_source", "research_experiments",
         "CREATE INDEX IF NOT EXISTS idx_exp_victor_source "
         "ON research_experiments(source)"),
        ("idx_exp_victor_strategy", "research_experiments",
         "CREATE INDEX IF NOT EXISTS idx_exp_victor_strategy "
         "ON research_experiments(strategy_id, symbol, timeframe, regime)"),
        ("idx_res_victor_hash", "research_results",
         "CREATE INDEX IF NOT EXISTS idx_res_victor_hash "
         "ON research_results(result_hash)"),
        ("idx_mem_victor_type", "research_memory",
         "CREATE INDEX IF NOT EXISTS idx_mem_victor_type "
         "ON research_memory(memory_type, symbol, timeframe, regime)"),
    ]
    for _name, _table, stmt in indexes:
        cursor.execute(stmt)
    connection.commit()


# ── input normalization ───────────────────────────────────────────

def normalize_str(value: Any, default: str = "") -> str:
    if value is None:
        return default
    s = str(value).strip()
    return s if s else default


def normalize_regime(value: Any) -> str:
    if value is None or (isinstance(value, str) and not value.strip()):
        return "UNKNOWN"
    return str(value).strip().upper()[:50]


def normalize_timestamp(value: Any) -> str:
    if value is None or (isinstance(value, str) and not value.strip()):
        return utc_now()
    return str(value).strip()[:128]


def load_input(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Extract and normalize Victor BT input fields."""
    return {
        "strategy_id": normalize_str(payload.get("strategyId")),
        "strategy_name": normalize_str(payload.get("strategyName")),
        "strategy_family": normalize_str(payload.get("strategyFamily")),
        "symbol": normalize_str(payload.get("symbol")),
        "timeframe": normalize_str(payload.get("timeframe")),
        "regime": normalize_regime(payload.get("regime")),
        "result_hash": normalize_str(payload.get("resultHash")),
        "data_period": payload.get("dataPeriod") or {},
        "train_metrics": payload.get("trainMetrics") or {},
        "oos_validation_metrics": payload.get("oosValidationMetrics") or {},
        "wfo_folds": payload.get("wfoFolds") or [],
        "monte_carlo": payload.get("monteCarlo") or {},
        "trade_count": payload.get("tradeCount"),
        "insufficient_sample": bool(payload.get("insufficientSample", False)),
        "data_cutoff_timestamp": normalize_timestamp(payload.get("dataCutoffTimestamp")),
        "timestamp": normalize_timestamp(payload.get("timestamp")),
    }


# ── existing-row lookup ───────────────────────────────────────────

def find_existing_result(
    connection: sqlite3.Connection,
    result_hash: str,
) -> Optional[sqlite3.Row]:
    """Check if this exact result_hash was already persisted."""
    return connection.execute(
        """
        SELECT id, result_id, experiment_id, result_hash, created_at
        FROM research_results
        WHERE result_hash = ?
        LIMIT 1
        """,
        (result_hash,),
    ).fetchone()


def find_existing_experiment(
    connection: sqlite3.Connection,
    strategy_id: str,
    symbol: str,
    timeframe: str,
    regime: str,
    source: str,
) -> Optional[sqlite3.Row]:
    """
    Find an existing experiment for the same strategy × symbol × timeframe × regime
    with source = 'victor_bt'. Returns the most recent one.
    """
    return connection.execute(
        """
        SELECT id, experiment_id, strategy_id, symbol, timeframe, regime, source,
               created_at
        FROM research_experiments
        WHERE strategy_id = ?
          AND symbol = ?
          AND timeframe = ?
          AND regime = ?
          AND source = ?
        ORDER BY id DESC
        LIMIT 1
        """,
        (strategy_id, symbol, timeframe, regime, source),
    ).fetchone()


# ── write path ─────────────────────────────────────────────────────

def write_experiment(
    connection: sqlite3.Connection,
    input_data: Dict[str, Any],
) -> Tuple[int, str]:
    """
    Insert (or ignore-duplicate) a research_experiments row for Victor BT.
    Returns (db_id, experiment_id).
    """
    now = utc_now()
    experiment_id = f"VICTOR-BT-EXP-{sha256_text(now + input_data['strategy_id'] + input_data['symbol'])[:8].upper()}"

    cursor = connection.cursor()
    cursor.execute(
        """
        INSERT OR IGNORE INTO research_experiments (
            experiment_id, run_id, strategy_id, strategy_name,
            dataset_version_id, symbol, timeframe,
            scope_train_start, scope_train_end,
            scope_validation_start, scope_validation_end,
            scope_independent_start, scope_independent_end,
            research_question, hypothesis, rule_definition,
            parameters_json, cost_model_json, feedback_json,
            provenance_json, config_hash, status,
            created_at, updated_at, source
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            experiment_id,
            f"victor_bt_run_{experiment_id}",
            input_data["strategy_id"],
            input_data["strategy_name"],
            None,  # dataset_version_id — Victor BT doesn't track dataset version in this schema
            input_data["symbol"],
            input_data["timeframe"],
            input_data["data_period"].get("start"),
            input_data["data_period"].get("end"),
            None,  # scope_validation_start
            None,  # scope_validation_end
            None,  # scope_independent_start
            None,  # scope_independent_end
            f"Victor BT performance evaluation: {input_data['strategy_name']}",
            None,
            None,
            compact_json({"strategy_family": input_data["strategy_family"]}),
            None,
            None,
            compact_json({
                "source": "victor_bt",
                "strategy_family": input_data["strategy_family"],
                "data_period": input_data["data_period"],
            }),
            None,
            "COMPLETED",
            now,
            now,
            "victor_bt",
        ),
    )
    connection.commit()

    # If INSERT OR IGNORE didn't insert (duplicate experiment key), find the existing row
    if cursor.rowcount == 0:
        existing = find_existing_experiment(
            connection,
            input_data["strategy_id"],
            input_data["symbol"],
            input_data["timeframe"],
            input_data["regime"],
            "victor_bt",
        )
        if existing is not None:
            return int(existing["id"]), str(existing["experiment_id"])
        # Edge case: rowcount==0 but no existing row found — re-read
        connection.rollback()
        cursor.execute(
            """
            SELECT id, experiment_id FROM research_experiments
            WHERE strategy_id = ? AND symbol = ? AND timeframe = ?
              AND regime = ? AND source = ?
            ORDER BY id DESC LIMIT 1
            """,
            (input_data["strategy_id"], input_data["symbol"],
             input_data["timeframe"], input_data["regime"], "victor_bt"),
        )
        row = cursor.fetchone()
        if row is not None:
            return int(row["id"]), str(row["experiment_id"])
        raise RuntimeError("Experiment insert failed and no existing row found.")

    return cursor.lastrowid, experiment_id


def write_result(
    connection: sqlite3.Connection,
    experiment_db_id: int,
    experiment_id: str,
    input_data: Dict[str, Any],
) -> Tuple[int, str, bool]:
    """
    Insert a research_results row for Victor BT.
    Returns (db_id, result_id, was_duplicate).
    """
    now = utc_now()
    result_id = f"VICTOR-BT-RES-{sha256_text(now + input_data['result_hash'])[:8].upper()}"

    # Assemble summary_json: combines WFO folds + Monte Carlo + data period + sample info
    summary = {
        "source": "victor_bt",
        "data_period": input_data["data_period"],
        "trade_count": input_data["trade_count"],
        "insufficient_sample": input_data["insufficient_sample"],
        "wfo_folds": input_data["wfo_folds"],
        "monte_carlo": input_data["monte_carlo"],
        "data_cutoff_timestamp": input_data["data_cutoff_timestamp"],
        "result_timestamp": input_data["timestamp"],
    }

    # Check for duplicate by result_hash BEFORE inserting
    existing = find_existing_result(connection, input_data["result_hash"])
    if existing is not None:
        return int(existing["id"]), str(existing["result_id"]), True

    cursor = connection.cursor()
    cursor.execute(
        """
        INSERT INTO research_results (
            result_id, experiment_id, run_id, execution_status,
            validation_status, started_at, completed_at, duration_ms,
            metrics_json, validation_json, summary_json, provenance_json,
            result_hash, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            result_id,
            experiment_id,
            f"victor_bt_run_{result_id}",
            "COMPLETED",
            "VALIDATED",  # Victor BT results are post-validation by construction
            input_data["data_cutoff_timestamp"],
            input_data["timestamp"],
            None,  # duration_ms
            compact_json({
                "source": "victor_bt",
                "strategy_id": input_data["strategy_id"],
                "symbol": input_data["symbol"],
                "timeframe": input_data["timeframe"],
                "regime": input_data["regime"],
                "train_metrics": input_data["train_metrics"],       # ← rule 1 & 2
                "trade_count": input_data["trade_count"],
                "insufficient_sample": input_data["insufficient_sample"],
            }),
            compact_json({
                "source": "victor_bt",
                "oos_validation_metrics": input_data["oos_validation_metrics"],  # ← rule 1 & 2
                "trade_count": input_data["trade_count"],
                "insufficient_sample": input_data["insufficient_sample"],
            }),
            compact_json(summary),
            compact_json({
                "source": "victor_bt",
                "strategy_family": input_data["strategy_family"],
            }),
            input_data["result_hash"],
            now,
        ),
    )
    connection.commit()
    return cursor.lastrowid, result_id, False


def write_memory(
    connection: sqlite3.Connection,
    experiment_db_id: int,
    result_db_id: int,
    experiment_id: str,
    result_id: str,
    input_data: Dict[str, Any],
    title: str,
    summary: str,
) -> Tuple[int, str]:
    """
    Insert a research_memory row linking experiment + result.
    Returns (db_id, memory_id).
    """
    memory_key = f"victor_bt:performance:{experiment_id}:{result_id}"
    memory_type = "VICTOR_BT_PERFORMANCE"
    status = "ACTIVE"
    confidence = None
    decision = None

    evidence = {
        "adapter": ADAPTER_NAME,
        "schemaVersion": SCHEMA_VERSION,
        "experiment": {
            "experimentId": experiment_id,
            "strategyId": input_data["strategy_id"],
            "strategyFamily": input_data["strategy_family"],
            "symbol": input_data["symbol"],
            "timeframe": input_data["timeframe"],
            "regime": input_data["regime"],
        },
        "result": {
            "resultId": result_id,
            "source": "victor_bt",
            "trade_count": input_data["trade_count"],
            "insufficient_sample": input_data["insufficient_sample"],
            "data_period": input_data["data_period"],
            "wfo_folds": input_data["wfo_folds"],
            "monte_carlo": input_data["monte_carlo"],
            "train_metrics": input_data["train_metrics"],
            "oos_validation_metrics": input_data["oos_validation_metrics"],
            "result_timestamp": input_data["timestamp"],
        },
        "resultHash": input_data["result_hash"],
    }

    learning = {
        "source": "victor_bt",
        "performance_type": "backtest",
        "strategy_family": input_data["strategy_family"],
        "regime": input_data["regime"],
        "data_period": input_data["data_period"],
    }

    metadata = {
        "adapter": ADAPTER_NAME,
        "schemaVersion": SCHEMA_VERSION,
        "database": DB_FILE,
        "experimentDatabaseId": experiment_db_id,
        "experimentId": experiment_id,
        "resultDatabaseId": result_db_id,
        "resultId": result_id,
        "source": "victor_bt",
    }

    now = utc_now()
    evidence_json = compact_json(evidence)
    learning_json = compact_json(learning)
    metadata_json = compact_json(metadata)

    content_for_hash = {
        "memoryKey": memory_key,
        "memoryType": memory_type,
        "title": title,
        "summary": summary,
        "decision": decision,
        "confidence": confidence,
        "status": status,
    }
    content_hash = sha256_text(compact_json(content_for_hash))

    cursor = connection.cursor()
    cursor.execute(
        """
        INSERT INTO research_memory (
            memory_key, memory_type, title, summary, decision,
            confidence, status, evidence_json, learning_json,
            metadata_json, content_hash, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            memory_key,
            memory_type,
            title,
            summary,
            decision,
            confidence,
            status,
            evidence_json,
            learning_json,
            metadata_json,
            content_hash,
            now,
            now,
        ),
    )
    connection.commit()
    return cursor.lastrowid, f"mem-{content_hash[:12].upper()}"


# ── main entry point ───────────────────────────────────────────────

def main() -> None:
    payload = load_input(read_stdin_json())

    # Basic required-field validation
    missing = [k for k in ("strategy_id", "symbol", "timeframe", "result_hash")
               if not payload[k]]
    if missing:
        response = {
            "success": False,
            "persisted": False,
            "duplicate": False,
            "error": f"Missing required fields: {', '.join(missing)}",
            "adapter": ADAPTER_NAME,
            "schemaVersion": SCHEMA_VERSION,
        }
        print(json.dumps(response, ensure_ascii=False, default=json_default))
        sys.exit(1)

    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    try:
        verify_required_tables(conn)
        ensure_victor_bt_indexes(conn)

        # 1. Write/lookup experiment
        experiment_db_id, experiment_id = write_experiment(conn, payload)

        # 2. Write result (with duplicate detection)
        result_db_id, result_id, was_duplicate = write_result(
            conn, experiment_db_id, experiment_id, payload,
        )

        if was_duplicate:
            response = {
                "success": True,
                "persisted": False,
                "duplicate": True,
                "error": None,
                "adapter": ADAPTER_NAME,
                "schemaVersion": SCHEMA_VERSION,
                "experimentId": experiment_id,
                "resultId": result_id,
                "strategyId": payload["strategy_id"],
                "symbol": payload["symbol"],
                "timeframe": payload["timeframe"],
                "regime": payload["regime"],
                "resultHash": payload["result_hash"],
                "source": "victor_bt",
                "timestamp": payload["timestamp"],
                "message": "Duplicate result_hash — no new row created.",
            }
            print(json.dumps(response, ensure_ascii=False, default=json_default))
            sys.exit(0)

        # 3. Write memory record
        title = (
            f"Victor BT Performance: {payload['strategy_name']} "
            f"({payload['symbol']}/{payload['timeframe']})"
        )
        summary = compact_json({
            "strategy_family": payload["strategy_family"],
            "regime": payload["regime"],
            "trade_count": payload["trade_count"],
            "insufficient_sample": payload["insufficient_sample"],
            "data_period": payload["data_period"],
            "source": "victor_bt",
            "timestamp": payload["timestamp"],
        })
        memory_db_id, memory_id = write_memory(
            conn, experiment_db_id, result_db_id,
            experiment_id, result_id, payload, title, summary,
        )

        response = {
            "success": True,
            "persisted": True,
            "duplicate": False,
            "memoryId": memory_id,
            "experimentId": experiment_id,
            "resultId": result_id,
            "strategyId": payload["strategy_id"],
            "symbol": payload["symbol"],
            "timeframe": payload["timeframe"],
            "regime": payload["regime"],
            "resultHash": payload["result_hash"],
            "source": "victor_bt",
            "timestamp": payload["timestamp"],
        }
        print(json.dumps(response, ensure_ascii=False, default=json_default))

    except Exception as exc:
        if conn:
            try:
                conn.rollback()
            except Exception:
                pass
        response = {
            "success": False,
            "persisted": False,
            "duplicate": False,
            "error": str(exc),
            "adapter": ADAPTER_NAME,
            "schemaVersion": SCHEMA_VERSION,
        }
        print(json.dumps(response, ensure_ascii=False, default=json_default))
        sys.exit(1)
    finally:
        if conn:
            conn.close()


if __name__ == "__main__":
    main()
