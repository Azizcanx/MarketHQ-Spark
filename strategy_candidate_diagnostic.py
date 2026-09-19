# -*- coding: utf-8 -*-

"""
MarketHQ - Strategy Candidate Diagnostic V1
-------------------------------------------

Amaç:
V4.2 pipeline'ında 384 adayın neden
"Yeterli trade üreten aday yok" sonucuna düştüğünü
teşhis etmek.

Bu dosya:
- Mevcut backtest motorunu kullanır.
- Strateji üretmez.
- KB değiştirmez.
- Broker / order execution yapmaz.
- Sadece araştırma ve teşhis yapar.

Çıktı:
- Her sembolde kaç adayın 0 trade ürettiği
- 1-2 trade üreten aday sayısı
- 3-4 trade üreten aday sayısı
- 5-7 trade üreten aday sayısı
- 8+ trade üreten aday sayısı
- En fazla trade üreten adaylar
- En iyi return / PF adayları
"""

from __future__ import annotations

import json
import math
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from backtest_engine import run_backtest


PROJECT_ROOT = Path(__file__).resolve().parent

RESULT_DIR = (
    PROJECT_ROOT
    / "strategy_diagnostic_results"
)

RESULT_DIR.mkdir(
    parents=True,
    exist_ok=True,
)


BIST_RESEARCH_UNIVERSE = [
    "THYAO.IS",
    "ASELS.IS",
    "GARAN.IS",
    "AKBNK.IS",
    "EREGL.IS",
    "TUPRS.IS",
    "SISE.IS",
    "BIMAS.IS",
]


US_RESEARCH_UNIVERSE = [
    "AAPL",
    "MSFT",
    "NVDA",
    "AMZN",
    "GOOGL",
    "META",
    "TSLA",
    "AVGO",
]


COMBINED_RESEARCH_UNIVERSE = (
    BIST_RESEARCH_UNIVERSE
    + US_RESEARCH_UNIVERSE
)


BACKTEST_PERIOD = "1y"

MIN_TRAIN_TRADES = 8


SMA_FAST_VALUES = [
    10,
    20,
    30,
]

SMA_SLOW_VALUES = [
    50,
    100,
]

EMA_FAST_VALUES = [
    10,
    20,
]

EMA_SLOW_VALUES = [
    30,
    50,
]

RSI_PERIOD_VALUES = [
    14,
]

RSI_OVERSOLD_VALUES = [
    25,
    30,
]

RSI_OVERBOUGHT_VALUES = [
    65,
    70,
]

STOP_ATR_VALUES = [
    1.5,
    2.0,
]

TARGET_ATR_VALUES = [
    2.0,
    3.0,
]


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def utc_timestamp() -> str:
    return utc_now().strftime(
        "%Y%m%d_%H%M%S"
    )


def safe_float(
    value: Any,
    default: float = 0.0,
) -> float:

    try:

        if value is None:
            return default

        result = float(value)

        if not math.isfinite(result):
            return default

        return result

    except (
        TypeError,
        ValueError,
    ):

        return default


def safe_int(
    value: Any,
    default: int = 0,
) -> int:

    try:
        return int(value)

    except (
        TypeError,
        ValueError,
    ):

        return default


def normalize_history(
    data: pd.DataFrame,
) -> pd.DataFrame:

    if data is None:
        return pd.DataFrame()

    if not isinstance(
        data,
        pd.DataFrame,
    ):
        return pd.DataFrame()

    result = data.copy()

    if isinstance(
        result.columns,
        pd.MultiIndex,
    ):

        flattened = []

        for column in result.columns:

            if isinstance(
                column,
                tuple,
            ):

                flattened.append(
                    str(column[0])
                )

            else:

                flattened.append(
                    str(column)
                )

        result.columns = flattened

    rename_map = {}

    for column in result.columns:

        name = (
            str(column)
            .strip()
            .lower()
        )

        if name == "open":
            rename_map[column] = "Open"

        elif name == "high":
            rename_map[column] = "High"

        elif name == "low":
            rename_map[column] = "Low"

        elif name == "close":
            rename_map[column] = "Close"

        elif name == "adj close":
            rename_map[column] = "Adj Close"

        elif name == "volume":
            rename_map[column] = "Volume"

    result = result.rename(
        columns=rename_map
    )

    required = [
        "Open",
        "High",
        "Low",
        "Close",
        "Volume",
    ]

    if not all(
        column in result.columns
        for column in required
    ):

        return pd.DataFrame()

    result = result[
        required
    ].copy()

    for column in required:

        result[column] = pd.to_numeric(
            result[column],
            errors="coerce",
        )

    result = result.dropna(
        subset=[
            "Open",
            "High",
            "Low",
            "Close",
        ]
    )

    result = result.sort_index()

    return result


