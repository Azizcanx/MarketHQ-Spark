from __future__ import annotations

import hashlib
import json
import re
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


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def clean_text(value: Any) -> str:
    return str(value or "").strip()


def json_load(value: Any, fallback: Any) -> Any:
    if value is None:
        return fallback

    if isinstance(value, (list, dict)):
        return value

    try:
        return json.loads(str(value))
    except (TypeError, ValueError, json.JSONDecodeError):
        return fallback


def content_hash(text: str) -> str:
    return hashlib.sha256(
        text.encode("utf-8")
    ).hexdigest()


def connect() -> sqlite3.Connection:
    # V3'te journal mode değiştirmiyoruz.
    # Böylece importer DB'yi WAL'e çevirmeye çalışırken yeni bir lock üretmez.
    conn = sqlite3.connect(
        DB_PATH,
        timeout=10.0,
        isolation_level=None,
    )
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 10000")
    conn.execute("PRAGMA locking_mode = NORMAL")
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


def column_value(
    row: sqlite3.Row,
    columns: set[str],
    name: str,
    default: Any = None,
) -> Any:
    if name not in columns:
        return default

    return row[name]


def get_node_id(
    conn: sqlite3.Connection,
    node_key: str,
) -> int | None:
    row = conn.execute(
        """
        SELECT id
        FROM brain_nodes
        WHERE node_key = ?
        LIMIT 1
        """,
        (node_key,),
    ).fetchone()

    return int(row["id"]) if row else None


def upsert_node(
    conn: sqlite3.Connection,
    *,
    node_key: str,
    node_type: str,
    canonical_name: str,
    summary: str | None = None,
    confidence: float | None = None,
    first_seen_at: str | None = None,
    last_seen_at: str | None = None,
) -> int:
    now = utc_now()

    existing = conn.execute(
        """
        SELECT id
        FROM brain_nodes
        WHERE node_key = ?
        LIMIT 1
        """,
        (node_key,),
    ).fetchone()

    if existing:
        node_id = int(existing["id"])

        conn.execute(
            """
            UPDATE brain_nodes
            SET node_type = ?,
                canonical_name = ?,
                summary = COALESCE(?, summary),
                confidence = COALESCE(?, confidence),
                first_seen_at = COALESCE(?, first_seen_at),
                last_seen_at = COALESCE(?, last_seen_at),
                updated_at = ?
            WHERE id = ?
            """,
            (
                node_type,
                canonical_name,
                summary,
                confidence,
                first_seen_at,
                last_seen_at,
                now,
                node_id,
            ),
        )

        return node_id

    cursor = conn.execute(
        """
        INSERT INTO brain_nodes (
            node_key,
            node_type,
            canonical_name,
            summary,
            confidence,
            status,
            first_seen_at,
            last_seen_at,
            metadata_json,
            created_at,
            updated_at
        )
        VALUES (?, ?, ?, ?, ?, 'active', ?, ?, '{}', ?, ?)
        """,
        (
            node_key,
            node_type,
            canonical_name,
            summary,
            confidence,
            first_seen_at,
            last_seen_at,
            now,
            now,
        ),
    )

    return int(cursor.lastrowid)


