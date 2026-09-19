from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import pandas as pd

from agents.market_data_agent import get_signal_data
from signal_engine import DEFAULT_CONFIG, add_indicators, generate_signal


# =========================================================
# AYARLAR
# =========================================================

SYMBOL = "THYAO.IS"
PERIOD = "1y"

TEST_CANDIDATES = [
    {
        "name": "DEFAULT",
        "config": {},
    },
    {
        "name": "SMA_10_100",
        "config": {
            "sma_fast": 10,
            "sma_slow": 100,
            "ema_fast": 20,
            "ema_slow": 50,
            "rsi_period": 14,
            "rsi_oversold": 30,
            "rsi_overbought": 65,
        },
    },
    {
        "name": "SMA_5_20",
        "config": {
            "sma_fast": 5,
            "sma_slow": 20,
            "ema_fast": 9,
            "ema_slow": 21,
            "rsi_period": 14,
            "rsi_oversold": 30,
            "rsi_overbought": 70,
        },
    },
    {
        "name": "SMA_20_50",
        "config": {
            "sma_fast": 20,
            "sma_slow": 50,
            "ema_fast": 20,
            "ema_slow": 50,
            "rsi_period": 14,
            "rsi_oversold": 30,
            "rsi_overbought": 70,
        },
    },
]


# =========================================================
# HELPERS
# =========================================================

def safe_float(
    value: Any,
    default: float | None = None,
) -> float | None:
    try:
        if value is None:
            return default

        result = float(value)

        if not math.isfinite(result):
            return default

        return result

    except (TypeError, ValueError):
        return default


def merge_config(
    base: dict[str, Any],
    override: dict[str, Any] | None,
) -> dict[str, Any]:

    result = dict(base)

    if override:
        result.update(override)

    return result


def json_safe(value: Any) -> Any:
    if value is None:
        return None

    if isinstance(value, (str, int, bool)):
        return value

    if isinstance(value, float):
        if math.isfinite(value):
            return value
        return None

    if hasattr(value, "item"):
        try:
            return json_safe(value.item())
        except Exception:
            pass

    if isinstance(value, dict):
        return {
            str(key): json_safe(item)
            for key, item in value.items()
        }

    if isinstance(value, (list, tuple)):
        return [
            json_safe(item)
            for item in value
        ]

    return str(value)


def run_signal(
    row: pd.Series,
    config: dict[str, Any],
) -> dict[str, Any]:

    try:
        result = generate_signal(
            row,
            config,
        )

        if isinstance(result, dict):
            return result

        return {
            "signal": str(result),
            "score": None,
            "reason": "",
        }

    except Exception as exc:
        return {
            "signal": "ERROR",
            "score": None,
            "reason": str(exc),
        }


# =========================================================
# DATA
# =========================================================

def load_data() -> pd.DataFrame | None:

    print()
    print("=" * 70)
    print("MarketHQ SIGNAL ENGINE DIAGNOSTIC")
    print("=" * 70)
    print()

    print(f"Symbol : {SYMBOL}")
    print(f"Period : {PERIOD}")
    print()

    try:
        data = get_signal_data(
            SYMBOL,
            period=PERIOD,
        )

    except Exception as exc:
        print(
            f"❌ Veri alınamadı: {exc}"
        )
        return None

    if data is None or data.empty:
        print(
            "❌ Veri boş."
        )
        return None

    print(
        f"✅ Veri alındı: {len(data)} bar"
    )

    print(
        f"📅 İlk tarih : {data.index.min()}"
    )

    print(
        f"📅 Son tarih : {data.index.max()}"
    )

    return data


# =========================================================
# INDICATOR DIAGNOSTIC
# =========================================================

