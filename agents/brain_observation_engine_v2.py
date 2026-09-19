
from __future__ import annotations

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

ENGINE_NAME = "MARKETHQ_BRAIN_OBSERVATION_ENGINE"
ENGINE_VERSION = "V2"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(
        DB_PATH,
        timeout=30.0,
    )
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout = 30000")
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def table_exists(
    conn: sqlite3.Connection,
    table_name: str,
) -> bool:
    row = conn.execute(
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


def table_columns(
    conn: sqlite3.Connection,
    table_name: str,
) -> set[str]:
    if not table_exists(conn, table_name):
        return set()

    return {
        str(row["name"])
        for row in conn.execute(
            f'PRAGMA table_info("{table_name}")'
        ).fetchall()
    }


def json_dumps(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
    )


def stable_hash(value: str) -> str:
    return hashlib.sha256(
        value.encode("utf-8")
    ).hexdigest()


def ensure_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS brain_observations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,

            observation_key TEXT NOT NULL UNIQUE,

            method_name TEXT NOT NULL,
            symbol TEXT,
            market TEXT,
            timeframe TEXT,

            market_regime TEXT,
            volume_state TEXT,
            volatility_state TEXT,

            sample_size INTEGER NOT NULL,

            positive_count INTEGER NOT NULL DEFAULT 0,
            negative_count INTEGER NOT NULL DEFAULT 0,
            neutral_count INTEGER NOT NULL DEFAULT 0,

            positive_rate REAL,
            average_return_1d REAL,
            average_return_5d REAL,
            average_return_20d REAL,

            median_return_20d REAL,
            best_return_20d REAL,
            worst_return_20d REAL,

            avg_max_favorable_move REAL,
            avg_max_adverse_move REAL,

            confidence REAL,
            status TEXT NOT NULL DEFAULT 'candidate',

            first_observation_date TEXT,
            last_observation_date TEXT,

            source_experiments_json TEXT NOT NULL DEFAULT '[]',

            observation_text TEXT,
            metadata_json TEXT NOT NULL DEFAULT '{}',

            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_brain_observations_method
            ON brain_observations(method_name);

        CREATE INDEX IF NOT EXISTS idx_brain_observations_symbol
            ON brain_observations(symbol);

        CREATE INDEX IF NOT EXISTS idx_brain_observations_market
            ON brain_observations(market);

        CREATE INDEX IF NOT EXISTS idx_brain_observations_regime
            ON brain_observations(market_regime);

        CREATE INDEX IF NOT EXISTS idx_brain_observations_volatility
            ON brain_observations(volatility_state);

        CREATE INDEX IF NOT EXISTS idx_brain_observations_sample
            ON brain_observations(sample_size DESC);

        CREATE TABLE IF NOT EXISTS brain_observation_sources (
            observation_id INTEGER NOT NULL,
            experiment_id INTEGER NOT NULL,

            created_at TEXT NOT NULL,

            PRIMARY KEY (
                observation_id,
                experiment_id
            ),

            FOREIGN KEY (observation_id)
                REFERENCES brain_observations(id)
                ON DELETE CASCADE,

            FOREIGN KEY (experiment_id)
                REFERENCES learning_experiments(id)
                ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_brain_obs_sources_experiment
            ON brain_observation_sources(experiment_id);

        CREATE TABLE IF NOT EXISTS brain_observation_evidence (
            observation_id INTEGER NOT NULL,
            evidence_id INTEGER NOT NULL,

            role TEXT NOT NULL DEFAULT 'supports',
            weight REAL,

            created_at TEXT NOT NULL,

            PRIMARY KEY (
                observation_id,
                evidence_id
            ),

            FOREIGN KEY (observation_id)
                REFERENCES brain_observations(id)
                ON DELETE CASCADE,

            FOREIGN KEY (evidence_id)
                REFERENCES brain_evidence(id)
                ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_brain_obs_evidence_evidence
            ON brain_observation_evidence(evidence_id);
        """
    )

    conn.commit()


def normalized_key(
    method_name: str,
    symbol: str | None,
    market: str | None,
    timeframe: str | None,
    market_regime: str | None,
    volume_state: str | None,
    volatility_state: str | None,
) -> str:
    values = [
        str(method_name or "").strip().lower(),
        str(symbol or "").strip().lower(),
        str(market or "").strip().lower(),
        str(timeframe or "").strip().lower(),
        str(market_regime or "").strip().lower(),
        str(volume_state or "").strip().lower(),
        str(volatility_state or "").strip().lower(),
    ]

    return "|".join(values)


def observation_key(
    method_name: str,
    symbol: str | None,
    market: str | None,
    timeframe: str | None,
    market_regime: str | None,
    volume_state: str | None,
    volatility_state: str | None,
) -> str:
    return stable_hash(
        normalized_key(
            method_name,
            symbol,
            market,
            timeframe,
            market_regime,
            volume_state,
            volatility_state,
        )
    )


def median_or_none(values: list[float]) -> float | None:
    if not values:
        return None

    ordered = sorted(values)
    n = len(ordered)
    middle = n // 2

    if n % 2:
        return ordered[middle]

    return (
        ordered[middle - 1] +
        ordered[middle]
    ) / 2.0


def safe_float(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None

        return float(value)
    except (TypeError, ValueError):
        return None


def safe_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def build_confidence(
    sample_size: int,
    positive_rate: float | None,
    average_return_20d: float | None,
) -> float:
    """
    Candidate confidence only.
    This is deliberately conservative: it is not a claim of predictive validity.

    Factors:
    - sample support
    - stability around 50% -> less evidence than a clearly directional result
    - modest return signal

    The score is capped below 1.0 so "observation candidate" is never silently
    promoted to verified knowledge.
    """
    if sample_size <= 0:
        return 0.0

    sample_factor = min(
        1.0,
        sample_size / 250.0,
    )

    if positive_rate is None:
        directional_factor = 0.0
    else:
        directional_factor = min(
            1.0,
            abs(positive_rate - 0.5) * 2.0,
        )

    if average_return_20d is None:
        return_factor = 0.0
    else:
        # Saturating transformation around ±20%.
        return_factor = min(
            1.0,
            abs(average_return_20d) / 20.0,
        )

    score = (
        0.55 * sample_factor
        + 0.30 * directional_factor
        + 0.15 * return_factor
    )

    return round(
        min(0.95, max(0.0, score)),
        4,
    )


def classify_status(
    sample_size: int,
    confidence: float,
) -> str:
    if sample_size < 5:
        return "insufficient"

    if sample_size < 20:
        return "weak_candidate"

    if sample_size < 50:
        return "candidate"

    if confidence >= 0.70:
        return "strong_candidate"

    return "candidate"


def build_observation_text(
    *,
    method_name: str,
    symbol: str | None,
    market: str | None,
    timeframe: str | None,
    market_regime: str | None,
    volume_state: str | None,
    volatility_state: str | None,
    sample_size: int,
    positive_rate: float | None,
    average_return_20d: float | None,
) -> str:
    context = " | ".join(
        x
        for x in [
            method_name,
            symbol,
            market,
            timeframe,
            market_regime,
            volume_state,
            volatility_state,
        ]
        if x
    )

    stats: list[str] = [
        f"sample={sample_size}",
    ]

    if positive_rate is not None:
        stats.append(
            f"positive_rate={positive_rate:.4f}"
        )

    if average_return_20d is not None:
        stats.append(
            f"average_return_20d={average_return_20d:.4f}"
        )

    return (
        f"Observation candidate: {context}. "
        + ", ".join(stats)
        + "."
    )


def upsert_observation(
    conn: sqlite3.Connection,
    row: sqlite3.Row,
) -> int:
    method_name = str(
        row["method_name"] or "UNKNOWN"
    ).strip()

    symbol = (
        str(row["symbol"]).strip()
        if row["symbol"] is not None
        else None
    )

    market = (
        str(row["market"]).strip()
        if row["market"] is not None
        else None
    )

    timeframe = (
        str(row["timeframe"]).strip()
        if row["timeframe"] is not None
        else None
    )

    market_regime = (
        str(row["market_regime"]).strip()
        if row["market_regime"] is not None
        else None
    )

    volume_state = (
        str(row["volume_state"]).strip()
        if row["volume_state"] is not None
        else None
    )

    volatility_state = (
        str(row["volatility_state"]).strip()
        if row["volatility_state"] is not None
        else None
    )

    sample_size = safe_int(row["sample_size"])
    positive_count = safe_int(row["positive_count"])
    negative_count = safe_int(row["negative_count"])
    neutral_count = safe_int(row["neutral_count"])

    positive_rate = safe_float(
        row["positive_rate"]
    )

    average_return_1d = safe_float(
        row["average_return_1d"]
    )

    average_return_5d = safe_float(
        row["average_return_5d"]
    )

    average_return_20d = safe_float(
        row["average_return_20d"]
    )

    median_return_20d = safe_float(
        row["median_return_20d"]
    )

    best_return_20d = safe_float(
        row["best_return_20d"]
    )

    worst_return_20d = safe_float(
        row["worst_return_20d"]
    )

    avg_max_favorable_move = safe_float(
        row["avg_max_favorable_move"]
    )

    avg_max_adverse_move = safe_float(
        row["avg_max_adverse_move"]
    )

    confidence = build_confidence(
        sample_size,
        positive_rate,
        average_return_20d,
    )

    status = classify_status(
        sample_size,
        confidence,
    )

    source_experiments = [
        int(x)
        for x in json.loads(
            row["source_experiments_json"] or "[]"
        )
    ]

    obs_key = observation_key(
        method_name,
        symbol,
        market,
        timeframe,
        market_regime,
        volume_state,
        volatility_state,
    )

    text = build_observation_text(
        method_name=method_name,
        symbol=symbol,
        market=market,
        timeframe=timeframe,
        market_regime=market_regime,
        volume_state=volume_state,
        volatility_state=volatility_state,
        sample_size=sample_size,
        positive_rate=positive_rate,
        average_return_20d=average_return_20d,
    )

    metadata = {
        "engine": ENGINE_NAME,
        "engine_version": ENGINE_VERSION,
        "source_experiment_count": len(
            source_experiments
        ),
        "grouping": [
            "method_name",
            "symbol",
            "market",
            "timeframe",
            "market_regime",
            "volume_state",
            "volatility_state",
        ],
        "raw_results_are_preserved": True,
    }

    existing = conn.execute(
        """
        SELECT id
        FROM brain_observations
        WHERE observation_key = ?
        LIMIT 1
        """,
        (obs_key,),
    ).fetchone()

    now = utc_now()

    if existing:
        observation_id = int(existing["id"])

        conn.execute(
            """
            UPDATE brain_observations
            SET sample_size = ?,
                positive_count = ?,
                negative_count = ?,
                neutral_count = ?,
                positive_rate = ?,
                average_return_1d = ?,
                average_return_5d = ?,
                average_return_20d = ?,
                median_return_20d = ?,
                best_return_20d = ?,
                worst_return_20d = ?,
                avg_max_favorable_move = ?,
                avg_max_adverse_move = ?,
                confidence = ?,
                status = ?,
                first_observation_date = ?,
                last_observation_date = ?,
                source_experiments_json = ?,
                observation_text = ?,
                metadata_json = ?,
                updated_at = ?
            WHERE id = ?
            """,
            (
                sample_size,
                positive_count,
                negative_count,
                neutral_count,
                positive_rate,
                average_return_1d,
                average_return_5d,
                average_return_20d,
                median_return_20d,
                best_return_20d,
                worst_return_20d,
                avg_max_favorable_move,
                avg_max_adverse_move,
                confidence,
                status,
                row["first_observation_date"],
                row["last_observation_date"],
                json_dumps(source_experiments),
                text,
                json_dumps(metadata),
                now,
                observation_id,
            ),
        )

        return observation_id

    cursor = conn.execute(
        """
        INSERT INTO brain_observations (
            observation_key,
            method_name,
            symbol,
            market,
            timeframe,
            market_regime,
            volume_state,
            volatility_state,
            sample_size,
            positive_count,
            negative_count,
            neutral_count,
            positive_rate,
            average_return_1d,
            average_return_5d,
            average_return_20d,
            median_return_20d,
            best_return_20d,
            worst_return_20d,
            avg_max_favorable_move,
            avg_max_adverse_move,
            confidence,
            status,
            first_observation_date,
            last_observation_date,
            source_experiments_json,
            observation_text,
            metadata_json,
            created_at,
            updated_at
        )
        VALUES (
            ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
        )
        """,
        (
            obs_key,
            method_name,
            symbol,
            market,
            timeframe,
            market_regime,
            volume_state,
            volatility_state,
            sample_size,
            positive_count,
            negative_count,
            neutral_count,
            positive_rate,
            average_return_1d,
            average_return_5d,
            average_return_20d,
            median_return_20d,
            best_return_20d,
            worst_return_20d,
            avg_max_favorable_move,
            avg_max_adverse_move,
            confidence,
            status,
            row["first_observation_date"],
            row["last_observation_date"],
            json_dumps(source_experiments),
            text,
            json_dumps(metadata),
            now,
            now,
        ),
    )

    return int(cursor.lastrowid)


def load_grouped_rows(
    conn: sqlite3.Connection,
) -> list[sqlite3.Row]:
    required = [
        "learning_experiments",
        "experiment_results",
    ]

    missing = [
        table
        for table in required
        if not table_exists(conn, table)
    ]

    if missing:
        raise RuntimeError(
            "Eksik kaynak tabloları: "
            + ", ".join(missing)
        )

    # We deliberately group only on fields already present in the
    # existing experiment/result schema. No raw data is changed.
    rows = conn.execute(
        """
        SELECT
            le.method_name AS method_name,
            le.symbol AS symbol,
            le.market AS market,
            le.timeframe AS timeframe,

            er.market_regime AS market_regime,
            er.volume_state AS volume_state,
            er.volatility_state AS volatility_state,

            COUNT(*) AS sample_size,

            SUM(
                CASE
                    WHEN er.return_20d > 0 THEN 1
                    ELSE 0
                END
            ) AS positive_count,

            SUM(
                CASE
                    WHEN er.return_20d < 0 THEN 1
                    ELSE 0
                END
            ) AS negative_count,

            SUM(
                CASE
                    WHEN er.return_20d = 0 THEN 1
                    ELSE 0
                END
            ) AS neutral_count,

            AVG(
                CASE
                    WHEN er.return_20d IS NOT NULL
                    THEN er.return_20d
                END
            ) AS average_return_20d,

            AVG(
                CASE
                    WHEN er.return_1d IS NOT NULL
                    THEN er.return_1d
                END
            ) AS average_return_1d,

            AVG(
                CASE
                    WHEN er.return_5d IS NOT NULL
                    THEN er.return_5d
                END
            ) AS average_return_5d,

            AVG(
                CASE
                    WHEN er.max_favorable_move IS NOT NULL
                    THEN er.max_favorable_move
                END
            ) AS avg_max_favorable_move,

            AVG(
                CASE
                    WHEN er.max_adverse_move IS NOT NULL
                    THEN er.max_adverse_move
                END
            ) AS avg_max_adverse_move,

            MIN(
                CASE
                    WHEN er.observation_date IS NOT NULL
                    THEN er.observation_date
                END
            ) AS first_observation_date,

            MAX(
                CASE
                    WHEN er.observation_date IS NOT NULL
                    THEN er.observation_date
                END
            ) AS last_observation_date,

            GROUP_CONCAT(
                DISTINCT CAST(le.id AS TEXT)
            ) AS source_experiments_csv

        FROM experiment_results er
        JOIN learning_experiments le
            ON le.id = er.experiment_id

        GROUP BY
            le.method_name,
            le.symbol,
            le.market,
            le.timeframe,
            er.market_regime,
            er.volume_state,
            er.volatility_state

        HAVING COUNT(*) >= 5

        ORDER BY COUNT(*) DESC
        """
    ).fetchall()

    output: list[sqlite3.Row] = []

    # SQLite can calculate the basic aggregates above, but median/best/worst
    # need a second pass per group. We keep that pass deterministic.
    for row in rows:
        experiments_csv = str(
            row["source_experiments_csv"] or ""
        )

        experiment_ids = [
            int(x)
            for x in experiments_csv.split(",")
            if x.strip().isdigit()
        ]

        params: list[Any] = [
            row["method_name"],
            row["symbol"],
            row["market"],
            row["timeframe"],
            row["market_regime"],
            row["volume_state"],
            row["volatility_state"],
        ]

        # Build a null-safe WHERE matching SQLite grouping semantics.
        clauses = [
            "le.method_name IS ?",
            "le.symbol IS ?",
            "le.market IS ?",
            "le.timeframe IS ?",
            "er.market_regime IS ?",
            "er.volume_state IS ?",
            "er.volatility_state IS ?",
        ]

        result_rows = conn.execute(
            """
            SELECT
                er.return_20d
            FROM experiment_results er
            JOIN learning_experiments le
                ON le.id = er.experiment_id
            WHERE
                le.method_name IS ?
                AND le.symbol IS ?
                AND le.market IS ?
                AND le.timeframe IS ?
                AND er.market_regime IS ?
                AND er.volume_state IS ?
                AND er.volatility_state IS ?
                AND er.return_20d IS NOT NULL
            """,
            params,
        ).fetchall()

        returns = [
            float(r["return_20d"])
            for r in result_rows
            if r["return_20d"] is not None
        ]

        sample_size = safe_int(row["sample_size"])
        positive_count = safe_int(row["positive_count"])
        negative_count = safe_int(row["negative_count"])
        neutral_count = safe_int(row["neutral_count"])

        positive_rate = (
            positive_count / sample_size
            if sample_size
            else None
        )

        row_data = dict(row)
        row_data["source_experiments_json"] = json_dumps(
            sorted(set(experiment_ids))
        )
        row_data["median_return_20d"] = (
            median_or_none(returns)
        )
        row_data["best_return_20d"] = (
            max(returns)
            if returns
            else None
        )
        row_data["worst_return_20d"] = (
            min(returns)
            if returns
            else None
        )
        row_data["positive_rate"] = positive_rate

        # Prepared values are used in the final dict pass below.
        _ = row_data

    final_rows: list[dict[str, Any]] = []

    for row in rows:
        params = [
            row["method_name"],
            row["symbol"],
            row["market"],
            row["timeframe"],
            row["market_regime"],
            row["volume_state"],
            row["volatility_state"],
        ]

        result_rows = conn.execute(
            """
            SELECT er.return_20d
            FROM experiment_results er
            JOIN learning_experiments le
                ON le.id = er.experiment_id
            WHERE
                le.method_name IS ?
                AND le.symbol IS ?
                AND le.market IS ?
                AND le.timeframe IS ?
                AND er.market_regime IS ?
                AND er.volume_state IS ?
                AND er.volatility_state IS ?
                AND er.return_20d IS NOT NULL
            """,
            params,
        ).fetchall()

        returns = [
            float(r["return_20d"])
            for r in result_rows
            if r["return_20d"] is not None
        ]

        sample_size = safe_int(row["sample_size"])
        positive_count = safe_int(row["positive_count"])

        final_rows.append(
            {
                "method_name": row["method_name"],
                "symbol": row["symbol"],
                "market": row["market"],
                "timeframe": row["timeframe"],
                "market_regime": row["market_regime"],
                "volume_state": row["volume_state"],
                "volatility_state": row["volatility_state"],
                "sample_size": sample_size,
                "positive_count": positive_count,
                "negative_count": safe_int(row["negative_count"]),
                "neutral_count": safe_int(row["neutral_count"]),
                "positive_rate": (
                    positive_count / sample_size
                    if sample_size
                    else None
                ),
                "average_return_1d": row["average_return_1d"],
                "average_return_5d": row["average_return_5d"],
                "average_return_20d": row["average_return_20d"],
                "median_return_20d": (
                    median_or_none(returns)
                ),
                "best_return_20d": (
                    max(returns)
                    if returns
                    else None
                ),
                "worst_return_20d": (
                    min(returns)
                    if returns
                    else None
                ),
                "avg_max_favorable_move": row["avg_max_favorable_move"],
                "avg_max_adverse_move": row["avg_max_adverse_move"],
                "first_observation_date": row["first_observation_date"],
                "last_observation_date": row["last_observation_date"],
                "source_experiments_json": json_dumps(
                    [
                        int(x)
                        for x in str(
                            row["source_experiments_csv"] or ""
                        ).split(",")
                        if x.strip().isdigit()
                    ]
                ),
            }
        )

    return final_rows


def load_evidence_ids_for_experiment(
    conn: sqlite3.Connection,
    experiment_ids: list[int],
) -> list[int]:
    if not experiment_ids:
        return []

    placeholders = ",".join(
        "?"
        for _ in experiment_ids
    )

    rows = conn.execute(
        f"""
        SELECT DISTINCT id
        FROM brain_evidence
        WHERE source_table = 'experiment_results'
          AND source_id IN ({placeholders})
        ORDER BY id ASC
        """,
        experiment_ids,
    ).fetchall()

    return [
        int(row["id"])
        for row in rows
    ]


def import_observations(
    conn: sqlite3.Connection,
) -> dict[str, int]:
    rows = load_grouped_rows(conn)

    stats = {
        "groups_seen": len(rows),
        "groups_written": 0,
        "sources_linked": 0,
        "evidence_linked": 0,
        "candidate_claims": 0,
        "strong_candidates": 0,
        "insufficient_groups": 0,
    }

    for row in rows:
        observation_id = upsert_observation(
            conn,
            row,
        )

        experiment_ids = [
            int(x)
            for x in json.loads(
                row["source_experiments_json"]
            )
        ]

        for experiment_id in experiment_ids:
            conn.execute(
                """
                INSERT OR IGNORE INTO brain_observation_sources (
                    observation_id,
                    experiment_id,
                    created_at
                )
                VALUES (?, ?, ?)
                """,
                (
                    observation_id,
                    experiment_id,
                    utc_now(),
                ),
            )

            stats["sources_linked"] += 1

        evidence_ids = load_evidence_ids_for_experiment(
            conn,
            experiment_ids,
        )

        for evidence_id in evidence_ids:
            conn.execute(
                """
                INSERT OR IGNORE INTO brain_observation_evidence (
                    observation_id,
                    evidence_id,
                    role,
                    weight,
                    created_at
                )
                VALUES (?, ?, 'supports', ?, ?)
                """,
                (
                    observation_id,
                    evidence_id,
                    row["positive_rate"],
                    utc_now(),
                ),
            )

            stats["evidence_linked"] += 1

        confidence = build_confidence(
            safe_int(row["sample_size"]),
            safe_float(row["positive_rate"]),
            safe_float(row["average_return_20d"]),
        )

        status = classify_status(
            safe_int(row["sample_size"]),
            confidence,
        )

        if status == "strong_candidate":
            stats["strong_candidates"] += 1

        if status == "insufficient":
            stats["insufficient_groups"] += 1

        if status in {
            "candidate",
            "strong_candidate",
        }:
            stats["candidate_claims"] += 1

        stats["groups_written"] += 1

    return stats


def print_report(
    stats: dict[str, int],
    conn: sqlite3.Connection,
) -> None:
    print()
    print("=" * 76)
    print("MARKETHQ BRAIN OBSERVATION ENGINE V2")
    print("=" * 76)
    print()
    print(f"Database : {DB_PATH}")
    print(f"Engine   : {ENGINE_NAME}")
    print(f"Version  : {ENGINE_VERSION}")
    print()

    print("OBSERVATION RUN")
    for key, value in stats.items():
        print(f"{key:28} {value:>10}")

    print()
    print("BRAIN OBSERVATION TABLE")
    print(
        f"{'brain_observations':28} "
        f"{count_table(conn, 'brain_observations'):>10}"
    )
    print(
        f"{'brain_observation_sources':28} "
        f"{count_table(conn, 'brain_observation_sources'):>10}"
    )
    print(
        f"{'brain_observation_evidence':28} "
        f"{count_table(conn, 'brain_observation_evidence'):>10}"
    )

    print()
    print("TOP OBSERVATIONS")

    rows = conn.execute(
        """
        SELECT
            method_name,
            symbol,
            market,
            timeframe,
            market_regime,
            volatility_state,
            sample_size,
            positive_rate,
            average_return_20d,
            confidence,
            status
        FROM brain_observations
        ORDER BY sample_size DESC, confidence DESC
        LIMIT 20
        """
    ).fetchall()

    if not rows:
        print("Henüz observation yok.")
    else:
        for row in rows:
            positive_rate = row["positive_rate"]
            avg_return = row["average_return_20d"]
            confidence = row["confidence"]

            print(
                f"{str(row['method_name'])[:28]:28} | "
                f"{str(row['symbol'] or '-')[:8]:8} | "
                f"{str(row['market'] or '-')[:7]:7} | "
                f"{str(row['timeframe'] or '-')[:5]:5} | "
                f"regime={str(row['market_regime'] or '-')[:12]:12} | "
                f"vol={str(row['volatility_state'] or '-')[:8]:8} | "
                f"n={int(row['sample_size']):>5} | "
                f"pos={float(positive_rate):.3f}"
                if positive_rate is not None
                else
                f"{str(row['method_name'])[:28]:28} | "
                f"{str(row['symbol'] or '-')[:8]:8} | "
                f"n={int(row['sample_size']):>5}"
            )

            if avg_return is not None or confidence is not None:
                print(
                    f"  avg20={float(avg_return):.4f} "
                    f"confidence={float(confidence):.4f} "
                    f"status={row['status']}"
                    if avg_return is not None
                    else
                    f"  confidence={float(confidence):.4f} "
                    f"status={row['status']}"
                )

    print()
    print("IMPORTANT")
    print("- Raw experiment/result kayıtları değiştirilmedi.")
    print("- Observation'lar türetilmiş aday hafıza katmanıdır.")
    print("- Candidate observation otomatik olarak doğrulanmış kural değildir.")
    print("- Bir sonraki aşama: observation -> claim -> contradiction/evaluation.")
    print()


def count_table(
    conn: sqlite3.Connection,
    table_name: str,
) -> int:
    if not table_exists(conn, table_name):
        return 0

    row = conn.execute(
        f'SELECT COUNT(*) AS n FROM "{table_name}"'
    ).fetchone()

    return int(row["n"] or 0)


def main() -> None:
    print("MARKETHQ BRAIN OBSERVATION ENGINE V1")
    print(f"Database : {DB_PATH}")
    print()

    if not DB_PATH.exists():
        raise SystemExit(
            f"market_hq.db bulunamadı: {DB_PATH}"
        )

    conn = connect()

    try:
        ensure_schema(conn)

        stats = import_observations(conn)

        conn.commit()

        print_report(
            stats,
            conn,
        )

    except sqlite3.OperationalError as exc:
        try:
            conn.rollback()
        except sqlite3.Error:
            pass

        if "locked" in str(exc).lower():
            raise SystemExit(
                "SQLite database kilitlendi. "
                "MarketHQ/dashboard/main.py gibi çalışan processleri kapatıp "
                "tekrar çalıştır."
            ) from exc

        raise

    finally:
        conn.close()


if __name__ == "__main__":
    main()