def upsert_episode(
    conn: sqlite3.Connection,
    *,
    episode_type: str,
    source_table: str,
    source_id: int | None,
    source_key: str | None,
    title: str | None,
    content: str | None,
    observed_at: str | None,
    source_uri: str | None = None,
    author: str | None = None,
) -> int:
    text = clean_text(content)
    digest = content_hash(text) if text else None

    existing = conn.execute(
        """
        SELECT id
        FROM brain_episodes
        WHERE source_table IS ?
          AND source_id IS ?
          AND episode_type = ?
        ORDER BY id DESC
        LIMIT 1
        """,
        (
            source_table,
            source_id,
            episode_type,
        ),
    ).fetchone()

    if existing:
        episode_id = int(existing["id"])

        conn.execute(
            """
            UPDATE brain_episodes
            SET title = COALESCE(?, title),
                content = COALESCE(?, content),
                content_hash = COALESCE(?, content_hash),
                observed_at = COALESCE(?, observed_at),
                source_uri = COALESCE(?, source_uri),
                author = COALESCE(?, author)
            WHERE id = ?
            """,
            (
                title,
                text or None,
                digest,
                observed_at,
                source_uri,
                author,
                episode_id,
            ),
        )

        return episode_id

    cursor = conn.execute(
        """
        INSERT INTO brain_episodes (
            episode_type,
            source_table,
            source_id,
            source_key,
            title,
            content,
            content_hash,
            observed_at,
            ingested_at,
            source_uri,
            author,
            metadata_json
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, '{}')
        """,
        (
            episode_type,
            source_table,
            source_id,
            source_key,
            title,
            text or None,
            digest,
            observed_at,
            utc_now(),
            source_uri,
            author,
        ),
    )

    return int(cursor.lastrowid)


def upsert_evidence(
    conn: sqlite3.Connection,
    *,
    evidence_type: str,
    source_table: str,
    source_id: int | None,
    polarity: str,
    strength: float | None,
    observation_date: str | None,
    note: str | None,
    content: str | None,
) -> int:
    text = clean_text(content or note)

    digest = content_hash(
        f"{source_table}|{source_id}|{evidence_type}|{polarity}|{text}"
    )

    existing = conn.execute(
        """
        SELECT id
        FROM brain_evidence
        WHERE content_hash = ?
        LIMIT 1
        """,
        (digest,),
    ).fetchone()

    if existing:
        return int(existing["id"])

    cursor = conn.execute(
        """
        INSERT INTO brain_evidence (
            evidence_type,
            source_table,
            source_id,
            polarity,
            strength,
            observation_date,
            extracted_at,
            content_hash,
            note,
            metadata_json
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, '{}')
        """,
        (
            evidence_type,
            source_table,
            source_id,
            polarity,
            strength,
            observation_date,
            utc_now(),
            digest,
            note,
        ),
    )

    return int(cursor.lastrowid)


def link_node_evidence(
    conn: sqlite3.Connection,
    node_id: int,
    evidence_id: int,
    role: str = "supports",
    weight: float | None = None,
) -> None:
    conn.execute(
        """
        INSERT OR IGNORE INTO brain_node_evidence (
            node_id,
            evidence_id,
            role,
            weight,
            created_at
        )
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            node_id,
            evidence_id,
            role,
            weight,
            utc_now(),
        ),
    )


def link_edge_evidence(
    conn: sqlite3.Connection,
    edge_id: int,
    evidence_id: int,
    role: str = "supports",
    weight: float | None = None,
) -> None:
    conn.execute(
        """
        INSERT OR IGNORE INTO brain_edge_evidence (
            edge_id,
            evidence_id,
            role,
            weight,
            created_at
        )
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            edge_id,
            evidence_id,
            role,
            weight,
            utc_now(),
        ),
    )


