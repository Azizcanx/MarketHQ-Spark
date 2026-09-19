from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent


def find_project_root() -> Path:
    candidates = [
        SCRIPT_DIR,
        SCRIPT_DIR.parent,
        Path.cwd(),
        Path.cwd().parent,
    ]

    seen: set[Path] = set()
    for candidate in candidates:
        candidate = candidate.resolve()
        if candidate in seen:
            continue
        seen.add(candidate)
        if (candidate / "market_hq.db").exists():
            return candidate

    if SCRIPT_DIR.name.lower() == "agents":
        return SCRIPT_DIR.parent

    return SCRIPT_DIR


BASE_DIR = find_project_root()
DB_PATH = BASE_DIR / "market_hq.db"
SCHEMA_VERSION = "research_storage_v1"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    name TEXT PRIMARY KEY,
    applied_at TEXT NOT NULL
);

-- ============================================================
-- MARKET DATASET
-- Logical dataset identity. OHLCV rows are NOT copied into
-- experiments. Experiments reference a dataset version instead.
-- ============================================================
CREATE TABLE IF NOT EXISTS market_datasets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    dataset_key TEXT NOT NULL UNIQUE,
    symbol TEXT NOT NULL,
    market TEXT,
    timeframe TEXT NOT NULL,
    provider TEXT NOT NULL,
    source_uri TEXT,

    status TEXT NOT NULL DEFAULT 'active',

    first_available_at TEXT,
    last_available_at TEXT,
    row_count INTEGER NOT NULL DEFAULT 0,

    current_version_id INTEGER,
    metadata_json TEXT NOT NULL DEFAULT '{}',

    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_market_datasets_symbol
    ON market_datasets(symbol);

CREATE INDEX IF NOT EXISTS idx_market_datasets_timeframe
    ON market_datasets(timeframe);

CREATE INDEX IF NOT EXISTS idx_market_datasets_provider
    ON market_datasets(provider);

-- ============================================================
-- DATASET VERSION
-- Immutable snapshot/version of a dataset.
-- ============================================================
CREATE TABLE IF NOT EXISTS market_dataset_versions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    dataset_id INTEGER NOT NULL,
    version_key TEXT NOT NULL UNIQUE,

    content_hash TEXT NOT NULL,
    schema_version TEXT NOT NULL,

    first_available_at TEXT,
    last_available_at TEXT,
    row_count INTEGER NOT NULL DEFAULT 0,

    provider TEXT NOT NULL,
    retrieval_params_json TEXT NOT NULL DEFAULT '{}',
    artifact_path TEXT,
    metadata_json TEXT NOT NULL DEFAULT '{}',

    created_at TEXT NOT NULL,

    FOREIGN KEY (dataset_id)
        REFERENCES market_datasets(id)
        ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_dataset_versions_dataset
    ON market_dataset_versions(dataset_id);

CREATE INDEX IF NOT EXISTS idx_dataset_versions_hash
    ON market_dataset_versions(content_hash);

CREATE INDEX IF NOT EXISTS idx_dataset_versions_dates
    ON market_dataset_versions(first_available_at, last_available_at);

-- ============================================================
-- RESEARCH EXPERIMENT
-- One immutable-ish research configuration and its dataset
-- reference. The actual market rows live in the dataset layer.
-- ============================================================
CREATE TABLE IF NOT EXISTS research_experiments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    experiment_id TEXT NOT NULL UNIQUE,
    run_id TEXT,

    strategy_id TEXT NOT NULL,
    strategy_name TEXT,

    dataset_version_id INTEGER NOT NULL,
    symbol TEXT NOT NULL,
    timeframe TEXT NOT NULL,

    scope_train_start TEXT,
    scope_train_end TEXT,
    scope_validation_start TEXT,
    scope_validation_end TEXT,
    scope_independent_start TEXT NOT NULL,
    scope_independent_end TEXT NOT NULL,

    research_question TEXT,
    hypothesis TEXT,
    rule_definition TEXT,

    parameters_json TEXT NOT NULL DEFAULT '{}',
    cost_model_json TEXT NOT NULL DEFAULT '{}',
    feedback_json TEXT NOT NULL DEFAULT '{}',
    provenance_json TEXT NOT NULL DEFAULT '{}',

    config_hash TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'CREATED',

    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,

    FOREIGN KEY (dataset_version_id)
        REFERENCES market_dataset_versions(id)
        ON DELETE RESTRICT
);

