# -*- coding: utf-8 -*-
"""
MarketHQ Learning / Ranking Loop V1
===================================

Amaç
-----
Evidence Consolidation -> Learning Score -> Strategy Ranking

Bu motor:
    - V6 pipeline evidence
    - latest Evidence Consolidation
    - latest Strategy Evidence Review
    - latest Final Research Decision
katmanlarını tek bir learning/ranking kaydında birleştirir.

ÖNEMLİ GÜVENLİK KURALLARI
--------------------------
- Research-only çalışır.
- Canlı emir / broker / execution yapmaz.
- learned_rules tablosuna yazmaz.
- claims / validations / observations değiştirmez.
- Knowledge verification state değiştirmez.
- "LEARNING_CANDIDATE" doğrulanmış learned rule değildir.
- Aynı input fingerprint ile tekrar çalıştırıldığında duplicate ranking
  üretmemek için deterministic idempotency uygulanır.

Karar seviyeleri
----------------
PROMOTE_TO_LEARNING_CANDIDATE
    Güçlü ve yeterli kanıt; yine de doğrulanmış learned rule değildir.

CONTINUE_RESEARCH
    Kanıt kısmen destekliyor ancak bağımsızlık / robustness / review
    katmanlarında daha fazla araştırma gerekir.

DEPRIORITIZE
    Mevcut kanıt stratejiyi sonraki öğrenme aşamasına taşımaya yetmiyor.

Bu sürüm özellikle mevcut stratejinin durumunu ölçmek içindir.
"""

from __future__ import annotations

import hashlib
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
CONSOLIDATION_DIR = PROJECT_ROOT / "evidence_consolidation_results"
FINAL_DECISION_DIR = PROJECT_ROOT / "final_research_decisions"

ENGINE_NAME = "MARKETHQ_LEARNING_RANKING_LOOP"
ENGINE_VERSION = "V1"

TARGET_STRATEGY_ID = "STR-43839FA9C6"

RESEARCH_ONLY = True
EXECUTION_ENABLED = False

# Transparent weights. Holdout is available for the historical independent
# evidence in the current consolidation, so it is included.
WEIGHTS = {
    "independent_consistency": 0.20,
    "holdout_consistency": 0.10,
    "strategy_review": 0.15,
    "cross_symbol_robustness": 0.15,
    "cost_robustness": 0.15,
    "parameter_stability": 0.10,
    "regime_stability": 0.10,
    "v6_rank_score": 0.05,
}

PROMOTE_THRESHOLD = 0.70
CONTINUE_THRESHOLD = 0.40


# ============================================================================
# HELPERS
# ============================================================================

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
        number = float(value)
        if math.isfinite(number):
            return number
    except (TypeError, ValueError):
        pass
    return default


def ratio01(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number):
        return None
    if number > 1.0:
        number /= 100.0
    return max(0.0, min(1.0, number))


def compact_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
        default=str,
    )


def parse_json(value: Any) -> Any:
    if isinstance(value, (dict, list)):
        return value
    text = norm(value)
    if not text:
        return {}
    try:
        return json.loads(text)
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def latest_json(directory: Path, pattern: str) -> Path | None:
    if not directory.exists():
        return None

    candidates = [
        path
        for path in directory.glob(pattern)
        if path.is_file()
    ]

    if not candidates:
        return None

    candidates.sort(
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    return candidates[0]


def load_json_file(path: Path | None) -> Any:
    if path is None or not path.exists():
        return {}

    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


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
        f'PRAGMA table_info("{table_name}")'
    ).fetchall()

    return {
        norm(row["name"])
        for row in rows
    }


def open_db() -> sqlite3.Connection:
    if not DB_PATH.exists():
        raise FileNotFoundError(
            f"market_hq.db bulunamadı: {DB_PATH}"
        )

    conn = sqlite3.connect(
        str(DB_PATH),
        timeout=60,
    )
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout = 60000")
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


# ============================================================================
# SAFETY
# ============================================================================

def assert_research_only() -> None:
    if not RESEARCH_ONLY:
        raise RuntimeError(
            "Safety gate: RESEARCH_ONLY=False"
        )

    if EXECUTION_ENABLED:
        raise RuntimeError(
            "Safety gate: EXECUTION_ENABLED=True"
        )


# ============================================================================
# INPUT: V6 PIPELINE
# ============================================================================

