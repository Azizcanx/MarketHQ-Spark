# -*- coding: utf-8 -*-
"""
MarketHQ Brain Research Queue Enrichment Engine V2
---------------------------------------------------
Evidence Review -> Research Queue görevlerinin Research Agent tarafından
işlenebilmesi için eksik provenance/context alanlarını tamamlar.

MEVCUT DURUM
------------
Evidence Update V1 iki follow-up task oluşturdu:
    queue 11 -> TOASO
    queue 12 -> ASELS

Bu task'larda symbol/method/market/timeframe var; ancak Research Agent V4
context guard için ayrıca en az bir tane:
    learned_rule_id
    validation_id
    claim_id
gerektiriyor.

Bu motor mevcut queue task'larını:
    queue
      -> review_id
      -> knowledge_item
      -> metadata/context
      -> learned_rule_id / validation_id / claim_id
zinciriyle enrich eder.

DEĞİŞTİRİLMEYENLER
-----------------
- experiment/result
- learned_rules
- brain_claims
- brain_rule_validations
- observations
- research episodes
- evidence reviews

Sadece brain_research_queue metadata ve target_claim_id alanları,
provenance'ı tamamlamak için güncellenir.

ÖNEMLİ
------
- Yeni queue task üretmez.
- Task status değiştirmez.
- Aynı provenance tekrar yazılmaz.
- Context çözülemezse task olduğu gibi bırakılır.

Çalıştırma:
    python agents/brain_research_queue_enrichment_v2.py
"""

from __future__ import annotations

import json
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DB_PATH = PROJECT_ROOT / "market_hq.db"

ENGINE_NAME = "MARKETHQ_BRAIN_RESEARCH_QUEUE_ENRICHMENT"
ENGINE_VERSION = "V2"


def now() -> str:
    return datetime.now(
        timezone.utc
    ).isoformat(
        timespec="seconds"
    )


