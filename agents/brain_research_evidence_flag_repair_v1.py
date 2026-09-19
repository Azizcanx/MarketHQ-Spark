# -*- coding: utf-8 -*-
"""
MarketHQ Brain Research Evidence Flag Repair Engine V1
-------------------------------------------------------
Amaç:
    brain_research_evidence_reviews içindeki verdict ile
    contradiction_flag alanını tutarlı hale getirmek.

Kural:
    CONTRADICTORY -> contradiction_flag = 1
    diğer verdictler -> contradiction_flag = 0

Neden?
    PARTIALLY_SUPPORTIVE bir review, tek başına contradiction değildir.
    Önceki Evidence Review çıktısında bu alanın 1 gelmesi,
    downstream Brain Update'in gereksiz contradiction üretme riskini
    oluşturuyordu.

GÜVENLİK
--------
Bu motor yalnızca:
    brain_research_evidence_reviews.contradiction_flag

alanını düzeltir.

Değiştirmez:
    knowledge_items
    brain_observations
    brain_claims
    learned_rules
    validations
    experiments/results
    research queue
    research episodes

DELETE yok.

Çalıştırma:
    python agents/brain_research_evidence_flag_repair_v1.py
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DB_PATH = PROJECT_ROOT / "market_hq.db"

ENGINE_NAME = "MARKETHQ_BRAIN_RESEARCH_EVIDENCE_FLAG_REPAIR"
ENGINE_VERSION = "V1"


def utc_now() -> str:
    return datetime.now(
        timezone.utc
    ).isoformat(
        timespec="seconds"
    )


def norm(value):
    if value is None:
        return ""
    return str(value).strip()


def safe_int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def open_db():
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


def table_exists(conn, table):
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


def run():
    conn = open_db()

    try:
        if not table_exists(
            conn,
            "brain_research_evidence_reviews",
        ):
            raise RuntimeError(
                "brain_research_evidence_reviews tablosu bulunamadı."
            )

        rows = conn.execute(
            """
            SELECT
                id,
                verdict,
                contradiction_flag
            FROM brain_research_evidence_reviews
            ORDER BY id ASC
            """
        ).fetchall()

        changed = 0
        already_consistent = 0
        errors = 0

        by_verdict = {}

        for row in rows:
            verdict = norm(
                row["verdict"]
            ).upper()

            expected = int(
                verdict == "CONTRADICTORY"
            )

            current = safe_int(
                row["contradiction_flag"]
            )

            by_verdict[verdict] = (
                by_verdict.get(
                    verdict,
                    0,
                )
                + 1
            )

            if current == expected:
                already_consistent += 1
                continue

            try:
                conn.execute(
                    """
                    UPDATE brain_research_evidence_reviews
                    SET contradiction_flag=?
                    WHERE id=?
                    """,
                    (
                        expected,
                        safe_int(
                            row["id"]
                        ),
                    ),
                )

                changed += 1

            except Exception:
                errors += 1

        conn.commit()

        contradiction_count = conn.execute(
            """
            SELECT COUNT(*)
            FROM brain_research_evidence_reviews
            WHERE contradiction_flag=1
            """
        ).fetchone()[0]

        non_contradiction_count = conn.execute(
            """
            SELECT COUNT(*)
            FROM brain_research_evidence_reviews
            WHERE contradiction_flag=0
            """
        ).fetchone()[0]

        print("=" * 76)
        print(
            "MARKETHQ BRAIN RESEARCH EVIDENCE FLAG REPAIR ENGINE V1"
        )
        print("=" * 76)
        print()
        print(
            f"Database : {DB_PATH}"
        )
        print(
            f"Engine   : {ENGINE_NAME}"
        )
        print(
            f"Version  : {ENGINE_VERSION}"
        )
        print()
        print("FLAG REPAIR RUN")
        print("-" * 76)
        print(
            f"reviews_seen                           {len(rows)}"
        )
        print(
            f"flags_changed                          {changed}"
        )
        print(
            f"already_consistent                     {already_consistent}"
        )
        print(
            f"errors                                 {errors}"
        )

        print()
        print("VERDICT COUNTS")
        print("-" * 76)

        for verdict, count in sorted(
            by_verdict.items()
        ):
            print(
                f"{verdict or '<EMPTY>':35s} {count}"
            )

        print()
        print("FINAL FLAG COUNTS")
        print("-" * 76)
        print(
            f"contradiction_flag=1                  "
            f"{safe_int(contradiction_count)}"
        )
        print(
            f"contradiction_flag=0                  "
            f"{safe_int(non_contradiction_count)}"
        )

        print()
        print("RECENT REVIEWS")
        print("-" * 76)

        recent = conn.execute(
            """
            SELECT
                id,
                knowledge_item_id,
                observation_id,
                verdict,
                score,
                contradiction_flag,
                review_method
            FROM brain_research_evidence_reviews
            ORDER BY id DESC
            LIMIT 10
            """
        ).fetchall()

        for row in recent:
            print(
                f"review={safe_int(row['id'])} | "
                f"knowledge={safe_int(row['knowledge_item_id'])} | "
                f"obs={safe_int(row['observation_id'])} | "
                f"{norm(row['verdict'])} | "
                f"score={float(row['score'] or 0):.3f} | "
                f"contradiction={safe_int(row['contradiction_flag'])} | "
                f"{norm(row['review_method'])}"
            )

        print()
        print("IMPORTANT")
        print("-" * 76)
        print("- Yalnız contradiction_flag alanı verdict ile hizalandı.")
        print("- PARTIALLY_SUPPORTIVE artık contradiction sayılmıyor.")
        print("- Review sonucu verified rule'a çevrilmedi.")
        print("- Diğer Brain tabloları değiştirilmedi.")
        print("- DELETE yapılmadı.")
        print(
            f"- Repair timestamp: {utc_now()}"
        )
        print()

    finally:
        conn.close()


if __name__ == "__main__":
    run()