def extract_strategy_record(
    payload: Any,
    strategy_id: str,
) -> dict[str, Any] | None:
    found: dict[str, Any] | None = None

    def walk(obj: Any) -> None:
        nonlocal found

        if found is not None:
            return

        if isinstance(obj, dict):
            current_id = norm(
                obj.get("strategy_id")
                or obj.get("id")
            )

            ranking = obj.get("ranking")

            if (
                current_id.upper() == strategy_id.upper()
                and isinstance(ranking, dict)
            ):
                found = obj
                return

            for value in obj.values():
                if isinstance(value, (dict, list)):
                    walk(value)

                if found is not None:
                    return

        elif isinstance(obj, list):
            for value in obj:
                if isinstance(value, (dict, list)):
                    walk(value)

                if found is not None:
                    return

    walk(payload)
    return found


def load_v6(strategy_id: str) -> dict[str, Any]:
    path = latest_json(
        PIPELINE_DIR,
        "strategy_pipeline_v6_*.json",
    )

    if path is None:
        return {
            "available": False,
            "reason": "V6 pipeline file not found",
        }

    payload = load_json_file(path)
    record = extract_strategy_record(
        payload,
        strategy_id,
    )

    if record is None:
        return {
            "available": False,
            "file": str(path),
            "reason": "Strategy record not found in V6 file",
        }

    ranking = record.get("ranking", {})
    if not isinstance(ranking, dict):
        ranking = {}

    raw_score = safe_float(
        ranking.get("score"),
        0.0,
    )

    # V6 score is not a probability. For the composite it is normalized to
    # a conservative 0..1 research-quality signal using 10 as an upper scale.
    normalized_rank_score = max(
        0.0,
        min(1.0, raw_score / 10.0),
    )

    return {
        "available": True,
        "file": str(path),
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
        "ranking_score": raw_score,
        "normalized_ranking_score": normalized_rank_score,
        "average_return": safe_float(
            ranking.get("average_return")
        ),
        "cross_symbol_ratio": ratio01(
            ranking.get("cross_symbol_positive_ratio")
            if ranking.get("cross_symbol_positive_ratio") is not None
            else ranking.get("cross_symbol_ratio")
        ),
        "cost_robustness": ratio01(
            ranking.get("cost_survival")
        ),
        "parameter_stability": ratio01(
            ranking.get("parameter_stability")
        ),
        "regime_stability": ratio01(
            ranking.get("regime_stability")
        ),
        "wfo_positive_ratio": ratio01(
            ranking.get("wfo_positive_ratio")
            if ranking.get("wfo_positive_ratio") is not None
            else ranking.get("positive_wfo_ratio")
        ),
    }


# ============================================================================
# INPUT: LATEST CONSOLIDATION
# ============================================================================

def load_latest_consolidation(strategy_id: str) -> dict[str, Any]:
    path = latest_json(
        CONSOLIDATION_DIR,
        f"evidence_consolidation_{strategy_id}_*.json",
    )

    if path is None:
        return {
            "available": False,
            "reason": "Evidence consolidation file not found",
        }

    payload = load_json_file(path)

    if not isinstance(payload, dict):
        return {
            "available": False,
            "file": str(path),
            "reason": "Consolidation JSON is not an object",
        }

    if norm(
        payload.get("strategy_id")
    ).upper() != strategy_id.upper():
        return {
            "available": False,
            "file": str(path),
            "reason": "Different strategy_id",
        }

    independent = payload.get(
        "consolidated_independent"
    )
    if not isinstance(independent, dict):
        independent = {}

    interpretation = payload.get(
        "interpretation"
    )
    if not isinstance(interpretation, dict):
        interpretation = {}

    sources = payload.get("sources")
    if not isinstance(sources, dict):
        sources = {}

    return {
        "available": True,
        "file": str(path),
        "created_at": norm(
            payload.get("created_at")
        ),
        "verified": bool(
            payload.get("verified", False)
        ),
        "evidence_records": safe_int(
            independent.get("evidence_records")
        ),
        "symbols_across_records": safe_int(
            independent.get("symbols_across_records")
        ),
        "positive_full_runs": safe_int(
            independent.get("positive_full_runs")
        ),
        "negative_full_runs": safe_int(
            independent.get("negative_full_runs")
        ),
        "pooled_positive_ratio": ratio01(
            independent.get("pooled_positive_ratio")
        ),
        "holdout_positive_folds": safe_int(
            independent.get("holdout_positive_folds")
        ),
        "holdout_total_folds": safe_int(
            independent.get("holdout_total_folds")
        ),
        "holdout_positive_ratio": ratio01(
            independent.get("holdout_positive_ratio")
        ),
        "cross_time_consistency": norm(
            interpretation.get(
                "independent_cross_time_consistency"
            )
        ).upper(),
        "strategy_review_verdict": norm(
            interpretation.get(
                "strategy_review_verdict"
            )
        ).upper(),
        "strategy_review_score": safe_float(
            interpretation.get(
                "strategy_review_score"
            )
        ),
        "sources": sources,
        "next_research_question": norm(
            payload.get("next_research_question")
        ),
    }