def load_history(
    symbol: str,
    period: str,
) -> pd.DataFrame:

    print(
        f"   📥 Veri alınıyor: "
        f"{symbol} | {period}"
    )

    try:

        import yfinance as yf

        data = yf.download(
            symbol,
            period=period,
            interval="1d",
            auto_adjust=False,
            progress=False,
        )

        result = normalize_history(
            data
        )

        if result.empty:

            print(
                "   ⚠️ Veri boş."
            )

        else:

            print(
                f"   ✅ {len(result)} bar"
            )

        return result

    except Exception as exc:

        print(
            f"   ❌ Veri alınamadı: "
            f"{type(exc).__name__}: {exc}"
        )

        return pd.DataFrame()


def build_parameter_candidates() -> list[
    dict[str, Any]
]:

    candidates = []

    for sma_fast in SMA_FAST_VALUES:

        for sma_slow in SMA_SLOW_VALUES:

            for ema_fast in EMA_FAST_VALUES:

                for ema_slow in EMA_SLOW_VALUES:

                    for rsi_period in (
                        RSI_PERIOD_VALUES
                    ):

                        for rsi_oversold in (
                            RSI_OVERSOLD_VALUES
                        ):

                            for rsi_overbought in (
                                RSI_OVERBOUGHT_VALUES
                            ):

                                for stop_atr in (
                                    STOP_ATR_VALUES
                                ):

                                    for target_atr in (
                                        TARGET_ATR_VALUES
                                    ):

                                        if (
                                            sma_fast
                                            >= sma_slow
                                        ):
                                            continue

                                        if (
                                            ema_fast
                                            >= ema_slow
                                        ):
                                            continue

                                        if (
                                            rsi_oversold
                                            >= rsi_overbought
                                        ):
                                            continue

                                        candidates.append(
                                            {
                                                "sma_fast": sma_fast,
                                                "sma_slow": sma_slow,
                                                "ema_fast": ema_fast,
                                                "ema_slow": ema_slow,
                                                "rsi_period": rsi_period,
                                                "rsi_oversold": rsi_oversold,
                                                "rsi_overbought": rsi_overbought,
                                                "stop_atr_multiplier": stop_atr,
                                                "target_atr_multiplier": target_atr,
                                            }
                                        )

    return candidates


def build_signal_config(
    candidate: dict[str, Any],
) -> dict[str, Any]:

    return {
        "sma_fast": candidate[
            "sma_fast"
        ],
        "sma_slow": candidate[
            "sma_slow"
        ],
        "ema_fast": candidate[
            "ema_fast"
        ],
        "ema_slow": candidate[
            "ema_slow"
        ],
        "rsi_period": candidate[
            "rsi_period"
        ],
        "rsi_oversold": candidate[
            "rsi_oversold"
        ],
        "rsi_overbought": candidate[
            "rsi_overbought"
        ],
        "buy_threshold": 3,
        "sell_threshold": -3,
    }


def build_backtest_config(
    candidate: dict[str, Any],
) -> dict[str, Any]:

    return {
        "initial_capital": 100000,
        "position_size": 0.10,
        "commission": 0.001,
        "slippage": 0.0005,
        "allow_short": True,
        "one_position_at_a_time": True,
        "stop_atr_multiplier": candidate[
            "stop_atr_multiplier"
        ],
        "target_atr_multiplier": candidate[
            "target_atr_multiplier"
        ],
        "max_holding_bars": 60,
        "exit_on_opposite_signal": True,
    }


def extract_metrics(
    result: dict[str, Any],
) -> dict[str, Any]:

    trades = safe_int(
        result.get(
            "trades",
            result.get(
                "total_trades",
                0,
            ),
        )
    )

    wins = safe_int(
        result.get(
            "wins",
            result.get(
                "winning_trades",
                0,
            ),
        )
    )

    losses = safe_int(
        result.get(
            "losses",
            result.get(
                "losing_trades",
                0,
            ),
        )
    )

    win_rate = safe_float(
        result.get(
            "win_rate",
            0,
        )
    )

    profit_factor = safe_float(
        result.get(
            "profit_factor",
            result.get(
                "pf",
                0,
            ),
        )
    )

    total_pnl = safe_float(
        result.get(
            "total_pnl",
            result.get(
                "net_pnl",
                0,
            ),
        )
    )

    return_pct = safe_float(
        result.get(
            "return_pct",
            result.get(
                "return",
                0,
            ),
        )
    )

    max_drawdown = safe_float(
        result.get(
            "max_drawdown",
            result.get(
                "max_dd",
                0,
            ),
        )
    )

    return {
        "trades": trades,
        "wins": wins,
        "losses": losses,
        "win_rate": win_rate,
        "profit_factor": profit_factor,
        "total_pnl": total_pnl,
        "return_pct": return_pct,
        "max_drawdown": max_drawdown,
    }


