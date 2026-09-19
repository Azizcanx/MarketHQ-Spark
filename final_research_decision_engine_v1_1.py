# -*- coding: utf-8 -*-
"""
MarketHQ Final Research Decision Engine V1.1
==========================================

AMAÇ
-----
MarketHQ araştırma zincirinin son karar katmanı.

Girdi:
    - Strategy-level independent evidence review
    - Independent evidence knowledge item metadata
    - Mevcut V6 strategy pipeline ranking/robustness sonucu
    - Paper evidence / research evidence bağlamı

Çıktı:
    - Final research decision
    - Araştırma önceliği
    - Açıklanabilir skor
    - Ayrı karar hafızası

ÖNEMLİ
-------
- Bu motor VERIFIED kural üretmez.
- learned_rules / claims / validations değiştirmez.
- brain_observations değiştirmez.
- Canlı işlem / broker execution yapmaz.
- Research-only karar üretir.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parent
DB_PATH = PROJECT_ROOT / "market_hq.db"
PIPELINE_DIR = PROJECT_ROOT / "strategy_pipeline_results"
OUTPUT_DIR = PROJECT_ROOT / "final_research_decisions"

ENGINE_NAME = "MARKETHQ_FINAL_RESEARCH_DECISION"
ENGINE_VERSION = "V1.1"

TARGET_STRATEGY_ID = "STR-43839FA9C6"

VALID_DECISIONS = {
    "PROMISING_RESEARCH_CANDIDATE",
    "MIXED_NEEDS_MORE_RESEARCH",
    "WEAK_RESEARCH_CANDIDATE",
    "REJECT_RESEARCH_CANDIDATE",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


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


def parse_json(value: Any) -> dict[str, Any]:
    try:
        obj = json.loads(norm(value) or "{}")
        return obj if isinstance(obj, dict) else {}
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}


def compact_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def open_db() -> sqlite3.Connection:
    if not DB_PATH.exists():
        raise FileNotFoundError(f"Database bulunamadı: {DB_PATH}")

    conn = sqlite3.connect(str(DB_PATH), timeout=60)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout = 60000")
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
    row = conn.execute(
        """
        SELECT 1
        FROM sqlite_master
        WHERE type='table' AND name=?
        LIMIT 1
        """,
        (table_name,),
    ).fetchone()
    return row is not None


def table_columns(conn: sqlite3.Connection, table_name: str) -> set[str]:
    if not table_exists(conn, table_name):
        return set()

    rows = conn.execute(
        f"PRAGMA table_info({table_name})"
    ).fetchall()

    return {norm(row["name"]) for row in rows}


def find_latest_pipeline_result() -> Path | None:
    if not PIPELINE_DIR.exists():
        return None

    candidates = sorted(
        PIPELINE_DIR.glob("strategy_pipeline_v6_*.json"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )

    if not candidates:
        candidates = sorted(
            PIPELINE_DIR.glob("strategy_pipeline_*STR-43839FA9C6*.json"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )

    return candidates[0] if candidates else None


def load_json_file(path: Path | None) -> dict[str, Any]:
    if path is None or not path.exists():
        return {}

    try:
        obj = json.loads(path.read_text(encoding="utf-8"))
        return obj if isinstance(obj, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def recursive_find(obj: Any, keys: tuple[str, ...]) -> Any:
    wanted = {k.lower() for k in keys}

    if isinstance(obj, dict):
        for key, value in obj.items():
            if norm(key).lower() in wanted:
                return value

        for value in obj.values():
            found = recursive_find(value, keys)
            if found is not None:
                return found

    elif isinstance(obj, list):
        for value in obj:
            found = recursive_find(value, keys)
            if found is not None:
                return found

    return None


def load_strategy_review(
    conn: sqlite3.Connection,
    strategy_id: str,
) -> dict[str, Any]:
    if not table_exists(conn, "brain_research_strategy_evidence_reviews"):
        raise RuntimeError(
            "brain_research_strategy_evidence_reviews tablosu bulunamadı."
        )

    cols = table_columns(conn, "brain_research_strategy_evidence_reviews")
    if not {"id", "knowledge_item_id", "verdict", "score"}.issubset(cols):
        raise RuntimeError(
            "Strategy review tablosunda beklenen temel kolonlar yok."
        )

    rows = conn.execute(
        """
        SELECT *
        FROM brain_research_strategy_evidence_reviews
        ORDER BY id DESC
        """
    ).fetchall()

    for row in rows:
        data = dict(row)
        metadata = parse_json(data.get("metadata_json"))

        row_strategy_id = norm(
            data.get("strategy_id")
            or metadata.get("strategy_id")
        )

        if row_strategy_id.upper() == strategy_id.upper():
            data["metadata"] = metadata
            return data

        knowledge_id = safe_int(data.get("knowledge_item_id"))
        if knowledge_id:
            ki = conn.execute(
                """
                SELECT metadata_json
                FROM knowledge_items
                WHERE id=?
                LIMIT 1
                """,
                (knowledge_id,),
            ).fetchone()

            if ki:
                ki_meta = parse_json(ki["metadata_json"])
                if (
                    norm(ki_meta.get("strategy_id")).upper()
                    == strategy_id.upper()
                ):
                    data["metadata"] = metadata
                    data["knowledge_metadata"] = ki_meta
                    return data

    return {}


def load_independent_knowledge(
    conn: sqlite3.Connection,
    strategy_id: str,
) -> dict[str, Any]:
    if not table_exists(conn, "knowledge_items"):
        raise RuntimeError("knowledge_items tablosu bulunamadı.")

    rows = conn.execute(
        """
        SELECT *
        FROM knowledge_items
        WHERE id=693
        LIMIT 1
        """
    ).fetchall()

    if rows:
        return dict(rows[0])

    # Fallback: resolve by metadata strategy_id + independent tags.
    cols = table_columns(conn, "knowledge_items")
    select_cols = ["id"]
    for col in ("title", "summary", "content", "confidence", "metadata_json", "tags_json"):
        if col in cols:
            select_cols.append(col)

    rows = conn.execute(
        f"SELECT {', '.join(select_cols)} FROM knowledge_items ORDER BY id DESC"
    ).fetchall()

    for row in rows:
        data = dict(row)
        meta = parse_json(data.get("metadata_json"))
        tags = []
        try:
            raw_tags = json.loads(norm(data.get("tags_json")) or "[]")
            if isinstance(raw_tags, list):
                tags = [norm(x).lower() for x in raw_tags]
        except (TypeError, ValueError, json.JSONDecodeError):
            pass

        if (
            norm(meta.get("strategy_id")).upper() == strategy_id.upper()
            and (
                "independent_evidence" in tags
                or "strategy_evidence" in tags
            )
        ):
            return data

    return {}


def v6_is_strategy_record(value: Any) -> bool:
    return (
        isinstance(value, dict)
        and bool(value.get("strategy_id") or value.get("id"))
        and isinstance(value.get("ranking"), dict)
    )


def v6_extract_strategy_records(payload: Any) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    seen: set[int] = set()

    def walk(value: Any) -> None:
        if isinstance(value, dict):
            object_id = id(value)
            if object_id in seen:
                return
            seen.add(object_id)

            if v6_is_strategy_record(value):
                records.append(value)

            for child in value.values():
                if isinstance(child, (dict, list)):
                    walk(child)

        elif isinstance(value, list):
            for child in value:
                if isinstance(child, (dict, list)):
                    walk(child)

    walk(payload)
    return records


def v6_get_containers(record: dict[str, Any]) -> list[dict[str, Any]]:
    """
    Selection Engine V2 ile aynı öncelik sırasını kullanır.

    ÖNEMLİ:
    cost değeri V6 ranking içinde `cost_survival` olarak tutuluyor.
    Eski motor yalnızca `cost_survival_ratio` aradığı için 0.00 okuyordu.
    """
    containers: list[dict[str, Any]] = []

    priority = [
        "ranking",
        "consistency",
        "validation",
        "cost_stress",
        "parameter_stability",
        "regime_stability",
        "metrics",
        "summary",
        "research_summary",
        "result",
        "research",
    ]

    for key in priority:
        value = record.get(key)
        if isinstance(value, dict):
            containers.append(value)

    containers.append(record)
    return containers


def v6_find_metric(
    record: dict[str, Any],
    *keys: str,
    default: Any = None,
) -> Any:
    containers = v6_get_containers(record)

    for container in containers:
        for key in keys:
            if key in container:
                return container[key]

    return default


def extract_pipeline_metrics(
    pipeline: dict[str, Any],
    strategy_id: str,
) -> dict[str, Any]:
    records = v6_extract_strategy_records(pipeline)

    target_record: dict[str, Any] | None = None

    for record in records:
        row_id = norm(
            record.get("strategy_id")
            or record.get("id")
        )
        if row_id.upper() == strategy_id.upper():
            target_record = record
            break

    if target_record is None:
        raise RuntimeError(
            f"V6 pipeline içinde strategy_id bulunamadı: {strategy_id}"
        )

    classification = norm(
        v6_find_metric(
            target_record,
            "classification",
            default=target_record.get("classification"),
        )
    ).upper()

    ranking_score = safe_float(
        v6_find_metric(
            target_record,
            "score",
            "ranking_score",
            "v6_ranking_score",
            default=0.0,
        )
    )

    cross_symbol_ratio = safe_float(
        v6_find_metric(
            target_record,
            "cross_symbol_positive_ratio",
            "cross_symbol_ratio",
            "cross_symbol_success_ratio",
            default=0.0,
        )
    )

    average_return = safe_float(
        v6_find_metric(
            target_record,
            "average_return",
            "avg_return",
            "return_percent",
            default=0.0,
        )
    )

    # V6 canonical field is `cost_survival`.
    cost_survival_raw = v6_find_metric(
        target_record,
        "cost_survival",
        "cost_survival_ratio",
        "cost_robustness",
        "cost_robustness_ratio",
        default=None,
    )

    parameter_stability = safe_float(
        v6_find_metric(
            target_record,
            "parameter_stability",
            "parameter_stability_ratio",
            default=0.0,
        )
    )

    regime_stability = safe_float(
        v6_find_metric(
            target_record,
            "regime_stability",
            "regime_stability_ratio",
            default=0.0,
        )
    )

    wfo_positive = safe_int(
        v6_find_metric(
            target_record,
            "wfo_positive_folds",
            "positive_wfo_folds",
            "wfo_positive",
            default=0,
        )
    )

    wfo_negative = safe_int(
        v6_find_metric(
            target_record,
            "wfo_negative_folds",
            "negative_wfo_folds",
            "wfo_negative",
            default=0,
        )
    )

    wfo_inconclusive = safe_int(
        v6_find_metric(
            target_record,
            "wfo_inconclusive_folds",
            "inconclusive_wfo_folds",
            "wfo_inconclusive",
            default=0,
        )
    )

    # Separate ratio key wins when present; otherwise fold counts are used.
    wfo_ratio_raw = v6_find_metric(
        target_record,
        "wfo_positive_ratio",
        "positive_wfo_ratio",
        "wfo_consistency",
        default=None,
    )

    return {
        "strategy_name": norm(
            target_record.get("strategy_name")
            or target_record.get("name")
        ),
        "classification": classification,
        "ranking_score": ranking_score,
        "cross_symbol_ratio": cross_symbol_ratio,
        "average_return": average_return,
        "cost_robustness": (
            safe_float(cost_survival_raw)
            if cost_survival_raw is not None
            else 0.0
        ),
        "cost_metric_key": (
            "cost_survival"
            if "cost_survival" in target_record.get("ranking", {})
            else (
                "cost_survival_ratio"
                if "cost_survival_ratio" in target_record.get("ranking", {})
                else (
                    "cost_robustness"
                    if "cost_robustness" in target_record.get("ranking", {})
                    else "not_found"
                )
            )
        ),
        "parameter_stability": parameter_stability,
        "regime_stability": regime_stability,
        "wfo_positive": wfo_positive,
        "wfo_negative": wfo_negative,
        "wfo_inconclusive": wfo_inconclusive,
        "wfo_positive_ratio": (
            safe_float(wfo_ratio_raw)
            if wfo_ratio_raw is not None
            else (
                wfo_positive
                / (wfo_positive + wfo_negative + wfo_inconclusive)
                if (wfo_positive + wfo_negative + wfo_inconclusive) > 0
                else 0.0
            )
        ),
        "source_record_strategy_id": norm(
            target_record.get("strategy_id")
            or target_record.get("id")
        ),
    }

def build_independent_metrics(
    knowledge: dict[str, Any],
) -> dict[str, Any]:
    metadata = parse_json(knowledge.get("metadata_json"))
    summary = metadata.get("summary", {})
    if not isinstance(summary, dict):
        summary = {}

    return {
        "symbols_tested": safe_int(summary.get("symbols_tested")),
        "positive_full_runs": safe_int(summary.get("positive_full_runs")),
        "negative_full_runs": safe_int(summary.get("negative_full_runs")),
        "cost_survivors": safe_int(summary.get("cost_survivors")),
        "total_holdout_folds": safe_int(summary.get("total_holdout_folds")),
        "positive_holdout_folds": safe_int(summary.get("positive_holdout_folds")),
        "strategy_id": norm(metadata.get("strategy_id")),
        "strategy_name": norm(metadata.get("strategy_name")),
        "verified": bool(metadata.get("verified", False)),
        "research_derived": bool(metadata.get("research_derived", False)),
    }


def normalized_ratio(value: float) -> float:
    if value > 1.0:
        return max(0.0, min(1.0, value / 100.0))
    return max(0.0, min(1.0, value))


def evaluate_decision(
    strategy_review: dict[str, Any],
    independent: dict[str, Any],
    pipeline: dict[str, Any],
) -> dict[str, Any]:
    review_verdict = norm(strategy_review.get("verdict")).upper()
    review_score = safe_float(strategy_review.get("score"))

    cross_symbol = normalized_ratio(
        safe_float(pipeline.get("cross_symbol_ratio"))
    )
    cost_robustness = normalized_ratio(
        safe_float(pipeline.get("cost_robustness"))
    )
    parameter_stability = normalized_ratio(
        safe_float(pipeline.get("parameter_stability"))
    )
    regime_stability = normalized_ratio(
        safe_float(pipeline.get("regime_stability"))
    )

    holdout_total = safe_int(independent.get("total_holdout_folds"))
    holdout_positive = safe_int(independent.get("positive_holdout_folds"))
    holdout_ratio = (
        holdout_positive / holdout_total
        if holdout_total > 0
        else 0.0
    )

    symbols = safe_int(independent.get("symbols_tested"))
    positive_full = safe_int(independent.get("positive_full_runs"))
    full_symbol_ratio = (
        positive_full / symbols
        if symbols > 0
        else 0.0
    )

    # Composite research score is deliberately conservative.
    evidence_component = min(max(review_score, 0.0), 1.0)
    robustness_component = (
        cross_symbol
        + cost_robustness
        + parameter_stability
        + regime_stability
    ) / 4.0
    holdout_component = holdout_ratio
    full_run_component = full_symbol_ratio

    composite = (
        0.35 * evidence_component
        + 0.30 * robustness_component
        + 0.20 * holdout_component
        + 0.15 * full_run_component
    )

    reasons: list[str] = []

    if review_verdict == "SUPPORTIVE":
        reasons.append("Strategy-level independent evidence is supportive.")
    elif review_verdict == "PARTIALLY_SUPPORTIVE":
        reasons.append("Independent strategy evidence is only partially supportive.")
    elif review_verdict == "CONTRADICTORY":
        reasons.append("Independent evidence contains a contradiction.")
    else:
        reasons.append("Independent strategy evidence remains insufficient.")

    if cross_symbol < 0.60:
        reasons.append(
            f"Cross-symbol success ratio is only {cross_symbol:.2%}."
        )

    if cost_robustness < 0.50:
        reasons.append(
            f"Cost robustness is only {cost_robustness:.2%}."
        )

    if parameter_stability < 0.50:
        reasons.append(
            f"Parameter stability is only {parameter_stability:.2%}."
        )

    if regime_stability < 0.50:
        reasons.append(
            f"Regime stability is only {regime_stability:.2%}."
        )

    if holdout_ratio < 0.55:
        reasons.append(
            f"Independent holdout positive ratio is only {holdout_ratio:.2%}."
        )

    if review_verdict == "CONTRADICTORY":
        decision = "REJECT_RESEARCH_CANDIDATE"
    elif composite >= 0.72 and review_verdict == "SUPPORTIVE":
        decision = "PROMISING_RESEARCH_CANDIDATE"
    elif composite >= 0.45:
        decision = "MIXED_NEEDS_MORE_RESEARCH"
    elif composite >= 0.25:
        decision = "WEAK_RESEARCH_CANDIDATE"
    else:
        decision = "REJECT_RESEARCH_CANDIDATE"

    # Hard conservative gates.
    if (
        review_verdict != "SUPPORTIVE"
        and decision == "PROMISING_RESEARCH_CANDIDATE"
    ):
        decision = "MIXED_NEEDS_MORE_RESEARCH"

    if (
        cost_robustness < 0.25
        or parameter_stability < 0.25
        or regime_stability < 0.25
    ):
        if decision == "PROMISING_RESEARCH_CANDIDATE":
            decision = "MIXED_NEEDS_MORE_RESEARCH"

    action = {
        "PROMISING_RESEARCH_CANDIDATE": "PAPER_RESEARCH_CONTINUE",
        "MIXED_NEEDS_MORE_RESEARCH": "RESEARCH_MORE_INDEPENDENT_EVIDENCE",
        "WEAK_RESEARCH_CANDIDATE": "RESEARCH_MORE_OR_DEPRIORITIZE",
        "REJECT_RESEARCH_CANDIDATE": "DEPRIORITIZE_RESEARCH",
    }[decision]

    confidence = min(
        1.0,
        0.50
        + 0.25 * evidence_component
        + 0.25 * robustness_component,
    )

    return {
        "decision": decision,
        "action": action,
        "composite_score": round(composite, 4),
        "decision_confidence": round(confidence, 4),
        "strategy_review_verdict": review_verdict,
        "strategy_review_score": round(review_score, 4),
        "cross_symbol_ratio": round(cross_symbol, 4),
        "cost_robustness": round(cost_robustness, 4),
        "parameter_stability": round(parameter_stability, 4),
        "regime_stability": round(regime_stability, 4),
        "independent_holdout_ratio": round(holdout_ratio, 4),
        "independent_full_run_ratio": round(full_symbol_ratio, 4),
        "reasons": reasons,
        "next_research_question": (
            "Can a fresh independent historical slice reproduce the "
            "strategy edge while preserving the same rule definition, "
            "cost model and regime robustness?"
        ),
    }


def ensure_decision_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS brain_final_research_decisions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            strategy_id TEXT NOT NULL,
            knowledge_item_id INTEGER,
            strategy_review_id INTEGER,
            decision TEXT NOT NULL,
            action TEXT NOT NULL,
            composite_score REAL NOT NULL,
            decision_confidence REAL NOT NULL,
            decision_json TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )

    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS
        idx_final_research_decisions_strategy
        ON brain_final_research_decisions(strategy_id)
        """
    )


