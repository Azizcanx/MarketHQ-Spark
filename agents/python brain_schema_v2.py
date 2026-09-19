from __future__ import annotations

import argparse
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent


def find_project_root() -> Path:
    """
    Brain script agents/ klasörüne konulsa bile MarketHQ kökündeki
    market_hq.db dosyasını bulur.

    Arama sırası:
    1) script klasörü
    2) script klasörünün parent'ı
    3) mevcut çalışma klasörü
    4) mevcut çalışma klasörünün parent'ları
    """
    candidates = [
        SCRIPT_DIR,
        SCRIPT_DIR.parent,
        Path.cwd(),
        Path.cwd().parent,
    ]

    seen = set()

    for candidate in candidates:
        candidate = candidate.resolve()
        if candidate in seen:
            continue
        seen.add(candidate)

        db_path = candidate / "market_hq.db"
        if db_path.exists():
            return candidate

    # Dosya bulunamazsa en mantıklı varsayılan:
    # script agents/ içindeyse bir üst klasör = MarketHQ.
    if SCRIPT_DIR.name.lower() == "agents":
        return SCRIPT_DIR.parent

    return SCRIPT_DIR


BASE_DIR = find_project_root()
DB_PATH = BASE_DIR / "market_hq.db"

SCHEMA_VERSION = "brain_v1"


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
-- BRAIN NODES
-- One durable entity/concept/method/symbol/regime in the graph.
-- ============================================================
CREATE TABLE IF NOT EXISTS brain_nodes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    node_key TEXT NOT NULL UNIQUE,
    node_type TEXT NOT NULL,
    canonical_name TEXT NOT NULL,
    summary TEXT,
    confidence REAL,
    status TEXT NOT NULL DEFAULT 'active',

    first_seen_at TEXT,
    last_seen_at TEXT,

    metadata_json TEXT NOT NULL DEFAULT '{}',

    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_brain_nodes_type
    ON brain_nodes(node_type);

CREATE INDEX IF NOT EXISTS idx_brain_nodes_name
    ON brain_nodes(canonical_name);

CREATE INDEX IF NOT EXISTS idx_brain_nodes_confidence
    ON brain_nodes(confidence DESC);

-- ============================================================
-- BRAIN EDGES
-- Directed relationship between two nodes.
-- Multiple historical versions of the same relationship are
-- intentionally allowed.
-- ============================================================
CREATE TABLE IF NOT EXISTS brain_edges (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    source_node_id INTEGER NOT NULL,
    relation TEXT NOT NULL,
    target_node_id INTEGER NOT NULL,

    confidence REAL,

    valid_from TEXT,
    valid_to TEXT,

    observed_at TEXT,
    status TEXT NOT NULL DEFAULT 'active',

    metadata_json TEXT NOT NULL DEFAULT '{}',

    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,

    FOREIGN KEY (source_node_id)
        REFERENCES brain_nodes(id)
        ON DELETE CASCADE,

    FOREIGN KEY (target_node_id)
        REFERENCES brain_nodes(id)
        ON DELETE CASCADE,

    CHECK (source_node_id <> target_node_id)
);

CREATE INDEX IF NOT EXISTS idx_brain_edges_source
    ON brain_edges(source_node_id);

CREATE INDEX IF NOT EXISTS idx_brain_edges_target
    ON brain_edges(target_node_id);

CREATE INDEX IF NOT EXISTS idx_brain_edges_relation
    ON brain_edges(relation);

CREATE INDEX IF NOT EXISTS idx_brain_edges_validity
    ON brain_edges(valid_from, valid_to);

-- ============================================================
-- BRAIN EPISODES
-- Immutable-ish provenance units: a source document, a result
-- batch, an observation, an agent finding, etc.
-- ============================================================
CREATE TABLE IF NOT EXISTS brain_episodes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    episode_type TEXT NOT NULL,
    source_table TEXT,
    source_id INTEGER,
    source_key TEXT,

    title TEXT,
    content TEXT,
    content_hash TEXT,

    observed_at TEXT,
    ingested_at TEXT NOT NULL,

    source_uri TEXT,
    author TEXT,

    metadata_json TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_brain_episodes_type
    ON brain_episodes(episode_type);

CREATE INDEX IF NOT EXISTS idx_brain_episodes_source
    ON brain_episodes(source_table, source_id);

CREATE INDEX IF NOT EXISTS idx_brain_episodes_observed
    ON brain_episodes(observed_at);

CREATE INDEX IF NOT EXISTS idx_brain_episodes_hash
    ON brain_episodes(content_hash);