# ============================================================================
# INPUT: LATEST FINAL DECISION
# ============================================================================

def load_latest_final_decision(
    strategy_id: str,
) -> dict[str, Any]:
    path = latest_json(
        FINAL_DECISION_DIR,
        f"final_decision_{strategy_id}_*.json",
    )

    if path is None:
        return {
            "available": False,
            "reason": "Final decision file not found",
        }

    payload = load_json_file(path)

    if not isinstance(payload, dict):
        return {
            "available": False,
            "file": str(path),
            "reason": "Final decision JSON is not an object",
        }

    return {
        "available": True,
        "file": str(path),
        "decision": norm(
            payload.get("decision")
        ).upper(),
        "action": norm(
            payload.get("action")
        ).upper(),
        "composite": safe_float(
            payload.get("composite")
        ),
        "confidence": safe_float(
            payload.get("confidence")
        ),
        "knowledge_verified_unchanged": True,
    }


# ============================================================================
# INPUT: STRATEGY-LEVEL REVIEW
# ============================================================================

def load_latest_strategy_review(
    conn: sqlite3.Connection,
    strategy_id: str,
) -> dict[str, Any]:
    table = "brain_research_strategy_evidence_reviews"

    if not table_exists(conn, table):
        return {
            "available": False,
            "reason": f"{table} not found",
        }

    columns = table_columns(
        conn,
        table,
    )

    required = {
        "id",
        "knowledge_item_id",
        "verdict",
        "score",
    }

    if not required.issubset(columns):
        return {
            "available": False,
            "reason": "Strategy review schema incomplete",
        }

    rows = conn.execute(
        f'SELECT * FROM "{table}" ORDER BY id DESC'
    ).fetchall()

    for row in rows:
        data = dict(row)
        metadata = parse_json(
            data.get("metadata_json")
        )

        row_strategy_id = norm(
            data.get("strategy_id")
        )

        if not row_strategy_id and isinstance(
            metadata,
            dict,
        ):
            row_strategy_id = norm(
                metadata.get("strategy_id")
            )

        if row_strategy_id.upper() == strategy_id.upper():
            return {
                "available": True,
                "review_id": safe_int(
                    data.get("id")
                ),
                "knowledge_item_id": safe_int(
                    data.get("knowledge_item_id")
                ),
                "strategy_id": row_strategy_id,
                "verdict": norm(
                    data.get("verdict")
                ).upper(),
                "score": max(
                    0.0,
                    min(
                        1.0,
                        safe_float(
                            data.get("score")
                        ),
                    ),
                ),
                "review_method": norm(
                    data.get("review_method")
                ),
                "created_at": norm(
                    data.get("created_at")
                ),
            }

        knowledge_id = safe_int(
            data.get("knowledge_item_id")
        )

        if (
            knowledge_id
            and table_exists(
                conn,
                "knowledge_items",
            )
        ):
            knowledge_columns = table_columns(
                conn,
                "knowledge_items",
            )

            wanted = {
                "id",
                "metadata_json",
            }

            if wanted.issubset(knowledge_columns):
                knowledge_row = conn.execute(
                    """
                    SELECT id, metadata_json
                    FROM knowledge_items
                    WHERE id=?
                    LIMIT 1
                    """,
                    (knowledge_id,),
                ).fetchone()

                if knowledge_row:
                    ki_meta = parse_json(
                        knowledge_row["metadata_json"]
                    )

                    if (
                        isinstance(ki_meta, dict)
                        and norm(
                            ki_meta.get("strategy_id")
                        ).upper()
                        == strategy_id.upper()
                    ):
                        return {
                            "available": True,
                            "review_id": safe_int(
                                data.get("id")
                            ),
                            "knowledge_item_id": knowledge_id,
                            "strategy_id": strategy_id,
                            "verdict": norm(
                                data.get("verdict")
                            ).upper(),
                            "score": max(
                                0.0,
                                min(
                                    1.0,
                                    safe_float(
                                        data.get("score")
                                    ),
                                ),
                            ),
                            "review_method": norm(
                                data.get(
                                    "review_method"
                                )
                            ),
                            "created_at": norm(
                                data.get("created_at")
                            ),
                        }

    return {
        "available": False,
        "reason": "No strategy-level review found",
    }