def save_decision(
    conn: sqlite3.Connection,
    strategy_id: str,
    knowledge_item_id: int,
    strategy_review_id: int,
    result: dict[str, Any],
) -> int:
    cur = conn.execute(
        """
        INSERT INTO brain_final_research_decisions (
            strategy_id,
            knowledge_item_id,
            strategy_review_id,
            decision,
            action,
            composite_score,
            decision_confidence,
            decision_json,
            created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            strategy_id,
            knowledge_item_id or None,
            strategy_review_id or None,
            result["decision"],
            result["action"],
            safe_float(result["composite_score"]),
            safe_float(result["decision_confidence"]),
            compact_json(result),
            utc_now(),
        ),
    )
    return safe_int(cur.lastrowid)


def main() -> int:
    conn = open_db()

    try:
        strategy_id = TARGET_STRATEGY_ID

        strategy_review = load_strategy_review(
            conn,
            strategy_id,
        )
        if not strategy_review:
            raise RuntimeError(
                f"Strategy review bulunamadı: {strategy_id}"
            )

        knowledge_item_id = safe_int(
            strategy_review.get("knowledge_item_id")
        )

        independent_knowledge = load_independent_knowledge(
            conn,
            strategy_id,
        )

        if not independent_knowledge:
            raise RuntimeError(
                "Independent evidence knowledge kaydı bulunamadı."
            )

        independent_metrics = build_independent_metrics(
            independent_knowledge
        )

        pipeline_path = find_latest_pipeline_result()
        pipeline_data = load_json_file(pipeline_path)
        pipeline_metrics = extract_pipeline_metrics(
            pipeline_data,
            strategy_id,
        )

        decision = evaluate_decision(
            strategy_review,
            independent_metrics,
            pipeline_metrics,
        )

        ensure_decision_table(conn)

        # Audit-safe idempotence:
        # - If the exact same computed decision already exists, reuse it.
        # - If the same strategy/review exists but the corrected metric parsing
        #   changes the decision payload, create a new record rather than
        #   hiding the corrected result behind the old record.
        review_id = safe_int(strategy_review.get("id"))

        existing_rows = conn.execute(
            """
            SELECT id, decision_json
            FROM brain_final_research_decisions
            WHERE strategy_id=?
              AND strategy_review_id=?
            ORDER BY id DESC
            """,
            (strategy_id, review_id),
        ).fetchall()

        current_signature = compact_json(decision)
        matching_id = None

        for row in existing_rows:
            stored = parse_json(row["decision_json"])
            if compact_json(stored) == current_signature:
                matching_id = safe_int(row["id"])
                break

        if matching_id is not None:
            decision_id = matching_id
            status = "already_present"
        else:
            decision_id = save_decision(
                conn,
                strategy_id,
                knowledge_item_id,
                review_id,
                decision,
            )
            status = (
                "created_corrected"
                if existing_rows
                else "created"
            )

        conn.commit()

        print("=" * 76)
        print("MARKETHQ FINAL RESEARCH DECISION ENGINE V1.1")
        print("=" * 76)
        print()
        print(f"Database        : {DB_PATH}")
        print(f"Strategy        : {strategy_id}")
        print(f"Strategy review : {safe_int(strategy_review.get('id'))}")
        print(f"Knowledge item  : {knowledge_item_id}")
        print(f"Pipeline file   : {pipeline_path}")
        print()
        print("EVIDENCE")
        print("-" * 76)
        print(
            f"Strategy review verdict : "
            f"{norm(strategy_review.get('verdict')).upper()}"
        )
        print(
            f"Strategy review score   : "
            f"{safe_float(strategy_review.get('score')):.3f}"
        )
        print(
            f"Independent symbols     : "
            f"{safe_int(independent_metrics.get('symbols_tested'))}"
        )
        print(
            f"Independent positive    : "
            f"{safe_int(independent_metrics.get('positive_full_runs'))}"
        )
        print(
            f"Independent holdout    : "
            f"{safe_int(independent_metrics.get('positive_holdout_folds'))}/"
            f"{safe_int(independent_metrics.get('total_holdout_folds'))}"
        )
        print()
        print("ROBUSTNESS")
        print("-" * 76)
        print(
            f"Cross-symbol ratio      : "
            f"{pipeline_metrics['cross_symbol_ratio']:.2%}"
        )
        print(
            f"Cost robustness         : "
            f"{pipeline_metrics['cost_robustness']:.2%}"
        )
        print(
            f"Cost metric source      : "
            f"{pipeline_metrics.get('cost_metric_key', 'unknown')}"
        )
        print(
            f"Parameter stability     : "
            f"{pipeline_metrics['parameter_stability']:.2%}"
        )
        print(
            f"Regime stability        : "
            f"{pipeline_metrics['regime_stability']:.2%}"
        )
        print()
        print("FINAL DECISION")
        print("-" * 76)
        print(f"Decision                 : {decision['decision']}")
        print(f"Action                   : {decision['action']}")
        print(f"Composite score          : {decision['composite_score']:.4f}")
        print(f"Decision confidence      : {decision['decision_confidence']:.4f}")
        print()
        for reason in decision["reasons"]:
            print(f"- {reason}")
        print()
        print(
            f"Decision record          : {decision_id} ({status})"
        )
        print()
        print("SAFETY")
        print("-" * 76)
        print("Research Only            : True")
        print("Execution Enabled        : False")
        print("learned_rules            : unchanged")
        print("claims                   : unchanged")
        print("validations              : unchanged")
        print("observations             : unchanged")
        print("Knowledge Verified       : unchanged")
        print()
        print(
            "Next research question   : "
            + decision["next_research_question"]
        )

        OUTPUT_DIR.mkdir(
            parents=True,
            exist_ok=True,
        )

        output_path = (
            OUTPUT_DIR
            / (
                f"final_decision_{strategy_id}_"
                f"{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            )
        )

        payload = {
            "engine": ENGINE_NAME,
            "engine_version": ENGINE_VERSION,
            "created_at": utc_now(),
            "strategy_id": strategy_id,
            "strategy_review": {
                "id": safe_int(strategy_review.get("id")),
                "knowledge_item_id": knowledge_item_id,
                "verdict": norm(strategy_review.get("verdict")).upper(),
                "score": safe_float(strategy_review.get("score")),
            },
            "independent_metrics": independent_metrics,
            "pipeline_metrics": pipeline_metrics,
            "pipeline_metric_source": pipeline_metrics.get(
                "cost_metric_key",
                "unknown",
            ),
            "decision": decision,
            "decision_record_id": decision_id,
            "research_only": True,
            "execution_enabled": False,
        }

        output_path.write_text(
            json.dumps(
                payload,
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

        print()
        print(f"Saved decision JSON    : {output_path}")

        return 0

    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())