def run_candidate(
    data: pd.DataFrame,
    symbol: str,
    candidate: dict[str, Any],
) -> dict[str, Any]:

    try:

        result = run_backtest(
            data=data,
            symbol=symbol,
            signal_config=build_signal_config(
                candidate
            ),
            backtest_config=build_backtest_config(
                candidate
            ),
        )

        if not isinstance(
            result,
            dict,
        ):

            return {
                "status": "ERROR",
                "error": (
                    "Backtest dict "
                    "döndürmedi."
                ),
                "metrics": {},
            }

        if (
            result.get("status")
            == "ERROR"
        ):

            return {
                "status": "ERROR",
                "error": str(
                    result.get(
                        "error",
                        "Bilinmeyen hata",
                    )
                ),
                "metrics": {},
            }

        return {
            "status": "DONE",
            "error": None,
            "metrics": extract_metrics(
                result
            ),
        }

    except Exception as exc:

        return {
            "status": "ERROR",
            "error": (
                f"{type(exc).__name__}: "
                f"{exc}"
            ),
            "metrics": {},
        }


def classify_trade_count(
    trades: int,
) -> str:

    if trades == 0:
        return "ZERO"

    if trades <= 2:
        return "LOW_1_2"

    if trades <= 4:
        return "LOW_3_4"

    if trades <= 7:
        return "NEAR_THRESHOLD_5_7"

    return "PASS_8_PLUS"