# ============================================================================
# LEARNING SCORE
# ============================================================================

def review_score_to_signal(
    verdict: str,
    score: float,
) -> float:
    """
    Strategy review score is already numeric, but verdict constrains
    interpretation so a contradictory / insufficient review cannot
    accidentally behave like positive evidence.
    """

    verdict = norm(verdict).upper()
    base = max(
        0.0,
        min(
            1.0,
            safe_float(score),
        ),
    )

    if verdict == "SUPPORTIVE":
        return min(1.0, base)

    if verdict == "PARTIALLY_SUPPORTIVE":
        return min(
            1.0,
            base * 0.90,
        )

    if verdict == "INSUFFICIENT":
        return min(
            1.0,
            base * 0.50,
        )

    if verdict == "CONTRADICTORY":
        return 0.0

    return min(
        1.0,
        base * 0.60,
    )


def weighted_average(
    values: dict[str, float | None],
) -> tuple[float, dict[str, float]]:
    """
    Uses only available signals and renormalizes weights across those
    signals. This prevents an unavailable metric from becoming a fake zero.
    """

    weighted_sum = 0.0
    used_weight = 0.0
    contributions: dict[str, float] = {}

    for name, value in values.items():
        weight = safe_float(
            WEIGHTS.get(name),
            0.0,
        )

        if value is None or weight <= 0.0:
            continue

        weighted_sum += value * weight
        used_weight += weight

    if used_weight <= 0.0:
        return 0.0, contributions

    composite = weighted_sum / used_weight

    for name, value in values.items():
        weight = safe_float(
            WEIGHTS.get(name),
            0.0,
        )

        if (
            value is not None
            and weight > 0.0
        ):
            contributions[name] = (
                value * weight / used_weight
            )

    return composite, contributions


def choose_action(
    learning_score: float,
    evidence_records: int,
    review_signal: float,
    cost_robustness: float | None,
    cross_symbol_ratio: float | None,
) -> tuple[str, str]:
    """
    Conservative research-only action policy.
    """

    score = max(
        0.0,
        min(
            1.0,
            learning_score,
        ),
    )

    if (
        score >= PROMOTE_THRESHOLD
        and evidence_records >= 2
        and review_signal >= 0.65
        and (
            cost_robustness is None
            or cost_robustness >= 0.60
        )
        and (
            cross_symbol_ratio is None
            or cross_symbol_ratio >= 0.60
        )
    ):
        return (
            "PROMOTE_TO_LEARNING_CANDIDATE",
            "research evidence is sufficiently strong for a learning candidate",
        )

    if score >= CONTINUE_THRESHOLD:
        return (
            "CONTINUE_RESEARCH",
            "evidence is useful but robustness/review is not strong enough for promotion",
        )

    return (
        "DEPRIORITIZE",
        "current evidence does not justify further learning priority",
    )


# ============================================================================
# BUILD RANKING
# ============================================================================