def upsert_edge(
    conn: sqlite3.Connection,
    *,
    source_node_id: int,
    relation: str,
    target_node_id: int,
    confidence: float | None = None,
    valid_from: str | None = None,
    valid_to: str | None = None,
    observed_at: str | None = None,
) -> int:
    existing = conn.execute(
        """
        SELECT id
        FROM brain_edges
        WHERE source_node_id = ?
          AND relation = ?
          AND target_node_id = ?
          AND COALESCE(valid_from, '') = COALESCE(?, '')
          AND COALESCE(valid_to, '') = COALESCE(?, '')
        ORDER BY id DESC
        LIMIT 1
        """,
        (
            source_node_id,
            relation,
            target_node_id,
            valid_from,
            valid_to,
        ),
    ).fetchone()

    if existing:
        edge_id = int(existing["id"])

        conn.execute(
            """
            UPDATE brain_edges
            SET confidence = COALESCE(?, confidence),
                observed_at = COALESCE(?, observed_at),
                updated_at = ?
            WHERE id = ?
            """,
            (
                confidence,
                observed_at,
                utc_now(),
                edge_id,
            ),
        )

        return edge_id

    cursor = conn.execute(
        """
        INSERT INTO brain_edges (
            source_node_id,
            relation,
            target_node_id,
            confidence,
            valid_from,
            valid_to,
            observed_at,
            status,
            metadata_json,
            created_at,
            updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, 'active', '{}', ?, ?)
        """,
        (
            source_node_id,
            relation,
            target_node_id,
            confidence,
            valid_from,
            valid_to,
            observed_at,
            utc_now(),
            utc_now(),
        ),
    )

    return int(cursor.lastrowid)


def create_claim(
    conn: sqlite3.Connection,
    *,
    claim_key: str,
    subject_node_id: int | None,
    predicate: str,
    object_node_id: int | None,
    claim_text: str,
    claim_type: str,
    confidence: float | None,
) -> int:
    existing = conn.execute(
        """
        SELECT id
        FROM brain_claims
        WHERE claim_key = ?
        LIMIT 1
        """,
        (claim_key,),
    ).fetchone()

    if existing:
        claim_id = int(existing["id"])

        conn.execute(
            """
            UPDATE brain_claims
            SET claim_text = ?,
                confidence = COALESCE(?, confidence),
                updated_at = ?
            WHERE id = ?
            """,
            (
                claim_text,
                confidence,
                utc_now(),
                claim_id,
            ),
        )

        return claim_id

    cursor = conn.execute(
        """
        INSERT INTO brain_claims (
            claim_key,
            subject_node_id,
            predicate,
            object_node_id,
            claim_text,
            claim_type,
            status,
            confidence,
            valid_from,
            valid_to,
            created_at,
            updated_at,
            metadata_json
        )
        VALUES (?, ?, ?, ?, ?, ?, 'active', ?, NULL, NULL, ?, ?, '{}')
        """,
        (
            claim_key,
            subject_node_id,
            predicate,
            object_node_id,
            claim_text,
            claim_type,
            confidence,
            utc_now(),
            utc_now(),
        ),
    )

    return int(cursor.lastrowid)


def link_claim_evidence(
    conn: sqlite3.Connection,
    claim_id: int,
    evidence_id: int,
    role: str = "supports",
    weight: float | None = None,
) -> None:
    conn.execute(
        """
        INSERT OR IGNORE INTO brain_claim_evidence (
            claim_id,
            evidence_id,
            role,
            weight,
            created_at
        )
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            claim_id,
            evidence_id,
            role,
            weight,
            utc_now(),
        ),
    )


def link_brain_learning_event(
    conn: sqlite3.Connection,
    *,
    event_type: str,
    experiment_id: int | None = None,
    experiment_result_id: int | None = None,
    learned_rule_id: int | None = None,
    source_claim_id: int | None = None,
    created_node_id: int | None = None,
    created_edge_id: int | None = None,
    score: float | None = None,
    decision: str | None = None,
) -> None:
    # Idempotency key built from source identifiers.
    digest = "|".join(
        [
            event_type,
            str(experiment_id or ""),
            str(experiment_result_id or ""),
            str(learned_rule_id or ""),
            str(source_claim_id or ""),
            str(created_node_id or ""),
            str(created_edge_id or ""),
        ]
    )

    exists = conn.execute(
        """
        SELECT 1
        FROM brain_learning_events
        WHERE metadata_json LIKE ?
        LIMIT 1
        """,
        (f'%\"source_key\":\"{digest}\"%',),
    ).fetchone()

    if exists:
        return

    metadata = json.dumps(
        {"source_key": digest},
        ensure_ascii=False,
    )

    conn.execute(
        """
        INSERT INTO brain_learning_events (
            event_type,
            experiment_id,
            experiment_result_id,
            learned_rule_id,
            source_claim_id,
            created_node_id,
            created_edge_id,
            score,
            decision,
            created_at,
            metadata_json
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            event_type,
            experiment_id,
            experiment_result_id,
            learned_rule_id,
            source_claim_id,
            created_node_id,
            created_edge_id,
            score,
            decision,
            utc_now(),
            metadata,
        ),
    )


