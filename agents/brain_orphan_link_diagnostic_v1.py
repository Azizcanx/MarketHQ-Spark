# -*- coding: utf-8 -*-
"""
MarketHQ Brain Orphan Link Diagnostic V1
----------------------------------------
Amaç:
    27 orphan node'un özellikle 26 symbol + 1 concept kayıtlarının
    graph üzerinde hangi mevcut node'lara bağlanabileceğini READ ONLY
    olarak teşhis etmek.

DEĞİŞTİRMEZ:
    brain_nodes
    brain_edges
    brain_claims
    learned_rules
    observations
    experiments/results
    knowledge
    queue

Çalıştır:
    python agents/brain_orphan_link_diagnostic_v1.py
"""

from __future__ import annotations

import json
import sqlite3
from collections import Counter
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DB_PATH = PROJECT_ROOT / "market_hq.db"


def norm(v: Any) -> str:
    return "" if v is None else str(v).strip()


def si(v: Any, default: int = 0) -> int:
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


def sf(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def parse_json(v: Any) -> dict[str, Any]:
    try:
        x = json.loads(norm(v) or "{}")
        return x if isinstance(x, dict) else {}
    except (json.JSONDecodeError, TypeError):
        return {}


def open_db() -> sqlite3.Connection:
    conn = sqlite3.connect(
        str(DB_PATH),
        timeout=60,
    )
    conn.row_factory = sqlite3.Row
    conn.execute(
        "PRAGMA busy_timeout=60000"
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


def get_degrees(
    conn: sqlite3.Connection,
) -> dict[int, int]:
    degree = Counter()

    for row in conn.execute(
        """
        SELECT source_node_id AS node_id, COUNT(*) AS n
        FROM brain_edges
        GROUP BY source_node_id
        """
    ):
        degree[si(row["node_id"])] += si(row["n"])

    for row in conn.execute(
        """
        SELECT target_node_id AS node_id, COUNT(*) AS n
        FROM brain_edges
        GROUP BY target_node_id
        """
    ):
        degree[si(row["node_id"])] += si(row["n"])

    return dict(degree)


def load_orphans(
    conn: sqlite3.Connection,
) -> list[sqlite3.Row]:
    degree = get_degrees(conn)

    evidence_nodes = set()

    if table_exists(
        conn,
        "brain_node_evidence",
    ):
        evidence_nodes = {
            si(row["node_id"])
            for row in conn.execute(
                """
                SELECT DISTINCT node_id
                FROM brain_node_evidence
                """
            )
        }

    rows = conn.execute(
        """
        SELECT
            id,
            node_key,
            node_type,
            canonical_name,
            summary,
            confidence,
            status,
            metadata_json
        FROM brain_nodes
        ORDER BY id
        """
    ).fetchall()

    out = []

    for row in rows:
        node_id = si(row["id"])

        if degree.get(node_id, 0) != 0:
            continue

        if node_id in evidence_nodes:
            continue

        out.append(row)

    return out


def text_blob(
    row: sqlite3.Row,
) -> str:
    meta = parse_json(
        row["metadata_json"]
    )

    return " ".join(
        [
            norm(row["node_key"]),
            norm(row["canonical_name"]),
            norm(row["summary"]),
            norm(meta.get("symbol")),
            norm(meta.get("ticker")),
            norm(meta.get("market")),
            norm(meta.get("source")),
        ]
    ).lower()


def find_candidates(
    conn: sqlite3.Connection,
    orphan: sqlite3.Row,
) -> list[tuple[float, str, sqlite3.Row]]:
    orphan_type = norm(
        orphan["node_type"]
    )

    meta = parse_json(
        orphan["metadata_json"]
    )

    name = norm(
        orphan["canonical_name"]
    )

    symbol = (
        norm(
            meta.get("symbol")
        )
        or (
            name
            if orphan_type == "symbol"
            else ""
        )
    )

    concept_key = norm(
        orphan["node_key"]
    )

    if not symbol and concept_key.startswith(
        "result:"
    ):
        symbol = ""

    all_nodes = conn.execute(
        """
        SELECT
            id,
            node_key,
            node_type,
            canonical_name,
            summary,
            confidence,
            status,
            metadata_json
        FROM brain_nodes
        WHERE id <> ?
        """,
        (
            si(orphan["id"]),
        ),
    ).fetchall()

    candidates = []

    target = symbol.lower()

    for row in all_nodes:
        node_id = si(row["id"])

        # Sadece bağlı node'lara odaklanıyoruz.
        # Orphan -> orphan eşleşmesi istemiyoruz.
        degree_row = conn.execute(
            """
            SELECT
                (
                    SELECT COUNT(*)
                    FROM brain_edges
                    WHERE source_node_id=?
                )
                +
                (
                    SELECT COUNT(*)
                    FROM brain_edges
                    WHERE target_node_id=?
                ) AS degree
            """,
            (
                node_id,
                node_id,
            ),
        ).fetchone()

        degree = si(
            degree_row["degree"]
        )

        if degree <= 0:
            continue

        blob = text_blob(
            row
        )

        score = 0.0
        reason_parts: list[str] = []

        if symbol:
            if (
                norm(row["canonical_name"]).lower()
                == target
            ):
                score += 1.00
                reason_parts.append(
                    "canonical_name_exact"
                )

            if (
                target
                and target in blob
            ):
                score += 0.45
                reason_parts.append(
                    "symbol_in_metadata/text"
                )

        if (
            orphan_type == "concept"
            and concept_key
            and concept_key.lower() in blob
        ):
            score += 0.90
            reason_parts.append(
                "concept_key_match"
            )

        # Domain importance:
        # learned rule / experiment / result / method / knowledge / claim
        if norm(row["node_type"]) in {
            "learned_rule",
            "experiment",
            "experiment_result",
            "method",
            "knowledge",
            "claim",
        }:
            score += 0.10
            reason_parts.append(
                "domain_node"
            )

        if score > 0:
            candidates.append(
                (
                    score,
                    " + ".join(
                        reason_parts
                    ),
                    row,
                )
            )

    candidates.sort(
        key=lambda item: (
            item[0],
            sf(item[2]["confidence"]),
        ),
        reverse=True,
    )

    # İlk 12 yeterli; büyük graph dump'ını önlüyoruz.
    return candidates[:12]


def existing_relations(
    conn: sqlite3.Connection,
    node_id: int,
) -> list[sqlite3.Row]:
    return list(
        conn.execute(
            """
            SELECT
                e.id,
                e.relation,
                e.source_node_id,
                e.target_node_id,
                n.node_type,
                n.canonical_name
            FROM brain_edges e
            JOIN brain_nodes n
              ON n.id =
                CASE
                    WHEN e.source_node_id=?
                    THEN e.target_node_id
                    ELSE e.source_node_id
                END
            WHERE
                e.source_node_id=?
                OR e.target_node_id=?
            LIMIT 20
            """,
            (
                node_id,
                node_id,
                node_id,
            ),
        ).fetchall()
    )


def main() -> None:
    conn = open_db()

    try:
        for table in (
            "brain_nodes",
            "brain_edges",
        ):
            if not table_exists(
                conn,
                table,
            ):
                raise RuntimeError(
                    f"Eksik tablo: {table}"
                )

        orphans = load_orphans(
            conn
        )

        symbol_orphans = [
            row
            for row in orphans
            if norm(row["node_type"])
            == "symbol"
        ]

        concept_orphans = [
            row
            for row in orphans
            if norm(row["node_type"])
            == "concept"
        ]

        print("=" * 78)
        print(
            "MARKETHQ BRAIN ORPHAN LINK DIAGNOSTIC V1"
        )
        print("=" * 78)
        print()
        print(
            f"Database : {DB_PATH}"
        )
        print(
            "Mode     : READ ONLY"
        )
        print()
        print(
            f"orphans_total                         {len(orphans)}"
        )
        print(
            f"symbol_orphans                        {len(symbol_orphans)}"
        )
        print(
            f"concept_orphans                       {len(concept_orphans)}"
        )

        if not orphans:
            print(
                "No orphan nodes."
            )
            return

        print()
        print("SYMBOL ORPHANS")
        print("-" * 78)

        for orphan in symbol_orphans:
            orphan_id = si(
                orphan["id"]
            )

            meta = parse_json(
                orphan["metadata_json"]
            )

            symbol = (
                norm(
                    meta.get(
                        "symbol"
                    )
                )
                or norm(
                    orphan["canonical_name"]
                )
            )

            print()
            print(
                f"ORPHAN | "
                f"id={orphan_id} | "
                f"symbol={symbol} | "
                f"confidence={sf(orphan['confidence']):.3f}"
            )
            print(
                f"  key={norm(orphan['node_key'])}"
            )

            candidates = find_candidates(
                conn,
                orphan,
            )

            if not candidates:
                print(
                    "  CANDIDATES: NONE"
                )
                continue

            print(
                "  CANDIDATES:"
            )

            for score, reason, candidate in candidates:
                print(
                    f"    score={score:.2f} | "
                    f"id={si(candidate['id'])} | "
                    f"type={norm(candidate['node_type'])} | "
                    f"name={norm(candidate['canonical_name'])}"
                )
                print(
                    f"      reason={reason}"
                )
                print(
                    f"      key={norm(candidate['node_key'])}"
                )

        print()
        print("CONCEPT ORPHANS")
        print("-" * 78)

        for orphan in concept_orphans:
            print()
            print(
                f"ORPHAN | "
                f"id={si(orphan['id'])} | "
                f"name={norm(orphan['canonical_name'])} | "
                f"key={norm(orphan['node_key'])}"
            )

            candidates = find_candidates(
                conn,
                orphan,
            )

            if not candidates:
                print(
                    "  CANDIDATES: NONE"
                )
                continue

            for score, reason, candidate in candidates:
                print(
                    f"  score={score:.2f} | "
                    f"id={si(candidate['id'])} | "
                    f"type={norm(candidate['node_type'])} | "
                    f"name={norm(candidate['canonical_name'])}"
                )
                print(
                    f"    reason={reason}"
                )

        print()
        print("DIAGNOSTIC SUMMARY")
        print("-" * 78)

        with_candidates = 0
        no_candidates = 0

        for orphan in orphans:
            candidates = find_candidates(
                conn,
                orphan,
            )

            if candidates:
                with_candidates += 1
            else:
                no_candidates += 1

        print(
            f"orphans_with_candidate                  {with_candidates}"
        )
        print(
            f"orphans_without_candidate               {no_candidates}"
        )

        print()
        print("DECISION RULE")
        print("-" * 78)
        print(
            "- Aynı sembole ait bağlı domain node bulunduysa "
            "bağlantı adayıdır."
        )
        print(
            "- Otomatik DELETE yok."
        )
        print(
            "- Orphan node kendi başına silinmeyecek."
        )
        print(
            "- Sonraki adım yalnızca yüksek güvenli "
            "link candidate'larını bağlamaktır."
        )
        print()
        print(
            "NO DATA WAS MODIFIED"
        )

    finally:
        conn.close()


if __name__ == "__main__":
    main()