CREATE INDEX IF NOT EXISTS idx_research_experiments_strategy
    ON research_experiments(strategy_id);

CREATE INDEX IF NOT EXISTS idx_research_experiments_symbol
    ON research_experiments(symbol);

CREATE INDEX IF NOT EXISTS idx_research_experiments_dataset
    ON research_experiments(dataset_version_id);

CREATE INDEX IF NOT EXISTS idx_research_experiments_run
    ON research_experiments(run_id);

CREATE INDEX IF NOT EXISTS idx_research_experiments_status
    ON research_experiments(status);

-- ============================================================
-- RESEARCH RESULT
-- Aggregate result of one experiment execution. Large arrays
-- such as trades/equity curves belong in artifacts, not here.
-- ============================================================
CREATE TABLE IF NOT EXISTS research_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    result_id TEXT NOT NULL UNIQUE,
    experiment_id INTEGER NOT NULL,
    run_id TEXT,

    execution_status TEXT NOT NULL,
    validation_status TEXT,

    started_at TEXT,
    completed_at TEXT,
    duration_ms INTEGER,

    metrics_json TEXT NOT NULL DEFAULT '{}',
    validation_json TEXT NOT NULL DEFAULT '{}',
    summary_json TEXT NOT NULL DEFAULT '{}',
    provenance_json TEXT NOT NULL DEFAULT '{}',

    result_hash TEXT NOT NULL,

    created_at TEXT NOT NULL,

    FOREIGN KEY (experiment_id)
        REFERENCES research_experiments(id)
        ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_research_results_experiment
    ON research_results(experiment_id);

CREATE INDEX IF NOT EXISTS idx_research_results_run
    ON research_results(run_id);

CREATE INDEX IF NOT EXISTS idx_research_results_status
    ON research_results(execution_status);

CREATE INDEX IF NOT EXISTS idx_research_results_hash
    ON research_results(result_hash);

-- ============================================================
-- RESEARCH ARTIFACT
-- References large payloads without embedding them in API/DB
-- result rows.
-- ============================================================
CREATE TABLE IF NOT EXISTS research_artifacts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    artifact_id TEXT NOT NULL UNIQUE,
    result_id INTEGER NOT NULL,

    artifact_type TEXT NOT NULL,
    artifact_path TEXT NOT NULL,
    content_hash TEXT,
    byte_size INTEGER,
    row_count INTEGER,

    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,

    FOREIGN KEY (result_id)
        REFERENCES research_results(id)
        ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_research_artifacts_result
    ON research_artifacts(result_id);

CREATE INDEX IF NOT EXISTS idx_research_artifacts_type
    ON research_artifacts(artifact_type);

CREATE INDEX IF NOT EXISTS idx_research_artifacts_hash
    ON research_artifacts(content_hash);