def build_ranking(
    conn: sqlite3.Connection,
    strategy_id: str,
) -> dict[str, Any]:
    v6 = load_v6(strategy_id)
    consolidation = load_latest_consolidation(
        strategy_id
    )
    final_decision = load_latest_final_decision(
        strategy_id
    )
    strategy_review = load_latest_strategy_review(
        conn,
        strategy_id,
    )

    independent_ratio = None
    holdout_ratio = None
    if consolidation.get("available"):
        independent_ratio = ratio01(
            consolidation.get(
                "pooled_positive_ratio"
            )
        )
        holdout_ratio = ratio01(
            consolidation.get(
                "holdout_positive_ratio"
            )
        )

    review_signal = None
    if strategy_review.get("available"):
        review_signal = review_score_to_signal(
            strategy_review.get("verdict"),
            strategy_review.get("score"),
        )

    cross_symbol = ratio01(
        v6.get("cross_symbol_ratio")
    )
    cost = ratio01(
        v6.get("cost_robustness")
    )
    parameter = ratio01(
        v6.get("parameter_stability")
    )
    regime = ratio01(
        v6.get("regime_stability")
    )
    v6_rank = ratio01(
        v6.get("normalized_ranking_score")
    )

    signals = {
        "independent_consistency": independent_ratio,
        "holdout_consistency": holdout_ratio,
        "strategy_review": review_signal,
        "cross_symbol_robustness": cross_symbol,
        "cost_robustness": cost,
        "parameter_stability": parameter,
        "regime_stability": regime,
        "v6_rank_score": v6_rank,
    }

    learning_score, contributions = weighted_average(
        signals
    )

    evidence_records = safe_int(
        consolidation.get(
            "evidence_records"
        )
        if consolidation.get("available")
        else 0
    )

    decision_action, action_reason = choose_action(
        learning_score=learning_score,
        evidence_records=evidence_records,
        review_signal=(
            review_signal
            if review_signal is not None
            else 0.0
        ),
        cost_robustness=cost,
        cross_symbol_ratio=cross_symbol,
    )

    strategy_name = norm(
        v6.get("strategy_name")
    )
    if not strategy_name:
        strategy_name = (
            strategy_id
        )

    next_question = norm(
        consolidation.get(
            "next_research_question"
        )
    )
    if not next_question:
        next_question = (
            "Can the strategy reproduce its edge "
            "on another genuinely independent time slice "
            "with stronger cost, parameter and regime stability?"
        )

    payload = {
        "engine": ENGINE_NAME,
        "engine_version": ENGINE_VERSION,
        "created_at": utc_now(),
        "strategy_id": strategy_id,
        "strategy_name": strategy_name,
        "research_only": True,
        "execution_enabled": False,
        "verified": False,
        "ranking": {
            "learning_score": learning_score,
            "learning_score_percent": learning_score * 100.0,
            "action": decision_action,
            "action_reason": action_reason,
            "signals": signals,
            "weights": WEIGHTS,
            "contributions": contributions,
            "thresholds": {
                "promote": PROMOTE_THRESHOLD,
                "continue": CONTINUE_THRESHOLD,
            },
        },
        "evidence_context": {
            "v6": v6,
            "consolidation": {
                key: value
                for key, value in consolidation.items()
                if key != "sources"
            },
            "strategy_review": strategy_review,
            "final_decision": final_decision,
        },
        "research_guidance": {
            "next_research_question": next_question,
            "verification_status": "NOT_VERIFIED",
            "learning_candidate_status": (
                "CANDIDATE_ONLY"
                if decision_action
                == "PROMOTE_TO_LEARNING_CANDIDATE"
                else "NOT_PROMOTED"
            ),
        },
        "safety": {
            "learned_rules_changed": False,
            "claims_changed": False,
            "validations_changed": False,
            "observations_changed": False,
            "knowledge_verified_changed": False,
            "broker_execution": False,
            "live_orders": False,
        },
    }

    return payload


# ============================================================================
# DATABASE OUTPUT
# ============================================================================

def ensure_table(conn: sqlite3.Connection) -> None:
    """
    Separate table deliberately used instead of learned_rules.

    This table stores ranking/evaluation snapshots only.
    """

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS brain_strategy_learning_rankings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            strategy_id TEXT NOT NULL,
            strategy_name TEXT,
            learning_score REAL NOT NULL,
            action TEXT NOT NULL,
            review_verdict TEXT,
            review_score REAL,
            independent_positive_ratio REAL,
            holdout_positive_ratio REAL,
            cross_symbol_ratio REAL,
            cost_robustness REAL,
            parameter_stability REAL,
            regime_stability REAL,
            v6_ranking_score REAL,
            verified INTEGER NOT NULL DEFAULT 0,
            input_fingerprint TEXT NOT NULL,
            ranking_json TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )

    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS
        idx_brain_strategy_learning_rankings_strategy
        ON brain_strategy_learning_rankings(strategy_id)
        """
    )

    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS
        idx_brain_strategy_learning_rankings_score
        ON brain_strategy_learning_rankings(learning_score DESC)
        """
    )

    conn.commit()


