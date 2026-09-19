"""
MarketHQ Strategy Selection Engine V2.0
=======================================

V6 araştırma çıktılarından en güçlü stratejileri seçer ve
research-only / paper-research adayları üretir.

AKIŞ
----
V6 Pipeline JSON
    ↓
V6 ranking + validation metriklerini oku
    ↓
Normalize et
    ↓
Selection Score
    ↓
Kalite filtresi
    ↓
Shortlist
    ↓
Paper Research Candidate

GÜVENLİK
--------
- Research only
- Paper candidate only
- Broker yok
- Order execution yok
- Gerçek para işlemi yok
"""

from __future__ import annotations

import argparse
import json
import math
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


# ============================================================================
# CONFIG
# ============================================================================

PIPELINE_VERSION = "V6.0"
SELECTION_VERSION = "V2.0"

RESEARCH_ONLY = True
EXECUTION_ENABLED = False

BASE_DIR = Path(__file__).resolve().parent
PIPELINE_RESULTS_DIR = BASE_DIR / "strategy_pipeline_results"
OUTPUT_DIR = BASE_DIR / "strategy_selection_results"

DEFAULT_TOP_N = 5
DEFAULT_PAPER_LIMIT = 3

# Kalite eşikleri
MIN_RANKING_SCORE = 2.50
MIN_CROSS_SYMBOL_RATIO = 0.50

# Bu eşikler kalite sınıflandırmasında kullanılır.
STRONG_RANKING_SCORE = 6.00
STRONG_CROSS_SYMBOL_RATIO = 0.60
STRONG_COST_SURVIVAL = 0.50
STRONG_PARAMETER_STABILITY = 0.50
STRONG_REGIME_STABILITY = 0.50


# ============================================================================
# BASIC HELPERS
# ============================================================================

def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
        if math.isfinite(number):
            return number
    except (TypeError, ValueError):
        pass

    return default


def safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        pass

    return default


def clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def normalize_ratio(value: Any) -> float:
    """
    0-1 veya 0-100 gelen oranları 0-1'e çevirir.
    """
    number = safe_float(value)

    if number > 1.0:
        number /= 100.0

    return clamp(number)


def timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


# ============================================================================
# JSON
# ============================================================================

def load_json(path: Path) -> Any | None:
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)

    except Exception as exc:
        print(f"⚠️ JSON okunamadı: {path.name}")
        print(f"   Hata: {exc}")
        return None


def discover_pipeline_files() -> list[Path]:
    """
    V6 pipeline sonuçlarını en yeniden eskiye sıralar.
    """
    if not PIPELINE_RESULTS_DIR.exists():
        return []

    return sorted(
        PIPELINE_RESULTS_DIR.glob("strategy_pipeline_v6_*.json"),
        key=lambda item: item.stat().st_mtime,
        reverse=True,
    )


# ============================================================================
# STRATEGY RECORD EXTRACTION
# ============================================================================

def is_strategy_record(value: Any) -> bool:
    """
    V6 gerçek strategy result kaydını tespit eder.

    V6 sonucu için:
        strategy_id
        ranking: {...}
    kombinasyonu temel alınır.
    """
    if not isinstance(value, dict):
        return False

    strategy_id = value.get("strategy_id") or value.get("id")
    ranking = value.get("ranking")

    return bool(strategy_id) and isinstance(ranking, dict)


def extract_strategy_records(payload: Any) -> list[dict[str, Any]]:
    """
    JSON'u recursive tarar.

    Böylece master dosya veya iç içe result yapısı fark etmez.
    """
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


# ============================================================================
# METRIC EXTRACTION
# ============================================================================

