# -*- coding: utf-8 -*-
"""
MarketHQ Brain Learning Pipeline V1
=====================================

Connects setup_outcome → learning_event → brain_claim_candidate

Task 3: Learning Event Pipeline
  - event_id, source_setup_id, setup_type, strategy, regime, timeframe,
    outcome, R, quality, evidence, dataset_version, confidence, timestamp
  - Duplicate prevention: check for duplicate events before creating
  - Claim lifecycle: CANDIDATE → VALIDATED (auto) → PROMOTED (manual only)

Task 4: Brain Claim Model
  - claim_id, hypothesis, evidence, sample_size, confidence, uncertainty,
    dataset, timeframe, validation_period, source_setup_ids, created_at,
    status (CANDIDATE/VALIDATED/PROMOTED)
  - Traceability: which setup/outcome records generated the claim

Weight versioning: weight_v1 (Task 5)
Hierarchical fallback: strategy+regime+timeframe → strategy+regime →
  strategy global → neutral (Task 6)
Walk-forward train/validation split (Task 7)
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from setup_outcome_tracker import DB_PATH, TABLE_NAME, _db, ensure_table, record_outcome


# =========================================================
# PATHS
# =========================================================

BASE_DIR = Path(__file__).resolve().parent
DB_PATH_LEARNING = BASE_DIR / "market_hq.db"


# =========================================================
# DATABASE SETUP
# =========================================================

def init_learning_tables() -> None:
    """Create brain learning tables if not exists.

    Handles schema migration: drops old incompatible tables first, then
    creates/updates all tables with the current schema.
    """
    conn = sqlite3.connect(str(DB_PATH_LEARNING))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")

    # Check if old incompatible schema exists (pre-Task tables)
    existing_tables = {
        r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }

    # Drop old brain_learning_events if it has the incompatible schema
    if "brain_learning_events" in existing_tables:
        cols = {r[1] for r in conn.execute("PRAGMA table_info(brain_learning_events)").fetchall()}
        # Old schema has event_type but not source_setup_id
        if "source_setup_id" not in cols:
            conn.execute("DROP TABLE IF EXISTS brain_learning_events")
            existing_tables.discard("brain_learning_events")

    # Drop old brain_setup_claims if it exists with wrong schema
    if "brain_setup_claims" in existing_tables:
        cols = {r[1] for r in conn.execute("PRAGMA table_info(brain_setup_claims)").fetchall()}
        if "hypothesis" not in cols:
            conn.execute("DROP TABLE IF EXISTS brain_setup_claims")
            existing_tables.discard("brain_setup_claims")

    # Drop old brain_weight_versions if it exists with wrong schema
    if "brain_weight_versions" in existing_tables:
        cols = {r[1] for r in conn.execute("PRAGMA table_info(brain_weight_versions)").fetchall()}
        if "strategy" not in cols:
            conn.execute("DROP TABLE IF EXISTS brain_weight_versions")
            existing_tables.discard("brain_weight_versions")

    # Drop old brain_walkforward_splits if it exists
    if "brain_walkforward_splits" in existing_tables:
        conn.execute("DROP TABLE IF EXISTS brain_walkforward_splits")
        existing_tables.discard("brain_walkforward_splits")

    conn.commit()

    # --- Learning Events Table ---
    conn.execute("""
        CREATE TABLE IF NOT EXISTS brain_learning_events (
            event_id TEXT PRIMARY KEY,
            source_setup_id INTEGER NOT NULL,
            setup_type TEXT NOT NULL,
            strategy TEXT NOT NULL,
            regime TEXT NOT NULL,
            timeframe TEXT NOT NULL,
            outcome TEXT NOT NULL,
            R REAL,
            quality REAL,
            evidence TEXT,
            dataset_version TEXT DEFAULT 'v1',
            confidence REAL,
            sample_size_confidence TEXT DEFAULT 'unknown',
            created_at TEXT DEFAULT (datetime('now')),
            UNIQUE(source_setup_id)
        )
    """)
    # Add missing columns if table existed with old schema
    _add_col = lambda conn, t, c, ty: conn.execute(
        f"ALTER TABLE {t} ADD COLUMN {c} {ty}"
    ) if c not in {r[1] for r in conn.execute(f"PRAGMA table_info({t})").fetchall()} else None

    _add_col(conn, "brain_learning_events", "event_id", "TEXT")
    _add_col(conn, "brain_learning_events", "source_setup_id", "INTEGER")
    _add_col(conn, "brain_learning_events", "strategy", "TEXT")
    _add_col(conn, "brain_learning_events", "regime", "TEXT")
    _add_col(conn, "brain_learning_events", "timeframe", "TEXT")
    _add_col(conn, "brain_learning_events", "R", "REAL")
    _add_col(conn, "brain_learning_events", "quality", "REAL")
    _add_col(conn, "brain_learning_events", "evidence", "TEXT")
    _add_col(conn, "brain_learning_events", "dataset_version", "TEXT")
    _add_col(conn, "brain_learning_events", "confidence", "REAL")
    _add_col(conn, "brain_learning_events", "sample_size_confidence", "TEXT")

    conn.execute("CREATE INDEX IF NOT EXISTS idx_brain_ev_setup ON brain_learning_events(source_setup_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_brain_ev_type ON brain_learning_events(setup_type)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_brain_ev_regime ON brain_learning_events(regime)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_brain_ev_timeframe ON brain_learning_events(timeframe)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_brain_ev_outcome ON brain_learning_events(outcome)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_brain_ev_dataset ON brain_learning_events(dataset_version)")

    # --- Brain Setup Claims Table (Task 4) ---
    conn.execute("""
        CREATE TABLE IF NOT EXISTS brain_setup_claims (
            claim_id TEXT PRIMARY KEY,
            hypothesis TEXT NOT NULL,
            evidence TEXT,
            sample_size INTEGER DEFAULT 0,
            confidence REAL DEFAULT 0.0,
            uncertainty REAL DEFAULT 1.0,
            dataset TEXT DEFAULT 'v1',
            timeframe TEXT NOT NULL,
            validation_period TEXT,
            source_setup_ids TEXT DEFAULT '[]',
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now')),
            status TEXT DEFAULT 'CANDIDATE' CHECK(status IN ('CANDIDATE','VALIDATED','PROMOTED')),
            weight_version TEXT DEFAULT 'weight_v1',
            traceability_json TEXT DEFAULT '{}'
        )
    """)
    _add_col_b = lambda conn, t, c, ty: conn.execute(
        f"ALTER TABLE {t} ADD COLUMN {c} {ty}"
    ) if c not in {r[1] for r in conn.execute(f"PRAGMA table_info({t})").fetchall()} else None

    _add_col_b(conn, "brain_setup_claims", "hypothesis", "TEXT")
    _add_col_b(conn, "brain_setup_claims", "evidence", "TEXT")
    _add_col_b(conn, "brain_setup_claims", "sample_size", "INTEGER")
    _add_col_b(conn, "brain_setup_claims", "confidence", "REAL")
    _add_col_b(conn, "brain_setup_claims", "uncertainty", "REAL")
    _add_col_b(conn, "brain_setup_claims", "dataset", "TEXT")
    _add_col_b(conn, "brain_setup_claims", "validation_period", "TEXT")
    _add_col_b(conn, "brain_setup_claims", "source_setup_ids", "TEXT")
    _add_col_b(conn, "brain_setup_claims", "status", "TEXT")
    _add_col_b(conn, "brain_setup_claims", "weight_version", "TEXT")
    _add_col_b(conn, "brain_setup_claims", "traceability_json", "TEXT")
    _add_col_b(conn, "brain_setup_claims", "updated_at", "TEXT")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_brain_claim_status ON brain_setup_claims(status)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_brain_claim_dataset ON brain_setup_claims(dataset)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_brain_claim_timeframe ON brain_setup_claims(timeframe)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_brain_claim_weight_ver ON brain_setup_claims(weight_version)")

    # --- Weight Versions Table ---
    conn.execute("""
        CREATE TABLE IF NOT EXISTS brain_weight_versions (
            version_id TEXT PRIMARY KEY,
            weight_version TEXT NOT NULL,
            strategy TEXT NOT NULL,
            regime TEXT NOT NULL,
            timeframe TEXT NOT NULL,
            raw_weight REAL,
            adjusted_weight REAL,
            sample_size INTEGER,
            confidence REAL,
            uncertainty REAL,
            correlation_penalty REAL DEFAULT 0.0,
            family_diversity REAL DEFAULT 0.0,
            weight_source_level TEXT DEFAULT 'full',
            weight_fallback_used INTEGER DEFAULT 0,
            weight_fallback_reason TEXT,
            dataset TEXT DEFAULT 'v1',
            generated_at TEXT DEFAULT (datetime('now'))
        )
    """)
    _add_col_c = lambda conn, t, c, ty: conn.execute(
        f"ALTER TABLE {t} ADD COLUMN {c} {ty}"
    ) if c not in {r[1] for r in conn.execute(f"PRAGMA table_info({t})").fetchall()} else None

    _add_col_c(conn, "brain_weight_versions", "raw_weight", "REAL")
    _add_col_c(conn, "brain_weight_versions", "adjusted_weight", "REAL")
    _add_col_c(conn, "brain_weight_versions", "sample_size", "INTEGER")
    _add_col_c(conn, "brain_weight_versions", "confidence", "REAL")
    _add_col_c(conn, "brain_weight_versions", "uncertainty", "REAL")
    _add_col_c(conn, "brain_weight_versions", "correlation_penalty", "REAL")
    _add_col_c(conn, "brain_weight_versions", "family_diversity", "REAL")
    _add_col_c(conn, "brain_weight_versions", "weight_source_level", "TEXT")
    _add_col_c(conn, "brain_weight_versions", "weight_fallback_used", "INTEGER")
    _add_col_c(conn, "brain_weight_versions", "weight_fallback_reason", "TEXT")
    _add_col_c(conn, "brain_weight_versions", "dataset", "TEXT")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_wt_ver_strategy ON brain_weight_versions(strategy)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_wt_ver_regime ON brain_weight_versions(regime)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_wt_ver_timeframe ON brain_weight_versions(timeframe)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_wt_ver_version ON brain_weight_versions(weight_version)")

    # --- Train/Validation Splits Table ---
    conn.execute("""
        CREATE TABLE IF NOT EXISTS brain_walkforward_splits (
            split_id TEXT PRIMARY KEY,
            weight_version TEXT NOT NULL,
            train_start TEXT,
            train_end TEXT,
            validation_start TEXT,
            validation_end TEXT,
            train_size INTEGER,
            validation_size INTEGER,
            baseline_train_r REAL,
            baseline_val_r REAL,
            adaptive_train_r REAL,
            adaptive_val_r REAL,
            lookahead_check_passed INTEGER DEFAULT 1,
            created_at TEXT DEFAULT (datetime('now'))
        )
    """)

    conn.commit()
    conn.close()


# =========================================================
# LEARNING EVENTS (Task 3)
# =========================================================

@dataclass
class LearningEvent:
    event_id: str = ""
    source_setup_id: int = 0
    setup_type: str = ""
    strategy: str = ""
    regime: str = ""
    timeframe: str = ""
    outcome: str = ""
    R: float = 0.0
    quality: float = 0.0
    evidence: str = ""
    dataset_version: str = "v1"
    confidence: float = 0.0
    sample_size_confidence: str = "unknown"
    created_at: str = ""


def _make_event_id(source_setup_id: int) -> str:
    """Deterministic event ID from source setup ID."""
    raw = f"event_{source_setup_id}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def event_exists(conn: sqlite3.Connection, source_setup_id: int) -> bool:
    """Check if a learning event already exists for this setup (duplicate prevention)."""
    row = conn.execute(
        "SELECT 1 FROM brain_learning_events WHERE source_setup_id = ? LIMIT 1",
        (source_setup_id,),
    ).fetchone()
    return row is not None


def create_learning_event(
    source_setup_id: int,
    setup_type: str,
    strategy: str,
    regime: str,
    timeframe: str,
    outcome: str,
    R: float = 0.0,
    quality: float = 0.0,
    evidence: str = "",
    dataset_version: str = "v1",
    confidence: float = 0.0,
    sample_size_confidence: str = "unknown",
    conn: sqlite3.Connection | None = None,
) -> str:
    """Create a learning event from a setup outcome.

    Returns event_id. Raises if duplicate detected.
    """
    init_learning_tables()
    close_conn = conn is None
    if conn is None:
        conn = sqlite3.connect(str(DB_PATH_LEARNING))
        conn.row_factory = sqlite3.Row

    try:
        # Duplicate prevention (Task 3)
        if event_exists(conn, source_setup_id):
            existing = conn.execute(
                "SELECT event_id FROM brain_learning_events WHERE source_setup_id = ?",
                (source_setup_id,),
            ).fetchone()
            raise ValueError(
                f"Duplicate learning event: source_setup_id={source_setup_id} "
                f"already has event_id={existing['event_id']}"
            )

        event_id = _make_event_id(source_setup_id)
        now = datetime.now(timezone.utc).isoformat()

        conn.execute("""
            INSERT INTO brain_learning_events
                (event_id, source_setup_id, setup_type, strategy, regime,
                 timeframe, outcome, R, quality, evidence, dataset_version,
                 confidence, sample_size_confidence, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            event_id, source_setup_id, setup_type, strategy, regime,
            timeframe, outcome, R, quality, evidence, dataset_version,
            confidence, sample_size_confidence, now,
        ))
        conn.commit()
        return event_id
    finally:
        if close_conn:
            conn.close()