def input_fingerprint(
    ranking: dict[str, Any],
) -> str:
    evidence_context = ranking.get(
        "evidence_context",
        {},
    )

    stable = {
        "engine": ranking.get("engine"),
        "engine_version": ranking.get(
            "engine_version"
        ),
        "strategy_id": ranking.get(
            "strategy_id"
        ),
        "v6": evidence_context.get(
            "v6",
            {},
        ),
        "consolidation": evidence_context.get(
            "consolidation",
            {},
        ),
        "strategy_review": evidence_context.get(
            "strategy_review",
            {},
        ),
        "final_decision": evidence_context.get(
            "final_decision",
            {},
        ),
    }

    return sha256_text(
        compact_json(stable)
    )


def save_ranking(
    conn: sqlite3.Connection,
    ranking: dict[str, Any],
) -> tuple[int, bool]:
    rank = ranking["ranking"]
    signals = rank["signals"]
    review = ranking["evidence_context"].get(
        "strategy_review",
        {},
    )
    v6 = ranking["evidence_context"].get(
        "v6",
        {},
    )

    fingerprint = input_fingerprint(
        ranking
    )

    existing = conn.execute(
        """
        SELECT id
        FROM brain_strategy_learning_rankings
        WHERE
            strategy_id=?
            AND input_fingerprint=?
        ORDER BY id DESC
        LIMIT 1
        """,
        (
            ranking["strategy_id"],
            fingerprint,
        ),
    ).fetchone()

    if existing:
        return (
            safe_int(existing["id"]),
            False,
        )

    cur = conn.execute(
        """
        INSERT INTO brain_strategy_learning_rankings (
            strategy_id,
            strategy_name,
            learning_score,
            action,
            review_verdict,
            review_score,
            independent_positive_ratio,
            holdout_positive_ratio,
            cross_symbol_ratio,
            cost_robustness,
            parameter_stability,
            regime_stability,
            v6_ranking_score,
            verified,
            input_fingerprint,
            ranking_json,
            created_at
        )
        VALUES (
            ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?, ?
        )
        """,
        (
            ranking["strategy_id"],
            ranking["strategy_name"],
            safe_float(
                rank.get(
                    "learning_score"
                )
            ),
            norm(
                rank.get(
                    "action"
                )
            ),
            norm(
                review.get(
                    "verdict"
                )
            ).upper(),
            safe_float(
                review.get(
                    "score"
                )
            ),
            signals.get(
                "independent_consistency"
            ),
            signals.get(
                "holdout_consistency"
            ),
            signals.get(
                "cross_symbol_robustness"
            ),
            signals.get(
                "cost_robustness"
            ),
            signals.get(
                "parameter_stability"
            ),
            signals.get(
                "regime_stability"
            ),
            safe_float(
                v6.get(
                    "ranking_score"
                )
            ),
            fingerprint,
            compact_json(
                ranking
            ),
            ranking["created_at"],
        ),
    )

    return (
        safe_int(cur.lastrowid),
        True,
    )


# ============================================================================
# JSON OUTPUT
# ============================================================================

def save_json(
    ranking: dict[str, Any],
) -> Path:
    OUTPUT_DIR = (
        PROJECT_ROOT
        / "learning_ranking_results"
    )
    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    timestamp = datetime.now(
        timezone.utc
    ).strftime(
        "%Y%m%d_%H%M%S"
    )

    path = (
        OUTPUT_DIR
        / (
            f"learning_ranking_"
            f"{ranking['strategy_id']}_"
            f"{timestamp}.json"
        )
    )

    path.write_text(
        json.dumps(
            ranking,
            ensure_ascii=False,
            indent=2,
            default=str,
        ),
        encoding="utf-8",
    )

    return path


# ============================================================================
# REPORT
# ============================================================================

def pct_or_na(value: float | None) -> str:
    if value is None:
        return "N/A"
    return f"{value:.2%}"