def get_containers(record: dict[str, Any]) -> list[dict[str, Any]]:
    """
    Metriklerin bulunabileceği alanları öncelik sırasıyla döndürür.
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

    # Doğrudan alanları da kontrol et.
    containers.append(record)

    return containers


def find_metric(
    record: dict[str, Any],
    *keys: str,
    default: Any = 0.0,
) -> Any:
    """
    Verilen anahtarları tüm önemli V6 container'larında arar.
    """
    containers = get_containers(record)

    for container in containers:
        for key in keys:
            if key in container:
                return container[key]

    return default


def extract_strategy_id(record: dict[str, Any]) -> str:
    value = record.get("strategy_id") or record.get("id")

    if value:
        return str(value)

    strategy = record.get("strategy")

    if isinstance(strategy, dict):
        value = strategy.get("strategy_id") or strategy.get("id")

        if value:
            return str(value)

    return "UNKNOWN"


def extract_strategy_name(record: dict[str, Any]) -> str:
    value = (
        record.get("strategy_name")
        or record.get("name")
    )

    if value:
        return str(value)

    strategy = record.get("strategy")

    if isinstance(strategy, dict):
        value = (
            strategy.get("strategy_name")
            or strategy.get("name")
            or strategy.get("title")
        )

        if value:
            return str(value)

    if isinstance(strategy, str):
        return strategy

    return "Unnamed Strategy"


def extract_wfo_positive_ratio(record: dict[str, Any]) -> float:
    """
    Önce V6 ranking.wfo_positive_ratio kullanılır.

    Yoksa fold sayılarından hesaplanır.
    """
    direct = find_metric(
        record,
        "wfo_positive_ratio",
        "positive_wfo_ratio",
        "wfo_consistency",
        default=None,
    )

    if direct is not None:
        return normalize_ratio(direct)

    positive = safe_int(
        find_metric(
            record,
            "wfo_positive_folds",
            "positive_wfo_folds",
            default=0,
        )
    )

    negative = safe_int(
        find_metric(
            record,
            "wfo_negative_folds",
            "negative_wfo_folds",
            default=0,
        )
    )

    inconclusive = safe_int(
        find_metric(
            record,
            "wfo_inconclusive_folds",
            "inconclusive_wfo_folds",
            default=0,
        )
    )

    total = positive + negative + inconclusive

    if total <= 0:
        return 0.0

    return clamp(positive / total)


# ============================================================================
# SCORING
# ============================================================================

def classify_quality(
    ranking_score: float,
    cross_symbol_ratio: float,
    average_return: float,
    cost_survival: float,
    parameter_stability: float,
    regime_stability: float,
) -> str:
    """
    Araştırma kalitesi.

    PROMISING:
        Birden fazla bağımsız araştırma metriğinde güçlü sonuç.

    MIXED:
        Araştırmaya devam etmeye değer fakat güçlü doğrulama yok.

    REJECTED:
        Mevcut V6 kanıtı shortlist için yetersiz.
    """
    strong_checks = 0

    if ranking_score >= 7.0:
        strong_checks += 1

    if cross_symbol_ratio >= STRONG_CROSS_SYMBOL_RATIO:
        strong_checks += 1

    if average_return > 0:
        strong_checks += 1

    if cost_survival >= STRONG_COST_SURVIVAL:
        strong_checks += 1

    if parameter_stability >= STRONG_PARAMETER_STABILITY:
        strong_checks += 1

    if regime_stability >= STRONG_REGIME_STABILITY:
        strong_checks += 1

    if (
        ranking_score >= STRONG_RANKING_SCORE
        and strong_checks >= 4
    ):
        return "PROMISING"

    # V6'da ranking 2.5+ ve cross-symbol %50+ ise
    # araştırma/paper takip adayı olarak MIXED kabul edilir.
    if (
        ranking_score >= MIN_RANKING_SCORE
        and cross_symbol_ratio >= MIN_CROSS_SYMBOL_RATIO
    ):
        return "MIXED"

    # Çok güçlü ranking tek başına da araştırmayı sürdürmeye yeter.
    if ranking_score >= 4.0:
        return "MIXED"

    return "REJECTED"


def build_selection_score(record: dict[str, Any]) -> dict[str, Any]:
    """
    V6 metriklerini 0-10 arası selection score'a dönüştürür.

    Ağırlık:
        Ranking score       25%
        Cross-symbol        20%
        Average return      15%
        Cost survival       15%
        Parameter stability 10%
        Regime stability    10%
        WFO consistency      5%
    """

    ranking_score = safe_float(
        find_metric(
            record,
            "score",
            "ranking_score",
            "v6_ranking_score",
            default=0.0,
        )
    )

    cross_symbol_ratio = normalize_ratio(
        find_metric(
            record,
            "cross_symbol_positive_ratio",
            "cross_symbol_ratio",
            "cross_symbol_success_ratio",
            default=0.0,
        )
    )

    average_return = safe_float(
        find_metric(
            record,
            "average_return",
            "avg_return",
            "return_percent",
            default=0.0,
        )
    )

    cost_survival = normalize_ratio(
        find_metric(
            record,
            "cost_survival",
            "cost_robustness",
            "cost_robustness_ratio",
            default=0.0,
        )
    )

    parameter_stability = normalize_ratio(
        find_metric(
            record,
            "parameter_stability",
            "parameter_stability_ratio",
            default=0.0,
        )
    )

    regime_stability = normalize_ratio(
        find_metric(
            record,
            "regime_stability",
            "regime_stability_ratio",
            default=0.0,
        )
    )

    wfo_positive_ratio = extract_wfo_positive_ratio(record)

    ranking_component = clamp(ranking_score / 10.0)

    # -2% = 0, +2% = 1
    return_component = clamp(
        (average_return + 2.0) / 4.0
    )

    selection_score = (
        ranking_component * 0.25
        + cross_symbol_ratio * 0.20
        + return_component * 0.15
        + cost_survival * 0.15
        + parameter_stability * 0.10
        + regime_stability * 0.10
        + wfo_positive_ratio * 0.05
    ) * 10.0

    quality = classify_quality(
        ranking_score=ranking_score,
        cross_symbol_ratio=cross_symbol_ratio,
        average_return=average_return,
        cost_survival=cost_survival,
        parameter_stability=parameter_stability,
        regime_stability=regime_stability,
    )

    return {
        "selection_score": round(selection_score, 4),
        "quality": quality,
        "metrics": {
            "ranking_score": round(ranking_score, 4),
            "cross_symbol_ratio": round(cross_symbol_ratio, 4),
            "average_return_percent": round(average_return, 4),
            "cost_survival": round(cost_survival, 4),
            "parameter_stability": round(parameter_stability, 4),
            "regime_stability": round(regime_stability, 4),
            "wfo_positive_ratio": round(wfo_positive_ratio, 4),
        },
    }


# ============================================================================
# DEDUPLICATION
# ============================================================================

def deduplicate_records(
    records: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    Aynı strategy_id birden fazla V6 dosyasında bulunursa
    en yüksek selection score'a sahip kayıt tutulur.
    """
    unique: dict[str, dict[str, Any]] = {}

    for record in records:
        strategy_id = extract_strategy_id(record)

        if strategy_id == "UNKNOWN":
            strategy_id = re.sub(
                r"\s+",
                " ",
                extract_strategy_name(record).strip().lower(),
            )

        current = unique.get(strategy_id)

        if current is None:
            unique[strategy_id] = record
            continue

        current_score = build_selection_score(
            current
        )["selection_score"]

        new_score = build_selection_score(
            record
        )["selection_score"]

        if new_score > current_score:
            unique[strategy_id] = record

    return list(unique.values())