def run_symbol_diagnostic(
    symbol: str,
    data: pd.DataFrame,
    candidates: list[
        dict[str, Any]
    ],
) -> dict[str, Any]:

    print()
    print("=" * 78)
    print(
        f"🔎 DIAGNOSTIC: {symbol}"
    )
    print("=" * 78)

    print(
        f"Bars       : {len(data)}"
    )

    print(
        f"Candidates : {len(candidates)}"
    )

    distribution = {
        "ZERO": 0,
        "LOW_1_2": 0,
        "LOW_3_4": 0,
        "NEAR_THRESHOLD_5_7": 0,
        "PASS_8_PLUS": 0,
    }

    successful = []
    errors = []

    total = len(candidates)

    for index, candidate in enumerate(
        candidates,
        start=1,
    ):

        result = run_candidate(
            data=data,
            symbol=symbol,
            candidate=candidate,
        )

        if (
            result["status"]
            == "ERROR"
        ):

            errors.append(
                {
                    "candidate": candidate,
                    "error": result[
                        "error"
                    ],
                }
            )

            continue

        metrics = result[
            "metrics"
        ]

        trades = metrics[
            "trades"
        ]

        category = classify_trade_count(
            trades
        )

        distribution[
            category
        ] += 1

        successful.append(
            {
                "candidate": candidate,
                "metrics": metrics,
            }
        )

        if (
            index == 1
            or index % 50 == 0
            or index == total
        ):

            print(
                f"   Progress: "
                f"{index}/{total}"
            )

    by_trades = sorted(
        successful,
        key=lambda item: (
            item["metrics"][
                "trades"
            ],
            item["metrics"][
                "return_pct"
            ],
        ),
        reverse=True,
    )

    by_return = sorted(
        successful,
        key=lambda item: (
            item["metrics"][
                "return_pct"
            ],
            item["metrics"][
                "profit_factor"
            ],
        ),
        reverse=True,
    )

    by_pf = sorted(
        successful,
        key=lambda item: (
            item["metrics"][
                "profit_factor"
            ],
            item["metrics"][
                "return_pct"
            ],
        ),
        reverse=True,
    )

    print()
    print(
        "📊 TRADE DISTRIBUTION"
    )

    print(
        f"   0 trade       : "
        f"{distribution['ZERO']}"
    )

    print(
        f"   1-2 trades   : "
        f"{distribution['LOW_1_2']}"
    )

    print(
        f"   3-4 trades   : "
        f"{distribution['LOW_3_4']}"
    )

    print(
        f"   5-7 trades   : "
        f"{distribution['NEAR_THRESHOLD_5_7']}"
    )

    print(
        f"   8+ trades    : "
        f"{distribution['PASS_8_PLUS']}"
    )

    print(
        f"   Errors       : "
        f"{len(errors)}"
    )

    print()
    print(
        "🏆 MOST ACTIVE CANDIDATES"
    )

    for rank, item in enumerate(
        by_trades[:5],
        start=1,
    ):

        candidate = item[
            "candidate"
        ]

        metrics = item[
            "metrics"
        ]

        print(
            f"   {rank}. "
            f"Trades={metrics['trades']} | "
            f"Return={metrics['return_pct']:.2f}% | "
            f"PF={metrics['profit_factor']:.3f} | "
            f"SMA="
            f"{candidate['sma_fast']}/"
            f"{candidate['sma_slow']} | "
            f"EMA="
            f"{candidate['ema_fast']}/"
            f"{candidate['ema_slow']} | "
            f"RSI="
            f"{candidate['rsi_oversold']}/"
            f"{candidate['rsi_overbought']} | "
            f"ATR="
            f"{candidate['stop_atr_multiplier']}/"
            f"{candidate['target_atr_multiplier']}"
        )

    print()
    print(
        "💰 BEST RETURN CANDIDATES"
    )

    for rank, item in enumerate(
        by_return[:5],
        start=1,
    ):

        candidate = item[
            "candidate"
        ]

        metrics = item[
            "metrics"
        ]

        print(
            f"   {rank}. "
            f"Return={metrics['return_pct']:.2f}% | "
            f"Trades={metrics['trades']} | "
            f"PF={metrics['profit_factor']:.3f} | "
            f"SMA="
            f"{candidate['sma_fast']}/"
            f"{candidate['sma_slow']} | "
            f"EMA="
            f"{candidate['ema_fast']}/"
            f"{candidate['ema_slow']}"
        )

    print()
    print(
        "📈 BEST PROFIT FACTOR CANDIDATES"
    )

    for rank, item in enumerate(
        by_pf[:5],
        start=1,
    ):

        candidate = item[
            "candidate"
        ]

        metrics = item[
            "metrics"
        ]

        print(
            f"   {rank}. "
            f"PF={metrics['profit_factor']:.3f} | "
            f"Return={metrics['return_pct']:.2f}% | "
            f"Trades={metrics['trades']} | "
            f"SMA="
            f"{candidate['sma_fast']}/"
            f"{candidate['sma_slow']} | "
            f"EMA="
            f"{candidate['ema_fast']}/"
            f"{candidate['ema_slow']}"
        )

    return {
        "symbol": symbol,
        "bars": len(data),
        "candidate_count": len(
            candidates
        ),
        "distribution": distribution,
        "errors": errors,
        "top_by_trades": by_trades[:10],
        "top_by_return": by_return[:10],
        "top_by_profit_factor": by_pf[:10],
    }


def print_global_summary(
    results: list[
        dict[str, Any]
    ],
) -> None:

    print()
    print("=" * 78)
    print(
        "🏁 GLOBAL DIAGNOSTIC SUMMARY"
    )
    print("=" * 78)

    total_zero = 0
    total_low_1_2 = 0
    total_low_3_4 = 0
    total_near = 0
    total_pass = 0
    total_errors = 0

    for result in results:

        distribution = result[
            "distribution"
        ]

        total_zero += distribution[
            "ZERO"
        ]

        total_low_1_2 += distribution[
            "LOW_1_2"
        ]

        total_low_3_4 += distribution[
            "LOW_3_4"
        ]

        total_near += distribution[
            "NEAR_THRESHOLD_5_7"
        ]

        total_pass += distribution[
            "PASS_8_PLUS"
        ]

        total_errors += len(
            result["errors"]
        )

    print(
        f"0 trade             : "
        f"{total_zero}"
    )

    print(
        f"1-2 trade           : "
        f"{total_low_1_2}"
    )

    print(
        f"3-4 trade           : "
        f"{total_low_3_4}"
    )

    print(
        f"5-7 trade           : "
        f"{total_near}"
    )

    print(
        f"8+ trade            : "
        f"{total_pass}"
    )

    print(
        f"Errors              : "
        f"{total_errors}"
    )

    print()

    if total_pass == 0:

        print(
            "🔴 TEŞHİS:"
        )

        print(
            "384 adayın hiçbiri "
            "minimum 8 trade filtresini "
            "geçemiyor."
        )

        print()
        print(
            "Bir sonraki adım:"
        )

        print(
            "Backtest filtresinden önce "
            "signal üretim katmanını "
            "incelemek gerekiyor."
        )

    else:

        print(
            "🟢 TEŞHİS:"
        )

        print(
            f"{total_pass} aday "
            "8+ trade üretiyor."
        )

        print(
            "V4.2'nin minimum trade "
            "filtresi tek başına sorun değil."
        )


