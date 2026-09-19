# -*- coding: utf-8 -*-
"""
MarketHQ Brain Safe Orphan Symbol Linker V1
-------------------------------------------
Dry-run / READ ONLY.

Amaç:
    Orphan symbol node'ları yalnızca EXACT symbol/canonical_name
    eşleşmesi olan bağlı domain node'larla ilişkilendirme adayına çevirmek.

ÖNEMLİ:
    Bu V1 hiçbir DB değişikliği yapmaz.
    INSERT / UPDATE / DELETE yok.

Güvenlik:
    - Fuzzy match yok.
    - Partial text match yok.
    - Orphan -> orphan eşleşmesi yok.
    - Sadece exact symbol eşleşmesi.
    - Öncelik: experiment_result > experiment > learned_rule >
      knowledge > claim > method > concept
    - Bir symbol için birden fazla güçlü aday varsa hepsi raporlanır,
      otomatik seçim yapılmaz.

Amaç sonraki V2 linker için güvenli aday listesi üretmek.
"""

from __future__ import annotations

import json
import sqlite3
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DB_PATH = PROJECT_ROOT / "market_hq.db"

DOMAIN_TYPES = {
    "experiment_result",
    "experiment",
    "learned_rule",
    "knowledge",
    "claim",
    "method",
    "concept",
    "observation",
    "research_result",
}

PRIORITY = {
    "experiment_result": 100,
    "experiment": 90,
    "learned_rule": 80,
    "claim": 70,
    "knowledge": 60,
    "observation": 50,
    "method": 40,
    "concept": 30,
    "research_result": 20,
}


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
        obj = json.loads(norm(v) or "{}")
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
        "PRAGMA busy_timeout=60000"
    )
    return conn


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


def get_evidenced_nodes(
    conn: sqlite3.Connection,
) -> set[int]:
    if not conn.execute(
        """
        SELECT 1 FROM sqlite_master
        WHERE type='table' AND name='brain_node_evidence'
        """
    ).fetchone():
        return set()

    return {
        si(row["node_id"])
        for row in conn.execute(
            """
            SELECT DISTINCT node_id
            FROM brain_node_evidence
            """
        )
    }