def print_report(
    ranking: dict[str, Any],
    record_id: int,
    created: bool,
    output_path: Path,
) -> None:
    rank = ranking["ranking"]
    signals = rank["signals"]
    context = ranking["evidence_context"]

    review = context.get(
        "strategy_review",
        {},
    )
    v6 = context.get(
        "v6",
        {},
    )
    consolidation = context.get(
        "consolidation",
        {},
    )

    print("=" * 82)
    print("MARKETHQ LEARNING / RANKING LOOP V1")
    print("=" * 82)
    print()
    print(
        f"Strategy              : {ranking['strategy_id']}"
    )
    print(
        f"Strategy Name         : {ranking['strategy_name']}"
    )
    print()

    print("INPUTS")
    print("-" * 82)
    print(
        f"V6 Pipeline           : "
        f"{'AVAILABLE' if v6.get('available') else 'MISSING'}"
    )
    print(
        f"Evidence Consolidation: "
        f"{'AVAILABLE' if consolidation.get('available') else 'MISSING'}"
    )
    print(
        f"Strategy Review       : "
        f"{review.get('verdict', 'MISSING')} | "
        f"score={safe_float(review.get('score')):.3f} | "
        f"id={safe_int(review.get('review_id'))}"
    )
    print()

    print("LEARNING SIGNALS")
    print("-" * 82)
    print(
        f"Independent consistency: "
        f"{pct_or_na(signals.get('independent_consistency'))}"
    )
    print(
        f"Holdout consistency    : "
        f"{pct_or_na(signals.get('holdout_consistency'))}"
    )
    print(
        f"Strategy review signal : "
        f"{pct_or_na(signals.get('strategy_review'))}"
    )
    print(
        f"Cross-symbol robustness: "
        f"{pct_or_na(signals.get('cross_symbol_robustness'))}"
    )
    print(
        f"Cost robustness        : "
        f"{pct_or_na(signals.get('cost_robustness'))}"
    )
    print(
        f"Parameter stability    : "
        f"{pct_or_na(signals.get('parameter_stability'))}"
    )
    print(
        f"Regime stability       : "
        f"{pct_or_na(signals.get('regime_stability'))}"
    )
    print(
        f"V6 normalized score    : "
        f"{pct_or_na(signals.get('v6_rank_score'))}"
    )
    print()

    print("FINAL LEARNING RANK")
    print("-" * 82)
    print(
        f"Learning Score         : "
        f"{safe_float(rank.get('learning_score')):.4f}"
    )
    print(
        f"Learning Score %       : "
        f"{safe_float(rank.get('learning_score')):.2%}"
    )
    print(
        f"Action                 : "
        f"{rank.get('action', 'UNKNOWN')}"
    )
    print(
        f"Reason                 : "
        f"{rank.get('action_reason', '')}"
    )
    print()

    print("RESEARCH GUIDANCE")
    print("-" * 82)
    print(
        "Next research question : "
        f"{ranking['research_guidance']['next_research_question']}"
    )
    print(
        "Verification status    : "
        f"{ranking['research_guidance']['verification_status']}"
    )
    print(
        "Candidate status       : "
        f"{ranking['research_guidance']['learning_candidate_status']}"
    )
    print()

    print("SAFETY")
    print("-" * 82)
    print(
        f"Research Only          : "
        f"{ranking['research_only']}"
    )
    print(
        f"Execution Enabled      : "
        f"{ranking['execution_enabled']}"
    )
    print(
        "learned_rules          : unchanged"
    )
    print(
        "claims                 : unchanged"
    )
    print(
        "validations            : unchanged"
    )
    print(
        "observations           : unchanged"
    )
    print(
        "Knowledge Verified     : unchanged"
    )
    print()

    print(
        f"Learning ranking record: "
        f"{record_id} | "
        f"{'created' if created else 'already_present'}"
    )
    print(
        f"Saved ranking JSON     : {output_path}"
    )
    print()
    print(
        "RUN STATUS             : SUCCESS"
    )


# ============================================================================
# MAIN
# ============================================================================

def run() -> dict[str, Any]:
    assert_research_only()

    conn = open_db()

    try:
        ensure_table(conn)

        ranking = build_ranking(
            conn,
            TARGET_STRATEGY_ID,
        )

        record_id, created = save_ranking(
            conn,
            ranking,
        )

        conn.commit()

        output_path = save_json(
            ranking
        )

        print_report(
            ranking=ranking,
            record_id=record_id,
            created=created,
            output_path=output_path,
        )

        return ranking

    except sqlite3.Error:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    # Syntax/runtime entrypoint.
    # This engine is research-only by construction.
    run()