def print_indicator_diagnostic(
    data: pd.DataFrame,
    config: dict[str, Any],
) -> pd.DataFrame:

    print()
    print("-" * 70)
    print("INDICATOR DIAGNOSTIC")
    print("-" * 70)

    try:
        df = add_indicators(
            data.copy(),
            config,
        )

    except Exception as exc:
        print(
            f"❌ Indicator hesaplama hatası: {exc}"
        )
        return pd.DataFrame()

    wanted_columns = [
        "Open",
        "High",
        "Low",
        "Close",
        "Volume",
        "SMA_fast",
        "SMA_slow",
        "EMA_fast",
        "EMA_slow",
        "RSI",
        "MACD",
        "MACD_signal",
        "MACD_hist",
        "BB_upper",
        "BB_middle",
        "BB_lower",
        "ATR",
        "Volume_Ratio",
    ]

    existing = [
        column
        for column in wanted_columns
        if column in df.columns
    ]

    print()
    print("Bulunan indicator kolonları:")

    for column in existing:
        print(
            f"  ✅ {column}"
        )

    missing = [
        column
        for column in wanted_columns
        if column not in df.columns
    ]

    if missing:
        print()
        print("Eksik indicator kolonları:")

        for column in missing:
            print(
                f"  ⚠️ {column}"
            )

    print()
    print("SON 5 BAR INDICATOR DURUMU")
    print("-" * 70)

    display_columns = [
        column
        for column in existing
        if column != "Volume"
    ]

    if display_columns:
        print(
            df[display_columns]
            .tail(5)
            .to_string()
        )

    return df


# =========================================================
# SIGNAL ANALYSIS
# =========================================================

def analyze_signals(
    df: pd.DataFrame,
    config: dict[str, Any],
) -> dict[str, Any]:

    signals: list[dict[str, Any]] = []

    for index, row in df.iterrows():

        result = run_signal(
            row,
            config,
        )

        signal = str(
            result.get(
                "signal",
                "WAIT",
            )
        ).upper()

        score = safe_float(
            result.get("score")
        )

        reason = str(
            result.get(
                "reason",
                "",
            )
        )

        signals.append(
            {
                "timestamp": str(index),
                "signal": signal,
                "score": score,
                "reason": reason,
            }
        )

    signal_counts = {
        "BUY": 0,
        "SELL": 0,
        "WAIT": 0,
        "ERROR": 0,
        "OTHER": 0,
    }

    scores: list[float] = []

    for item in signals:

        signal = item["signal"]

        if signal in signal_counts:
            signal_counts[signal] += 1
        else:
            signal_counts["OTHER"] += 1

        score = item["score"]

        if score is not None:
            scores.append(score)

    return {
        "signals": signals,
        "signal_counts": signal_counts,
        "scores": scores,
    }


# =========================================================
# SIGNAL REPORT
# =========================================================

def print_signal_report(
    candidate_name: str,
    analysis: dict[str, Any],
) -> None:

    counts = analysis["signal_counts"]
    scores = analysis["scores"]

    print()
    print("=" * 70)
    print(
        f"SIGNAL REPORT — {candidate_name}"
    )
    print("=" * 70)

    total = sum(
        counts.values()
    )

    print()
    print(
        f"Toplam bar : {total}"
    )

    print(
        f"BUY        : {counts['BUY']}"
    )

    print(
        f"SELL       : {counts['SELL']}"
    )

    print(
        f"WAIT       : {counts['WAIT']}"
    )

    print(
        f"ERROR      : {counts['ERROR']}"
    )

    print(
        f"OTHER      : {counts['OTHER']}"
    )

    print()

    if scores:
        print("SCORE ANALİZİ")
        print("-" * 70)

        print(
            f"Min        : {min(scores):.4f}"
        )

        print(
            f"Max        : {max(scores):.4f}"
        )

        print(
            f"Ortalama   : "
            f"{sum(scores) / len(scores):.4f}"
        )

    else:
        print(
            "⚠️ Hiçbir score üretilemedi."
        )

    print()
    print("SON 10 BAR")
    print("-" * 70)

    for item in analysis["signals"][-10:]:

        score_text = (
            f"{item['score']:.4f}"
            if item["score"] is not None
            else "None"
        )

        reason = item["reason"]

        if len(reason) > 100:
            reason = reason[:100] + "..."

        print(
            f"{item['timestamp']} | "
            f"{item['signal']:5s} | "
            f"score={score_text:>8s} | "
            f"{reason}"
        )


# =========================================================
# RAW SIGNAL SAMPLE
# =========================================================