def safe_float(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def import_knowledge(
    conn: sqlite3.Connection,
) -> dict[str, int]:
    if not table_exists(conn, "knowledge_items"):
        return {
            "knowledge_items": 0,
            "nodes": 0,
            "episodes": 0,
            "evidence": 0,
            "claims": 0,
            "edges": 0,
        }

    columns = table_columns(conn, "knowledge_items")
    rows = conn.execute(
        "SELECT * FROM knowledge_items ORDER BY id ASC"
    ).fetchall()

    counts = {
        "knowledge_items": 0,
        "nodes": 0,
        "episodes": 0,
        "evidence": 0,
        "claims": 0,
        "edges": 0,
    }

    for row in rows:
        knowledge_id = int(row["id"])

        title = clean_text(
            column_value(
                row,
                columns,
                "title",
            )
        ) or f"Knowledge #{knowledge_id}"

        content = clean_text(
            column_value(
                row,
                columns,
                "content",
            )
        )

        summary = clean_text(
            column_value(
                row,
                columns,
                "summary",
            )
        )

        method = clean_text(
            column_value(
                row,
                columns,
                "method",
            )
            or column_value(
                row,
                columns,
                "method_name",
            )
        )

        item_type = clean_text(
            column_value(
                row,
                columns,
                "item_type",
            )
        ).lower() or "knowledge"

        confidence = safe_float(
            column_value(
                row,
                columns,
                "confidence",
            )
        )

        source_id = column_value(
            row,
            columns,
            "source_id",
        )

        created_at = clean_text(
            column_value(
                row,
                columns,
                "created_at",
            )
        ) or utc_now()

        node_type = "knowledge"

        if item_type in {
            "method",
            "strategy",
            "algorithm",
        } or method:
            node_type = "method"

        node_name = method or title

        node_key = (
            "method:"
            if node_type == "method"
            else "knowledge:"
        ) + re.sub(
            r"\s+",
            " ",
            node_name.strip().lower(),
        )

        method_node_id = upsert_node(
            conn,
            node_key=node_key,
            node_type=node_type,
            canonical_name=node_name,
            summary=summary or content[:500] or None,
            confidence=confidence,
            first_seen_at=created_at,
            last_seen_at=created_at,
        )

        counts["nodes"] += 1

        episode_id = upsert_episode(
            conn,
            episode_type="knowledge_item",
            source_table="knowledge_items",
            source_id=knowledge_id,
            source_key=str(knowledge_id),
            title=title,
            content=content or summary,
            observed_at=created_at,
        )

        _ = episode_id
        counts["episodes"] += 1

        evidence_id = upsert_evidence(
            conn,
            evidence_type="knowledge_item",
            source_table="knowledge_items",
            source_id=knowledge_id,
            polarity="supports",
            strength=confidence,
            observation_date=created_at,
            note=summary or title,
            content=content,
        )

        link_node_evidence(
            conn,
            method_node_id,
            evidence_id,
            weight=confidence,
        )

        counts["evidence"] += 1

        claim_text = summary or content

        if claim_text:
            claim_key = (
                f"knowledge:{knowledge_id}:claim"
            )

            claim_id = create_claim(
                conn,
                claim_key=claim_key,
                subject_node_id=method_node_id,
                predicate="has_knowledge",
                object_node_id=None,
                claim_text=claim_text[:4000],
                claim_type="fact"
                if confidence is not None and confidence >= 0.8
                else "observation",
                confidence=confidence,
            )

            link_claim_evidence(
                conn,
                claim_id,
                evidence_id,
                weight=confidence,
            )

            counts["claims"] += 1

        symbols = json_load(
            column_value(
                row,
                columns,
                "symbols_json",
            ),
            [],
        )

        if isinstance(symbols, list):
            for symbol in symbols:
                symbol_name = clean_text(symbol)

                if not symbol_name:
                    continue

                symbol_node_id = upsert_node(
                    conn,
                    node_key=f"symbol:{symbol_name.lower()}",
                    node_type="symbol",
                    canonical_name=symbol_name,
                    summary=None,
                    confidence=1.0,
                    first_seen_at=created_at,
                    last_seen_at=created_at,
                )

                edge_id = upsert_edge(
                    conn,
                    source_node_id=method_node_id,
                    relation="APPLIES_TO",
                    target_node_id=symbol_node_id,
                    confidence=confidence,
                    observed_at=created_at,
                )

                link_edge_evidence(
                    conn,
                    edge_id,
                    evidence_id,
                    weight=confidence,
                )

                counts["edges"] += 1

        tags = json_load(
            column_value(
                row,
                columns,
                "tags_json",
            ),
            [],
        )

        if isinstance(tags, list):
            for tag in tags:
                tag_name = clean_text(tag)

                if not tag_name:
                    continue

                tag_node_id = upsert_node(
                    conn,
                    node_key=f"concept:{tag_name.lower()}",
                    node_type="concept",
                    canonical_name=tag_name,
                    summary=None,
                    confidence=1.0,
                    first_seen_at=created_at,
                    last_seen_at=created_at,
                )

                edge_id = upsert_edge(
                    conn,
                    source_node_id=method_node_id,
                    relation="TAGGED_AS",
                    target_node_id=tag_node_id,
                    confidence=confidence,
                    observed_at=created_at,
                )

                link_edge_evidence(
                    conn,
                    edge_id,
                    evidence_id,
                    weight=confidence,
                )

                counts["edges"] += 1

        counts["knowledge_items"] += 1

    return counts


def import_learning(
    conn: sqlite3.Connection,
) -> dict[str, int]:
    counts = {
        "experiments": 0,
        "results": 0,
        "rules": 0,
        "learning_events": 0,
        "nodes": 0,
        "edges": 0,
        "evidence": 0,
        "claims": 0,
    }

    experiment_rows: list[sqlite3.Row] = []

    if table_exists(conn, "learning_experiments"):
        experiment_rows = conn.execute(
            "SELECT * FROM learning_experiments ORDER BY id ASC"
        ).fetchall()

    experiment_columns = table_columns(
        conn,
        "learning_experiments",
    )

    experiment_node_ids: dict[int, int] = {}

    for row in experiment_rows:
        experiment_id = int(row["id"])

        method_name = clean_text(
            column_value(
                row,
                experiment_columns,
                "method_name",
            )
        ) or f"Experiment #{experiment_id}"

        symbol = clean_text(
            column_value(
                row,
                experiment_columns,
                "symbol",
            )
        )

        market = clean_text(
            column_value(
                row,
                experiment_columns,
                "market",
            )
        )

        timeframe = clean_text(
            column_value(
                row,
                experiment_columns,
                "timeframe",
            )
        )

        status = clean_text(
            column_value(
                row,
                experiment_columns,
                "status",
            )
        )

        start_date = clean_text(
            column_value(
                row,
                experiment_columns,
                "start_date",
            )
        )

        end_date = clean_text(
            column_value(
                row,
                experiment_columns,
                "end_date",
            )
        )

        method_node_id = upsert_node(
            conn,
            node_key=f"method:{method_name.lower()}",
            node_type="method",
            canonical_name=method_name,
            summary="Method referenced by learning experiment.",
            confidence=None,
            first_seen_at=start_date or None,
            last_seen_at=end_date or None,
        )

        experiment_node_id = upsert_node(
            conn,
            node_key=f"experiment:{experiment_id}",
            node_type="experiment",
            canonical_name=f"{method_name} / {symbol or 'UNKNOWN'}",
            summary=f"{market} {timeframe} {status}".strip(),
            confidence=None,
            first_seen_at=start_date or None,
            last_seen_at=end_date or None,
        )

        experiment_node_ids[experiment_id] = experiment_node_id

        edge_id = upsert_edge(
            conn,
            source_node_id=method_node_id,
            relation="EVALUATED_BY",
            target_node_id=experiment_node_id,
            observed_at=start_date or None,
        )

        conn.execute(
            """
            UPDATE brain_nodes
            SET metadata_json = ?
            WHERE id = ?
            """,
            (
                json.dumps(
                    {
                        "source": "learning_experiments",
                        "experiment_id": experiment_id,
                        "symbol": symbol,
                        "market": market,
                        "timeframe": timeframe,
                    },
                    ensure_ascii=False,
                ),
                experiment_node_id,
            ),
        )

        event_evidence = upsert_evidence(
            conn,
            evidence_type="experiment",
            source_table="learning_experiments",
            source_id=experiment_id,
            polarity="supports",
            strength=None,
            observation_date=start_date or None,
            note=f"{method_name} {symbol} {status}".strip(),
            content=" ".join(
                x for x in [
                    method_name,
                    symbol,
                    market,
                    timeframe,
                    status,
                    start_date,
                    end_date,
                ]
                if x
            ),
        )

        link_edge_evidence(
            conn,
            edge_id,
            event_evidence,
        )

        counts["evidence"] += 1
        counts["edges"] += 1
        counts["nodes"] += 2
        counts["experiments"] += 1

        result_rows: list[sqlite3.Row] = []

        if table_exists(conn, "experiment_results"):
            result_rows = conn.execute(
                """
                SELECT *
                FROM experiment_results
                WHERE experiment_id = ?
                ORDER BY id ASC
                """,
                (experiment_id,),
            ).fetchall()

        result_columns = table_columns(
            conn,
            "experiment_results",
        )

        for result in result_rows:
            result_id = int(result["id"])

            observation_date = clean_text(
                column_value(
                    result,
                    result_columns,
                    "observation_date",
                )
            )

            return_20d = safe_float(
                column_value(
                    result,
                    result_columns,
                    "return_20d",
                )
            )

            market_regime = clean_text(
                column_value(
                    result,
                    result_columns,
                    "market_regime",
                )
            )

            volatility_state = clean_text(
                column_value(
                    result,
                    result_columns,
                    "volatility_state",
                )
            )

            volume_state = clean_text(
                column_value(
                    result,
                    result_columns,
                    "volume_state",
                )
            )

            result_node_id = upsert_node(
                conn,
                node_key=f"experiment_result:{result_id}",
                node_type="experiment_result",
                canonical_name=f"Result #{result_id}",
                summary="Experiment observation/result.",
                confidence=None,
                first_seen_at=observation_date or None,
                last_seen_at=observation_date or None,
            )

            result_edge_id = upsert_edge(
                conn,
                source_node_id=experiment_node_id,
                relation="HAS_RESULT",
                target_node_id=result_node_id,
                confidence=None,
                observed_at=observation_date or None,
            )

            result_text = " ".join(
                x
                for x in [
                    market_regime,
                    volatility_state,
                    volume_state,
                    (
                        f"return_20d={return_20d}"
                        if return_20d is not None
                        else ""
                    ),
                ]
                if x
            )

            result_evidence_id = upsert_evidence(
                conn,
                evidence_type="experiment_result",
                source_table="experiment_results",
                source_id=result_id,
                polarity="supports"
                if return_20d is None or return_20d >= 0
                else "weakens",
                strength=None,
                observation_date=observation_date or None,
                note=result_text or f"Experiment result #{result_id}",
                content=result_text,
            )

            link_edge_evidence(
                conn,
                result_edge_id,
                result_evidence_id,
            )

            link_node_evidence(
                conn,
                result_node_id,
                result_evidence_id,
            )

            link_brain_learning_event(
                conn,
                event_type="experiment_result_imported",
                experiment_id=experiment_id,
                experiment_result_id=result_id,
                created_node_id=result_node_id,
                created_edge_id=result_edge_id,
            )

            counts["results"] += 1
            counts["nodes"] += 1
            counts["edges"] += 1
            counts["evidence"] += 1
            counts["learning_events"] += 1

    rule_rows: list[sqlite3.Row] = []

    if table_exists(conn, "learned_rules"):
        rule_rows = conn.execute(
            "SELECT * FROM learned_rules ORDER BY id ASC"
        ).fetchall()

    rule_columns = table_columns(
        conn,
        "learned_rules",
    )

    for row in rule_rows:
        rule_id = int(row["id"])

        method_name = clean_text(
            column_value(
                row,
                rule_columns,
                "method_name",
            )
        ) or f"Learned Rule #{rule_id}"

        symbol = clean_text(
            column_value(
                row,
                rule_columns,
                "symbol",
            )
        )

        timeframe = clean_text(
            column_value(
                row,
                rule_columns,
                "timeframe",
            )
        )

        condition_name = clean_text(
            column_value(
                row,
                rule_columns,
                "condition_name",
            )
        ) or "condition"

        sample_size = safe_float(
            column_value(
                row,
                rule_columns,
                "sample_size",
            )
        )

        success_rate = safe_float(
            column_value(
                row,
                rule_columns,
                "success_rate",
            )
        )

        average_return = safe_float(
            column_value(
                row,
                rule_columns,
                "average_return",
            )
        )

        confidence = safe_float(
            column_value(
                row,
                rule_columns,
                "confidence",
            )
        )

        observation = clean_text(
            column_value(
                row,
                rule_columns,
                "observation",
            )
        )

        method_node_id = upsert_node(
            conn,
            node_key=f"method:{method_name.lower()}",
            node_type="method",
            canonical_name=method_name,
            summary=None,
            confidence=None,
        )

        rule_node_id = upsert_node(
            conn,
            node_key=f"rule:{rule_id}",
            node_type="learned_rule",
            canonical_name=f"{method_name} — {condition_name}",
            summary=observation or "Imported learned rule.",
            confidence=confidence,
        )

        edge_id = upsert_edge(
            conn,
            source_node_id=method_node_id,
            relation="HAS_LEARNED_RULE",
            target_node_id=rule_node_id,
            confidence=confidence,
        )

        rule_text = " | ".join(
            x
            for x in [
                condition_name,
                symbol,
                timeframe,
                f"sample={sample_size}" if sample_size is not None else "",
                f"success={success_rate}" if success_rate is not None else "",
                f"avg_return={average_return}" if average_return is not None else "",
                observation,
            ]
            if x
        )

        evidence_id = upsert_evidence(
            conn,
            evidence_type="learned_rule",
            source_table="learned_rules",
            source_id=rule_id,
            polarity="supports",
            strength=confidence,
            observation_date=None,
            note=observation or condition_name,
            content=rule_text,
        )

        link_edge_evidence(
            conn,
            edge_id,
            evidence_id,
            weight=confidence,
        )

        claim_id = create_claim(
            conn,
            claim_key=f"rule:{rule_id}",
            subject_node_id=method_node_id,
            predicate="SUPPORTS_CONDITION",
            object_node_id=rule_node_id,
            claim_text=rule_text[:4000],
            claim_type="learned",
            confidence=confidence,
        )

        link_claim_evidence(
            conn,
            claim_id,
            evidence_id,
            weight=confidence,
        )

        link_brain_learning_event(
            conn,
            event_type="learned_rule_imported",
            learned_rule_id=rule_id,
            source_claim_id=claim_id,
            created_node_id=rule_node_id,
            created_edge_id=edge_id,
            score=confidence,
            decision="IMPORTED_AS_LEARNED_RULE",
        )

        counts["rules"] += 1
        counts["nodes"] += 2
        counts["edges"] += 1
        counts["evidence"] += 1
        counts["claims"] += 1
        counts["learning_events"] += 1

    return counts


def print_report(
    knowledge_counts: dict[str, int],
    learning_counts: dict[str, int],
) -> None:
    print()
    print("=" * 72)
    print("MARKETHQ BRAIN IMPORTER V1")
    print("=" * 72)
    print()
    print(f"Database : {DB_PATH}")
    print()
    print("KNOWLEDGE IMPORT")
    for key, value in knowledge_counts.items():
        print(f"{key:24} {value:>8}")

    print()
    print("LEARNING IMPORT")
    for key, value in learning_counts.items():
        print(f"{key:24} {value:>8}")

    print()
    print("Önemli:")
    print("- Mevcut knowledge/learning kayıtları silinmedi.")
    print("- Import idempotent tasarlandı; tekrar çalıştırılabilir.")
    print("- Öğrenilmiş kurallar Brain'e 'fact' olarak yükseltilmedi.")
    print("- Sonraki aşama: graph consolidation + contradiction + query engine.")
    print()


def main() -> None:
    print("MARKETHQ BRAIN IMPORTER V2")
    print(f"Database : {DB_PATH}")
    print("SQLite   : lock-tolerant mode")
    print()

    if not DB_PATH.exists():
        raise SystemExit(
            f"market_hq.db bulunamadı: {DB_PATH}"
        )

    conn = connect()

    try:
        print("SQLite bağlantısı açıldı.")
        print("Lock probe: BEGIN IMMEDIATE deneniyor...")

        try:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute("ROLLBACK")
            print("Lock probe: OK")
        except sqlite3.OperationalError as exc:
            if "locked" in str(exc).lower():
                raise SystemExit(
                    "Lock probe başarısız: market_hq.db başka bir işlem "
                    "tarafından yazma kilidinde tutuluyor."
                ) from exc
            raise

        print("Brain schema kontrolü başlıyor...")
        print()

        required_brain_tables = {
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
        }

        try:
            missing = [
                table
                for table in sorted(required_brain_tables)
                if not table_exists(conn, table)
            ]
        except sqlite3.OperationalError as exc:
            if "locked" in str(exc).lower():
                raise SystemExit(
                    "SQLite database hâlâ kilitli. "
                    "Önce MarketHQ Dashboard / main.py / başka çalışan "
                    "Python süreçlerini kapatıp importer'ı tekrar çalıştır."
                ) from exc
            raise

        if missing:
            raise SystemExit(
                "Brain schema eksik. Önce brain_schema_v2.py çalıştır.\n"
                "Eksik tablolar: "
                + ", ".join(missing)
            )

        print("1/2 Knowledge import başlıyor...")
        knowledge_counts = import_knowledge(conn)
        conn.commit()
        print("1/2 Knowledge import tamamlandı.")

        print("2/2 Learning import başlıyor...")
        learning_counts = import_learning(conn)
        conn.commit()
        print("2/2 Learning import tamamlandı.")

        print_report(
            knowledge_counts,
            learning_counts,
        )

    except sqlite3.OperationalError as exc:
        try:
            conn.rollback()
        except sqlite3.Error:
            pass

        if "locked" in str(exc).lower():
            raise SystemExit(
                "Import sırasında SQLite kilitlendi. "
                "Çalışan MarketHQ processlerini kapat ve tekrar dene."
            ) from exc

        raise

    finally:
        conn.close()


if __name__ == "__main__":
    main()

