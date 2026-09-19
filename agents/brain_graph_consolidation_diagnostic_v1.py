# -*- coding: utf-8 -*-
"""
MarketHQ Brain Graph Consolidation Diagnostic V1
-------------------------------------------------
PRATİK / SALT OKUNUR graph kalite teşhisi.

Amaç:
    - orphan node'ları sınıflandır
    - ilişkisiz node'ları bul
    - temporal edge adaylarını ölç
    - graph yoğunluğunu özetle
    - duplicate relation kontrolü
    - güvenli consolidation için net aday listesi üret

BU DOSYA VERİ DEĞİŞTİRMEZ:
    INSERT  yok
    UPDATE  yok
    DELETE  yok

Değiştirilmeyenler:
    brain_nodes
    brain_edges
    brain_evidence
    brain_claims
    brain_learning_events
    knowledge_items
    experiments/results
    learned_rules
    research queue

Çalıştırma:
    python agents/brain_graph_consolidation_diagnostic_v1.py
"""

from __future__ import annotations

import json
import sqlite3
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DB_PATH = PROJECT_ROOT / "market_hq.db"


def norm(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def si(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def sf(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def parse_json(raw: Any) -> dict[str, Any]:
    try:
        obj = json.loads(norm(raw) or "{}")
        return obj if isinstance(obj, dict) else {}
    except (json.JSONDecodeError, TypeError):
        return {}


def open_db() -> sqlite3.Connection:
    if not DB_PATH.exists():
        raise FileNotFoundError(
            f"Database bulunamadı: {DB_PATH}"
        )

    conn = sqlite3.connect(
        str(DB_PATH),
        timeout=60,
    )
    conn.row_factory = sqlite3.Row
    conn.execute(
        "PRAGMA busy_timeout = 60000"
    )
    return conn


def table_exists(
    conn: sqlite3.Connection,
    table: str,
) -> bool:
    return (
        conn.execute(
            """
            SELECT 1
            FROM sqlite_master
            WHERE type='table'
              AND name=?
            LIMIT 1
            """,
            (table,),
        ).fetchone()
        is not None
    )


def columns(
    conn: sqlite3.Connection,
    table: str,
) -> set[str]:
    if not table_exists(
        conn,
        table,
    ):
        return set()

    return {
        norm(row["name"])
        for row in conn.execute(
            f"PRAGMA table_info({table})"
        ).fetchall()
    }


def node_type_counts(
    conn: sqlite3.Connection,
) -> list[tuple[str, int]]:
    rows = conn.execute(
        """
        SELECT
            COALESCE(node_type, '<EMPTY>') AS node_type,
            COUNT(*) AS n
        FROM brain_nodes
        GROUP BY COALESCE(node_type, '<EMPTY>')
        ORDER BY n DESC, node_type ASC
        """
    ).fetchall()

    return [
        (
            norm(row["node_type"]),
            si(row["n"]),
        )
        for row in rows
    ]


def degree_map(
    conn: sqlite3.Connection,
) -> dict[int, int]:
    degrees: dict[int, int] = defaultdict(int)

    outgoing = conn.execute(
        """
        SELECT source_node_id AS node_id, COUNT(*) AS n
        FROM brain_edges
        GROUP BY source_node_id
        """
    ).fetchall()

    incoming = conn.execute(
        """
        SELECT target_node_id AS node_id, COUNT(*) AS n
        FROM brain_edges
        GROUP BY target_node_id
        """
    ).fetchall()

    for row in outgoing:
        degrees[
            si(row["node_id"])
        ] += si(row["n"])

    for row in incoming:
        degrees[
            si(row["node_id"])
        ] += si(row["n"])

    return degrees


def evidence_linked_nodes(
    conn: sqlite3.Connection,
) -> set[int]:
    linked: set[int] = set()

    if table_exists(
        conn,
        "brain_node_evidence",
    ):
        rows = conn.execute(
            """
            SELECT DISTINCT node_id
            FROM brain_node_evidence
            """
        ).fetchall()

        linked.update(
            si(row["node_id"])
            for row in rows
        )

    return linked


def classify_node(
    node: sqlite3.Row,
    degree: int,
    evidenced: bool,
) -> str:
    node_type = norm(
        node["node_type"]
    ).lower()

    metadata = parse_json(
        node["metadata_json"]
    )

    status = norm(
        node["status"]
    ).lower()

    if degree > 0:
        return "CONNECTED"

    if evidenced:
        return "ORPHAN_BUT_EVIDENCED"

    if node_type in {
        "experiment_result",
        "experiment",
        "learned_rule",
        "method",
        "concept",
        "knowledge",
        "symbol",
        "research_result",
        "observation",
        "claim",
    }:
        return "ORPHAN_DOMAIN_NODE"

    if metadata or status:
        return "ORPHAN_METADATA_NODE"

    return "ORPHAN_EMPTY_NODE"


def temporal_profile(
    conn: sqlite3.Connection,
) -> dict[str, int]:
    cols = columns(
        conn,
        "brain_edges",
    )

    if not cols:
        return {
            "total_edges": 0,
            "temporal_edges": 0,
            "edges_with_observed_at": 0,
            "edges_with_valid_from": 0,
            "edges_with_valid_to": 0,
        }

    total = si(
        conn.execute(
            "SELECT COUNT(*) AS n FROM brain_edges"
        ).fetchone()["n"]
    )

    observed_at = 0
    valid_from = 0
    valid_to = 0

    if "observed_at" in cols:
        observed_at = si(
            conn.execute(
                """
                SELECT COUNT(*)
                FROM brain_edges
                WHERE observed_at IS NOT NULL
                  AND TRIM(observed_at) <> ''
                """
            ).fetchone()[0]
        )

    if "valid_from" in cols:
        valid_from = si(
            conn.execute(
                """
                SELECT COUNT(*)
                FROM brain_edges
                WHERE valid_from IS NOT NULL
                  AND TRIM(valid_from) <> ''
                """
            ).fetchone()[0]
        )

    if "valid_to" in cols:
        valid_to = si(
            conn.execute(
                """
                SELECT COUNT(*)
                FROM brain_edges
                WHERE valid_to IS NOT NULL
                  AND TRIM(valid_to) <> ''
                """
            ).fetchone()[0]
        )

    return {
        "total_edges": total,
        "temporal_edges": max(
            observed_at,
            valid_from,
            valid_to,
        ),
        "edges_with_observed_at": observed_at,
        "edges_with_valid_from": valid_from,
        "edges_with_valid_to": valid_to,
    }


def duplicate_relation_groups(
    conn: sqlite3.Connection,
) -> list[sqlite3.Row]:
    return list(
        conn.execute(
            """
            SELECT
                source_node_id,
                relation,
                target_node_id,
                COUNT(*) AS n
            FROM brain_edges
            GROUP BY
                source_node_id,
                relation,
                target_node_id
            HAVING COUNT(*) > 1
            ORDER BY n DESC
            """
        ).fetchall()
    )


def relation_counts(
    conn: sqlite3.Connection,
) -> list[tuple[str, int]]:
    rows = conn.execute(
        """
        SELECT
            COALESCE(relation, '<EMPTY>') AS relation,
            COUNT(*) AS n
        FROM brain_edges
        GROUP BY COALESCE(relation, '<EMPTY>')
        ORDER BY n DESC, relation ASC
        LIMIT 20
        """
    ).fetchall()

    return [
        (
            norm(row["relation"]),
            si(row["n"]),
        )
        for row in rows
    ]


def temporal_candidate_counts(
    conn: sqlite3.Connection,
) -> dict[str, int]:
    """
    Mevcut graph'taki ilişkiler üzerinden aday zaman bağlantılarını ölçer.
    Yeni edge üretmez.

    Özellikle:
        experiment -> result
        knowledge/research -> observation
        learned_rule -> validation/research
    gibi zincirlerde node metadata'sında tarih varsa aday sayısını verir.
    """

    counts = {
        "experiment_nodes_with_date": 0,
        "result_nodes_with_date": 0,
        "research_knowledge_nodes_with_date": 0,
        "validation_related_nodes_with_date": 0,
    }

    rows = conn.execute(
        """
        SELECT
            id,
            node_type,
            first_seen_at,
            last_seen_at,
            metadata_json
        FROM brain_nodes
        WHERE
            first_seen_at IS NOT NULL
            OR last_seen_at IS NOT NULL
            OR metadata_json IS NOT NULL
        """
    ).fetchall()

    for row in rows:
        node_type = norm(
            row["node_type"]
        ).lower()

        meta = parse_json(
            row["metadata_json"]
        )

        has_date = bool(
            norm(
                row["first_seen_at"]
            )
            or norm(
                row["last_seen_at"]
            )
            or norm(
                meta.get("observation_date")
            )
            or norm(
                meta.get("created_at")
            )
            or norm(
                meta.get("date")
            )
        )

        if not has_date:
            continue

        if node_type == "experiment":
            counts[
                "experiment_nodes_with_date"
            ] += 1

        elif node_type == "experiment_result":
            counts[
                "result_nodes_with_date"
            ] += 1

        elif node_type in {
            "knowledge",
            "research_result",
        }:
            counts[
                "research_knowledge_nodes_with_date"
            ] += 1

        elif node_type in {
            "learned_rule",
            "validation",
            "claim",
        }:
            counts[
                "validation_related_nodes_with_date"
            ] += 1

    return counts


def main() -> None:
    conn = open_db()

    try:
        required = (
            "brain_nodes",
            "brain_edges",
        )

        for table in required:
            if not table_exists(
                conn,
                table,
            ):
                raise RuntimeError(
                    f"Gerekli tablo yok: {table}"
                )

        print("=" * 78)
        print(
            "MARKETHQ BRAIN GRAPH CONSOLIDATION DIAGNOSTIC V1"
        )
        print("=" * 78)
        print()
        print(
            f"Database : {DB_PATH}"
        )
        print(
            "Mode     : READ ONLY"
        )

        node_count = si(
            conn.execute(
                "SELECT COUNT(*) FROM brain_nodes"
            ).fetchone()[0]
        )

        edge_count = si(
            conn.execute(
                "SELECT COUNT(*) FROM brain_edges"
            ).fetchone()[0]
        )

        degrees = degree_map(
            conn
        )

        evidenced = evidence_linked_nodes(
            conn
        )

        nodes = conn.execute(
            """
            SELECT
                id,
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
            FROM brain_nodes
            ORDER BY id ASC
            """
        ).fetchall()

        orphan_rows = []

        classification_counts = Counter()

        for node in nodes:
            node_id = si(
                node["id"]
            )

            degree = degrees.get(
                node_id,
                0,
            )

            classification = classify_node(
                node,
                degree,
                node_id in evidenced,
            )

            classification_counts[
                classification
            ] += 1

            if classification != "CONNECTED":
                orphan_rows.append(
                    (
                        node,
                        degree,
                        classification,
                    )
                )

        temporal = temporal_profile(
            conn
        )

        duplicates = duplicate_relation_groups(
            conn
        )

        rel_counts = relation_counts(
            conn
        )

        temporal_candidates = temporal_candidate_counts(
            conn
        )

        print()
        print("GRAPH PROFILE")
        print("-" * 78)
        print(
            f"nodes                                  {node_count}"
        )
        print(
            f"edges                                  {edge_count}"
        )
        print(
            f"edges/nodes                             "
            f"{(edge_count / node_count if node_count else 0):.2f}"
        )
        print(
            f"evidenced_nodes                         {len(evidenced)}"
        )
        print(
            f"connected_nodes                         "
            f"{node_count - classification_counts.get('ORPHAN_EMPTY_NODE', 0) - classification_counts.get('ORPHAN_DOMAIN_NODE', 0) - classification_counts.get('ORPHAN_METADATA_NODE', 0) - classification_counts.get('ORPHAN_BUT_EVIDENCED', 0)}"
        )

        print()
        print("ORPHAN CLASSIFICATION")
        print("-" * 78)

        for label, count in classification_counts.most_common():
            print(
                f"{label:35s} {count}"
            )

        print()
        print("NODE TYPES")
        print("-" * 78)

        for label, count in node_type_counts(
            conn
        ):
            print(
                f"{label:35s} {count}"
            )

        print()
        print("TOP RELATIONS")
        print("-" * 78)

        for relation, count in rel_counts:
            print(
                f"{relation:35s} {count}"
            )

        print()
        print("TEMPORAL PROFILE")
        print("-" * 78)
        print(
            f"total_edges                            "
            f"{temporal['total_edges']}"
        )
        print(
            f"edges_with_observed_at                  "
            f"{temporal['edges_with_observed_at']}"
        )
        print(
            f"edges_with_valid_from                   "
            f"{temporal['edges_with_valid_from']}"
        )
        print(
            f"edges_with_valid_to                     "
            f"{temporal['edges_with_valid_to']}"
        )
        print(
            f"temporal_edges                          "
            f"{temporal['temporal_edges']}"
        )

        print()
        print("TEMPORAL CANDIDATE SIGNALS")
        print("-" * 78)

        for key, count in temporal_candidates.items():
            print(
                f"{key:40s} {count}"
            )

        print()
        print("DUPLICATE RELATION GROUPS")
        print("-" * 78)
        print(
            f"duplicate_relation_groups              "
            f"{len(duplicates)}"
        )

        if duplicates:
            for row in duplicates[:10]:
                print(
                    f"source={si(row['source_node_id'])} | "
                    f"relation={norm(row['relation'])} | "
                    f"target={si(row['target_node_id'])} | "
                    f"count={si(row['n'])}"
                )
        else:
            print(
                "None"
            )

        print()
        print("ORPHAN NODES")
        print("-" * 78)

        if not orphan_rows:
            print(
                "No orphan nodes."
            )
        else:
            # Önce en riskli görünenler:
            # evidence'siz + metadata'sız domain node'lar.
            orphan_rows.sort(
                key=lambda item: (
                    0
                    if item[2]
                    == "ORPHAN_EMPTY_NODE"
                    else (
                        1
                        if item[2]
                        == "ORPHAN_DOMAIN_NODE"
                        else 2
                    ),
                    si(item[0]["id"]),
                )
            )

            for node, degree, classification in orphan_rows[:40]:
                print(
                    f"id={si(node['id'])} | "
                    f"type={norm(node['node_type'])} | "
                    f"class={classification} | "
                    f"degree={degree} | "
                    f"confidence={sf(node['confidence']):.3f}"
                )
                print(
                    "  key="
                    + norm(
                        node["node_key"]
                    )
                )
                print(
                    "  name="
                    + norm(
                        node["canonical_name"]
                    )
                )
                print(
                    "  status="
                    + norm(
                        node["status"]
                    )
                )

        print()
        print("SAFE CONSOLIDATION CANDIDATES")
        print("-" * 78)

        safe_candidates = [
            (
                node,
                classification,
            )
            for (
                node,
                _degree,
                classification,
            ) in orphan_rows
            if classification
            in {
                "ORPHAN_EMPTY_NODE",
                "ORPHAN_METADATA_NODE",
            }
        ]

        print(
            f"candidate_count                       "
            f"{len(safe_candidates)}"
        )

        for node, classification in safe_candidates[:25]:
            print(
                f"id={si(node['id'])} | "
                f"type={norm(node['node_type'])} | "
                f"class={classification} | "
                f"name={norm(node['canonical_name'])}"
            )

        print()
        print("DIAGNOSTIC CONCLUSION")
        print("-" * 78)

        print(
            f"orphan_total                          {len(orphan_rows)}"
        )

        print(
            f"duplicate_groups                      {len(duplicates)}"
        )

        temporal_ratio = (
            temporal["temporal_edges"]
            / temporal["total_edges"]
            if temporal["total_edges"]
            else 0.0
        )

        print(
            "temporal_edge_ratio                   "
            f"{temporal_ratio:.2%}"
        )

        if len(duplicates) == 0:
            print(
                "Duplicate relation yapısı temiz."
            )

        if len(orphan_rows) > 0:
            print(
                "Orphan node'lar var; önce sınıflandırmak doğru."
            )

        if temporal["temporal_edges"] == 0:
            print(
                "Temporal edge henüz yok; metadata üzerinden "
                "zaman adayları mevcut."
            )

        print()
        print(
            "NO DATA WAS MODIFIED"
        )
        print("=" * 78)

    finally:
        conn.close()


if __name__ == "__main__":
    main()