# ============================================================================
# INPUT
# ============================================================================

def load_input_records(
    input_path: Path | None,
) -> tuple[list[dict[str, Any]], list[str]]:
    if input_path is not None:
        paths = [input_path]
    else:
        paths = discover_pipeline_files()

    records: list[dict[str, Any]] = []
    source_files: list[str] = []

    for path in paths:
        payload = load_json(path)

        if payload is None:
            continue

        found = extract_strategy_records(payload)

        if not found:
            continue

        records.extend(found)
        source_files.append(str(path))

    return deduplicate_records(records), source_files


# ============================================================================
# SELECTION
# ============================================================================

def build_selected_record(
    record: dict[str, Any],
    rank: int,
    paper_candidate: bool,
) -> dict[str, Any]:
    scoring = build_selection_score(record)

    return {
        "rank": rank,
        "strategy_id": extract_strategy_id(record),
        "strategy_name": extract_strategy_name(record),
        "selection_score": scoring["selection_score"],
        "quality": scoring["quality"],
        "paper_candidate": paper_candidate,
        "research_only": True,
        "execution_enabled": False,
        "source_pipeline": PIPELINE_VERSION,
        "metrics": scoring["metrics"],
    }


def select_strategies(
    records: list[dict[str, Any]],
    top_n: int,
    paper_limit: int,
) -> dict[str, Any]:
    accepted: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []

    for record in records:
        scoring = build_selection_score(record)

        if scoring["quality"] == "REJECTED":
            rejected.append(
                {
                    "strategy_id": extract_strategy_id(record),
                    "strategy_name": extract_strategy_name(record),
                    "selection_score": scoring["selection_score"],
                    "quality": scoring["quality"],
                    "metrics": scoring["metrics"],
                }
            )
            continue

        accepted.append(
            build_selected_record(
                record=record,
                rank=0,
                paper_candidate=False,
            )
        )

    accepted.sort(
        key=lambda item: (
            item["selection_score"],
            item["metrics"]["ranking_score"],
            item["metrics"]["cross_symbol_ratio"],
            item["metrics"]["average_return_percent"],
        ),
        reverse=True,
    )

    shortlist = accepted[:max(1, top_n)]

    paper_count = 0

    for rank, item in enumerate(shortlist, start=1):
        item["rank"] = rank

        if (
            item["quality"] in {"PROMISING", "MIXED"}
            and paper_count < paper_limit
        ):
            item["paper_candidate"] = True
            paper_count += 1

    return {
        "shortlist": shortlist,
        "paper_candidates": [
            item
            for item in shortlist
            if item["paper_candidate"]
        ],
        "rejected_count": len(rejected),
        "rejected_details": rejected,
    }