def save_results(
    results: list[
        dict[str, Any]
    ],
    candidates: list[
        dict[str, Any]
    ],
) -> Path:

    output = {
        "diagnostic_version": "V1",
        "timestamp": utc_now().isoformat(),
        "research_only": True,
        "execution_enabled": False,
        "period": BACKTEST_PERIOD,
        "minimum_trades": MIN_TRAIN_TRADES,
        "candidate_count": len(
            candidates
        ),
        "symbols": [
            result["symbol"]
            for result in results
        ],
        "results": results,
    }

    path = (
        RESULT_DIR
        / (
            "candidate_diagnostic_"
            f"{utc_timestamp()}.json"
        )
    )

    with path.open(
        "w",
        encoding="utf-8",
    ) as file:

        json.dump(
            output,
            file,
            ensure_ascii=False,
            indent=2,
            default=str,
        )

    return path


def main() -> int:

    print()
    print("=" * 78)
    print(
        "🔎 MARKET HQ CANDIDATE DIAGNOSTIC V1"
    )
    print("=" * 78)

    print()
    print(
        "Amaç:"
    )

    print(
        "384 adayın neden "
        "trade filtresini geçemediğini "
        "tespit etmek."
    )

    print()
    print(
        "Research Only     : True"
    )

    print(
        "Execution Enabled : False"
    )

    candidates = (
        build_parameter_candidates()
    )

    print()
    print(
        f"⚙️ Candidate count: "
        f"{len(candidates)}"
    )

    print()
    print(
        "🌍 Universe:"
    )

    print(
        ", ".join(
            COMBINED_RESEARCH_UNIVERSE
        )
    )

    results = []

    for index, symbol in enumerate(
        COMBINED_RESEARCH_UNIVERSE,
        start=1,
    ):

        print()
        print(
            f"📈 SYMBOL "
            f"{index}/"
            f"{len(COMBINED_RESEARCH_UNIVERSE)}: "
            f"{symbol}"
        )

        data = load_history(
            symbol,
            BACKTEST_PERIOD,
        )

        if data.empty:

            print(
                "   ⚠️ Sembol atlandı."
            )

            results.append(
                {
                    "symbol": symbol,
                    "bars": 0,
                    "candidate_count": len(
                        candidates
                    ),
                    "distribution": {
                        "ZERO": 0,
                        "LOW_1_2": 0,
                        "LOW_3_4": 0,
                        "NEAR_THRESHOLD_5_7": 0,
                        "PASS_8_PLUS": 0,
                    },
                    "errors": [],
                    "top_by_trades": [],
                    "top_by_return": [],
                    "top_by_profit_factor": [],
                    "status": "NO_DATA",
                }
            )

            continue

        result = run_symbol_diagnostic(
            symbol=symbol,
            data=data,
            candidates=candidates,
        )

        result["status"] = "DONE"

        results.append(
            result
        )

    print_global_summary(
        results
    )

    output_path = save_results(
        results=results,
        candidates=candidates,
    )

    print()
    print("=" * 78)
    print(
        "💾 DIAGNOSTIC RESULT SAVED"
    )
    print("=" * 78)

    print(
        output_path
    )

    print()
    print(
        "✅ Diagnostic tamamlandı."
    )

    print(
        "Bir sonraki aşamada bu çıktıya "
        "göre V4.2'yi düzelteceğiz."
    )

    return 0


if __name__ == "__main__":

    try:

        raise SystemExit(
            main()
        )

    except KeyboardInterrupt:

        print()
        print(
            "⛔ Diagnostic kullanıcı "
            "tarafından durduruldu."
        )

        raise SystemExit(130)

    except Exception as exc:

        print()
        print(
            "❌ DIAGNOSTIC ERROR"
        )

        print(
            f"{type(exc).__name__}: "
            f"{exc}"
        )

        traceback.print_exc()

        raise SystemExit(1)
