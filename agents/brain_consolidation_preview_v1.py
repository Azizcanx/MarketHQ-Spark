from __future__ import annotations

import sqlite3
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent


def find_project_root() -> Path:
    candidates = [SCRIPT_DIR, SCRIPT_DIR.parent, Path.cwd(), Path.cwd().parent]
    seen = set()

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


def table_exists(conn: sqlite3.Connection, name: str) -> bool:
    return (
        conn.execute(
            """
            SELECT 1
            FROM sqlite_master
            WHERE type='table' AND name=?
            LIMIT 1
            """,
            (name,),
        ).fetchone()
        is not None
    )


def count(conn: sqlite3.Connection, table: str) -> int:
    if not table_exists(conn, table):
        return 0

    row = conn.execute(
        f'SELECT COUNT(*) AS n FROM "{table}"'
    ).fetchone()

    return int(row["n"] or 0)


def print_header(title: str) -> None:
    print()
    print("=" * 76)
    print(title)
    print("=" * 76)
    print()


def main() -> None:
    print("MARKETHQ BRAIN CONSOLIDATION PREVIEW V1")
    print(f"Database : {DB_PATH}")
    print("Mode     : READ ONLY / NO DATA CHANGES")
    print()

    if not DB_PATH.exists():
        raise SystemExit(f"market_hq.db bulunamadı: {DB_PATH}")

    conn = connect()

    try:
        required = [
            "brain_nodes",
            "brain_edges",
            "brain_evidence",
            "learning_experiments",
            "experiment_results",
            "learned_rules",
        ]

        missing = [x for x in required if not table_exists(conn, x)]

        if missing:
            raise SystemExit(
                "Eksik tablo: " + ", ".join(missing)
            )

        # ------------------------------------------------------------
        # 1) CURRENT GRAPH PROFILE
        # ------------------------------------------------------------
        nodes = count(conn, "brain_nodes")
        edges = count(conn, "brain_edges")
        result_nodes = conn.execute(
            """
            SELECT COUNT(*) AS n
            FROM brain_nodes
            WHERE node_type='experiment_result'
            """
        ).fetchone()["n"]

        method_nodes = conn.execute(
            """
            SELECT COUNT(*) AS n
            FROM brain_nodes
            WHERE node_type='method'
            """
        ).fetchone()["n"]

        learning_rules = count(conn, "learned_rules")
        experiments = count(conn, "learning_experiments")
        results = count(conn, "experiment_results")

        print_header("1. CURRENT GRAPH PROFILE")

        print(f"nodes                         {nodes:>10}")
        print(f"edges                         {edges:>10}")
        print(f"experiment_result nodes       {int(result_nodes):>10}  "
              f"({(int(result_nodes)/nodes*100 if nodes else 0):.2f}%)")
        print(f"method nodes                  {int(method_nodes):>10}")
        print(f"experiments                   {experiments:>10}")
        print(f"experiment results            {results:>10}")
        print(f"learned rules                 {learning_rules:>10}")

        # ------------------------------------------------------------
        # 2) PROPOSED OBSERVATION GROUPS
        # ------------------------------------------------------------
        print_header("2. PROPOSED OBSERVATION GROUPS")

        # Group raw experiment results through their parent experiment.
        # The query deliberately keeps raw rows untouched.
        rows = conn.execute(
            """
            SELECT
                le.method_name,
                le.symbol,
                le.market,
                le.timeframe,
                er.market_regime,
                er.volume_state,
                er.volatility_state,
                COUNT(*) AS sample_size,
                AVG(er.return_20d) AS avg_return_20d,
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
                ) AS negative_count
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
            LIMIT 40
            """
        ).fetchall()

        if not rows:
            print("5+ örnekli observation cluster bulunamadı.")
        else:
            for row in rows:
                sample = int(row["sample_size"] or 0)
                avg_return = row["avg_return_20d"]
                avg_text = (
                    f"{float(avg_return):.5f}"
                    if avg_return is not None
                    else "-"
                )

                print(
                    f"{str(row['method_name'])[:24]:24} | "
                    f"{str(row['symbol'])[:8]:8} | "
                    f"{str(row['market'])[:8]:8} | "
                    f"{str(row['timeframe'])[:7]:7} | "
                    f"regime={str(row['market_regime'])[:10]:10} | "
                    f"vol={str(row['volatility_state'])[:8]:8} | "
                    f"n={sample:5} | "
                    f"avg20={avg_text}"
                )

        # ------------------------------------------------------------
        # 3) DOMINANT RAW EDGES
        # ------------------------------------------------------------
        print_header("3. EDGE CONCENTRATION")

        edge_rows = conn.execute(
            """
            SELECT relation, COUNT(*) AS n
            FROM brain_edges
            GROUP BY relation
            ORDER BY n DESC
            LIMIT 15
            """
        ).fetchall()

        total_edges = edges

        for row in edge_rows:
            rel = str(row["relation"])
            n = int(row["n"])
            share = (n / total_edges * 100) if total_edges else 0.0

            print(
                f"{rel:28} {n:>8} "
                f"({share:6.2f}%)"
            )

        # ------------------------------------------------------------
        # 4) DUPLICATE RELATION CANDIDATES
        # ------------------------------------------------------------
        print_header("4. DUPLICATE RELATION CANDIDATES")

        duplicate_rows = conn.execute(
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
            LIMIT 20
            """
        ).fetchall()

        duplicate_group_count = conn.execute(
            """
            SELECT COUNT(*) AS n
            FROM (
                SELECT source_node_id, relation, target_node_id
                FROM brain_edges
                GROUP BY source_node_id, relation, target_node_id
                HAVING COUNT(*) > 1
            )
            """
        ).fetchone()["n"]

        print(f"duplicate groups: {int(duplicate_group_count)}")

        for row in duplicate_rows:
            print(
                f"{int(row['source_node_id']):>8} "
                f"-[{str(row['relation'])}]-> "
                f"{int(row['target_node_id']):>8} "
                f"x{int(row['n'])}"
            )

        # ------------------------------------------------------------
        # 5) HIGH-LEVEL METHOD LOAD
        # ------------------------------------------------------------
        print_header("5. METHOD / EXPERIMENT LOAD")

        method_rows = conn.execute(
            """
            SELECT
                method_name,
                COUNT(*) AS experiments,
                COUNT(DISTINCT symbol) AS symbols,
                COUNT(DISTINCT market) AS markets,
                COUNT(DISTINCT timeframe) AS timeframes
            FROM learning_experiments
            GROUP BY method_name
            ORDER BY experiments DESC
            LIMIT 25
            """
        ).fetchall()

        for row in method_rows:
            print(
                f"{str(row['method_name'])[:38]:38} "
                f"experiments={int(row['experiments']):>6} "
                f"symbols={int(row['symbols']):>4} "
                f"markets={int(row['markets']):>3} "
                f"tf={int(row['timeframes']):>3}"
            )

        # ------------------------------------------------------------
        # 6) LEARNED RULE DISTRIBUTION
        # ------------------------------------------------------------
        print_header("6. LEARNED RULE DISTRIBUTION")

        rule_rows = conn.execute(
            """
            SELECT
                method_name,
                COUNT(*) AS rules,
                AVG(sample_size) AS avg_sample,
                AVG(success_rate) AS avg_success,
                AVG(confidence) AS avg_confidence
            FROM learned_rules
            GROUP BY method_name
            ORDER BY rules DESC
            LIMIT 25
            """
        ).fetchall()

        for row in rule_rows:
            avg_sample = row["avg_sample"]
            avg_success = row["avg_success"]
            avg_conf = row["avg_confidence"]

            print(
                f"{str(row['method_name'])[:32]:32} "
                f"rules={int(row['rules']):>4} "
                f"sample={float(avg_sample):7.1f} "
                f"success={float(avg_success):7.3f} "
                f"conf={float(avg_conf):7.3f}"
                if (
                    avg_sample is not None
                    and avg_success is not None
                    and avg_conf is not None
                )
                else
                f"{str(row['method_name'])[:32]:32} "
                f"rules={int(row['rules']):>4}"
            )

        # ------------------------------------------------------------
        # 7) CONSOLIDATION DECISION
        # ------------------------------------------------------------
        print_header("7. CONSOLIDATION DECISION")

        ratio = (
            (int(result_nodes) / nodes * 100.0)
            if nodes
            else 0.0
        )

        if ratio >= 90:
            print(
                "STATUS : RAW_RESULT_HEAVY"
            )
            print(
                "Karar  : Ham result node'larını silme."
            )
            print(
                "         Üst seviye observation/claim katmanı oluştur."
            )
        elif ratio >= 60:
            print(
                "STATUS : RESULT_HEAVY"
            )
            print(
                "Karar  : Kontrollü observation consolidation."
            )
        else:
            print(
                "STATUS : MIXED_GRAPH"
            )
            print(
                "Karar  : Graph query ve contradiction katmanına yaklaşabiliriz."
            )

        print()
        print(
            "Önerilen sıra:"
        )
        print(
            "  raw result -> observation cluster -> claim -> evidence"
        )
        print(
            "  raw nodes korunacak; yalnızca türetilmiş katman eklenecek."
        )
        print()

    finally:
        conn.close()


if __name__ == "__main__":
    main()