# ============================================================================
# DIAGNOSTICS
# ============================================================================

def build_diagnostics(
    records: list[dict[str, Any]],
) -> dict[str, Any]:
    """
    Shortlist boşsa veya sonuç beklenmedikse gerçek metrikleri gösterir.
    """
    items: list[dict[str, Any]] = []

    for record in records:
        scoring = build_selection_score(record)

        items.append(
            {
                "strategy_id": extract_strategy_id(record),
                "strategy_name": extract_strategy_name(record),
                "quality": scoring["quality"],
                "selection_score": scoring["selection_score"],
                **scoring["metrics"],
            }
        )

    items.sort(
        key=lambda item: item["selection_score"],
        reverse=True,
    )

    return {
        "records_checked": len(records),
        "top_records": items[:10],
    }


# ============================================================================
# SAVE
# ============================================================================

def save_result(result: dict[str, Any]) -> Path:
    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    output_path = OUTPUT_DIR / (
        f"strategy_selection_{timestamp()}.json"
    )

    with output_path.open(
        "w",
        encoding="utf-8",
    ) as handle:
        json.dump(
            result,
            handle,
            ensure_ascii=False,
            indent=2,
        )

    return output_path


# ============================================================================
# REPORT
# ============================================================================

def print_report(
    result: dict[str, Any],
    source_files: list[str],
) -> None:
    print()
    print("=" * 80)
    print("🏆 MARKET HQ STRATEGY SELECTION ENGINE V2.0")
    print("=" * 80)

    print(f"Input files       : {len(source_files)}")
    print(
        f"Strategies loaded : "
        f"{result['input_strategy_count']}"
    )
    print(
        f"Shortlist         : "
        f"{len(result['shortlist'])}"
    )
    print(
        f"Paper candidates  : "
        f"{len(result['paper_candidates'])}"
    )
    print(
        f"Rejected          : "
        f"{result['rejected_count']}"
    )
    print(f"Research Only     : {RESEARCH_ONLY}")
    print(
        f"Execution Enabled : "
        f"{EXECUTION_ENABLED}"
    )

    if not result["shortlist"]:
        print()
        print("⚠️ Seçilebilir strateji bulunamadı.")
        print()
        print("-" * 80)
        print("🔎 DIAGNOSTICS")
        print("-" * 80)

        diagnostics = result.get(
            "diagnostics",
            {},
        )

        for item in diagnostics.get(
            "top_records",
            [],
        ):
            print(
                f"• {item['strategy_id']} | "
                f"Score={item['selection_score']:.4f} | "
                f"Ranking={item['ranking_score']:.4f} | "
                f"Cross={item['cross_symbol_ratio'] * 100:.2f}% | "
                f"Return={item['average_return_percent']:.2f}% | "
                f"Cost={item['cost_survival'] * 100:.2f}% | "
                f"Param={item['parameter_stability'] * 100:.2f}% | "
                f"Regime={item['regime_stability'] * 100:.2f}% | "
                f"WFO={item['wfo_positive_ratio'] * 100:.2f}% | "
                f"{item['quality']}"
            )

        return

    print()
    print("-" * 80)
    print("📊 STRATEGY SHORTLIST")
    print("-" * 80)

    for item in result["shortlist"]:
        candidate_type = (
            "PAPER_RESEARCH"
            if item["paper_candidate"]
            else "RESEARCH_ONLY"
        )

        print(
            f"{item['rank']:>2}. "
            f"{item['strategy_id']} | "
            f"{item['strategy_name']} | "
            f"Score={item['selection_score']:.4f} | "
            f"{item['quality']} | "
            f"{candidate_type}"
        )

    print()
    print("-" * 80)
    print("🧪 PAPER RESEARCH CANDIDATES")
    print("-" * 80)

    if not result["paper_candidates"]:
        print("⚠️ Paper research candidate oluşmadı.")
    else:
        for item in result["paper_candidates"]:
            metrics = item["metrics"]

            print(
                f"• {item['strategy_id']} | "
                f"{item['strategy_name']}"
            )
            print(
                f"  Selection Score     : "
                f"{item['selection_score']:.4f}"
            )
            print(
                f"  Ranking score       : "
                f"{metrics['ranking_score']:.4f}"
            )
            print(
                f"  Cross-symbol        : "
                f"{metrics['cross_symbol_ratio'] * 100:.2f}%"
            )
            print(
                f"  Average return      : "
                f"{metrics['average_return_percent']:.2f}%"
            )
            print(
                f"  Cost survival       : "
                f"{metrics['cost_survival'] * 100:.2f}%"
            )
            print(
                f"  Parameter stability : "
                f"{metrics['parameter_stability'] * 100:.2f}%"
            )
            print(
                f"  Regime stability    : "
                f"{metrics['regime_stability'] * 100:.2f}%"
            )
            print(
                f"  WFO positive ratio  : "
                f"{metrics['wfo_positive_ratio'] * 100:.2f}%"
            )
            print()

    print("=" * 80)