def print_raw_signal_samples(
    df: pd.DataFrame,
    config: dict[str, Any],
) -> None:

    print()
    print("RAW SIGNAL SAMPLE")
    print("-" * 70)

    sample = df.tail(5)

    for index, row in sample.iterrows():

        result = run_signal(
            row,
            config,
        )

        print()
        print(
            f"Tarih : {index}"
        )

        print(
            f"Close : {safe_float(row.get('Close'))}"
        )

        safe_result = json.dumps(
            json_safe(result),
            ensure_ascii=False,
            indent=2,
        )

        print(
            f"Signal: {safe_result}"
        )


# =========================================================
# CANDIDATE TEST
# =========================================================

def test_candidate(
    data: pd.DataFrame,
    candidate_name: str,
    candidate_config: dict[str, Any],
) -> dict[str, Any]:

    config = merge_config(
        DEFAULT_CONFIG,
        candidate_config,
    )

    print()
    print()
    print("#" * 70)
    print(
        f"CANDIDATE: {candidate_name}"
    )
    print("#" * 70)

    print()
    print("KULLANILAN CONFIG")

    for key in sorted(config.keys()):
        print(
            f"  {key}: {config[key]}"
        )

    df = print_indicator_diagnostic(
        data,
        config,
    )

    if df.empty:
        return {
            "name": candidate_name,
            "config": config,
            "error": "Indicator hesaplanamadı",
        }

    analysis = analyze_signals(
        df,
        config,
    )

    print_signal_report(
        candidate_name,
        analysis,
    )

    print_raw_signal_samples(
        df,
        config,
    )

    return {
        "name": candidate_name,
        "config": config,
        "signal_counts": analysis["signal_counts"],
        "score_min": (
            min(analysis["scores"])
            if analysis["scores"]
            else None
        ),
        "score_max": (
            max(analysis["scores"])
            if analysis["scores"]
            else None
        ),
        "score_average": (
            sum(analysis["scores"])
            / len(analysis["scores"])
            if analysis["scores"]
            else None
        ),
        "last_10": analysis["signals"][-10:],
    }


# =========================================================
# SAVE RESULT
# =========================================================

def save_results(
    results: list[dict[str, Any]],
) -> Path:

    output_dir = Path(
        "strategy_diagnostic_results"
    )

    output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    output_file = (
        output_dir
        / "signal_engine_diagnostic.json"
    )

    payload = {
        "symbol": SYMBOL,
        "period": PERIOD,
        "research_only": True,
        "execution_enabled": False,
        "results": results,
    }

    with output_file.open(
        "w",
        encoding="utf-8",
    ) as handle:

        json.dump(
            json_safe(payload),
            handle,
            ensure_ascii=False,
            indent=2,
        )

    return output_file


# =========================================================
# GLOBAL SUMMARY
# =========================================================

def print_global_summary(
    results: list[dict[str, Any]],
) -> None:

    print()
    print()
    print("=" * 70)
    print("GLOBAL DIAGNOSTIC SUMMARY")
    print("=" * 70)

    print()

    for result in results:

        name = result.get(
            "name",
            "UNKNOWN",
        )

        if "error" in result:

            print(
                f"{name:15s} | "
                f"ERROR | "
                f"{result['error']}"
            )

            continue

        counts = result.get(
            "signal_counts",
            {},
        )

        print(
            f"{name:15s} | "
            f"BUY={counts.get('BUY', 0):4d} | "
            f"SELL={counts.get('SELL', 0):4d} | "
            f"WAIT={counts.get('WAIT', 0):4d} | "
            f"ERROR={counts.get('ERROR', 0):4d} | "
            f"SCORE="
            f"{result.get('score_min')} / "
            f"{result.get('score_max')}"
        )

    print()

    print(
        "Research Only : True"
    )

    print(
        "Execution     : False"
    )

    print("=" * 70)
    print()


# =========================================================
# MAIN
# =========================================================

def main() -> None:

    data = load_data()

    if data is None:
        return

    results: list[dict[str, Any]] = []

    for candidate in TEST_CANDIDATES:

        result = test_candidate(
            data=data,
            candidate_name=candidate["name"],
            candidate_config=candidate["config"],
        )

        results.append(result)

    print_global_summary(
        results
    )

    output_file = save_results(
        results
    )

    print(
        f"📁 Sonuç JSON: {output_file}"
    )

    print()
    print(
        "✅ Signal Engine diagnostic tamamlandı."
    )
    print()


if __name__ == "__main__":
    main()
