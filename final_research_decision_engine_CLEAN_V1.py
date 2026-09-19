# -*- coding: utf-8 -*-
"""
MarketHQ Final Research Decision Engine - CLEAN V1
==================================================

Amaç
-----
Strategy-level evidence review + independent evidence + V6 ranking
metriklerini birleştirerek research-only final karar üretir.

GÜVENLİK
--------
- Research only.
- Gerçek emir yok.
- Broker bağlantısı yok.
- learned_rules değişmez.
- claims değişmez.
- validations değişmez.
- brain_observations değişmez.
- knowledge verification değişmez.

ÖNEMLİ TASARIM
--------------
V6'nın canonical ranking alanları doğrudan `ranking` objesinden okunur.

Özellikle:
    ranking.cost_survival

alanı cost robustness olarak kullanılır.

Bu sürüm cost alanı bulunamadığında 0.00 üretip sessizce devam ETMEZ;
açık hata verir. Böylece yanlış metric path ile karar üretme riski azaltılır.

Çalıştırma
----------
.venv\\Scripts\\python.exe .\\final_research_decision_engine_CLEAN_V1.py
"""

from __future__ import annotations

import json
import math
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


# ============================================================================
# CONFIG
# ============================================================================

PROJECT_ROOT = Path(__file__).resolve().parent
DB_PATH = PROJECT_ROOT / "market_hq.db"
PIPELINE_DIR = PROJECT_ROOT / "strategy_pipeline_results"
OUTPUT_DIR = PROJECT_ROOT / "final_research_decisions"

ENGINE_NAME = "MARKETHQ_FINAL_RESEARCH_DECISION"
ENGINE_VERSION = "CLEAN_V1"

TARGET_STRATEGY_ID = "STR-43839FA9C6"

RESEARCH_ONLY = True
EXECUTION_ENABLED = False

# Composite weights
WEIGHT_EVIDENCE = 0.35
WEIGHT_ROBUSTNESS = 0.30
WEIGHT_HOLDOUT = 0.20
WEIGHT_FULL_RUN = 0.15


# ============================================================================
# BASIC HELPERS
# ============================================================================

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
        number = float(value)
        if math.isfinite(number):
            return number
    except (TypeError, ValueError):
        pass
    return default


def clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


def normalize_ratio(value: Any) -> float:
    number = safe_float(value)
    if number > 1.0:
        number /= 100.0
    return clamp01(number)


def parse_json(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value

    text = norm(value)
    if not text:
        return {}

    try:
        parsed = json.loads(text)
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}

    return parsed if isinstance(parsed, dict) else {}


def compact_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
        default=str,
    )


# ============================================================================
# SAFETY
# ============================================================================

def assert_research_only() -> None:
    if not RESEARCH_ONLY:
        raise RuntimeError("Safety gate: RESEARCH_ONLY=False.")

    if EXECUTION_ENABLED:
        raise RuntimeError("Safety gate: EXECUTION_ENABLED=True.")


# ============================================================================
# DATABASE
# ============================================================================

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
        WHERE type='table'
          AND name=?
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


# ============================================================================
# V6 PIPELINE
# ============================================================================

def latest_pipeline_file() -> Path:
    if not PIPELINE_DIR.exists():
        raise FileNotFoundError(
            f"Pipeline klasörü bulunamadı: {PIPELINE_DIR}"
        )

    files = sorted(
        PIPELINE_DIR.glob("strategy_pipeline_v6_*.json"),
        key=lambda item: item.stat().st_mtime,
        reverse=True,
    )

    if not files:
        raise FileNotFoundError(
            f"V6 JSON bulunamadı: {PIPELINE_DIR}"
        )

    return files[0]


