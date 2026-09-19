from __future__ import annotations

import sqlite3
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent


def find_project_root() -> Path:
    candidates = [SCRIPT_DIR, SCRIPT_DIR.parent, Path.cwd(), Path.cwd().parent]
    seen: set[Path] = set()
    for candidate in candidates:
        candidate = candidate.resolve()
        if candidate in seen:
            continue
        seen.add(candidate)
        if (candidate / "market_hq.db").exists():
            return candidate
    return SCRIPT_DIR.parent if SCRIPT_DIR.name.lower() == "agents" else SCRIPT_DIR


BASE_DIR = find_project_root()
DB_PATH = BASE_DIR / "market_hq.db"


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=15.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout = 15000")
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1",
        (table_name,),
    ).fetchone()
    return row is not None


def count(conn: sqlite3.Connection, table_name: str) -> int:
    if not table_exists(conn, table_name):
        return 0
    row = conn.execute(f'SELECT COUNT(*) AS n FROM "{table_name}"').fetchone()
    return int(row["n"] or 0)


def pct(a: int, b: int) -> float:
    return round((a / b) * 100.0, 2) if b else 0.0


def main() -> None:
    print("MARKETHQ BRAIN HEALTH CHECK V1")
    print(f"Database : {DB_PATH}")
    print()

    if not DB_PATH.exists():
        raise SystemExit(f"market_hq.db bulunamadı: {DB_PATH}")

    conn = connect()
    try:
        required = [
            "brain_nodes", "brain_edges", "brain_episodes",
            "brain_evidence", "brain_claims",
            "brain_node_evidence", "brain_edge_evidence",
            "brain_claim_evidence", "brain_learning_events",
        ]
        missing = [t for t in required if not table_exists(conn, t)]
        if missing:
            raise SystemExit("Brain schema eksik: " + ", ".join(missing))

        nodes = count(conn, "brain_nodes")
        edges = count(conn, "brain_edges")
        episodes = count(conn, "brain_episodes")
        evidence = count(conn, "brain_evidence")
        claims = count(conn, "brain_claims")
        node_evidence = count(conn, "brain_node_evidence")
        edge_evidence = count(conn, "brain_edge_evidence")
        claim_evidence = count(conn, "brain_claim_evidence")
        learning_events = count(conn, "brain_learning_events")

        print("GRAPH SIZE")
        print(f"{'brain_nodes':28} {nodes:>8}")
        print(f"{'brain_edges':28} {edges:>8}")
        print(f"{'brain_episodes':28} {episodes:>8}")
        print(f"{'brain_evidence':28} {evidence:>8}")
        print(f"{'brain_claims':28} {claims:>8}")
        print(f"{'brain_learning_events':28} {learning_events:>8}")
        print()

        print("LINK COVERAGE")
        print(f"node -> evidence           {node_evidence:>8} links")
        print(f"edge -> evidence           {edge_evidence:>8} links")
        print(f"claim -> evidence          {claim_evidence:>8} links")
        print(f"edges / nodes               {edges / nodes if nodes else 0:.2f}")
        print()

        print("NODE TYPES")
        for r in conn.execute(
            "SELECT node_type, COUNT(*) n FROM brain_nodes GROUP BY node_type ORDER BY n DESC"
        ).fetchall():
            print(f"{str(r['node_type']):28} {int(r['n']):>8}")
        print()

        print("TOP RELATIONS")
        for r in conn.execute(
            "SELECT relation, COUNT(*) n FROM brain_edges GROUP BY relation ORDER BY n DESC LIMIT 20"
        ).fetchall():
            print(f"{str(r['relation']):28} {int(r['n']):>8}")
        print()

        print("CLAIM TYPES")
        for r in conn.execute(
            "SELECT claim_type, status, COUNT(*) n FROM brain_claims GROUP BY claim_type, status ORDER BY n DESC"
        ).fetchall():
            print(f"{str(r['claim_type']):20} {str(r['status']):12} {int(r['n']):>8}")
        print()

        orphan_nodes = conn.execute(
            """
            SELECT COUNT(*) n
            FROM brain_nodes n
            WHERE NOT EXISTS (
                SELECT 1 FROM brain_edges e
                WHERE e.source_node_id=n.id OR e.target_node_id=n.id
            )
            """
        ).fetchone()["n"]

        orphan_evidence = conn.execute(
            """
            SELECT COUNT(*) n
            FROM brain_evidence e
            WHERE NOT EXISTS (
                SELECT 1 FROM brain_node_evidence ne WHERE ne.evidence_id=e.id
            )
            AND NOT EXISTS (
                SELECT 1 FROM brain_edge_evidence ee WHERE ee.evidence_id=e.id
            )
            AND NOT EXISTS (
                SELECT 1 FROM brain_claim_evidence ce WHERE ce.evidence_id=e.id
            )
            """
        ).fetchone()["n"]

        duplicate_edges = conn.execute(
            """
            SELECT COUNT(*) n FROM (
                SELECT source_node_id, relation, target_node_id
                FROM brain_edges
                GROUP BY source_node_id, relation, target_node_id
                HAVING COUNT(*) > 1
            )
            """
        ).fetchone()["n"]

        print("STRUCTURAL FLAGS")
        print(f"orphan_nodes                {int(orphan_nodes):>8}")
        print(f"orphan_evidence             {int(orphan_evidence):>8}")
        print(f"duplicate_edge_groups       {int(duplicate_edges):>8}")
        print()

        print("TEMPORAL COVERAGE")
        temporal_edges = conn.execute(
            "SELECT COUNT(*) n FROM brain_edges WHERE valid_from IS NOT NULL OR valid_to IS NOT NULL"
        ).fetchone()["n"]
        observed_episodes = conn.execute(
            "SELECT COUNT(*) n FROM brain_episodes WHERE observed_at IS NOT NULL"
        ).fetchone()["n"]
        print(f"temporal edges              {int(temporal_edges):>8} ({pct(int(temporal_edges), edges):.2f}%)")
        print(f"observed episodes           {int(observed_episodes):>8} ({pct(int(observed_episodes), episodes):.2f}%)")
        print()

        print("HEALTH SUMMARY")
        print("Bu araç sadece analiz yaptı; veri silmedi veya değiştirmedi.")
        print("Bir sonraki adım: çıktıdaki tekrarları ve ilişki kalitesini")
        print("ölçüp kontrollü graph consolidation yapmak.")
        print()

    finally:
        conn.close()


if __name__ == "__main__":
    main()