# ============================================================================
# RUN
# ============================================================================

def run(
    input_path: Path | None = None,
    top_n: int = DEFAULT_TOP_N,
    paper_limit: int = DEFAULT_PAPER_LIMIT,
) -> Path | None:
    if not RESEARCH_ONLY or EXECUTION_ENABLED:
        raise RuntimeError(
            "Safety gate: Strategy Selection Engine "
            "yalnızca research/paper modunda çalışabilir."
        )

    records, source_files = load_input_records(
        input_path
    )

    if not records:
        print()
        print("❌ V6 strategy result bulunamadı.")
        print(
            f"Aranan klasör: "
            f"{PIPELINE_RESULTS_DIR}"
        )
        print(
            "Önce strategy_research_pipeline_v6.py "
            "çalıştırmalısın."
        )
        return None

    selection = select_strategies(
        records=records,
        top_n=top_n,
        paper_limit=paper_limit,
    )

    diagnostics = build_diagnostics(records)

    result = {
        "selection_version": SELECTION_VERSION,
        "source_pipeline": PIPELINE_VERSION,
        "created_at": datetime.now(
            timezone.utc
        ).isoformat(),
        "research_only": RESEARCH_ONLY,
        "execution_enabled": EXECUTION_ENABLED,
        "input_strategy_count": len(records),
        "source_files": source_files,
        **selection,
        "diagnostics": diagnostics,
    }

    output_path = save_result(result)

    print_report(
        result=result,
        source_files=source_files,
    )

    print()
    print("💾 Selection result saved:")
    print(output_path)

    return output_path


# ============================================================================
# CLI
# ============================================================================

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "MarketHQ Strategy Selection Engine V2.0"
        )
    )

    parser.add_argument(
        "--input",
        type=str,
        default=None,
        help="Belirli bir V6 JSON sonucu.",
    )

    parser.add_argument(
        "--top",
        type=int,
        default=DEFAULT_TOP_N,
        help=(
            f"Shortlist boyutu. "
            f"Varsayılan: {DEFAULT_TOP_N}"
        ),
    )

    parser.add_argument(
        "--paper",
        type=int,
        default=DEFAULT_PAPER_LIMIT,
        help=(
            f"Paper candidate limiti. "
            f"Varsayılan: {DEFAULT_PAPER_LIMIT}"
        ),
    )

    return parser.parse_args()


def main() -> None:
    args = parse_args()

    input_path = (
        Path(args.input).resolve()
        if args.input
        else None
    )

    run(
        input_path=input_path,
        top_n=max(1, args.top),
        paper_limit=max(1, args.paper),
    )


if __name__ == "__main__":
    main()