-- ============================================================
-- RESEARCH MEMORY
-- Durable compact memory produced after result ingestion / learning.
-- This deliberately references experiment/result instead of copying
-- the full execution payload.
-- ============================================================
CREATE TABLE IF NOT EXISTS research_memory (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    memory_key TEXT NOT NULL UNIQUE,
    experiment_id INTEGER,
    result_id INTEGER,

    memory_type TEXT NOT NULL,
    title TEXT NOT NULL,
    summary TEXT NOT NULL,

    decision TEXT,
    confidence REAL,
    status TEXT NOT NULL DEFAULT 'ACTIVE',

    evidence_json TEXT NOT NULL DEFAULT '{}',
    learning_json TEXT NOT NULL DEFAULT '{}',
    metadata_json TEXT NOT NULL DEFAULT '{}',

    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,

    FOREIGN KEY (experiment_id)
        REFERENCES research_experiments(id)
        ON DELETE SET NULL,

    FOREIGN KEY (result_id)
        REFERENCES research_results(id)
        ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_research_memory_type
    ON research_memory(memory_type);

CREATE INDEX IF NOT EXISTS idx_research_memory_experiment
    ON research_memory(experiment_id);

CREATE INDEX IF NOT EXISTS idx_research_memory_result
    ON research_memory(result_id);

CREATE INDEX IF NOT EXISTS idx_research_memory_status
    ON research_memory(status);

-- ============================================================
-- DATASET <-> EXPERIMENT audit link
-- Useful for lineage queries without duplicating OHLCV.
-- ============================================================
CREATE TABLE IF NOT EXISTS research_dataset_usage (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    dataset_version_id INTEGER NOT NULL,
    experiment_id INTEGER NOT NULL,
    usage_role TEXT NOT NULL DEFAULT 'research_input',
    created_at TEXT NOT NULL,

    UNIQUE(dataset_version_id, experiment_id, usage_role),

    FOREIGN KEY (dataset_version_id)
        REFERENCES market_dataset_versions(id)
        ON DELETE CASCADE,

    FOREIGN KEY (experiment_id)
        REFERENCES research_experiments(id)
        ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_research_dataset_usage_dataset
    ON research_dataset_usage(dataset_version_id);

CREATE INDEX IF NOT EXISTS idx_research_dataset_usage_experiment
    ON research_dataset_usage(experiment_id);
"""


def table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
    row = conn.execute(
        """
        SELECT 1
        FROM sqlite_master
        WHERE type = 'table' AND name = ?
        LIMIT 1
        """,
        (table_name,),
    ).fetchone()
    return row is not None


def table_count(conn: sqlite3.Connection, table_name: str) -> int:
    if not table_exists(conn, table_name):
        return 0
    row = conn.execute(
        f'SELECT COUNT(*) AS n FROM "{table_name}"'
    ).fetchone()
    return int(row["n"] or 0)


def migration_applied(conn: sqlite3.Connection) -> bool:
    if not table_exists(conn, "schema_migrations"):
        return False
    row = conn.execute(
        "SELECT 1 FROM schema_migrations WHERE name = ? LIMIT 1",
        (SCHEMA_VERSION,),
    ).fetchone()
    return row is not None


def apply_schema(conn: sqlite3.Connection) -> bool:
    already = migration_applied(conn)
    conn.executescript(SCHEMA_SQL)

    if not already:
        conn.execute(
            """
            INSERT INTO schema_migrations(name, applied_at)
            VALUES (?, ?)
            """,
            (SCHEMA_VERSION, utc_now()),
        )

    conn.commit()
    return not already


def inspect(conn: sqlite3.Connection) -> dict[str, int]:
    tables = [
        "market_datasets",
        "market_dataset_versions",
        "research_experiments",
        "research_results",
        "research_artifacts",
        "research_memory",
        "research_dataset_usage",
    ]
    return {table: table_count(conn, table) for table in tables}


def canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )


def sha256_json(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def print_report(counts: dict[str, int], applied: bool) -> None:
    print()
    print("=" * 76)
    print("MARKETHQ RESEARCH STORAGE V1")
    print("=" * 76)
    print()
    print(f"Database : {DB_PATH}")
    print(f"Schema   : {SCHEMA_VERSION}")
    print(f"Action   : {'APPLIED' if applied else 'ALREADY_PRESENT'}")
    print()

    for table, count in counts.items():
        print(f"{table:30} {count:>6}")

    print()
    print("Architecture:")
    print("  MARKET DATA -> DATASET -> DATASET VERSION")
    print("  EXPERIMENT  -> DATASET VERSION REFERENCE")
    print("  RESULT      -> EXPERIMENT REFERENCE")
    print("  ARTIFACT    -> LARGE RESULT PAYLOAD REFERENCE")
    print("  MEMORY      -> COMPACT RESEARCH LEARNING")
    print()
    print("OHLCV rows are intentionally not copied into experiments.")
    print("This migration does not enable pipeline database writes.")
    print("It only prepares the durable research storage schema.")
    print()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create or inspect MarketHQ Research Storage V1 schema."
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Schema değiştirme; sadece Research Storage tablolarını kontrol et.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    if not DB_PATH.exists():
        raise SystemExit(f"market_hq.db bulunamadı: {DB_PATH}")

    conn = connect()
    try:
        if args.check:
            print_report(inspect(conn), applied=False)
            return

        applied = apply_schema(conn)
        print_report(inspect(conn), applied=applied)
    finally:
        conn.close()


if __name__ == "__main__":
    main()