-- ============================================================
-- BRAIN EVIDENCE
-- A normalized proof/observation record that can support or
-- weaken claims and relationships.
-- ============================================================
CREATE TABLE IF NOT EXISTS brain_evidence (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    evidence_type TEXT NOT NULL,
    source_table TEXT,
    source_id INTEGER,

    polarity TEXT NOT NULL DEFAULT 'supports',
    strength REAL,

    observation_date TEXT,
    extracted_at TEXT NOT NULL,

    content_hash TEXT,
    note TEXT,

    metadata_json TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_brain_evidence_type
    ON brain_evidence(evidence_type);

CREATE INDEX IF NOT EXISTS idx_brain_evidence_source
    ON brain_evidence(source_table, source_id);

CREATE INDEX IF NOT EXISTS idx_brain_evidence_date
    ON brain_evidence(observation_date);

-- ============================================================
-- NODE <-> EVIDENCE
-- ============================================================
CREATE TABLE IF NOT EXISTS brain_node_evidence (
    node_id INTEGER NOT NULL,
    evidence_id INTEGER NOT NULL,

    role TEXT NOT NULL DEFAULT 'supports',
    weight REAL,

    created_at TEXT NOT NULL,

    PRIMARY KEY (node_id, evidence_id),

    FOREIGN KEY (node_id)
        REFERENCES brain_nodes(id)
        ON DELETE CASCADE,

    FOREIGN KEY (evidence_id)
        REFERENCES brain_evidence(id)
        ON DELETE CASCADE
);

-- ============================================================
-- EDGE <-> EVIDENCE
-- ============================================================
CREATE TABLE IF NOT EXISTS brain_edge_evidence (
    edge_id INTEGER NOT NULL,
    evidence_id INTEGER NOT NULL,

    role TEXT NOT NULL DEFAULT 'supports',
    weight REAL,

    created_at TEXT NOT NULL,

    PRIMARY KEY (edge_id, evidence_id),

    FOREIGN KEY (edge_id)
        REFERENCES brain_edges(id)
        ON DELETE CASCADE,

    FOREIGN KEY (evidence_id)
        REFERENCES brain_evidence(id)
        ON DELETE CASCADE
);

-- ============================================================
-- BRAIN CLAIMS
-- Human/AI-readable knowledge units with explicit epistemic
-- state. This prevents "hypothesis" from becoming "fact".
-- ============================================================
CREATE TABLE IF NOT EXISTS brain_claims (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    claim_key TEXT NOT NULL UNIQUE,

    subject_node_id INTEGER,
    predicate TEXT NOT NULL,
    object_node_id INTEGER,

    claim_text TEXT NOT NULL,

    claim_type TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',

    confidence REAL,

    valid_from TEXT,
    valid_to TEXT,

    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,

    metadata_json TEXT NOT NULL DEFAULT '{}',

    FOREIGN KEY (subject_node_id)
        REFERENCES brain_nodes(id)
        ON DELETE SET NULL,

    FOREIGN KEY (object_node_id)
        REFERENCES brain_nodes(id)
        ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_brain_claims_type
    ON brain_claims(claim_type);

CREATE INDEX IF NOT EXISTS idx_brain_claims_status
    ON brain_claims(status);

CREATE INDEX IF NOT EXISTS idx_brain_claims_subject
    ON brain_claims(subject_node_id);

CREATE INDEX IF NOT EXISTS idx_brain_claims_object
    ON brain_claims(object_node_id);

CREATE INDEX IF NOT EXISTS idx_brain_claims_confidence
    ON brain_claims(confidence DESC);

-- ============================================================
-- CLAIM <-> EVIDENCE
-- ============================================================
CREATE TABLE IF NOT EXISTS brain_claim_evidence (
    claim_id INTEGER NOT NULL,
    evidence_id INTEGER NOT NULL,

    role TEXT NOT NULL DEFAULT 'supports',
    weight REAL,

    created_at TEXT NOT NULL,

    PRIMARY KEY (claim_id, evidence_id),

    FOREIGN KEY (claim_id)
        REFERENCES brain_claims(id)
        ON DELETE CASCADE,

    FOREIGN KEY (evidence_id)
        REFERENCES brain_evidence(id)
        ON DELETE CASCADE
);

-- ============================================================
-- BRAIN LEARNING EVENTS
-- Connects existing experiments/rules to brain updates.
-- ============================================================
CREATE TABLE IF NOT EXISTS brain_learning_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    event_type TEXT NOT NULL,

    experiment_id INTEGER,
    experiment_result_id INTEGER,
    learned_rule_id INTEGER,

    source_claim_id INTEGER,
    created_node_id INTEGER,
    created_edge_id INTEGER,

    score REAL,
    decision TEXT,

    created_at TEXT NOT NULL,

    metadata_json TEXT NOT NULL DEFAULT '{}',

    FOREIGN KEY (experiment_id)
        REFERENCES learning_experiments(id)
        ON DELETE SET NULL,

    FOREIGN KEY (experiment_result_id)
        REFERENCES experiment_results(id)
        ON DELETE SET NULL,

    FOREIGN KEY (learned_rule_id)
        REFERENCES learned_rules(id)
        ON DELETE SET NULL,

    FOREIGN KEY (source_claim_id)
        REFERENCES brain_claims(id)
        ON DELETE SET NULL,

    FOREIGN KEY (created_node_id)
        REFERENCES brain_nodes(id)
        ON DELETE SET NULL,

    FOREIGN KEY (created_edge_id)
        REFERENCES brain_edges(id)
        ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_brain_learning_events_type
    ON brain_learning_events(event_type);

CREATE INDEX IF NOT EXISTS idx_brain_learning_events_experiment
    ON brain_learning_events(experiment_id);

CREATE INDEX IF NOT EXISTS idx_brain_learning_events_rule
    ON brain_learning_events(learned_rule_id);

-- ============================================================
-- BRAIN CONTRADICTIONS
-- Stores unresolved disagreements instead of silently choosing
-- one side.
-- ============================================================
CREATE TABLE IF NOT EXISTS brain_contradictions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    topic_key TEXT NOT NULL,

    claim_a_id INTEGER,
    claim_b_id INTEGER,

    severity REAL,
    status TEXT NOT NULL DEFAULT 'open',

    detected_at TEXT NOT NULL,
    resolved_at TEXT,

    resolution_note TEXT,
    metadata_json TEXT NOT NULL DEFAULT '{}',

    FOREIGN KEY (claim_a_id)
        REFERENCES brain_claims(id)
        ON DELETE SET NULL,

    FOREIGN KEY (claim_b_id)
        REFERENCES brain_claims(id)
        ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_brain_contradictions_status
    ON brain_contradictions(status);

CREATE INDEX IF NOT EXISTS idx_brain_contradictions_topic
    ON brain_contradictions(topic_key);

-- ============================================================
-- BRAIN RESEARCH QUEUE
-- What the brain still needs to learn or validate.
-- ============================================================
CREATE TABLE IF NOT EXISTS brain_research_queue (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    question TEXT NOT NULL,
    reason TEXT,
    priority REAL NOT NULL DEFAULT 0.5,

    target_node_id INTEGER,
    target_claim_id INTEGER,

    status TEXT NOT NULL DEFAULT 'queued',

    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,

    metadata_json TEXT NOT NULL DEFAULT '{}',

    FOREIGN KEY (target_node_id)
        REFERENCES brain_nodes(id)
        ON DELETE SET NULL,

    FOREIGN KEY (target_claim_id)
        REFERENCES brain_claims(id)
        ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_brain_research_queue_status
    ON brain_research_queue(status);

CREATE INDEX IF NOT EXISTS idx_brain_research_queue_priority
    ON brain_research_queue(priority DESC);
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


def existing_migration(conn: sqlite3.Connection) -> bool:
    if not table_exists(conn, "schema_migrations"):
        return False

    row = conn.execute(
        """
        SELECT 1
        FROM schema_migrations
        WHERE name = ?
        LIMIT 1
        """,
        (SCHEMA_VERSION,),
    ).fetchone()

    return row is not None


def apply_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA_SQL)

    if not existing_migration(conn):
        conn.execute(
            """
            INSERT INTO schema_migrations (
                name,
                applied_at
            )
            VALUES (?, ?)
            """,
            (
                SCHEMA_VERSION,
                utc_now(),
            ),
        )

    conn.commit()


def inspect(conn: sqlite3.Connection) -> dict[str, int]:
    tables = [
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
    ]

    return {
        table: table_count(conn, table)
        for table in tables
    }


def print_report(
    counts: dict[str, int],
    applied: bool,
) -> None:
    print()
    print("=" * 72)
    print("MARKETHQ BRAIN SCHEMA V1")
    print("=" * 72)
    print()
    print(f"Database : {DB_PATH}")
    print(f"Schema   : {SCHEMA_VERSION}")
    print(f"Action   : {'APPLIED' if applied else 'CHECK ONLY'}")
    print()

    for table, count in counts.items():
        print(f"{table:28} {count:>6}")

    print()
    print("Mevcut veri bu sürümde otomatik taşınmadı.")
    print("Sıradaki adım: mevcut Knowledge / Experiment / Rule verisini")
    print("Brain Nodes + Claims + Evidence + Episodes katmanına bağlamak.")
    print()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create or inspect MarketHQ Brain V1 schema."
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Schema oluşturma; sadece mevcut Brain tablolarını kontrol et.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    if not DB_PATH.exists():
        raise SystemExit(
            f"market_hq.db bulunamadı: {DB_PATH}"
        )

    conn = connect()

    try:
        if args.check:
            counts = inspect(conn)
            print_report(
                counts,
                applied=False,
            )
            return

        apply_schema(conn)

        counts = inspect(conn)

        print_report(
            counts,
            applied=True,
        )

    finally:
        conn.close()


if __name__ == "__main__":
    main()
