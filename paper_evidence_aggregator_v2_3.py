"""
MarketHQ Paper Evidence Aggregator V2.1
-------------------------------------
Research-only aggregation layer.

Purpose:
    Paper Trading JSON results
            ↓
    Strategy-level evidence aggregation
            ↓
    Cross-symbol / cross-run metrics
            ↓
    Evidence quality classification
            ↓
    Research recommendations

Safety:
- No broker connection.
- No real-money execution.
- No order placement.
- Does not modify learned_rules.
- Does not promote a strategy to "validated".
- Only aggregates existing paper/research results.

The engine is intentionally tolerant of the nested V1.3 paper schema:
    {
        "strategy": {...},
        "market": {...},
        "metrics": {...},
        "trades": [...],
        ...
    }

Usage:
    .\\.venv\\Scripts\\python.exe paper_evidence_aggregator_v1.py

Optional:
    .\\.venv\\Scripts\\python.exe paper_evidence_aggregator_v1.py --strategy-id STR-43839FA9C6
    .\\.venv\\Scripts\\python.exe paper_evidence_aggregator_v1.py --min-trades 8
"""

from __future__ import annotations

import argparse
import json
import math
import re
import hashlib
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean, median
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parent
PAPER_RESULTS_DIR = PROJECT_ROOT / "paper_trading_results"
OUTPUT_DIR = PROJECT_ROOT / "paper_evidence_results"

ENGINE_NAME = "MARKETHQ_PAPER_EVIDENCE_AGGREGATOR"
ENGINE_VERSION = "V2.3"

RESEARCH_ONLY = True
EXECUTION_ENABLED = False

STRATEGY_ID_PATTERN = re.compile(
    r"\bSTR-[A-Z0-9]{6,20}\b",
    re.IGNORECASE,
)

DEFAULT_MIN_TRADES = 8
DEFAULT_MAX_FILES = 5000


# ============================================================================
# BASIC HELPERS
# ============================================================================

def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def safe_text(value: Any, default: str = "") -> str:
    if value is None:
        return default
    return str(value).strip()


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        number = float(value)
        if not math.isfinite(number):
            return default
        return number
    except (TypeError, ValueError):
        return default


def safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def compact_json(data: Any) -> str:
    return json.dumps(
        data,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def average(values: list[float]) -> float:
    return mean(values) if values else 0.0


def median_safe(values: list[float]) -> float:
    return median(values) if values else 0.0


def percentile(values: list[float], q: float) -> float:
    if not values:
        return 0.0

    ordered = sorted(values)

    if len(ordered) == 1:
        return ordered[0]

    position = (len(ordered) - 1) * q
    lower = math.floor(position)
    upper = math.ceil(position)

    if lower == upper:
        return ordered[lower]

    weight = position - lower
    return (
        ordered[lower] * (1.0 - weight)
        + ordered[upper] * weight
    )


# ============================================================================
# JSON EXTRACTION
# ============================================================================

def find_value_recursive(
    data: Any,
    keys: set[str],
) -> Any:
    if isinstance(data, dict):
        for key, value in data.items():
            if str(key).lower() in keys:
                return value

        for value in data.values():
            found = find_value_recursive(value, keys)
            if found is not None:
                return found

    elif isinstance(data, list):
        for item in data:
            found = find_value_recursive(item, keys)
            if found is not None:
                return found

    return None


def extract_strategy_id(data: dict[str, Any], path: Path) -> str:
    direct = find_value_recursive(
        data,
        {
            "strategy_id",
            "strategyid",
        },
    )

    if direct:
        match = STRATEGY_ID_PATTERN.search(str(direct))
        if match:
            return match.group(0).upper()

    match = STRATEGY_ID_PATTERN.search(path.name)
    if match:
        return match.group(0).upper()

    serialized = json.dumps(
        data,
        ensure_ascii=False,
    )

    match = STRATEGY_ID_PATTERN.search(serialized)

    if match:
        return match.group(0).upper()

    return ""


def extract_strategy_name(data: dict[str, Any]) -> str:
    value = find_value_recursive(
        data,
        {
            "strategy_name",
            "strategyname",
        },
    )
    return safe_text(value, "UNKNOWN_STRATEGY")


def extract_symbol(data: dict[str, Any]) -> str:
    # Paper Engine V1.3 stores the authoritative symbol at market.symbol.
    # Prefer that exact path so a stale/secondary nested "symbol" field
    # can never overwrite the actual replay symbol.
    market = data.get("market")
    if isinstance(market, dict):
        direct = market.get("symbol")
        if direct is not None and safe_text(direct):
            return safe_text(direct).upper()

    # Backward-compatible fallback for older result schemas.
    value = find_value_recursive(
        data,
        {
            "symbol",
        },
    )
    return safe_text(value, "UNKNOWN").upper()


def extract_metrics(data: dict[str, Any]) -> dict[str, Any]:
    metrics = data.get("metrics")

    if isinstance(metrics, dict):
        return metrics

    found = find_value_recursive(
        data,
        {"metrics"},
    )

    if isinstance(found, dict):
        return found

    return {}


def extract_market(data: dict[str, Any]) -> dict[str, Any]:
    market = data.get("market")

    if isinstance(market, dict):
        return market

    found = find_value_recursive(
        data,
        {"market"},
    )

    if isinstance(found, dict):
        return found

    return {}


def extract_period(data: dict[str, Any]) -> str:
    market = extract_market(data)
    return safe_text(
        market.get("period")
        or data.get("period"),
        "UNKNOWN",
    )


def extract_interval(data: dict[str, Any]) -> str:
    market = extract_market(data)
    return safe_text(
        market.get("interval")
        or data.get("interval"),
        "UNKNOWN",
    )


def metric_value(
    metrics: dict[str, Any],
    *keys: str,
    default: float = 0.0,
) -> float:
    for key in keys:
        if key in metrics:
            return safe_float(
                metrics.get(key),
                default,
            )

    return default


# ============================================================================
# PAPER RESULT NORMALIZATION
# ============================================================================

def extract_market_dates(data: dict[str, Any]) -> tuple[str, str]:
    market = data.get("market")
    if not isinstance(market, dict):
        market = {}

    start = safe_text(
        market.get("start")
        or data.get("start")
        or data.get("start_date")
        or data.get("history_start")
    )
    end = safe_text(
        market.get("end")
        or data.get("end")
        or data.get("end_date")
        or data.get("history_end")
    )
    return start, end


def extract_parameter_snapshot(data: dict[str, Any]) -> dict[str, Any]:
    strategy = data.get("strategy")
    if not isinstance(strategy, dict):
        strategy = {}

    signal = strategy.get("signal_config_used") or strategy.get("signal_config") or {}
    risk = strategy.get("risk_config_used") or strategy.get("risk_parameters_used") or strategy.get("risk_config") or {}

    if not isinstance(signal, dict):
        signal = {}
    if not isinstance(risk, dict):
        risk = {}

    return {
        "signal": signal,
        "risk": risk,
    }


def replay_identity(row: dict[str, Any]) -> str:
    payload = {
        "strategy_id": safe_text(row.get("strategy_id")).upper(),
        "symbol": safe_text(row.get("symbol")).upper(),
        "period": safe_text(row.get("period")),
        "interval": safe_text(row.get("interval")),
        "start_date": safe_text(row.get("start_date")),
        "end_date": safe_text(row.get("end_date")),
        "parameters": row.get("parameters", {}),
    }
    return compact_json(payload)


def deduplicate_results(
    results: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    unique: list[dict[str, Any]] = []
    duplicates: list[dict[str, Any]] = []
    seen: dict[str, dict[str, Any]] = {}

    for row in sorted(
        results,
        key=lambda item: safe_text(item.get("source_file")),
    ):
        identity = replay_identity(row)
        row["replay_identity"] = identity
        row["replay_fingerprint"] = hashlib.sha256(
            identity.encode("utf-8")
        ).hexdigest()[:16]

        if identity in seen:
            duplicates.append({
                "source_file": row["source_file"],
                "duplicate_of": seen[identity]["source_file"],
                "identity": identity,
            })
            continue

        seen[identity] = row
        unique.append(row)

    return unique, duplicates


def normalize_paper_file(
    path: Path,
) -> dict[str, Any] | None:
    try:
        with path.open(
            "r",
            encoding="utf-8",
        ) as handle:
            data = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return None

    if not isinstance(data, dict):
        return None

    strategy_id = extract_strategy_id(
        data,
        path,
    )

    symbol = extract_symbol(data)

    if not strategy_id or symbol == "UNKNOWN":
        return None

    metrics = extract_metrics(data)
    start_date, end_date = extract_market_dates(data)
    parameters = extract_parameter_snapshot(data)

    return {
        "source_file": str(path),
        "source_name": path.name,
        "strategy_id": strategy_id,
        "strategy_name": extract_strategy_name(data),
        "symbol": symbol,
        "period": extract_period(data),
        "interval": extract_interval(data),
        "start_date": start_date,
        "end_date": end_date,
        "parameters": parameters,
        "total_trades": safe_int(
            metric_value(
                metrics,
                "trades",
                "total_trades",
            )
        ),
        "wins": safe_int(
            metric_value(
                metrics,
                "wins",
                "winning_trades",
            )
        ),
        "losses": safe_int(
            metric_value(
                metrics,
                "losses",
                "losing_trades",
            )
        ),
        "win_rate_percent": metric_value(
            metrics,
            "win_rate_percent",
            "win_rate",
        ),
        "profit_factor": metric_value(
            metrics,
            "profit_factor",
            "pf",
        ),
        "net_pnl": metric_value(
            metrics,
            "net_pnl",
            "aggregate_net_pnl",
        ),
        "return_percent": metric_value(
            metrics,
            "return_percent",
            "total_return_percent",
            "aggregate_return_percent",
        ),
        "max_drawdown_percent": metric_value(
            metrics,
            "max_drawdown_percent",
            "max_drawdown",
        ),
        "average_trade_pnl": metric_value(
            metrics,
            "average_trade_pnl",
            "average_trade",
        ),
        "initial_capital": metric_value(
            metrics,
            "initial_capital",
        ),
        "final_equity": metric_value(
            metrics,
            "final_equity",
        ),
    }



def diagnostic_symbol_scan(
    rows: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "count": len(rows),
        "symbols": sorted(
            {
                safe_text(row.get("symbol")).upper()
                for row in rows
                if safe_text(row.get("symbol"))
            }
        ),
        "files_by_symbol": {
            symbol: [
                safe_text(row.get("source_name"))
                for row in rows
                if safe_text(row.get("symbol")).upper() == symbol
            ]
            for symbol in sorted(
                {
                    safe_text(row.get("symbol")).upper()
                    for row in rows
                    if safe_text(row.get("symbol"))
                }
            )
        },
    }



# ============================================================================
# DISCOVERY
# ============================================================================

def discover_files(
    max_files: int = DEFAULT_MAX_FILES,
) -> list[Path]:
    if not PAPER_RESULTS_DIR.exists():
        return []

    files = sorted(
        PAPER_RESULTS_DIR.glob("*.json"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )

    return files[:max_files]


def load_results(
    strategy_id: str | None = None,
    max_files: int = DEFAULT_MAX_FILES,
) -> tuple[list[dict[str, Any]], int]:
    normalized: list[dict[str, Any]] = []
    invalid = 0

    wanted = safe_text(
        strategy_id
    ).upper()

    for path in discover_files(max_files):
        result = normalize_paper_file(path)

        if result is None:
            invalid += 1
            continue

        if wanted and result["strategy_id"] != wanted:
            continue

        normalized.append(result)

    return normalized, invalid


# ============================================================================
# AGGREGATION
# ============================================================================

def weighted_return(results: list[dict[str, Any]]) -> float:
    total_initial = sum(
        safe_float(row["initial_capital"])
        for row in results
        if safe_float(row["initial_capital"]) > 0
    )

    if total_initial > 0:
        total_pnl = sum(
            safe_float(row["net_pnl"])
            for row in results
        )
        return (total_pnl / total_initial) * 100.0

    return average(
        [
            safe_float(row["return_percent"])
            for row in results
        ]
    )


def aggregate_strategy(
    results: list[dict[str, Any]],
) -> dict[str, Any]:
    if not results:
        raise ValueError(
            "Aggregate için paper sonucu bulunamadı."
        )

    strategy_id = results[0]["strategy_id"]
    strategy_name = results[0]["strategy_name"]

    symbols = sorted(
        {
            safe_text(row["symbol"]).upper()
            for row in results
        }
    )

    positive = [
        row for row in results
        if safe_float(row["return_percent"]) > 0
    ]

    negative = [
        row for row in results
        if safe_float(row["return_percent"]) < 0
    ]

    flat = [
        row for row in results
        if safe_float(row["return_percent"]) == 0
    ]

    total_trades = sum(
        safe_int(row["total_trades"])
        for row in results
    )

    total_wins = sum(
        safe_int(row["wins"])
        for row in results
    )

    total_losses = sum(
        safe_int(row["losses"])
        for row in results
    )

    aggregate_win_rate = (
        (total_wins / total_trades) * 100.0
        if total_trades > 0
        else 0.0
    )

    pf_values = [
        safe_float(row["profit_factor"])
        for row in results
        if safe_float(row["profit_factor"]) > 0
    ]

    return_values = [
        safe_float(row["return_percent"])
        for row in results
    ]

    dd_values = [
        safe_float(row["max_drawdown_percent"])
        for row in results
    ]

    pnl_values = [
        safe_float(row["net_pnl"])
        for row in results
    ]

    return {
        "strategy_id": strategy_id,
        "strategy_name": strategy_name,
        "runs": len(results),
        "symbols": symbols,
        "symbol_count": len(symbols),
        "positive_runs": len(positive),
        "negative_runs": len(negative),
        "flat_runs": len(flat),
        "positive_run_ratio_percent": (
            len(positive) / len(results) * 100.0
        ),
        "total_trades": total_trades,
        "total_wins": total_wins,
        "total_losses": total_losses,
        "aggregate_win_rate_percent": aggregate_win_rate,
        "aggregate_net_pnl": sum(pnl_values),
        "aggregate_return_percent": weighted_return(results),
        "average_run_return_percent": average(return_values),
        "median_run_return_percent": median_safe(return_values),
        "best_run_return_percent": max(return_values),
        "worst_run_return_percent": min(return_values),
        "p25_run_return_percent": percentile(return_values, 0.25),
        "p75_run_return_percent": percentile(return_values, 0.75),
        "average_profit_factor": average(pf_values),
        "median_profit_factor": median_safe(pf_values),
        "best_profit_factor": max(pf_values) if pf_values else 0.0,
        "worst_profit_factor": min(pf_values) if pf_values else 0.0,
        "average_max_drawdown_percent": average(dd_values),
        "worst_max_drawdown_percent": max(dd_values),
        "average_trade_pnl": average(
            [
                safe_float(row["average_trade_pnl"])
                for row in results
            ]
        ),
        "periods": sorted(
            {
                safe_text(row["period"])
                for row in results
            }
        ),
        "intervals": sorted(
            {
                safe_text(row["interval"])
                for row in results
            }
        ),
    }


# ============================================================================
# EVIDENCE QUALITY
# ============================================================================

def classify_evidence(
    aggregate: dict[str, Any],
    min_trades: int,
) -> dict[str, Any]:
    runs = safe_int(aggregate["runs"])
    symbols = safe_int(aggregate["symbol_count"])
    trades = safe_int(aggregate["total_trades"])
    positive_ratio = safe_float(
        aggregate["positive_run_ratio_percent"]
    )
    avg_pf = safe_float(
        aggregate["average_profit_factor"]
    )
    aggregate_return = safe_float(
        aggregate["aggregate_return_percent"]
    )

    reasons: list[str] = []

    if trades < min_trades:
        reasons.append(
            f"toplam işlem sayısı {trades} < {min_trades}"
        )

    if symbols < 3:
        reasons.append(
            f"farklı sembol sayısı {symbols} < 3"
        )

    if runs < 3:
        reasons.append(
            f"paper run sayısı {runs} < 3"
        )

    if avg_pf < 1.0:
        reasons.append(
            "ortalama profit factor 1.0 altında"
        )

    if aggregate_return < 0:
        reasons.append(
            "aggregate paper getirisi negatif"
        )

    if positive_ratio < 50.0:
        reasons.append(
            "pozitif paper run oranı %50 altında"
        )

    if (
        trades >= 30
        and symbols >= 3
        and runs >= 3
        and avg_pf >= 1.10
        and aggregate_return > 0
        and positive_ratio >= 60.0
    ):
        classification = "PROMISING_PAPER_EVIDENCE"

    elif (
        trades >= min_trades
        and runs >= 2
        and (
            avg_pf >= 1.0
            or aggregate_return > 0
            or positive_ratio >= 50.0
        )
    ):
        classification = "MIXED_PAPER_EVIDENCE"

    elif trades < min_trades or runs < 2:
        classification = "INSUFFICIENT_PAPER_EVIDENCE"

    else:
        classification = "WEAK_PAPER_EVIDENCE"

    if not reasons:
        reasons.append(
            "mevcut paper örneklemi temel kanıt eşiğini geçti"
        )

    return {
        "classification": classification,
        "reasons": reasons,
    }


def research_actions(
    aggregate: dict[str, Any],
    classification: str,
) -> list[str]:
    actions: list[str] = []

    symbols = safe_int(aggregate["symbol_count"])
    trades = safe_int(aggregate["total_trades"])
    avg_pf = safe_float(aggregate["average_profit_factor"])
    aggregate_return = safe_float(
        aggregate["aggregate_return_percent"]
    )
    positive_ratio = safe_float(
        aggregate["positive_run_ratio_percent"]
    )

    if symbols < 3:
        actions.append(
            "Aynı stratejiyi en az 3 farklı sembolde tekrar paper/research testine gönder."
        )

    if trades < 30:
        actions.append(
            "Daha uzun tarih aralığı veya daha fazla bağımsız run ile örneklemi büyüt."
        )

    if avg_pf < 1.0:
        actions.append(
            "Parametre, giriş/çıkış ve maliyet varsayımlarını araştır; PF < 1 kalıyorsa adayın elenmesini değerlendir."
        )

    if aggregate_return < 0:
        actions.append(
            "Negatif aggregate sonucu dönem ve piyasa rejimlerine göre ayrıştır."
        )

    if positive_ratio < 50.0:
        actions.append(
            "Hangi sembol/rejim gruplarının pozitif davranışı taşıdığını incele."
        )

    if classification == "PROMISING_PAPER_EVIDENCE":
        actions.append(
            "Bağımsız WFO + validation + cost stress sonuçlarıyla çapraz kontrol yap."
        )
    else:
        actions.append(
            "Paper kanıtını doğrulanmış strateji olarak yükseltme; WFO ve bağımsız validation devam etsin."
        )

    return actions


# ============================================================================
# SYMBOL BREAKDOWN
# ============================================================================

def symbol_breakdown(
    results: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)

    for row in results:
        groups[row["symbol"]].append(row)

    output: list[dict[str, Any]] = []

    for symbol, rows in sorted(groups.items()):
        returns = [
            safe_float(row["return_percent"])
            for row in rows
        ]

        pf_values = [
            safe_float(row["profit_factor"])
            for row in rows
            if safe_float(row["profit_factor"]) > 0
        ]

        trades = sum(
            safe_int(row["total_trades"])
            for row in rows
        )

        output.append(
            {
                "symbol": symbol,
                "runs": len(rows),
                "trades": trades,
                "positive_runs": sum(
                    1
                    for value in returns
                    if value > 0
                ),
                "negative_runs": sum(
                    1
                    for value in returns
                    if value < 0
                ),
                "average_return_percent": average(returns),
                "best_return_percent": max(returns),
                "worst_return_percent": min(returns),
                "average_profit_factor": average(pf_values),
            }
        )

    return output


# ============================================================================
# OUTPUT
# ============================================================================

def save_report(
    report: dict[str, Any],
) -> Path:
    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    strategy_id = safe_text(
        report.get("strategy_id"),
        "ALL",
    )

    timestamp = datetime.now().strftime(
        "%Y%m%d_%H%M%S"
    )

    path = (
        OUTPUT_DIR
        / f"paper_evidence_{strategy_id}_{timestamp}.json"
    )

    with path.open(
        "w",
        encoding="utf-8",
    ) as handle:
        json.dump(
            report,
            handle,
            ensure_ascii=False,
            indent=2,
        )

    return path


def print_report(
    report: dict[str, Any],
) -> None:
    aggregate = report["aggregate"]

    print()
    print("=" * 82)
    print(f"🧠 MARKET HQ PAPER EVIDENCE AGGREGATOR {ENGINE_VERSION}")
    print("=" * 82)
    print()
    print(
        f"Research Only       : {RESEARCH_ONLY}"
    )
    print(
        f"Execution Enabled   : {EXECUTION_ENABLED}"
    )
    print()
    print(
        f"Strategy ID         : {aggregate['strategy_id']}"
    )
    print(
        f"Strategy            : {aggregate['strategy_name']}"
    )
    print()
    print("-" * 82)
    print("AGGREGATED PAPER EVIDENCE")
    print("-" * 82)
    print(
        f"Raw Paper Runs      : {report['raw_run_count']}"
    )
    print(
        f"Unique Paper Runs   : {report['unique_run_count']}"
    )
    print(
        f"Duplicate Runs      : {report['duplicate_run_count']}"
    )
    print(
        f"Symbols             : {aggregate['symbol_count']}"
    )
    print(
        f"Total Trades        : {aggregate['total_trades']}"
    )
    print(
        f"Wins / Losses       : "
        f"{aggregate['total_wins']} / {aggregate['total_losses']}"
    )
    print(
        f"Win Rate            : "
        f"{aggregate['aggregate_win_rate_percent']:.2f}%"
    )
    print(
        f"Aggregate Net PnL   : "
        f"{aggregate['aggregate_net_pnl']:.2f}"
    )
    print(
        f"Aggregate Return    : "
        f"{aggregate['aggregate_return_percent']:.4f}%"
    )
    print(
        f"Avg Run Return      : "
        f"{aggregate['average_run_return_percent']:.4f}%"
    )
    print(
        f"Median Run Return   : "
        f"{aggregate['median_run_return_percent']:.4f}%"
    )
    print(
        f"Best / Worst Return : "
        f"{aggregate['best_run_return_percent']:.4f}% / "
        f"{aggregate['worst_run_return_percent']:.4f}%"
    )
    print(
        f"Avg Profit Factor   : "
        f"{aggregate['average_profit_factor']:.4f}"
    )
    print(
        f"Worst Profit Factor : "
        f"{aggregate['worst_profit_factor']:.4f}"
    )
    print(
        f"Avg Max Drawdown    : "
        f"{aggregate['average_max_drawdown_percent']:.4f}%"
    )
    print(
        f"Worst Max Drawdown  : "
        f"{aggregate['worst_max_drawdown_percent']:.4f}%"
    )
    print()
    print("-" * 82)
    print("EVIDENCE DECISION")
    print("-" * 82)
    print(
        f"Classification      : "
        f"{report['classification']}"
    )
    print()
    print("Reasons:")

    for reason in report["reasons"]:
        print(
            f"  • {reason}"
        )

    if report["duplicate_run_count"] > 0:
        print()
        print("-" * 82)
        print("DUPLICATE CONTROL")
        print("-" * 82)
        print(
            f"{report['duplicate_run_count']} duplicate replay sonucu "
            "aggregation dışında bırakıldı."
        )

    print()
    print("-" * 82)
    print("SYMBOL BREAKDOWN")
    print("-" * 82)

    for row in report["symbol_breakdown"]:
        print(
            f"{row['symbol']:12} | "
            f"runs={row['runs']:>2} | "
            f"trades={row['trades']:>3} | "
            f"avg_ret={row['average_return_percent']:>8.3f}% | "
            f"avg_pf={row['average_profit_factor']:>6.3f}"
        )

    print()
    print("-" * 82)
    print("RESEARCH ACTIONS")
    print("-" * 82)

    for action in report["research_actions"]:
        print(
            f"  → {action}"
        )

    print()
    print("=" * 82)
    print("ÖNEMLİ")
    print("=" * 82)
    print(
        "• Bu rapor yalnızca mevcut paper sonuçlarını toplar."
    )
    print(
        "• Paper evidence, doğrulanmış strateji anlamına gelmez."
    )
    print(
        "• learned_rules tablosuna otomatik kural yazılmaz."
    )
    print(
        "• Gerçek emir / broker / execution yoktur."
    )
    print(
        "• Nihai araştırma kararı bağımsız WFO + validation + cost stress ile verilmelidir."
    )
    print("=" * 82)
    print()
    print(
        f"💾 Evidence report: {report['output_file']}"
    )


# ============================================================================
# MAIN
# ============================================================================

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            f"MarketHQ Paper Evidence Aggregator {ENGINE_VERSION}"
        )
    )

    parser.add_argument(
        "--strategy-id",
        default=None,
        help=(
            "Belirli strategy_id için paper sonuçlarını "
            "toplar."
        ),
    )

    parser.add_argument(
        "--min-trades",
        type=int,
        default=DEFAULT_MIN_TRADES,
        help=(
            "Temel evidence sınıflandırması için minimum "
            "toplam işlem sayısı."
        ),
    )

    parser.add_argument(
        "--max-files",
        type=int,
        default=DEFAULT_MAX_FILES,
        help=(
            "Taranacak maksimum paper JSON sayısı."
        ),
    )

    return parser


def run(
    strategy_id: str | None = None,
    min_trades: int = DEFAULT_MIN_TRADES,
    max_files: int = DEFAULT_MAX_FILES,
) -> Path:
    if not RESEARCH_ONLY:
        raise RuntimeError(
            "Safety gate: RESEARCH_ONLY=False."
        )

    if EXECUTION_ENABLED:
        raise RuntimeError(
            "Safety gate: EXECUTION_ENABLED=True."
        )

    if min_trades < 1:
        raise ValueError(
            "--min-trades en az 1 olmalıdır."
        )

    if max_files < 1:
        raise ValueError(
            "--max-files en az 1 olmalıdır."
        )

    results, invalid = load_results(
        strategy_id=strategy_id,
        max_files=max_files,
    )

    if not results:
        wanted = (
            safe_text(strategy_id).upper()
            if strategy_id
            else "ALL"
        )

        raise FileNotFoundError(
            "Paper evidence için kullanılabilir sonuç bulunamadı. "
            f"strategy_id={wanted}, "
            f"directory={PAPER_RESULTS_DIR}"
        )

    strategy_groups: dict[str, list[dict[str, Any]]] = defaultdict(list)

    for result in results:
        strategy_groups[
            result["strategy_id"]
        ].append(result)

    if len(strategy_groups) > 1:
        raise ValueError(
            "Birden fazla strategy_id bulundu. "
            "Aggregator tek bir strategy için çalışmalıdır. "
            "Lütfen --strategy-id kullan."
        )

    raw_results = next(
        iter(strategy_groups.values())
    )

    raw_diagnostic = diagnostic_symbol_scan(raw_results)
    print()
    print("RAW SYMBOL DIAGNOSTIC")
    print("-" * 82)
    print(f"Rows loaded         : {raw_diagnostic['count']}")
    print(f"Raw symbols         : {raw_diagnostic['symbols']}")
    for symbol, files in raw_diagnostic["files_by_symbol"].items():
        print(f"  {symbol:<12} : {len(files)} file(s)")

    only_results, duplicate_results = deduplicate_results(
        raw_results
    )

    if not only_results:
        raise ValueError(
            "Duplicate filtrelemesinden sonra kullanılabilir paper sonucu kalmadı."
        )

    aggregate = aggregate_strategy(
        only_results
    )

    classification_data = classify_evidence(
        aggregate,
        min_trades=min_trades,
    )

    classification = classification_data[
        "classification"
    ]

    reasons = classification_data[
        "reasons"
    ]

    actions = research_actions(
        aggregate,
        classification,
    )

    report = {
        "engine": ENGINE_NAME,
        "diagnostics": {
            "raw_rows_loaded": len(results),
            "unique_rows_after_dedup": len(only_results),
            "duplicate_rows_removed": len(duplicate_results),
            "unique_symbols_loaded": sorted(
                {
                    safe_text(row.get("symbol")).upper()
                    for row in only_results
                    if safe_text(row.get("symbol"))
                }
            ),
            "raw_symbols_loaded": sorted(
                {
                    safe_text(row.get("symbol")).upper()
                    for row in results
                    if safe_text(row.get("symbol"))
                }
            ),
            "raw_files_by_symbol": raw_diagnostic["files_by_symbol"],
        },
        "engine_version": ENGINE_VERSION,
        "created_at": utc_now(),
        "research_only": True,
        "execution_enabled": False,
        "strategy_id": aggregate["strategy_id"],
        "strategy_name": aggregate["strategy_name"],
        "classification": classification,
        "reasons": reasons,
        "aggregate": aggregate,
        "raw_run_count": len(raw_results),
        "unique_run_count": len(only_results),
        "duplicate_run_count": len(duplicate_results),
        "duplicate_runs": duplicate_results,
        "symbol_breakdown": symbol_breakdown(
            only_results
        ),
        "source_files": [
            row["source_file"]
            for row in only_results
        ],
        "raw_source_files": [
            row["source_file"]
            for row in raw_results
        ],
        "invalid_files_skipped": invalid,
        "duplicate_replays": duplicate_results,
        "research_actions": actions,
    }

    output_path = save_report(
        report
    )

    report["output_file"] = str(
        output_path
    )

    # Rewrite after output_file is known.
    with output_path.open(
        "w",
        encoding="utf-8",
    ) as handle:
        json.dump(
            report,
            handle,
            ensure_ascii=False,
            indent=2,
        )

    print_report(
        report
    )

    return output_path


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    try:
        run(
            strategy_id=args.strategy_id,
            min_trades=args.min_trades,
            max_files=args.max_files,
        )

    except KeyboardInterrupt:
        print()
        print(
            "İşlem kullanıcı tarafından durduruldu."
        )

    except Exception as exc:
        print()
        print("=" * 82)
        print(
            "❌ PAPER EVIDENCE AGGREGATOR HATASI"
        )
        print("=" * 82)
        print(
            f"{type(exc).__name__}: {exc}"
        )
        print("=" * 82)
        raise SystemExit(1)


if __name__ == "__main__":
    main()