def load_json_file(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(
            f"Pipeline JSON okunamadı: {path}\n{exc}"
        ) from exc


def is_strategy_record(value: Any) -> bool:
    return (
        isinstance(value, dict)
        and bool(
            value.get("strategy_id")
            or value.get("id")
        )
        and isinstance(value.get("ranking"), dict)
    )


def extract_strategy_records(payload: Any) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    seen: set[int] = set()

    def walk(value: Any) -> None:
        if isinstance(value, dict):
            object_id = id(value)
            if object_id in seen:
                return

            seen.add(object_id)

            if is_strategy_record(value):
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


def find_strategy_record(
    payload: Any,
    strategy_id: str,
) -> dict[str, Any]:
    records = extract_strategy_records(payload)

    for record in records:
        record_id = norm(
            record.get("strategy_id")
            or record.get("id")
        )

        if record_id.upper() == strategy_id.upper():
            return record

    raise RuntimeError(
        f"V6 pipeline içinde strategy_id bulunamadı: {strategy_id}"
    )


def read_required_ranking_metric(
    ranking: dict[str, Any],
    metric_name: str,
    aliases: tuple[str, ...] = (),
) -> tuple[float, str]:
    keys = (metric_name, *aliases)

    for key in keys:
        if key in ranking:
            value = ranking[key]

            if value is None:
                raise RuntimeError(
                    f"V6 ranking.{key} değeri None."
                )

            return safe_float(value), key

    raise RuntimeError(
        "V6 canonical metric bulunamadı. "
        f"Beklenen alanlar: {', '.join(keys)}"
    )


def extract_v6_metrics(
    payload: Any,
    strategy_id: str,
) -> dict[str, Any]:
    record = find_strategy_record(payload, strategy_id)
    ranking = record["ranking"]

    ranking_score, ranking_score_key = read_required_ranking_metric(
        ranking,
        "score",
        ("ranking_score", "v6_ranking_score"),
    )

    cross_symbol, cross_key = read_required_ranking_metric(
        ranking,
        "cross_symbol_positive_ratio",
        ("cross_symbol_ratio", "cross_symbol_success_ratio"),
    )

    average_return, average_return_key = read_required_ranking_metric(
        ranking,
        "average_return",
        ("avg_return", "return_percent"),
    )

    # KESİN: V6 pipeline'ın canonical cost alanı ranking.cost_survival.
    cost_survival, cost_key = read_required_ranking_metric(
        ranking,
        "cost_survival",
        ("cost_survival_ratio", "cost_robustness", "cost_robustness_ratio"),
    )

    parameter_stability, parameter_key = read_required_ranking_metric(
        ranking,
        "parameter_stability",
        ("parameter_stability_ratio",),
    )

    regime_stability, regime_key = read_required_ranking_metric(
        ranking,
        "regime_stability",
        ("regime_stability_ratio",),
    )

    wfo_positive, wfo_positive_key = read_required_ranking_metric(
        ranking,
        "wfo_positive_ratio",
        ("positive_wfo_ratio", "wfo_consistency"),
    )

    return {
        "strategy_id": norm(
            record.get("strategy_id")
            or record.get("id")
        ),
        "strategy_name": norm(
            record.get("strategy_name")
            or record.get("name")
            or record.get("title")
        ),
        "classification": norm(
            ranking.get("classification")
            or record.get("classification")
        ).upper(),
        "ranking_score": ranking_score,
        "ranking_score_key": ranking_score_key,
        "cross_symbol_ratio": normalize_ratio(cross_symbol),
        "cross_symbol_key": cross_key,
        "average_return": average_return,
        "average_return_key": average_return_key,
        "cost_robustness": normalize_ratio(cost_survival),
        "cost_metric_key": cost_key,
        "parameter_stability": normalize_ratio(parameter_stability),
        "parameter_metric_key": parameter_key,
        "regime_stability": normalize_ratio(regime_stability),
        "regime_metric_key": regime_key,
        "wfo_positive_ratio": normalize_ratio(wfo_positive),
        "wfo_positive_metric_key": wfo_positive_key,
    }


# ============================================================================
# DATABASE EVIDENCE
# ============================================================================

def load_strategy_review(
    conn: sqlite3.Connection,
    strategy_id: str,
) -> dict[str, Any]:
    table = "brain_research_strategy_evidence_reviews"

    if not table_exists(conn, table):
        raise RuntimeError(f"{table} tablosu bulunamadı.")

    cols = table_columns(conn, table)

    required = {
        "id",
        "knowledge_item_id",
        "verdict",
        "score",
    }

    if not required.issubset(cols):
        missing = sorted(required - cols)
        raise RuntimeError(
            f"{table} eksik kolonlar: {missing}"
        )

    rows = conn.execute(
        f"SELECT * FROM {table} ORDER BY id DESC"
    ).fetchall()

    for row in rows:
        data = dict(row)
        metadata = parse_json(data.get("metadata_json"))

        row_strategy = norm(
            data.get("strategy_id")
            or metadata.get("strategy_id")
        )

        if row_strategy.upper() == strategy_id.upper():
            data["metadata"] = metadata
            return data

        knowledge_id = safe_int(
            data.get("knowledge_item_id")
        )

        if knowledge_id and table_exists(conn, "knowledge_items"):
            knowledge_row = conn.execute(
                """
                SELECT metadata_json
                FROM knowledge_items
                WHERE id=?
                LIMIT 1
                """,
                (knowledge_id,),
            ).fetchone()

            if knowledge_row:
                knowledge_meta = parse_json(
                    knowledge_row["metadata_json"]
                )

                if (
                    norm(
                        knowledge_meta.get("strategy_id")
                    ).upper()
                    == strategy_id.upper()
                ):
                    data["metadata"] = metadata
                    data["knowledge_metadata"] = knowledge_meta
                    return data

    raise RuntimeError(
        f"Strategy review bulunamadı: {strategy_id}"
    )


def tags_from_row(row: dict[str, Any]) -> set[str]:
    raw = row.get("tags_json")
    if isinstance(raw, list):
        return {
            norm(item).lower()
            for item in raw
        }

    text = norm(raw)
    if not text:
        return set()

    try:
        parsed = json.loads(text)
    except (TypeError, ValueError, json.JSONDecodeError):
        return set()

    if not isinstance(parsed, list):
        return set()

    return {
        norm(item).lower()
        for item in parsed
    }


def load_independent_knowledge(
    conn: sqlite3.Connection,
    strategy_id: str,
) -> dict[str, Any]:
    table = "knowledge_items"

    if not table_exists(conn, table):
        raise RuntimeError("knowledge_items tablosu bulunamadı.")

    rows = conn.execute(
        f"SELECT * FROM {table} ORDER BY id DESC"
    ).fetchall()

    candidates: list[dict[str, Any]] = []

    for row in rows:
        data = dict(row)
        metadata = parse_json(
            data.get("metadata_json")
        )

        row_strategy = norm(
            metadata.get("strategy_id")
        )

        tags = tags_from_row(data)

        independent_marker = (
            "independent_evidence" in tags
            or "strategy_evidence" in tags
            or bool(metadata.get("independent_evidence"))
        )

        if (
            row_strategy.upper() == strategy_id.upper()
            and independent_marker
        ):
            data["metadata"] = metadata
            candidates.append(data)

    if not candidates:
        raise RuntimeError(
            "Bağımsız strategy evidence knowledge kaydı bulunamadı."
        )

    return candidates[0]


def build_independent_metrics(
    knowledge: dict[str, Any],
) -> dict[str, Any]:
    metadata = knowledge.get("metadata")
    if not isinstance(metadata, dict):
        metadata = parse_json(
            knowledge.get("metadata_json")
        )

    summary = metadata.get("summary")
    if not isinstance(summary, dict):
        summary = {}

    symbols_tested = safe_int(
        summary.get("symbols_tested")
    )
    positive_full_runs = safe_int(
        summary.get("positive_full_runs")
    )
    total_holdout = safe_int(
        summary.get("total_holdout_folds")
    )
    positive_holdout = safe_int(
        summary.get("positive_holdout_folds")
    )

    if symbols_tested <= 0:
        raise RuntimeError(
            "Independent evidence: symbols_tested geçersiz."
        )

    if total_holdout <= 0:
        raise RuntimeError(
            "Independent evidence: total_holdout_folds geçersiz."
        )

    return {
        "knowledge_item_id": safe_int(
            knowledge.get("id")
        ),
        "symbols_tested": symbols_tested,
        "positive_full_runs": positive_full_runs,
        "negative_full_runs": safe_int(
            summary.get("negative_full_runs")
        ),
        "cost_survivors": safe_int(
            summary.get("cost_survivors")
        ),
        "total_holdout_folds": total_holdout,
        "positive_holdout_folds": positive_holdout,
        "full_run_ratio": clamp01(
            positive_full_runs / symbols_tested
        ),
        "holdout_ratio": clamp01(
            positive_holdout / total_holdout
        ),
        "strategy_id": norm(
            metadata.get("strategy_id")
        ),
        "strategy_name": norm(
            metadata.get("strategy_name")
        ),
        "verified": bool(
            metadata.get("verified", False)
        ),
        "research_derived": bool(
            metadata.get("research_derived", False)
        ),
    }


# ============================================================================
# DECISION
# ============================================================================

def evaluate_decision(
    review: dict[str, Any],
    independent: dict[str, Any],
    v6: dict[str, Any],
) -> dict[str, Any]:
    review_verdict = norm(
        review.get("verdict")
    ).upper()

    review_score = clamp01(
        safe_float(review.get("score"))
    )

    cross_symbol = clamp01(
        safe_float(v6["cross_symbol_ratio"])
    )
    cost = clamp01(
        safe_float(v6["cost_robustness"])
    )
    parameter = clamp01(
        safe_float(v6["parameter_stability"])
    )
    regime = clamp01(
        safe_float(v6["regime_stability"])
    )

    holdout = clamp01(
        safe_float(independent["holdout_ratio"])
    )
    full_run = clamp01(
        safe_float(independent["full_run_ratio"])
    )

    robustness = (
        cross_symbol
        + cost
        + parameter
        + regime
    ) / 4.0

    composite = (
        WEIGHT_EVIDENCE * review_score
        + WEIGHT_ROBUSTNESS * robustness
        + WEIGHT_HOLDOUT * holdout
        + WEIGHT_FULL_RUN * full_run
    )

    reasons: list[str] = []

    if review_verdict == "SUPPORTIVE":
        reasons.append(
            "Strategy-level independent evidence is supportive."
        )
    elif review_verdict == "PARTIALLY_SUPPORTIVE":
        reasons.append(
            "Independent strategy evidence is only partially supportive."
        )
    elif review_verdict == "CONTRADICTORY":
        reasons.append(
            "Independent evidence contains a contradiction."
        )
    else:
        reasons.append(
            "Independent strategy evidence remains insufficient."
        )

    if cross_symbol < 0.60:
        reasons.append(
            f"Cross-symbol success ratio is only {cross_symbol:.2%}."
        )

    if cost < 0.50:
        reasons.append(
            f"Cost robustness is only {cost:.2%}."
        )

    if parameter < 0.50:
        reasons.append(
            f"Parameter stability is only {parameter:.2%}."
        )

    if regime < 0.50:
        reasons.append(
            f"Regime stability is only {regime:.2%}."
        )

    if holdout < 0.55:
        reasons.append(
            "Independent holdout positive ratio is only "
            f"{holdout:.2%}."
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

    # Conservative gate:
    if (
        review_verdict != "SUPPORTIVE"
        and decision == "PROMISING_RESEARCH_CANDIDATE"
    ):
        decision = "MIXED_NEEDS_MORE_RESEARCH"

    # Very weak robustness blocks a promising decision.
    if (
        cost < 0.25
        or parameter < 0.25
        or regime < 0.25
    ):
        if decision == "PROMISING_RESEARCH_CANDIDATE":
            decision = "MIXED_NEEDS_MORE_RESEARCH"

    actions = {
        "PROMISING_RESEARCH_CANDIDATE": "PAPER_RESEARCH_CONTINUE",
        "MIXED_NEEDS_MORE_RESEARCH": (
            "RESEARCH_MORE_INDEPENDENT_EVIDENCE"
        ),
        "WEAK_RESEARCH_CANDIDATE": (
            "RESEARCH_MORE_OR_DEPRIORITIZE"
        ),
        "REJECT_RESEARCH_CANDIDATE": (
            "DEPRIORITIZE_RESEARCH"
        ),
    }

    confidence = min(
        1.0,
        0.50
        + 0.25 * review_score
        + 0.25 * robustness,
    )

    return {
        "decision": decision,
        "action": actions[decision],
        "composite_score": round(composite, 4),
        "decision_confidence": round(confidence, 4),
        "strategy_review_verdict": review_verdict,
        "strategy_review_score": round(review_score, 4),
        "cross_symbol_ratio": round(cross_symbol, 4),
        "cost_robustness": round(cost, 4),
        "parameter_stability": round(parameter, 4),
        "regime_stability": round(regime, 4),
        "independent_holdout_ratio": round(holdout, 4),
        "independent_full_run_ratio": round(full_run, 4),
        "reasons": reasons,
        "next_research_question": (
            "Can a fresh independent historical slice reproduce "
            "the strategy edge while preserving the same rule "
            "definition, cost model and regime robustness?"
        ),
    }


# ============================================================================
# DECISION TABLE
# ============================================================================

def ensure_decision_table(
    conn: sqlite3.Connection,
) -> None:
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
    cursor = conn.execute(
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

    return safe_int(cursor.lastrowid)


def find_matching_decision(
    conn: sqlite3.Connection,
    strategy_id: str,
    strategy_review_id: int,
    result: dict[str, Any],
) -> tuple[int | None, int]:
    rows = conn.execute(
        """
        SELECT id, decision_json
        FROM brain_final_research_decisions
        WHERE strategy_id=?
          AND strategy_review_id=?
        ORDER BY id DESC
        """,
        (
            strategy_id,
            strategy_review_id,
        ),
    ).fetchall()

    target_signature = compact_json(result)

    for row in rows:
        stored = parse_json(
            row["decision_json"]
        )

        if compact_json(stored) == target_signature:
            return safe_int(row["id"]), len(rows)

    return None, len(rows)


# ============================================================================
# REPORT
# ============================================================================

def print_report(
    strategy_id: str,
    review: dict[str, Any],
    independent: dict[str, Any],
    v6: dict[str, Any],
    decision: dict[str, Any],
    pipeline_path: Path,
    decision_id: int,
    status: str,
) -> None:
    print("=" * 78)
    print("MARKETHQ FINAL RESEARCH DECISION ENGINE CLEAN V1")
    print("=" * 78)
    print()

    print(f"Database        : {DB_PATH}")
    print(f"Strategy        : {strategy_id}")
    print(
        f"Strategy review : "
        f"{safe_int(review.get('id'))}"
    )
    print(
        f"Knowledge item  : "
        f"{safe_int(review.get('knowledge_item_id'))}"
    )
    print(f"Pipeline file   : {pipeline_path}")
    print()

    print("EVIDENCE")
    print("-" * 78)
    print(
        "Strategy review verdict : "
        f"{norm(review.get('verdict')).upper()}"
    )
    print(
        "Strategy review score   : "
        f"{safe_float(review.get('score')):.3f}"
    )
    print(
        "Independent symbols     : "
        f"{independent['symbols_tested']}"
    )
    print(
        "Independent positive    : "
        f"{independent['positive_full_runs']}"
    )
    print(
        "Independent holdout    : "
        f"{independent['positive_holdout_folds']}/"
        f"{independent['total_holdout_folds']}"
    )
    print()

    print("ROBUSTNESS")
    print("-" * 78)
    print(
        "Cross-symbol ratio      : "
        f"{v6['cross_symbol_ratio']:.2%} "
        f"[{v6['cross_symbol_key']}]"
    )
    print(
        "Cost robustness         : "
        f"{v6['cost_robustness']:.2%} "
        f"[ranking.{v6['cost_metric_key']}]"
    )
    print(
        "Parameter stability     : "
        f"{v6['parameter_stability']:.2%} "
        f"[{v6['parameter_metric_key']}]"
    )
    print(
        "Regime stability        : "
        f"{v6['regime_stability']:.2%} "
        f"[{v6['regime_metric_key']}]"
    )
    print()

    print("V6 SOURCE CHECK")
    print("-" * 78)
    print(
        f"V6 classification       : "
        f"{v6['classification']}"
    )
    print(
        f"V6 ranking score        : "
        f"{v6['ranking_score']:.4f}"
    )
    print(
        f"V6 average return      : "
        f"{v6['average_return']:.4f}"
    )
    print(
        f"V6 WFO positive ratio  : "
        f"{v6['wfo_positive_ratio']:.2%}"
    )
    print()

    print("FINAL DECISION")
    print("-" * 78)
    print(
        f"Decision                 : "
        f"{decision['decision']}"
    )
    print(
        f"Action                   : "
        f"{decision['action']}"
    )
    print(
        f"Composite score          : "
        f"{decision['composite_score']:.4f}"
    )
    print(
        f"Decision confidence      : "
        f"{decision['decision_confidence']:.4f}"
    )
    print()

    for reason in decision["reasons"]:
        print(f"- {reason}")

    print()
    print(
        f"Decision record          : "
        f"{decision_id} ({status})"
    )
    print()

    print("SAFETY")
    print("-" * 78)
    print(f"Research Only            : {RESEARCH_ONLY}")
    print(
        f"Execution Enabled        : "
        f"{EXECUTION_ENABLED}"
    )
    print("learned_rules            : unchanged")
    print("claims                   : unchanged")
    print("validations              : unchanged")
    print("observations             : unchanged")
    print("Knowledge Verified       : unchanged")
    print()

    print(
        "Next research question   : "
        f"{decision['next_research_question']}"
    )


# ============================================================================
# MAIN
# ============================================================================

def main() -> int:
    assert_research_only()

    pipeline_path = latest_pipeline_file()
    pipeline_payload = load_json_file(
        pipeline_path
    )

    conn = open_db()

    try:
        strategy_id = TARGET_STRATEGY_ID

        review = load_strategy_review(
            conn,
            strategy_id,
        )

        independent_knowledge = load_independent_knowledge(
            conn,
            strategy_id,
        )

        independent = build_independent_metrics(
            independent_knowledge
        )

        v6 = extract_v6_metrics(
            pipeline_payload,
            strategy_id,
        )

        decision = evaluate_decision(
            review,
            independent,
            v6,
        )

        ensure_decision_table(conn)

        review_id = safe_int(
            review.get("id")
        )

        existing_id, existing_count = (
            find_matching_decision(
                conn,
                strategy_id,
                review_id,
                decision,
            )
        )

        if existing_id is not None:
            decision_id = existing_id
            status = "already_present"
        else:
            decision_id = save_decision(
                conn,
                strategy_id,
                safe_int(
                    independent_knowledge.get("id")
                ),
                review_id,
                decision,
            )
            status = (
                "created_corrected"
                if existing_count > 0
                else "created"
            )

        conn.commit()

        print_report(
            strategy_id= strategy_id,
            review=review,
            independent=independent,
            v6=v6,
            decision=decision,
            pipeline_path=pipeline_path,
            decision_id=decision_id,
            status=status,
        )

        OUTPUT_DIR.mkdir(
            parents=True,
            exist_ok=True,
        )

        output_path = OUTPUT_DIR / (
            f"final_decision_{strategy_id}_"
            f"{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        )

        payload = {
            "engine": ENGINE_NAME,
            "engine_version": ENGINE_VERSION,
            "created_at": utc_now(),
            "strategy_id": strategy_id,
            "strategy_review": {
                "id": review_id,
                "knowledge_item_id": safe_int(
                    review.get("knowledge_item_id")
                ),
                "verdict": norm(
                    review.get("verdict")
                ).upper(),
                "score": safe_float(
                    review.get("score")
                ),
            },
            "independent_metrics": independent,
            "v6_metrics": v6,
            "decision": decision,
            "decision_record_id": decision_id,
            "decision_status": status,
            "research_only": True,
            "execution_enabled": False,
        }

        output_path.write_text(
            json.dumps(
                payload,
                ensure_ascii=False,
                indent=2,
                default=str,
            ),
            encoding="utf-8",
        )

        print()
        print(f"Saved decision JSON    : {output_path}")
        print()
        print("RUN STATUS             : SUCCESS")
        return 0

    except Exception as exc:
        conn.rollback()

        print()
        print("=" * 78)
        print("RUN STATUS             : ERROR")
        print("=" * 78)
        print(f"{type(exc).__name__}: {exc}")
        return 1

    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())