def create_learning_events_from_outcomes(
    outcome_ids: list[int] | None = None,
    limit: int = 1000,
) -> dict[str, Any]:
    """Batch-create learning events from setup_outcome records.

    Skips outcomes that already have learning events (duplicate prevention).

    Returns summary dict.
    """
    init_learning_tables()
    conn = sqlite3.connect(str(DB_PATH_LEARNING))
    conn.row_factory = sqlite3.Row

    try:
        ensure_table()

        # Get outcomes not yet processed
        where = ""
        params: list[Any] = []
        if outcome_ids:
            placeholders = ",".join("?" for _ in outcome_ids)
            where = f"WHERE id IN ({placeholders})"
            params.extend(outcome_ids)
        else:
            # Only outcomes without existing learning events
            where = """WHERE id NOT IN (
                SELECT source_setup_id FROM brain_learning_events
            )"""

        rows = conn.execute(f"""
            SELECT * FROM {TABLE_NAME}
            {where}
            ORDER BY id ASC
            LIMIT ?
        """, params + [limit]).fetchall()

        created = 0
        skipped = 0
        errors = []

        for row in rows:
            try:
                # Determine strategy from setup_type
                strategy = row["setup_type"] or "unknown"

                # Extract evidence from metadata
                metadata = {}
                if row["metadata_json"]:
                    try:
                        metadata = json.loads(row["metadata_json"])
                    except (json.JSONDecodeError, TypeError):
                        pass

                evidence_parts = []
                if metadata.get("source"):
                    evidence_parts.append(f"source={metadata['source']}")
                if metadata.get("r_multiple"):
                    evidence_parts.append(f"R={metadata['r_multiple']:.2f}")
                if metadata.get("quality_breakdown"):
                    evidence_parts.append("quality_breakdown_available")

                create_learning_event(
                    source_setup_id=row["id"],
                    setup_type=row["setup_type"] or "unknown",
                    strategy=strategy,
                    regime=row["regime"] or "UNKNOWN",
                    timeframe=row["timeframe"] or "unknown",
                    outcome=row["outcome"] or "open",
                    R=row["pnl_pct"] or 0.0,
                    quality=row["quality_score"] or 0.0,
                    evidence="; ".join(evidence_parts),
                    dataset_version=row["dataset_version"] or "v1",
                    confidence=row["quality_score"] or 0.0,
                    sample_size_confidence="unknown",
                    conn=conn,
                )
                created += 1
            except ValueError as e:
                # Duplicate — skip
                skipped += 1
            except Exception as e:
                errors.append(str(e))

        return {
            "created": created,
            "skipped_duplicates": skipped,
            "errors": len(errors),
            "error_details": errors[:10],
        }
    finally:
        conn.close()


