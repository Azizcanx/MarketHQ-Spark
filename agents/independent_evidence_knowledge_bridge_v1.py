# -*- coding: utf-8 -*-
"""
MarketHQ Independent Evidence -> Knowledge Bridge V1

Research-only bridge:
Independent strategy evidence JSON
    -> knowledge_sources
    -> knowledge_items

No learned_rules / claims / validations / observations are modified.
No broker/execution.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DB_PATH = PROJECT_ROOT / "market_hq.db"
EVIDENCE_DIR = PROJECT_ROOT / "independent_strategy_evidence_results"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def norm(value: Any) -> str:
    return "" if value is None else str(value).strip()


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


def compact_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def text_hash(value: str) -> str:
    return hashlib.sha256(
        value.encode("utf-8")
    ).hexdigest()


def open_db() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH), timeout=60)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout = 60000")
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def table_exists(
    conn: sqlite3.Connection,
    table: str,
) -> bool:
    row = conn.execute(
        """
        SELECT 1
        FROM sqlite_master
        WHERE type='table' AND name=?
        LIMIT 1
        """,
        (table,),
    ).fetchone()
    return row is not None


def find_latest_evidence() -> Path:
    files = sorted(
        EVIDENCE_DIR.glob("independent_evidence_*.json"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    if not files:
        raise FileNotFoundError(
            f"Independent evidence JSON bulunamadı: {EVIDENCE_DIR}"
        )
    return files[0]


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        obj = json.load(handle)
    if not isinstance(obj, dict):
        raise ValueError("Evidence JSON bir dict olmalı.")
    return obj


def source_title(evidence: dict[str, Any]) -> str:
    return (
        "Independent Strategy Evidence | "
        f"{norm(evidence.get('strategy_id'))} | "
        f"{norm(evidence.get('strategy_name'))}"
    )


def item_title(evidence: dict[str, Any]) -> str:
    return (
        f"{norm(evidence.get('strategy_name'))} | "
        "INDEPENDENT_EVIDENCE"
    )


def insert_or_reuse_source(
    conn: sqlite3.Connection,
    evidence: dict[str, Any],
    evidence_path: Path,
) -> tuple[int, str]:
    if not table_exists(conn, "knowledge_sources"):
        raise RuntimeError("knowledge_sources tablosu bulunamadı.")

    title = source_title(evidence)
    url = f"file:///{evidence_path.as_posix()}"
    source_hash = text_hash(url)

    cols = {
        str(row["name"])
        for row in conn.execute(
            "PRAGMA table_info(knowledge_sources)"
        ).fetchall()
    }

    if "url" in cols:
        row = conn.execute(
            "SELECT id FROM knowledge_sources WHERE url=? LIMIT 1",
            (url,),
        ).fetchone()
        if row:
            return safe_int(row["id"]), "reused"

    if "title" not in cols:
        raise RuntimeError("knowledge_sources.title bulunamadı.")

    insert_cols = ["title"]
    values: list[Any] = [title]

    if "url" in cols:
        insert_cols.append("url")
        values.append(url)

    if "source_type" in cols:
        insert_cols.append("source_type")
        values.append("internal_research")

    if "created_at" in cols:
        insert_cols.append("created_at")
        values.append(utc_now())

    placeholders = ",".join("?" for _ in values)
    cur = conn.execute(
        f"""
        INSERT INTO knowledge_sources ({",".join(insert_cols)})
        VALUES ({placeholders})
        """,
        tuple(values),
    )
    return safe_int(cur.lastrowid), "created"


def build_content(evidence: dict[str, Any]) -> str:
    summary = evidence.get("summary", {})
    cost = evidence.get("cost_assumptions", {})
    periods = evidence.get("periods", {})
    results = evidence.get("results", {})

    lines = [
        "INDEPENDENT HISTORICAL STRATEGY EVIDENCE",
        "",
        f"strategy_id={norm(evidence.get('strategy_id'))}",
        f"strategy_name={norm(evidence.get('strategy_name'))}",
        f"research_only={evidence.get('research_only')}",
        f"execution_enabled={evidence.get('execution_enabled')}",
        "",
        "SUMMARY",
        f"symbols_tested={safe_int(summary.get('symbols_tested'))}",
        f"positive_full_runs={safe_int(summary.get('positive_full_runs'))}",
        f"negative_full_runs={safe_int(summary.get('negative_full_runs'))}",
        f"cost_survivors={safe_int(summary.get('cost_survivors'))}",
        f"total_holdout_folds={safe_int(summary.get('total_holdout_folds'))}",
        f"positive_holdout_folds={safe_int(summary.get('positive_holdout_folds'))}",
        "",
        "COST ASSUMPTIONS",
        compact_json(cost),
        "",
        "PERIODS",
        compact_json(periods),
        "",
        "REGIME DEFINITION",
        norm(evidence.get("regime_definition")),
        "",
        "SYMBOL RESULTS",
    ]

    for symbol, payload in results.items():
        lines.append("")
        lines.append(f"[{symbol}]")

        full = payload.get("full_backtest", {})
        with_costs = full.get("with_costs", {})
        cost_free = full.get("cost_free", {})
        rolling = payload.get("rolling_holdout", {})

        lines.append(
            "with_costs="
            + compact_json(with_costs.get("metrics", {}))
        )
        lines.append(
            "cost_free="
            + compact_json(cost_free.get("metrics", {}))
        )
        lines.append(
            "holdout="
            + compact_json(
                {
                    "status": rolling.get("status"),
                    "total_folds": rolling.get("total_folds"),
                    "positive_folds": rolling.get("positive_folds"),
                    "negative_folds": rolling.get("negative_folds"),
                }
            )
        )

        regime = full.get("regime_with_costs", {})
        for regime_name, regime_payload in regime.items():
            lines.append(
                f"regime_{regime_name}="
                + compact_json(regime_payload)
            )

    lines.extend(
        [
            "",
            "EPISTEMIC STATUS",
            norm(evidence.get("epistemic_status")),
        ]
    )

    return "\n".join(lines)


def insert_or_upgrade_item(
    conn: sqlite3.Connection,
    evidence: dict[str, Any],
    source_id: int,
    content: str,
) -> tuple[int, str]:
    if not table_exists(conn, "knowledge_items"):
        raise RuntimeError("knowledge_items tablosu bulunamadı.")

    strategy_id = norm(evidence.get("strategy_id"))
    title = item_title(evidence)
    metadata = {
        "engine": "MARKETHQ_INDEPENDENT_STRATEGY_EVIDENCE_RUNNER",
        "bridge": "MARKETHQ_INDEPENDENT_EVIDENCE_KNOWLEDGE_BRIDGE",
        "bridge_version": "V1",
        "strategy_id": strategy_id,
        "strategy_name": norm(evidence.get("strategy_name")),
        "evidence_file": str(
            evidence.get("selection_file", "")
        ),
        "research_derived": True,
        "verified": False,
        "not_a_live_signal": True,
        "summary": evidence.get("summary", {}),
        "cost_assumptions": evidence.get(
            "cost_assumptions",
            {},
        ),
        "periods": evidence.get("periods", {}),
    }

    cols = {
        str(row["name"])
        for row in conn.execute(
            "PRAGMA table_info(knowledge_items)"
        ).fetchall()
    }

    existing = None

    if "metadata_json" in cols:
        rows = conn.execute(
            """
            SELECT id, metadata_json
            FROM knowledge_items
            WHERE source_id=?
            ORDER BY id DESC
            """,
            (source_id,),
        ).fetchall()

        for row in rows:
            try:
                meta = json.loads(
                    norm(row["metadata_json"]) or "{}"
                )
            except json.JSONDecodeError:
                meta = {}

            if (
                norm(meta.get("strategy_id")).upper()
                == strategy_id.upper()
            ):
                existing = row
                break

    if existing:
        update_cols = []
        values: list[Any] = []

        if "title" in cols:
            update_cols.append("title=?")
            values.append(title)

        if "content" in cols:
            update_cols.append("content=?")
            values.append(content)

        if "summary" in cols:
            update_cols.append("summary=?")
            values.append(
                "Independent historical evidence; not verified."
            )

        if "confidence" in cols:
            update_cols.append("confidence=?")
            values.append(0.50)

        if "metadata_json" in cols:
            update_cols.append("metadata_json=?")
            values.append(compact_json(metadata))

        if update_cols:
            values.append(safe_int(existing["id"]))
            conn.execute(
                "UPDATE knowledge_items SET "
                + ", ".join(update_cols)
                + " WHERE id=?",
                tuple(values),
            )

        return safe_int(existing["id"]), "upgraded"

    insert_cols = []
    values = []

    def add(col: str, value: Any) -> None:
        if col in cols:
            insert_cols.append(col)
            values.append(value)

    add("source_id", source_id)
    add("item_type", "RESEARCH_FINDING")
    add("title", title)
    add("content", content)
    add(
        "summary",
        "Independent historical strategy evidence; not verified.",
    )
    add("method", norm(evidence.get("strategy_name")))
    add(
        "symbols_json",
        compact_json(evidence.get("symbols", [])),
    )
    add(
        "tags_json",
        compact_json(
            [
                "research_derived",
                "independent_evidence",
                "strategy_evidence",
                "not_verified",
            ]
        ),
    )
    add("confidence", 0.50)
    add("metadata_json", compact_json(metadata))
    add("created_at", utc_now())

    placeholders = ",".join("?" for _ in values)
    cur = conn.execute(
        f"""
        INSERT INTO knowledge_items ({",".join(insert_cols)})
        VALUES ({placeholders})
        """,
        tuple(values),
    )
    return safe_int(cur.lastrowid), "created"


def main() -> None:
    evidence_path = find_latest_evidence()
    evidence = load_json(evidence_path)

    conn = open_db()
    try:
        source_id, source_status = insert_or_reuse_source(
            conn,
            evidence,
            evidence_path,
        )

        content = build_content(evidence)

        item_id, item_status = insert_or_upgrade_item(
            conn,
            evidence,
            source_id,
            content,
        )

        conn.commit()

        print("=" * 76)
        print("MARKETHQ INDEPENDENT EVIDENCE → KNOWLEDGE BRIDGE V1")
        print("=" * 76)
        print(f"Evidence file  : {evidence_path.name}")
        print(
            f"Strategy       : "
            f"{norm(evidence.get('strategy_id'))} | "
            f"{norm(evidence.get('strategy_name'))}"
        )
        print(
            f"Source         : {source_id} ({source_status})"
        )
        print(
            f"Knowledge item : {item_id} ({item_status})"
        )
        print()
        print("SAFETY")
        print("Research Only      : True")
        print("Execution Enabled  : False")
        print("learned_rules      : unchanged")
        print("claims             : unchanged")
        print("validations        : unchanged")
        print("observations       : unchanged")
        print("Verified           : False")
        print()
        print(
            f"Saved knowledge item: {item_id}"
        )

    finally:
        conn.close()


if __name__ == "__main__":
    main()