def load_orphan_symbols(
    conn: sqlite3.Connection,
) -> list[sqlite3.Row]:
    degrees = get_degrees(conn)
    evidenced = get_evidenced_nodes(conn)

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
        WHERE node_type='symbol'
        ORDER BY id
        """
    ).fetchall()

    return [
        row
        for row in rows
        if degrees.get(si(row["id"]), 0) == 0
        and si(row["id"]) not in evidenced
    ]


def extract_symbol(
    row: sqlite3.Row,
) -> str:
    meta = parse_json(
        row["metadata_json"]
    )

    direct = norm(
        meta.get("symbol")
    )

    if direct:
        return direct

    key = norm(
        row["node_key"]
    )

    if key.startswith("symbol:"):
        return key[len("symbol:"):].strip()

    return norm(
        row["canonical_name"]
    )


def extract_symbol_from_node(
    row: sqlite3.Row,
) -> set[str]:
    values: set[str] = set()

    name = norm(
        row["canonical_name"]
    )

    meta = parse_json(
        row["metadata_json"]
    )

    for value in (
        name,
        norm(meta.get("symbol")),
        norm(meta.get("ticker")),
        norm(meta.get("underlying_symbol")),
    ):
        if value:
            values.add(value)

    context = meta.get(
        "context",
        {},
    )

    if isinstance(
        context,
        dict,
    ):
        for value in (
            norm(context.get("symbol")),
            norm(context.get("ticker")),
            norm(context.get("underlying_symbol")),
        ):
            if value:
                values.add(value)

    key = norm(
        row["node_key"]
    )

    if key.startswith("symbol:"):
        values.add(
            key[len("symbol:"):].strip()
        )

    return {
        value
        for value in values
        if value
    }


def connected_domain_nodes(
    conn: sqlite3.Connection,
) -> list[sqlite3.Row]:
    rows = conn.execute(
        """
        SELECT
            n.id,
            n.node_key,
            n.node_type,
            n.canonical_name,
            n.summary,
            n.confidence,
            n.status,
            n.metadata_json
        FROM brain_nodes n
        WHERE n.node_type IN (
            'experiment_result',
            'experiment',
            'learned_rule',
            'knowledge',
            'claim',
            'method',
            'concept',
            'observation',
            'research_result'
        )
        """
    ).fetchall()

    degrees = get_degrees(
        conn
    )

    return [
        row
        for row in rows
        if degrees.get(
            si(row["id"]),
            0,
        )
        > 0
    ]


def exact_candidates(
    orphan: sqlite3.Row,
    domain_nodes: list[sqlite3.Row],
) -> list[tuple[int, str, sqlite3.Row]]:
    symbol = extract_symbol(
        orphan
    )

    if not symbol:
        return []

    normalized = symbol.upper()
    matches = []

    for node in domain_nodes:
        node_symbols = extract_symbol_from_node(
            node
        )

        exact = any(
            value.upper() == normalized
            for value in node_symbols
        )

        if not exact:
            continue

        node_type = norm(
            node["node_type"]
        )

        score = PRIORITY.get(
            node_type,
            10,
        )

        # Deterministic exact canonical symbol name bonus.
        if (
            norm(
                node["canonical_name"]
            ).upper()
            == normalized
        ):
            score += 25

        matches.append(
            (
                score,
                "EXACT_SYMBOL",
                node,
            )
        )

    matches.sort(
        key=lambda item: (
            item[0],
            sf(
                item[2]["confidence"]
            ),
            si(
                item[2]["id"]
            ),
        ),
        reverse=True,
    )

    return matches


def existing_edge_relations(
    conn: sqlite3.Connection,
    orphan_id: int,
    candidate_id: int,
) -> list[str]:
    rows = conn.execute(
        """
        SELECT relation
        FROM brain_edges
        WHERE
            (source_node_id=? AND target_node_id=?)
            OR
            (source_node_id=? AND target_node_id=?)
        ORDER BY id
        """,
        (
            orphan_id,
            candidate_id,
            candidate_id,
            orphan_id,
        ),
    ).fetchall()

    return [
        norm(row["relation"])
        for row in rows
    ]


def main() -> None:
    conn = open_db()

    try:
        for table in (
            "brain_nodes",
            "brain_edges",
        ):
            exists = conn.execute(
                """
                SELECT 1
                FROM sqlite_master
                WHERE type='table'
                  AND name=?
                """,
                (table,),
            ).fetchone()

            if not exists:
                raise RuntimeError(
                    f"Eksik tablo: {table}"
                )

        orphans = load_orphan_symbols(
            conn
        )

        domains = connected_domain_nodes(
            conn
        )

        print("=" * 78)
        print(
            "MARKETHQ BRAIN SAFE ORPHAN SYMBOL LINKER V1"
        )
        print("=" * 78)
        print()
        print(
            f"Database : {DB_PATH}"
        )
        print(
            "Mode     : READ ONLY / DRY RUN"
        )
        print()
        print(
            f"orphan_symbol_nodes                    {len(orphans)}"
        )
        print(
            f"connected_domain_nodes                 {len(domains)}"
        )

        candidates_total = 0
        symbols_with_candidates = 0
        symbols_without_candidates = 0

        relation_candidates = Counter()
        candidate_rows = []

        print()
        print("SYMBOL LINK CANDIDATES")
        print("-" * 78)

        for orphan in orphans:
            orphan_id = si(
                orphan["id"]
            )
            symbol = extract_symbol(
                orphan
            )

            matches = exact_candidates(
                orphan,
                domains,
            )

            if not matches:
                symbols_without_candidates += 1

                print()
                print(
                    f"ORPHAN | id={orphan_id} | "
                    f"symbol={symbol or '<EMPTY>'} | "
                    "CANDIDATES=NONE"
                )
                continue

            symbols_with_candidates += 1
            candidates_total += len(
                matches
            )

            print()
            print(
                f"ORPHAN | id={orphan_id} | "
                f"symbol={symbol}"
            )

            for (
                score,
                match_type,
                candidate,
            ) in matches[:10]:
                candidate_id = si(
                    candidate["id"]
                )

                existing = existing_edge_relations(
                    conn,
                    orphan_id,
                    candidate_id,
                )

                relation_candidates[
                    norm(
                        candidate["node_type"]
                    )
                ] += 1

                candidate_rows.append(
                    (
                        orphan_id,
                        symbol,
                        score,
                        match_type,
                        candidate_id,
                        norm(
                            candidate["node_type"]
                        ),
                    )
                )

                print(
                    f"  score={score:3d} | "
                    f"id={candidate_id} | "
                    f"type={norm(candidate['node_type'])} | "
                    f"name={norm(candidate['canonical_name'])}"
                )
                print(
                    f"    key={norm(candidate['node_key'])}"
                )
                print(
                    f"    confidence="
                    f"{sf(candidate['confidence']):.3f}"
                )
                print(
                    "    exact_match=YES | "
                    f"existing_relations={existing or ['NONE']}"
                )

        print()
        print("SUMMARY")
        print("-" * 78)
        print(
            f"orphan_symbol_nodes                    {len(orphans)}"
        )
        print(
            f"symbols_with_candidates                {symbols_with_candidates}"
        )
        print(
            f"symbols_without_candidates             {symbols_without_candidates}"
        )
        print(
            f"exact_candidate_pairs                  {candidates_total}"
        )

        print()
        print("CANDIDATE NODE TYPE DISTRIBUTION")
        print("-" * 78)

        for node_type, count in (
            relation_candidates.most_common()
        ):
            print(
                f"{node_type:35s} {count}"
            )

        print()
        print("TOP CANDIDATE PAIRS")
        print("-" * 78)

        for (
            orphan_id,
            symbol,
            score,
            match_type,
            candidate_id,
            candidate_type,
        ) in sorted(
            candidate_rows,
            key=lambda row: (
                row[2],
                row[4],
            ),
            reverse=True,
        )[:40]:
            print(
                f"orphan={orphan_id} | "
                f"symbol={symbol} | "
                f"candidate={candidate_id} | "
                f"type={candidate_type} | "
                f"score={score} | "
                f"{match_type}"
            )

        print()
        print("DECISION")
        print("-" * 78)
        print(
            "Bu V1 yalnızca EXACT symbol eşleşmelerini gösterir."
        )
        print(
            "Henüz edge oluşturulmadı."
        )
        print(
            "Otomatik merge/delete yapılmadı."
        )
        print(
            "Bir sonraki linker sürümünde yalnızca "
            "tek-anlamlı yüksek güvenli adaylar bağlanabilir."
        )
        print()
        print(
            "NO DATA WAS MODIFIED"
        )

    finally:
        conn.close()


if __name__ == "__main__":
    main()