def norm(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def si(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def compact_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def parse_json(raw: Any) -> dict[str, Any]:
    try:
        obj = json.loads(
            norm(raw) or "{}"
        )
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
    conn.execute(
        "PRAGMA foreign_keys = ON"
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


def extract_id(
    text: str,
    pattern: str,
) -> int | None:
    match = re.search(
        pattern,
        norm(text),
        flags=re.IGNORECASE,
    )
    if not match:
        return None

    value = si(
        match.group(1),
        0,
    )

    return value if value > 0 else None


def resolve_from_metadata(
    metadata: dict[str, Any],
    keys: tuple[str, ...],
) -> int | None:
    for key in keys:
        value = si(
            metadata.get(key),
            0,
        )
        if value > 0:
            return value

    return None


def find_review(
    conn: sqlite3.Connection,
    review_id: int,
) -> sqlite3.Row | None:
    if not table_exists(
        conn,
        "brain_research_evidence_reviews",
    ):
        return None

    return conn.execute(
        """
        SELECT
            id,
            knowledge_item_id,
            observation_id,
            verdict,
            score,
            metadata_json
        FROM brain_research_evidence_reviews
        WHERE id=?
        LIMIT 1
        """,
        (review_id,),
    ).fetchone()


def find_knowledge_metadata(
    conn: sqlite3.Connection,
    knowledge_item_id: int,
) -> dict[str, Any]:
    if not table_exists(
        conn,
        "knowledge_items",
    ):
        return {}

    row = conn.execute(
        """
        SELECT metadata_json
        FROM knowledge_items
        WHERE id=?
        LIMIT 1
        """,
        (knowledge_item_id,),
    ).fetchone()

    if not row:
        return {}

    return parse_json(
        row["metadata_json"]
    )


def resolve_rule_from_claim(
    conn: sqlite3.Connection,
    claim_id: int | None,
) -> int | None:
    if not claim_id:
        return None

    if table_exists(
        conn,
        "brain_rule_promotion_events",
    ):
        row = conn.execute(
            """
            SELECT learned_rule_id
            FROM brain_rule_promotion_events
            WHERE
                source_claim_id=?
                AND decision='PROMOTED'
                AND status='promoted'
                AND learned_rule_id IS NOT NULL
            ORDER BY id DESC
            LIMIT 1
            """,
            (claim_id,),
        ).fetchone()

        if row:
            value = si(
                row["learned_rule_id"],
                0,
            )
            if value > 0:
                return value

    if table_exists(
        conn,
        "brain_learning_events",
    ):
        row = conn.execute(
            """
            SELECT learned_rule_id
            FROM brain_learning_events
            WHERE
                source_claim_id=?
                AND learned_rule_id IS NOT NULL
            ORDER BY id DESC
            LIMIT 1
            """,
            (claim_id,),
        ).fetchone()

        if row:
            value = si(
                row["learned_rule_id"],
                0,
            )
            if value > 0:
                return value

    return None


def enrich_task(
    conn: sqlite3.Connection,
    row: sqlite3.Row,
) -> tuple[bool, str]:
    metadata = parse_json(
        row["metadata_json"]
    )

    review_id = resolve_from_metadata(
        metadata,
        ("review_id",),
    )

    if review_id is None:
        review_id = extract_id(
            row["reason"],
            r"review_id\s*=\s*(\d+)",
        )

    if review_id is None:
        return (
            False,
            "review_id_not_found",
        )

    review = find_review(
        conn,
        review_id,
    )

    if review is None:
        return (
            False,
            f"review_not_found:{review_id}",
        )

    review_metadata = parse_json(
        review["metadata_json"]
    )

    knowledge_item_id = si(
        review["knowledge_item_id"],
        0,
    )

    knowledge_metadata = (
        find_knowledge_metadata(
            conn,
            knowledge_item_id,
        )
        if knowledge_item_id > 0
        else {}
    )

    claim_id = (
        si(
            metadata.get(
                "claim_id"
            ),
            0,
        )
        or si(
            review_metadata.get(
                "claim_id"
            ),
            0,
        )
        or si(
            knowledge_metadata.get(
                "claim_id"
            ),
            0,
        )
    ) or None

    learned_rule_id = (
        si(
            metadata.get(
                "learned_rule_id"
            ),
            0,
        )
        or si(
            review_metadata.get(
                "learned_rule_id"
            ),
            0,
        )
        or si(
            knowledge_metadata.get(
                "learned_rule_id"
            ),
            0,
        )
    ) or None

    validation_id = (
        si(
            metadata.get(
                "validation_id"
            ),
            0,
        )
        or si(
            review_metadata.get(
                "validation_id"
            ),
            0,
        )
        or si(
            knowledge_metadata.get(
                "validation_id"
            ),
            0,
        )
    ) or None

    if learned_rule_id is None:
        learned_rule_id = resolve_rule_from_claim(
            conn,
            claim_id,
        )

    # Review'in observation'ı bağlamından gelen core fields.
    observation_id = si(
        review["observation_id"],
        0,
    )

    if observation_id > 0 and table_exists(
        conn,
        "brain_observations",
    ):
        observation = conn.execute(
            """
            SELECT
                symbol,
                method_name,
                market,
                timeframe,
                market_regime,
                volume_state,
                volatility_state
            FROM brain_observations
            WHERE id=?
            LIMIT 1
            """,
            (observation_id,),
        ).fetchone()

        if observation:
            for field in (
                "symbol",
                "method_name",
                "market",
                "timeframe",
                "market_regime",
                "volume_state",
                "volatility_state",
            ):
                value = norm(
                    observation[field]
                )

                if value:
                    # Queue metadata içinde mevcut değer varsa onu
                    # ezmek yerine yalnızca boşsa doldur.
                    metadata.setdefault(
                        field,
                        value,
                    )

    # Critical provenance.
    if review_id:
        metadata["review_id"] = review_id

    metadata["knowledge_item_id"] = (
        knowledge_item_id
    )

    metadata["observation_id"] = (
        observation_id
    )

    if claim_id:
        metadata["claim_id"] = claim_id

    if learned_rule_id:
        metadata["learned_rule_id"] = (
            learned_rule_id
        )

    if validation_id:
        metadata["validation_id"] = (
            validation_id
        )

    metadata["queue_enrichment"] = {
        "engine": ENGINE_NAME,
        "engine_version": ENGINE_VERSION,
        "enriched_at": now(),
        "source": "evidence_review_to_knowledge_to_rule_chain",
    }

    target_claim_value = (
        claim_id
        if claim_id is not None
        else row["target_claim_id"]
    )

    updates = {
        "metadata_json": compact_json(
            metadata
        ),
        "updated_at": now(),
    }

    conn.execute(
        """
        UPDATE brain_research_queue
        SET
            target_claim_id=?,
            updated_at=?,
            metadata_json=?
        WHERE id=?
        """,
        (
            target_claim_value,
            updates["updated_at"],
            updates["metadata_json"],
            si(row["id"]),
        ),
    )

    if learned_rule_id is None and validation_id is None and claim_id is None:
        return (
            True,
            "enriched_but_no_rule_chain",
        )

    return (
        True,
        (
            f"enriched: "
            f"review={review_id}, "
            f"knowledge={knowledge_item_id}, "
            f"claim={claim_id}, "
            f"rule={learned_rule_id}, "
            f"validation={validation_id}"
        ),
    )


# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------

def run() -> None:
    conn = open_db()

    try:
        for table in (
            "brain_research_queue",
            "brain_research_evidence_reviews",
            "knowledge_items",
            "brain_observations",
        ):
            if not table_exists(
                conn,
                table,
            ):
                raise RuntimeError(
                    "Gerekli tablo bulunamadı: "
                    + table
                )

        rows = conn.execute(
            """
            SELECT *
            FROM brain_research_queue
            WHERE
                status='queued'
                AND metadata_json LIKE '%"generated_from_evidence_review":true%'
            ORDER BY priority DESC, id ASC
            """
        ).fetchall()

        selected = len(rows)
        enriched = 0
        failed = 0
        already_complete = 0

        print("=" * 76)
        print(
            "MARKETHQ BRAIN RESEARCH QUEUE ENRICHMENT ENGINE V1"
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
        print("QUEUE ENRICHMENT V2 RUN")
        print("-" * 76)
        print(
            "candidate_tasks_seen                  "
            f"{selected}"
        )

        for row in rows:
            try:
                metadata = parse_json(
                    row["metadata_json"]
                )

                # Zaten provenance zinciri varsa tekrar işlem yapma.
                if (
                    safe_int(
                        metadata.get(
                            "learned_rule_id"
                        ),
                        0,
                    )
                    > 0
                    or safe_int(
                        metadata.get(
                            "validation_id"
                        ),
                        0,
                    )
                    > 0
                    or safe_int(
                        metadata.get(
                            "claim_id"
                        ),
                        0,
                    )
                    > 0
                ):
                    already_complete += 1
                    print(
                        f"READY | queue={row['id']} | provenance already present"
                    )
                    continue

                ok, detail = enrich_task(
                    conn,
                    row,
                )

                if ok:
                    conn.commit()
                    enriched += 1

                    print(
                        f"ENRICHED | "
                        f"queue={row['id']} | "
                        f"{detail}"
                    )
                else:
                    conn.rollback()
                    failed += 1

                    print(
                        f"NOT_ENRICHED | "
                        f"queue={row['id']} | "
                        f"{detail}"
                    )

            except Exception as exc:
                conn.rollback()
                failed += 1

                print(
                    f"ERROR | "
                    f"queue={row['id']} | "
                    f"{type(exc).__name__}: {exc}"
                )

        print()
        print("CURRENT FOLLOW-UP QUEUE")
        print("-" * 76)

        active = conn.execute(
            """
            SELECT
                id,
                priority,
                question,
                metadata_json
            FROM brain_research_queue
            WHERE status IN ('queued','working')
              AND id IN (
                  SELECT id
                  FROM brain_research_queue
                  WHERE metadata_json LIKE '%"generated_from_evidence_review":true%'
              )
            ORDER BY priority DESC, id ASC
            """
        ).fetchall()

        for row in active:
            metadata = parse_json(
                row["metadata_json"]
            )

            print(
                f"queue={row['id']} | "
                f"priority={row['priority']} | "
                f"symbol={norm(metadata.get('symbol'))} | "
                f"rule={metadata.get('learned_rule_id')} | "
                f"validation={metadata.get('validation_id')} | "
                f"claim={metadata.get('claim_id')}"
            )
            print(
                f"  Q: {norm(row['question'])}"
            )

        print()
        print("SUMMARY")
        print("-" * 76)
        print(
            "candidate_tasks_seen                  "
            f"{selected}"
        )
        print(
            "tasks_enriched                        "
            f"{enriched}"
        )
        print(
            "already_ready                         "
            f"{already_complete}"
        )
        print(
            "tasks_not_enriched                    "
            f"{failed}"
        )

        print()
        print("IMPORTANT")
        print("-" * 76)
        print("- Sadece research queue metadata/provenance güncellendi.")
        print("- Queue status değiştirilmedi.")
        print("- Ham experiment/result verileri değişmedi.")
        print("- learned_rules / claims / validations değişmedi.")
        print("- Amaç Research Agent V4'ün context guard'ına gerçek provenance")
        print("  sağlamaktır.")
        print("- Sonraki adım: Research Agent V4 ile queue task'larını işlemek.")
        print()

    finally:
        conn.close()


if __name__ == "__main__":
    run()