# =========================================================
# CLAIM LIFECYCLE (Tasks 3 & 4)
# =========================================================

@dataclass
class BrainClaim:
    claim_id: str = ""
    hypothesis: str = ""
    evidence: str = ""
    sample_size: int = 0
    confidence: float = 0.0
    uncertainty: float = 1.0
    dataset: str = "v1"
    timeframe: str = ""
    validation_period: str = ""
    source_setup_ids: list[int] = field(default_factory=list)
    created_at: str = ""
    status: str = "CANDIDATE"  # CANDIDATE | VALIDATED | PROMOTED
    weight_version: str = "weight_v1"
    traceability: dict[str, Any] = field(default_factory=dict)


def _make_claim_id(hypothesis: str, timeframe: str) -> str:
    """Deterministic claim ID from hypothesis + timeframe."""
    raw = f"claim_{hypothesis}_{timeframe}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def create_claim(
    hypothesis: str,
    evidence: str = "",
    sample_size: int = 0,
    confidence: float = 0.0,
    uncertainty: float = 1.0,
    dataset: str = "v1",
    timeframe: str = "",
    validation_period: str = "",
    source_setup_ids: list[int] | None = None,
    weight_version: str = "weight_v1",
    traceability: dict[str, Any] | None = None,
    conn: sqlite3.Connection | None = None,
) -> str:
    """Create a new brain claim (CANDIDATE status).

    Returns claim_id.
    """
    init_learning_tables()
    close_conn = conn is None
    if conn is None:
        conn = sqlite3.connect(str(DB_PATH_LEARNING))
        conn.row_factory = sqlite3.Row

    try:
        claim_id = _make_claim_id(hypothesis, timeframe)
        now = datetime.now(timezone.utc).isoformat()

        conn.execute("""
            INSERT INTO brain_setup_claims
                (claim_id, hypothesis, evidence, sample_size, confidence,
                 uncertainty, dataset, timeframe, validation_period,
                 source_setup_ids, created_at, updated_at, status,
                 weight_version, traceability_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            claim_id, hypothesis, evidence, sample_size, confidence,
            uncertainty, dataset, timeframe, validation_period,
            json.dumps(source_setup_ids or []), now, now, "CANDIDATE",
            weight_version, json.dumps(traceability or {}),
        ))
        conn.commit()
        return claim_id
    finally:
        if close_conn:
            conn.close()


def validate_claim(claim_id: str, conn: sqlite3.Connection | None = None) -> bool:
    """Auto-validate a claim (CANDIDATE → VALIDATED).

    Auto-validation: claim has sufficient sample (>=5) and confidence >= 0.3.
    Returns True if validated, False if criteria not met.
    """
    init_learning_tables()
    close_conn = conn is None
    if conn is None:
        conn = sqlite3.connect(str(DB_PATH_LEARNING))
        conn.row_factory = sqlite3.Row

    try:
        row = conn.execute(
            "SELECT * FROM brain_setup_claims WHERE claim_id = ?",
            (claim_id,),
        ).fetchone()
        if row is None:
            return False
        if row["status"] != "CANDIDATE":
            return False

        # Auto-validation criteria
        sufficient_sample = row["sample_size"] >= 5
        sufficient_confidence = row["confidence"] >= 0.3

        if sufficient_sample and sufficient_confidence:
            conn.execute(
                "UPDATE brain_setup_claims SET status = 'VALIDATED', updated_at = ? WHERE claim_id = ?",
                (datetime.now(timezone.utc).isoformat(), claim_id),
            )
            conn.commit()
            return True
        return False
    finally:
        if close_conn:
            conn.close()


def promote_claim(claim_id: str, conn: sqlite3.Connection | None = None) -> bool:
    """Manually promote a claim (VALIDATED → PROMOTED).

    Only claims in VALIDATED status can be promoted.
    Returns True if promoted, False otherwise.
    """
    init_learning_tables()
    close_conn = conn is None
    if conn is None:
        conn = sqlite3.connect(str(DB_PATH_LEARNING))
        conn.row_factory = sqlite3.Row

    try:
        row = conn.execute(
            "SELECT status FROM brain_setup_claims WHERE claim_id = ?",
            (claim_id,),
        ).fetchone()
        if row is None:
            return False
        if row["status"] != "VALIDATED":
            return False

        conn.execute(
            "UPDATE brain_setup_claims SET status = 'PROMOTED', updated_at = ? WHERE claim_id = ?",
            (datetime.now(timezone.utc).isoformat(), claim_id),
        )
        conn.commit()
        return True
    finally:
        if close_conn:
            conn.close()


def get_claim(claim_id: str) -> dict[str, Any] | None:
    """Get a claim by ID."""
    conn = sqlite3.connect(str(DB_PATH_LEARNING))
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute(
            "SELECT * FROM brain_setup_claims WHERE claim_id = ?",
            (claim_id,),
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def get_claims_by_status(
    status: str = "CANDIDATE",
    dataset: str | None = None,
    timeframe: str | None = None,
) -> list[dict[str, Any]]:
    """Get claims filtered by status and optional dataset/timeframe."""
    conn = sqlite3.connect(str(DB_PATH_LEARNING))
    conn.row_factory = sqlite3.Row
    try:
        query = "SELECT * FROM brain_setup_claims WHERE status = ?"
        params: list[Any] = [status]
        if dataset:
            query += " AND dataset = ?"
            params.append(dataset)
        if timeframe:
            query += " AND timeframe = ?"
            params.append(timeframe)
        query += " ORDER BY created_at DESC"
        rows = conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def sync_claims_from_events(
    min_sample: int = 3,
    confidence_threshold: float = 0.3,
) -> dict[str, Any]:
    """Sync claims from learning events.

    Groups events by (setup_type, regime, timeframe) and creates/updates claims.
    """
    init_learning_tables()
    conn = sqlite3.connect(str(DB_PATH_LEARNING))
    conn.row_factory = sqlite3.Row

    try:
        # Group events by (setup_type, regime, timeframe)
        groups = conn.execute("""
            SELECT
                setup_type, regime, timeframe,
                COUNT(*) as n,
                AVG(R) as avg_R,
                AVG(quality) as avg_quality,
                GROUP_CONCAT(event_id) as event_ids,
                GROUP_CONCAT(source_setup_id) as setup_ids
            FROM brain_learning_events
            GROUP BY setup_type, regime, timeframe
            HAVING COUNT(*) >= ?
        """, (min_sample,)).fetchall()

        created = 0
        updated = 0

        for g in groups:
            hypothesis = (
                f"{g['setup_type']} in {g['regime']} "
                f"on {g['timeframe']} has avg R={g['avg_R']:.3f}"
            )
            evidence = f"events: {g['event_ids'][:200]}"
            confidence = min(abs(g["avg_R"]) / 2.0 + g["avg_quality"] / 2, 1.0)
            uncertainty = max(0.0, 1.0 - g["n"] / 50.0)

            existing = conn.execute(
                "SELECT claim_id FROM brain_setup_claims WHERE hypothesis = ? AND timeframe = ?",
                (hypothesis, g["timeframe"]),
            ).fetchone()

            source_ids = [int(x) for x in (g["setup_ids"] or "").split(",") if x]

            if existing:
                # Update existing claim
                conn.execute("""
                    UPDATE brain_setup_claims SET
                        sample_size = ?, confidence = ?, uncertainty = ?,
                        evidence = ?, source_setup_ids = ?, updated_at = ?
                    WHERE claim_id = ?
                """, (
                    g["n"], confidence, uncertainty, evidence,
                    json.dumps(source_ids),
                    datetime.now(timezone.utc).isoformat(),
                    existing["claim_id"],
                ))
                updated += 1
            else:
                # Create new claim
                create_claim(
                    hypothesis=hypothesis,
                    evidence=evidence,
                    sample_size=g["n"],
                    confidence=confidence,
                    uncertainty=uncertainty,
                    dataset="v1",
                    timeframe=g["timeframe"],
                    validation_period="pending",
                    source_setup_ids=source_ids,
                    weight_version="weight_v1",
                    traceability={
                        "source_events": g["event_ids"].split(",")[:10],
                        "group_key": f"{g['setup_type']}|{g['regime']}|{g['timeframe']}",
                    },
                    conn=conn,
                )
                created += 1

        conn.commit()
        return {"created": created, "updated": updated, "total_groups": len(groups)}
    finally:
        conn.close()


# =========================================================
# WEIGHT ENGINE HELPERS (Task 5)
# =========================================================

def _compute_correlation_penalty(
    existing_map: dict[str, float],
    strategy: str,
    regime: str,
    timeframe: str,
) -> float:
    """Compute correlation penalty for highly correlated strategies."""
    penalty = 0.0
    for key, w in existing_map.items():
        parts = key.split("|")
        if len(parts) >= 3:
            k_strategy, k_regime, k_timeframe = parts[0], parts[1], parts[2]
            if k_regime == regime and k_timeframe == timeframe:
                if k_strategy != strategy:
                    penalty += 0.05 * w
    return min(penalty, 0.3)


def _family_diversity_score(
    strategy: str,
    regime: str,
    timeframe: str,
    existing_weights: dict[str, float],
) -> float:
    """Compute family diversity score (0..1)."""
    families_in_cell = set()
    for key in existing_weights:
        parts = key.split("|")
        if len(parts) >= 3 and parts[1] == regime and parts[2] == timeframe:
            families_in_cell.add(parts[0])

    if not families_in_cell:
        return 1.0

    diversity = len(families_in_cell) / max(len(existing_weights), 1)
    return min(diversity + 0.5, 1.0)


# =========================================================
# STRATEGY WEIGHT ENGINE (Task 5)
# =========================================================

@dataclass
class StrategyWeight:
    """A single strategy weight entry (weight_v1)."""
    strategy: str = ""
    regime: str = ""
    timeframe: str = ""
    raw_weight: float = 0.0
    adjusted_weight: float = 0.0
    sample_size: int = 0
    confidence: float = 0.0
    uncertainty: float = 1.0
    correlation_penalty: float = 0.0
    weight_version: str = "weight_v1"
    generated_at: str = ""
    # Task 6: fallback tracking
    weight_source_level: str = "full"  # full | regime | strategy | neutral
    weight_fallback_used: int = 0
    weight_fallback_reason: str = ""
    # Dataset tracking
    dataset_version: str = "v1"


class StrategyWeightEngine:
    """Offline Strategy Weight Engine V1.

    Computes adaptive weights for strategy+regime+timeframe combinations
    from historical setup_outcome data.

    Factors:
      - historical performance (win_rate * avg_R)
      - sample size (shrinkage toward global mean)
      - uncertainty (inverse of sample size)
      - regime compatibility (from regime_filter)
      - correlation penalty (for correlated strategies)
      - family diversity bonus

    Weight versioning: weight_v1
    Hierarchical fallback (Task 6): strategy+regime+timeframe → strategy+regime
      → strategy global → neutral
    Walk-forward validation (Task 7): train/validation split with look-ahead check
    """

    SHRINKAGE_CONSTANT = 50.0  # Task 1: Bayesian shrinkage constant
    GLOBAL_MEAN_WEIGHT = 0.5   # Prior mean for shrinkage
    MIN_SAMPLE_FOR_FULL = 5    # Minimum samples for full-level weight
    MIN_SAMPLE_FOR_REGIME = 3  # Minimum samples for regime-level fallback
    MIN_SAMPLE_FOR_STRATEGY = 2  # Minimum samples for strategy-level fallback

    def __init__(self, db_path: Path | str = DB_PATH_LEARNING):
        self.db_path = Path(db_path)
        init_learning_tables()

    # ----------------------------------------------------------
    # Core weight computation
    # ----------------------------------------------------------

    def compute_weights(
        self,
        dataset_version: str = "v1",
        strategy_filter: str | None = None,
        regime_filter: str | None = None,
        timeframe_filter: str | None = None,
    ) -> list[StrategyWeight]:
        """Compute weights for all strategy+regime+timeframe combos.

        Uses learning events (brain_learning_events) as input,
        falling back to setup_outcomes if no events exist.
        """
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row

        try:
            # Get events for the dataset
            events = self._get_events(conn, dataset_version)

            if not events:
                # Fall back to setup_outcomes
                events = self._get_outcomes_as_events(conn, dataset_version)

            if not events:
                return []

            # Group by (strategy, regime, timeframe)
            groups: dict[tuple, list[dict]] = {}
            for ev in events:
                key = (ev["strategy"], ev["regime"], ev["timeframe"])
                groups.setdefault(key, []).append(ev)

            # Compute global mean for shrinkage
            all_R = [e["R"] for e in events if e["outcome"] in ("hit_target", "hit_invalidation")]
            global_mean_R = sum(all_R) / len(all_R) if all_R else 0.0

            weights = []
            for (strategy, regime, timeframe), group_events in groups.items():
                w = self._compute_single_weight(
                    strategy, regime, timeframe, group_events,
                    global_mean_R, weights,
                )
                weights.append(w)

            return weights
        finally:
            conn.close()

    def _get_events(
        self, conn: sqlite3.Connection, dataset_version: str,
    ) -> list[dict]:
        """Get learning events for the dataset."""
        rows = conn.execute(
            "SELECT * FROM brain_learning_events WHERE dataset_version = ?",
            (dataset_version,),
        ).fetchall()
        return [dict(r) for r in rows]

    def _get_outcomes_as_events(
        self, conn: sqlite3.Connection, dataset_version: str,
    ) -> list[dict]:
        """Convert setup_outcomes to event-like dicts for weight computation."""
        rows = conn.execute(
            "SELECT * FROM setup_outcomes WHERE dataset_version = ? AND outcome IN ('hit_target', 'hit_invalidation')",
            (dataset_version,),
        ).fetchall()
        return [{
            "strategy": r["setup_type"],
            "regime": r["regime"],
            "timeframe": r["timeframe"],
            "R": r["pnl_pct"] or 0.0,
            "quality": r["quality_score"] or 0.0,
            "outcome": r["outcome"],
            "confidence": r["quality_score"] or 0.0,
            "dataset_version": r["dataset_version"] or dataset_version,
        } for r in rows]

    def _compute_single_weight(
        self,
        strategy: str,
        regime: str,
        timeframe: str,
        events: list[dict],
        global_mean_R: float,
        existing_weights: list[StrategyWeight],
    ) -> StrategyWeight:
        """Compute weight for a single (strategy, regime, timeframe) cell."""
        n = len(events)

        # Historical performance
        hit_events = [e for e in events if e["outcome"] == "hit_target"]
        miss_events = [e for e in events if e["outcome"] == "hit_invalidation"]
        closed = hit_events + miss_events
        closed_n = len(closed)

        if closed_n == 0:
            raw_performance = 0.0
            win_rate = 0.0
            avg_R = 0.0
        else:
            win_rate = len(hit_events) / closed_n
            R_vals = [abs(e["R"]) for e in closed]
            avg_R = sum(R_vals) / len(R_vals) if R_vals else 0.0
            raw_performance = win_rate * avg_R

        # Sample size confidence (Task 1)
        from setup_quality_engine_v2 import sample_size_confidence
        ss_level, shrinkage = sample_size_confidence(closed_n)

        # Bayesian shrinkage toward global mean
        from setup_quality_engine_v2 import sample_adjusted_expectancy
        adjusted_perf = sample_adjusted_expectancy(
            closed_n, raw_performance, self.GLOBAL_MEAN_WEIGHT,
            self.SHRINKAGE_CONSTANT,
        )

        # Uncertainty (inverse of sample size, clamped 0..1)
        uncertainty = max(0.0, min(1.0, 1.0 - min(closed_n / 50.0, 1.0)))

        # Regime compatibility (from regime_filter if available)
        regime_compat = self._get_regime_compatibility(regime, strategy)

        # Correlation penalty (Task 5)
        existing_map: dict[str, float] = {}
        for ew in existing_weights:
            key = f"{ew.strategy}|{ew.regime}|{ew.timeframe}"
            existing_map[key] = ew.adjusted_weight
        corr_penalty = _compute_correlation_penalty(
            existing_map, strategy, regime, timeframe,
        )

        # Family diversity bonus
        diversity = _family_diversity_score(
            strategy, regime, timeframe, existing_map,
        )

        # Raw weight = performance * regime_compat * diversity - correlation_penalty
        raw_weight = (
            adjusted_perf * regime_compat * diversity
            - corr_penalty
        )
        raw_weight = max(0.0, raw_weight)  # clamp to non-negative

        # Adjusted weight with uncertainty scaling
        adjusted_weight = raw_weight * (1.0 - uncertainty * 0.5)

        confidence = 1.0 - uncertainty

        now = datetime.now(timezone.utc).isoformat()

        return StrategyWeight(
            strategy=strategy,
            regime=regime,
            timeframe=timeframe,
            raw_weight=round(raw_weight, 4),
            adjusted_weight=round(adjusted_weight, 4),
            sample_size=closed_n,
            confidence=round(confidence, 3),
            uncertainty=round(uncertainty, 3),
            correlation_penalty=round(corr_penalty, 4),
            weight_version="weight_v1",
            generated_at=now,
        )

    def _get_regime_compatibility(self, regime: str, strategy: str) -> float:
        """Get regime compatibility from regime_filter if available."""
        try:
            from regime_filter import classify_regime_eligibility, compute_regime_strategy_matrix
            matrix = compute_regime_strategy_matrix()
            decision = classify_regime_eligibility(regime, strategy, matrix)
            return decision.compatibility
        except Exception:
            return 0.5

    # ----------------------------------------------------------
    # Hierarchical Fallback (Task 6)
    # ----------------------------------------------------------

    def get_weight_with_fallback(
        self,
        strategy: str,
        regime: str,
        timeframe: str,
        dataset_version: str = "v1",
    ) -> StrategyWeight:
        """Get weight with hierarchical fallback.

        Lookup order:
          1. strategy+regime+timeframe (full specificity)
          2. strategy+regime (timeframe fallback)
          3. strategy global (regime+timeframe fallback)
          4. neutral (all fallback exhausted)

        Tracks which level was used via weight_source_level and
        weight_fallback_used/weight_fallback_reason.
        """
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row

        try:
            # Level 1: Full specificity
            w = self._lookup_weight(conn, strategy, regime, timeframe, dataset_version)
            if w and w.sample_size >= self.MIN_SAMPLE_FOR_FULL:
                w.weight_source_level = "full"
                w.weight_fallback_used = 0
                w.weight_fallback_reason = ""
                return w

            # Level 2: strategy+regime fallback
            w = self._lookup_weight(conn, strategy, regime, "", dataset_version)
            if w and w.sample_size >= self.MIN_SAMPLE_FOR_REGIME:
                w.weight_source_level = "regime"
                w.weight_fallback_used = 1
                w.weight_fallback_reason = f"fallback: no data for {timeframe} in {strategy}+{regime}"
                return w

            # Level 3: strategy global fallback
            w = self._lookup_weight(conn, strategy, "", "", dataset_version)
            if w and w.sample_size >= self.MIN_SAMPLE_FOR_STRATEGY:
                w.weight_source_level = "strategy"
                w.weight_fallback_used = 2
                w.weight_fallback_reason = f"fallback: no data for {regime}/{timeframe} in {strategy}"
                return w

            # Level 4: neutral fallback
            w = self._lookup_weight(conn, "neutral", "", "", dataset_version)
            if w is None:
                w = StrategyWeight(
                    strategy="neutral",
                    regime=regime,
                    timeframe=timeframe,
                    raw_weight=0.5,
                    adjusted_weight=0.5,
                    sample_size=0,
                    confidence=0.0,
                    uncertainty=1.0,
                    weight_version="weight_v1",
                    generated_at=datetime.now(timezone.utc).isoformat(),
                )
            w.weight_source_level = "neutral"
            w.weight_fallback_used = 3
            w.weight_fallback_reason = "fallback: all specific levels exhausted, using neutral"
            return w
        finally:
            conn.close()

    def _lookup_weight(
        self,
        conn: sqlite3.Connection,
        strategy: str,
        regime: str,
        timeframe: str,
        dataset_version: str,
    ) -> StrategyWeight | None:
        """Look up a weight from the weight_versions table."""
        row = conn.execute("""
            SELECT * FROM brain_weight_versions
            WHERE strategy = ? AND regime = ? AND timeframe = ?
              AND weight_version = ? AND dataset = ?
            ORDER BY generated_at DESC LIMIT 1
        """, (strategy, regime, timeframe, "weight_v1", dataset_version)).fetchone()

        if row is None:
            return None

        return StrategyWeight(
            strategy=row["strategy"],
            regime=row["regime"],
            timeframe=row["timeframe"],
            raw_weight=row["raw_weight"] or 0.0,
            adjusted_weight=row["adjusted_weight"] or 0.0,
            sample_size=row["sample_size"] or 0,
            confidence=row["confidence"] or 0.0,
            uncertainty=row["uncertainty"] or 1.0,
            correlation_penalty=row["correlation_penalty"] or 0.0,
            weight_version=row["weight_version"] or "weight_v1",
            generated_at=row["generated_at"] or "",
            weight_source_level=row["weight_source_level"] or "full",
            weight_fallback_used=row["weight_fallback_used"] or 0,
            weight_fallback_reason=row["weight_fallback_reason"] or "",
        )

    # ----------------------------------------------------------
    # Weight persistence
    # ----------------------------------------------------------

    def save_weights(self, weights: list[StrategyWeight]) -> int:
        """Save computed weights to the database."""
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        try:
            saved = 0
            for w in weights:
                conn.execute("""
                    INSERT INTO brain_weight_versions
                        (version_id, weight_version, strategy, regime, timeframe,
                         raw_weight, adjusted_weight, sample_size, confidence,
                         uncertainty, correlation_penalty, family_diversity,
                         weight_source_level, weight_fallback_used,
                         weight_fallback_reason, dataset, generated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    _make_event_id(hash(f"{w.strategy}|{w.regime}|{w.timeframe}") % 10**16),
                    w.weight_version, w.strategy, w.regime, w.timeframe,
                    w.raw_weight, w.adjusted_weight, w.sample_size, w.confidence,
                    w.uncertainty, w.correlation_penalty,
                    _family_diversity_score(w.strategy, w.regime, w.timeframe, {}),
                    w.weight_source_level, w.weight_fallback_used,
                    w.weight_fallback_reason, w.dataset_version, w.generated_at,
                ))
                saved += 1
            conn.commit()
            return saved
        finally:
            conn.close()

    # ----------------------------------------------------------
    # Walk-Forward Train/Validation Split (Task 7)
    # ----------------------------------------------------------

    def walk_forward_split(
        self,
        dataset_version: str = "v1",
        train_ratio: float = 0.7,
    ) -> dict[str, Any]:
        """Split outcomes into training (first 70%) and validation (last 30%).

        Train weights on training period, validate on validation period.
        Look-ahead check: no future data in training.
        Compare baseline vs adaptive_v1 out-of-sample.

        Returns split info and comparison metrics.
        """
        init_learning_tables()
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row

        try:
            # Get all events for this dataset, ordered by time
            events = conn.execute("""
                SELECT * FROM brain_learning_events
                WHERE dataset_version = ?
                ORDER BY created_at ASC
            """, (dataset_version,)).fetchall()

            if not events:
                # Fall back to setup_outcomes
                events_rows = conn.execute("""
                    SELECT * FROM setup_outcomes
                    WHERE dataset_version = ? AND outcome IN ('hit_target', 'hit_invalidation')
                    ORDER BY created_at ASC
                """, (dataset_version,)).fetchall()
                events = [{
                    "event_id": f"outcome_{r['id']}",
                    "source_setup_id": r["id"],
                    "setup_type": r["setup_type"],
                    "strategy": r["setup_type"],
                    "regime": r["regime"],
                    "timeframe": r["timeframe"],
                    "outcome": r["outcome"],
                    "R": r["pnl_pct"] or 0.0,
                    "quality": r["quality_score"] or 0.0,
                    "dataset_version": r["dataset_version"] or dataset_version,
                    "created_at": r["created_at"],
                } for r in events_rows]

            if len(events) < 10:
                return {
                    "error": "Insufficient data for walk-forward split",
                    "total_events": len(events),
                    "min_required": 10,
                }

            # Split: first 70% train, last 30% validation
            split_idx = int(len(events) * train_ratio)
            train_events = events[:split_idx]
            val_events = events[split_idx:]

            # Look-ahead check: training data must not include future events
            # relative to the earliest validation event
            if val_events and train_events:
                last_train_time = train_events[-1]["created_at"]
                first_val_time = val_events[0]["created_at"]
                lookahead_passed = last_train_time <= first_val_time
            else:
                lookahead_passed = True

            # Compute baseline (overall mean R) on validation
            val_R = [e["R"] for e in val_events]
            baseline_val_r = sum(val_R) / len(val_R) if val_R else 0.0

            train_R = [e["R"] for e in train_events]
            baseline_train_r = sum(train_R) / len(train_R) if train_R else 0.0

            # Compute adaptive weights from training data
            # Build weights from training events only
            train_groups: dict[tuple, list[dict]] = {}
            for ev in train_events:
                key = (ev["strategy"], ev["regime"], ev["timeframe"])
                train_groups.setdefault(key, []).append(ev)

            all_train_R = [e["R"] for e in train_events
                          if e["outcome"] in ("hit_target", "hit_invalidation")]
            global_mean_R = sum(all_train_R) / len(all_train_R) if all_train_R else 0.0

            adaptive_weights = []
            for (strategy, regime, timeframe), group in train_groups.items():
                w = self._compute_single_weight(
                    strategy, regime, timeframe, group,
                    global_mean_R, adaptive_weights,
                )
                adaptive_weights.append(w)

            # Validate adaptive weights on validation data
            # For each validation event, find the matching weight and compute expected R
            val_weighted_R = 0.0
            val_weight_count = 0
            for ev in val_events:
                key = (ev["strategy"], ev["regime"], ev["timeframe"])
                matching = [w for w in adaptive_weights
                           if w.strategy == key[0] and w.regime == key[1]
                           and w.timeframe == key[2]]
                if matching:
                    # Use the best matching weight
                    best = max(matching, key=lambda w: w.adjusted_weight)
                    val_weighted_R += best.adjusted_weight * (1.0 if ev["outcome"] == "hit_target" else -1.0)
                    val_weight_count += 1

            adaptive_val_r = val_weighted_R / val_weight_count if val_weight_count > 0 else 0.0

            split_id = hashlib.sha256(
                f"wf_{dataset_version}_{train_events[0]['created_at']}_{val_events[0]['created_at']}".encode()
            ).hexdigest()[:16]

            result = {
                "split_id": split_id,
                "dataset_version": dataset_version,
                "train_size": len(train_events),
                "validation_size": len(val_events),
                "train_start": train_events[0]["created_at"] if train_events else "",
                "train_end": train_events[-1]["created_at"] if train_events else "",
                "validation_start": val_events[0]["created_at"] if val_events else "",
                "validation_end": val_events[-1]["created_at"] if val_events else "",
                "lookahead_check_passed": lookahead_passed,
                "baseline_train_r": round(baseline_train_r, 4),
                "baseline_val_r": round(baseline_val_r, 4),
                "adaptive_train_r": round(sum(train_R) / len(train_R), 4) if train_R else 0.0,
                "adaptive_val_r": round(adaptive_val_r, 4),
                "adaptive_weights_count": len(adaptive_weights),
            }

            # Save split to DB
            conn.execute("""
                INSERT INTO brain_walkforward_splits
                    (split_id, weight_version, train_start, train_end,
                     validation_start, validation_end, train_size, validation_size,
                     baseline_train_r, baseline_val_r,
                     adaptive_train_r, adaptive_val_r,
                     lookahead_check_passed)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                split_id, "weight_v1",
                result["train_start"], result["train_end"],
                result["validation_start"], result["validation_end"],
                result["train_size"], result["validation_size"],
                result["baseline_train_r"], result["baseline_val_r"],
                result["adaptive_train_r"], result["adaptive_val_r"],
                1 if lookahead_passed else 0,
            ))
            conn.commit()

            return result
        finally:
            conn.close()


# =========================================================
# CLI
# =========================================================

if __name__ == "__main__":
    print("=== Brain Learning Pipeline V1 ===\n")

    # Init tables
    init_learning_tables()
    print("✅ Learning tables initialized")

    # Create learning events from existing outcomes
    result = create_learning_events_from_outcomes(limit=500)
    print(f"📊 Learning events: {result}")

    # Compute weights
    engine = StrategyWeightEngine()
    weights = engine.compute_weights()
    print(f"\n📈 Computed {len(weights)} strategy weights")

    # Walk-forward split
    wf = engine.walk_forward_split()
    print(f"\n🔄 Walk-forward split: {wf}")

    # Sync claims
    sync = sync_claims_from_events()
    print(f"\n🧠 Claims synced: {sync}")