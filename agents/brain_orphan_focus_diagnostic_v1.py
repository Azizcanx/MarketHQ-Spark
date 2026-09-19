# -*- coding: utf-8 -*-
"""
MarketHQ Brain Orphan Focus Diagnostic V1
-----------------------------------------
Sadece 27 orphan domain node'u gösterir.
READ ONLY — DB'ye hiçbir değişiklik yapmaz.

Çalıştır:
python agents/brain_orphan_focus_diagnostic_v1.py
"""

from __future__ import annotations

import sqlite3
import json
from pathlib import Path
from typing import Any
from collections import Counter

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DB_PATH = PROJECT_ROOT / "market_hq.db"


def norm(v: Any) -> str:
    return "" if v is None else str(v).strip()


def si(v: Any, d: int = 0) -> int:
    try:
        return int(v)
    except (TypeError, ValueError):
        return d


def sf(v: Any, d: float = 0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return d


def parse_json(v: Any) -> dict[str, Any]:
    try:
        x = json.loads(norm(v) or "{}")
        return x if isinstance(x, dict) else {}
    except (json.JSONDecodeError, TypeError):
        return {}


def open_db() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH), timeout=60)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout=60000")
    return conn


def main() -> None:
    conn = open_db()
    try:
        degrees: dict[int, int] = Counter()

        for r in conn.execute(
            "SELECT source_node_id AS node_id, COUNT(*) AS n "
            "FROM brain_edges GROUP BY source_node_id"
        ):
            degrees[si(r["node_id"])] += si(r["n"])

        for r in conn.execute(
            "SELECT target_node_id AS node_id, COUNT(*) AS n "
            "FROM brain_edges GROUP BY target_node_id"
        ):
            degrees[si(r["node_id"])] += si(r["n"])

        evidenced = set()

        if conn.execute(
            """
            SELECT 1 FROM sqlite_master
            WHERE type='table' AND name='brain_node_evidence'
            """
        ).fetchone():
            evidenced = {
                si(r["node_id"])
                for r in conn.execute(
                    "SELECT DISTINCT node_id FROM brain_node_evidence"
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
                first_seen_at,
                last_seen_at,
                metadata_json
            FROM brain_nodes
            ORDER BY id
            """
        ).fetchall()

        orphans = []

        for row in rows:
            node_id = si(row["id"])
            degree = degrees.get(node_id, 0)

            if degree != 0:
                continue

            if node_id in evidenced:
                continue

            # Domain node: diagnostic V1'de görülen orphan sınıfı.
            if norm(row["node_type"]) in {
                "experiment_result",
                "experiment",
                "learned_rule",
                "concept",
                "method",
                "knowledge",
                "symbol",
                "observation",
                "claim",
                "research_result",
            }:
                orphans.append(row)

        print("=" * 78)
        print("MARKETHQ BRAIN ORPHAN FOCUS DIAGNOSTIC V1")
        print("=" * 78)
        print()
        print(f"Database : {DB_PATH}")
        print("Mode     : READ ONLY")
        print()
        print(f"ORPHAN COUNT = {len(orphans)}")
        print()

        type_counts = Counter(
            norm(r["node_type"]) or "<EMPTY>"
            for r in orphans
        )

        print("ORPHAN TYPES")
        print("-" * 78)
        for k, v in type_counts.most_common():
            print(f"{k:30s} {v}")

        print()
        print("ORPHAN NODES")
        print("-" * 78)

        for r in orphans:
            meta = parse_json(r["metadata_json"])

            print(
                f"id={si(r['id'])} | "
                f"type={norm(r['node_type'])} | "
                f"name={norm(r['canonical_name'])} | "
                f"confidence={sf(r['confidence']):.3f} | "
                f"status={norm(r['status'])}"
            )
            print(
                f"  key={norm(r['node_key'])}"
            )

            if norm(r["summary"]):
                print(
                    f"  summary={norm(r['summary'])[:300]}"
                )

            print(
                f"  first_seen={norm(r['first_seen_at']) or '<EMPTY>'} | "
                f"last_seen={norm(r['last_seen_at']) or '<EMPTY>'}"
            )

            if meta:
                compact = json.dumps(
                    meta,
                    ensure_ascii=False,
                    sort_keys=True,
                )
                print(
                    f"  metadata={compact[:500]}"
                )
            else:
                print(
                    "  metadata=<EMPTY>"
                )

            print()

        print("DECISION GUIDE")
        print("-" * 78)
        print(
            "Bu 27 node'un türlerini gördükten sonra "
            "otomatik silme/merge yapmadan karar vereceğiz."
        )
        print(
            "Öncelik: gerçek domain node mu, sistem/artık node mu?"
        )
        print()
        print("NO DATA WAS MODIFIED")

    finally:
        conn.close()


if __name__ == "__main__":
    main()
