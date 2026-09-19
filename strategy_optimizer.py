# -*- coding: utf-8 -*-

"""
MarketHQ Strategy Optimizer V2
==============================

Amaç:
    Signal Engine ve Backtest Engine parametrelerini sistematik olarak
    test etmek.

ÖNEMLİ:
    Signal parametreleri -> signal_config
    Risk / execution parametreleri -> backtest_config

Böylece ATR stop/target gibi değerlerin gerçekten backtest sonucunu
değiştirdiği garanti edilir.

Bu dosya yalnızca araştırma / backtest içindir.
Gerçek emir göndermez.
"""

from __future__ import annotations

import itertools
import math
from pathlib import Path
from typing import Any

import pandas as pd

from agents.market_data_agent import get_signal_data
from backtest_engine import (
    DEFAULT_BACKTEST_CONFIG,
    run_backtest,
)


# =========================================================
# PATHS
# =========================================================

PROJECT_ROOT = Path(
    __file__
).resolve().parent

OUTPUT_DIR = (
    PROJECT_ROOT
    / "optimizer_results"
)


# =========================================================
# OPTIMIZER CONFIG
# =========================================================

DEFAULT_OPTIMIZER_CONFIG: dict[str, Any] = {

    # Ekranda kaç sonuç gösterilecek?
    "top_n": 20,

    # Çok az işlem yapan stratejileri
    # üst sıralara çıkarmama filtresi.
    "minimum_trades": 10,

    # -----------------------------------------------------
    # SMA
    # -----------------------------------------------------

    "sma_fast_values": [
        10,
        15,
        20,
    ],

    "sma_slow_values": [
        30,
        50,
        100,
    ],

    # -----------------------------------------------------
    # EMA
    # -----------------------------------------------------

    "ema_fast_values": [
        10,
        15,
        20,
    ],

    "ema_slow_values": [
        30,
        50,
        100,
    ],

    # -----------------------------------------------------
    # RSI
    # -----------------------------------------------------

    "rsi_period_values": [
        14,
    ],

    "rsi_oversold_values": [
        25,
        30,
        35,
    ],

    "rsi_overbought_values": [
        65,
        70,
        75,
    ],

    # -----------------------------------------------------
    # ATR STOP
    # -----------------------------------------------------

    "stop_atr_multiplier_values": [
        1.5,
        2.0,
        2.5,
    ],

    # -----------------------------------------------------
    # ATR TARGET
    # -----------------------------------------------------

    "target_atr_multiplier_values": [
        2.0,
        3.0,
        4.0,
    ],
}


# =========================================================
# HELPERS
# =========================================================

def safe_float(
    value: Any,
    default: float = 0.0,
) -> float:

    try:

        result = float(value)

        if not math.isfinite(result):
            return default

        return result

    except (
        TypeError,
        ValueError,
    ):

        return default


def merge_config(
    base: dict[str, Any],
    override: dict[str, Any] | None,
) -> dict[str, Any]:

    result = dict(base)

    if override:
        result.update(
            override
        )

    return result


# =========================================================
# PARAMETER COMBINATIONS
# =========================================================

def generate_parameter_combinations(
    config: dict[str, Any],
) -> list[dict[str, Any]]:

    combinations = []

    product = itertools.product(

        config["sma_fast_values"],

        config["sma_slow_values"],

        config["ema_fast_values"],

        config["ema_slow_values"],

        config["rsi_period_values"],

        config["rsi_oversold_values"],

        config["rsi_overbought_values"],

        config["stop_atr_multiplier_values"],

        config["target_atr_multiplier_values"],
    )

    for (
        sma_fast,
        sma_slow,
        ema_fast,
        ema_slow,
        rsi_period,
        rsi_oversold,
        rsi_overbought,
        stop_atr,
        target_atr,
    ) in product:

        # Mantıksal kontroller
        if sma_fast >= sma_slow:
            continue

        if ema_fast >= ema_slow:
            continue

        if rsi_oversold >= rsi_overbought:
            continue

        if stop_atr <= 0:
            continue

        if target_atr <= 0:
            continue

        combinations.append(
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

    return combinations


# =========================================================
# SCORE
# =========================================================

def calculate_score(
    metrics: dict[str, Any],
    minimum_trades: int,
) -> float:

    trades = int(
        metrics.get(
            "total_trades",
            0,
        )
    )

    if trades < minimum_trades:
        return -999999.0

    return_percent = safe_float(
        metrics.get(
            "total_return_percent",
            0.0,
        )
    )

    profit_factor = metrics.get(
        "profit_factor",
        0.0,
    )

    if profit_factor == float("inf"):
        profit_factor_value = 5.0
    else:
        profit_factor_value = safe_float(
            profit_factor
        )

    win_rate = safe_float(
        metrics.get(
            "win_rate_percent",
            0.0,
        )
    )

    max_drawdown = safe_float(
        metrics.get(
            "max_drawdown_percent",
            0.0,
        )
    )

    average_trade = safe_float(
        metrics.get(
            "average_trade_pnl",
            0.0,
        )
    )

    # -----------------------------------------------------
    # SCORE
    # -----------------------------------------------------

    score = 0.0

    # Getiri
    score += (
        return_percent
        * 3.0
    )

    # Profit Factor
    score += (
        profit_factor_value
        * 12.0
    )

    # Win Rate
    score += (
        win_rate
        * 0.20
    )

    # Ortalama işlem
    score += (
        average_trade
        * 0.01
    )

    # Drawdown cezası
    score -= (
        max_drawdown
        * 2.0
    )

    # İşlem sayısı güven katsayısı
    trade_factor = min(
        trades / 30.0,
        1.0,
    )

    score *= (
        0.50
        + (
            trade_factor
            * 0.50
        )
    )

    return score


# =========================================================
# TEST SINGLE COMBINATION
# =========================================================

def test_parameter_set(
    data: pd.DataFrame,
    symbol: str,
    parameters: dict[str, Any],
    minimum_trades: int,
) -> dict[str, Any]:

    try:

        # -------------------------------------------------
        # SIGNAL CONFIG
        # -------------------------------------------------

        signal_config = {

            "sma_fast": parameters[
                "sma_fast"
            ],

            "sma_slow": parameters[
                "sma_slow"
            ],

            "ema_fast": parameters[
                "ema_fast"
            ],

            "ema_slow": parameters[
                "ema_slow"
            ],

            "rsi_period": parameters[
                "rsi_period"
            ],

            "rsi_oversold": parameters[
                "rsi_oversold"
            ],

            "rsi_overbought": parameters[
                "rsi_overbought"
            ],
        }

        # -------------------------------------------------
        # BACKTEST CONFIG
        # -------------------------------------------------
        #
        # KRİTİK DÜZELTME:
        #
        # ATR parametreleri burada.
        #
        # Backtest Engine open_position() içinde:
        #
        # ATR * stop_atr_multiplier
        # ATR * target_atr_multiplier
        #
        # hesaplıyor.
        # -------------------------------------------------

        backtest_config = merge_config(
            DEFAULT_BACKTEST_CONFIG,
            {
                "stop_atr_multiplier": (
                    parameters[
                        "stop_atr_multiplier"
                    ]
                ),

                "target_atr_multiplier": (
                    parameters[
                        "target_atr_multiplier"
                    ]
                ),
            },
        )

        result = run_backtest(

            data=data,

            symbol=symbol,

            signal_config=signal_config,

            backtest_config=backtest_config,
        )

        metrics = result.get(
            "metrics",
            {},
        )

        score = calculate_score(
            metrics,
            minimum_trades,
        )

        profit_factor = metrics.get(
            "profit_factor",
            0.0,
        )

        if profit_factor == float("inf"):
            profit_factor_output = "INF"
        else:
            profit_factor_output = safe_float(
                profit_factor
            )

        return {

            "status": "OK",

            "score": score,

            "symbol": symbol,

            "bars": result.get(
                "bars",
                0,
            ),

            "trades": metrics.get(
                "total_trades",
                0,
            ),

            "wins": metrics.get(
                "winning_trades",
                0,
            ),

            "losses": metrics.get(
                "losing_trades",
                0,
            ),

            "win_rate": safe_float(
                metrics.get(
                    "win_rate_percent",
                    0.0,
                )
            ),

            "profit_factor": (
                profit_factor_output
            ),

            "net_pnl": safe_float(
                metrics.get(
                    "net_pnl",
                    0.0,
                )
            ),

            "return_percent": safe_float(
                metrics.get(
                    "total_return_percent",
                    0.0,
                )
            ),

            "max_drawdown": safe_float(
                metrics.get(
                    "max_drawdown_percent",
                    0.0,
                )
            ),

            "average_trade": safe_float(
                metrics.get(
                    "average_trade_pnl",
                    0.0,
                )
            ),

            "average_holding_bars": (
                safe_float(
                    metrics.get(
                        "average_holding_bars",
                        0.0,
                    )
                )
            ),

            "stop_loss_exits": int(
                metrics.get(
                    "stop_loss_exits",
                    0,
                )
            ),

            "take_profit_exits": int(
                metrics.get(
                    "take_profit_exits",
                    0,
                )
            ),

            "opposite_signal_exits": int(
                metrics.get(
                    "opposite_signal_exits",
                    0,
                )
            ),

            "max_holding_exits": int(
                metrics.get(
                    "max_holding_exits",
                    0,
                )
            ),

            # -------------------------------------------------
            # SIGNAL PARAMETRELERİ
            # -------------------------------------------------

            "sma_fast": parameters[
                "sma_fast"
            ],

            "sma_slow": parameters[
                "sma_slow"
            ],

            "ema_fast": parameters[
                "ema_fast"
            ],

            "ema_slow": parameters[
                "ema_slow"
            ],

            "rsi_period": parameters[
                "rsi_period"
            ],

            "rsi_oversold": parameters[
                "rsi_oversold"
            ],

            "rsi_overbought": parameters[
                "rsi_overbought"
            ],

            # -------------------------------------------------
            # RISK PARAMETRELERİ
            # -------------------------------------------------

            "stop_atr": parameters[
                "stop_atr_multiplier"
            ],

            "target_atr": parameters[
                "target_atr_multiplier"
            ],
        }

    except Exception as exc:

        return {

            "status": "ERROR",

            "score": -999999.0,

            "symbol": symbol,

            "bars": 0,

            "trades": 0,

            "wins": 0,

            "losses": 0,

            "win_rate": 0.0,

            "profit_factor": 0.0,

            "net_pnl": 0.0,

            "return_percent": 0.0,

            "max_drawdown": 0.0,

            "average_trade": 0.0,

            "average_holding_bars": 0.0,

            "stop_loss_exits": 0,

            "take_profit_exits": 0,

            "opposite_signal_exits": 0,

            "max_holding_exits": 0,

            "sma_fast": parameters.get(
                "sma_fast"
            ),

            "sma_slow": parameters.get(
                "sma_slow"
            ),

            "ema_fast": parameters.get(
                "ema_fast"
            ),

            "ema_slow": parameters.get(
                "ema_slow"
            ),

            "rsi_period": parameters.get(
                "rsi_period"
            ),

            "rsi_oversold": parameters.get(
                "rsi_oversold"
            ),

            "rsi_overbought": parameters.get(
                "rsi_overbought"
            ),

            "stop_atr": parameters.get(
                "stop_atr_multiplier"
            ),

            "target_atr": parameters.get(
                "target_atr_multiplier"
            ),

            "error": str(exc),
        }


# =========================================================
# OPTIMIZE
# =========================================================

def optimize_strategy(
    data: pd.DataFrame,
    symbol: str,
    optimizer_config: dict[str, Any] | None = None,
) -> pd.DataFrame:

    config = merge_config(
        DEFAULT_OPTIMIZER_CONFIG,
        optimizer_config,
    )

    combinations = (
        generate_parameter_combinations(
            config
        )
    )

    print()

    print("=" * 75)

    print(
        "MARKETHQ STRATEGY OPTIMIZER V2"
    )

    print("=" * 75)

    print(
        f"Sembol                  : {symbol}"
    )

    print(
        f"Bar sayısı              : {len(data)}"
    )

    print(
        f"Kombinasyon sayısı      : "
        f"{len(combinations)}"
    )

    print(
        f"Minimum işlem           : "
        f"{config['minimum_trades']}"
    )

    print()

    results = []

    total = len(
        combinations
    )

    for number, parameters in enumerate(
        combinations,
        start=1,
    ):

        print(
            f"\rTest ediliyor: "
            f"{number}/{total}",
            end="",
            flush=True,
        )

        result = test_parameter_set(

            data=data,

            symbol=symbol,

            parameters=parameters,

            minimum_trades=config[
                "minimum_trades"
            ],
        )

        results.append(
            result
        )

    print()

    result_df = pd.DataFrame(
        results
    )

    if result_df.empty:
        return result_df

    result_df = (
        result_df
        .sort_values(
            by=[
                "score",
                "profit_factor",
                "return_percent",
            ],
            ascending=[
                False,
                False,
                False,
            ],
        )
        .reset_index(
            drop=True
        )
    )

    result_df["rank"] = (
        result_df.index
        + 1
    )

    return result_df


# =========================================================
# PRINT RESULTS
# =========================================================

def print_top_results(
    result_df: pd.DataFrame,
    top_n: int,
) -> None:

    if result_df.empty:

        print(
            "Sonuç bulunamadı."
        )

        return

    top = result_df.head(
        top_n
    )

    print()

    print("=" * 145)

    print(
        f"EN İYİ {len(top)} STRATEJİ"
    )

    print("=" * 145)

    print(
        f"{'Rank':<5}"
        f"{'Score':>9}"
        f"{'Trades':>8}"
        f"{'Win%':>8}"
        f"{'PF':>8}"
        f"{'Return%':>10}"
        f"{'DD%':>8}"
        f"{'SMA':>10}"
        f"{'EMA':>10}"
        f"{'RSI':>12}"
        f"{'ATR':>12}"
        f"{'SL':>6}"
        f"{'TP':>6}"
    )

    print("-" * 145)

    for _, row in top.iterrows():

        pf = row[
            "profit_factor"
        ]

        if isinstance(
            pf,
            str,
        ):
            pf_text = pf
        else:
            pf_text = (
                f"{safe_float(pf):.2f}"
            )

        sma = (
            f"{int(row['sma_fast'])}/"
            f"{int(row['sma_slow'])}"
        )

        ema = (
            f"{int(row['ema_fast'])}/"
            f"{int(row['ema_slow'])}"
        )

        rsi = (
            f"{int(row['rsi_period'])}/"
            f"{int(row['rsi_oversold'])}/"
            f"{int(row['rsi_overbought'])}"
        )

        atr = (
            f"{safe_float(row['stop_atr']):.1f}/"
            f"{safe_float(row['target_atr']):.1f}"
        )

        print(
            f"{int(row['rank']):<5}"
            f"{safe_float(row['score']):>9.2f}"
            f"{int(row['trades']):>8}"
            f"{safe_float(row['win_rate']):>8.2f}"
            f"{pf_text:>8}"
            f"{safe_float(row['return_percent']):>10.2f}"
            f"{safe_float(row['max_drawdown']):>8.2f}"
            f"{sma:>10}"
            f"{ema:>10}"
            f"{rsi:>12}"
            f"{atr:>12}"
            f"{safe_float(row['stop_atr']):>6.1f}"
            f"{safe_float(row['target_atr']):>6.1f}"
        )

    print("=" * 145)

    print()


# =========================================================
# BEST CANDIDATE
# =========================================================

def get_best_candidate(
    result_df: pd.DataFrame,
) -> dict[str, Any] | None:

    if (
        result_df is None
        or result_df.empty
    ):
        return None

    row = result_df.iloc[0]

    return {

        "sma_fast": int(
            row["sma_fast"]
        ),

        "sma_slow": int(
            row["sma_slow"]
        ),

        "ema_fast": int(
            row["ema_fast"]
        ),

        "ema_slow": int(
            row["ema_slow"]
        ),

        "rsi_period": int(
            row["rsi_period"]
        ),

        "rsi_oversold": int(
            row["rsi_oversold"]
        ),

        "rsi_overbought": int(
            row["rsi_overbought"]
        ),

        "stop_atr_multiplier": (
            safe_float(
                row["stop_atr"]
            )
        ),

        "target_atr_multiplier": (
            safe_float(
                row["target_atr"]
            )
        ),

        "trades": int(
            row["trades"]
        ),

        "win_rate": safe_float(
            row["win_rate"]
        ),

        "profit_factor": row[
            "profit_factor"
        ],

        "return_percent": safe_float(
            row["return_percent"]
        ),

        "max_drawdown": safe_float(
            row["max_drawdown"]
        ),

        "score": safe_float(
            row["score"]
        ),
    }


# =========================================================
# SAVE CSV
# =========================================================

def save_results(
    result_df: pd.DataFrame,
    symbol: str,
) -> Path | None:

    if (
        result_df is None
        or result_df.empty
    ):
        return None

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    safe_symbol = (
        symbol
        .replace(
            "^",
            "",
        )
        .replace(
            ".",
            "_",
        )
        .replace(
            "/",
            "_",
        )
    )

    path = (
        OUTPUT_DIR
        / f"{safe_symbol}_optimization_v2.csv"
    )

    result_df.to_csv(
        path,
        index=False,
        encoding="utf-8-sig",
    )

    return path


# =========================================================
# MAIN
# =========================================================

def main() -> None:

    symbol = "THYAO.IS"

    print()

    print(
        "MarketHQ Strategy Optimizer V2 başlıyor..."
    )

    print()

    print(
        f"Veri alınıyor: {symbol}"
    )

    try:

        data = get_signal_data(
            symbol,
            period="1y",
        )

    except Exception as exc:

        print(
            f"❌ Veri alınamadı: {exc}"
        )

        return

    if (
        data is None
        or data.empty
    ):

        print(
            "❌ Optimizer için veri bulunamadı."
        )

        return

    print(
        f"📊 {len(data)} bar alındı."
    )

    # -----------------------------------------------------
    # OPTIMIZATION
    # -----------------------------------------------------

    result_df = optimize_strategy(

        data=data,

        symbol=symbol,
    )

    if result_df.empty:

        print(
            "❌ Optimizer sonuç üretemedi."
        )

        return

    # -----------------------------------------------------
    # RESULTS
    # -----------------------------------------------------

    print_top_results(

        result_df,

        DEFAULT_OPTIMIZER_CONFIG[
            "top_n"
        ],
    )

    # -----------------------------------------------------
    # BEST
    # -----------------------------------------------------

    best = get_best_candidate(
        result_df
    )

    print(
        "EN İYİ ADAY"
    )

    print("-" * 60)

    if best:

        for key, value in (
            best.items()
        ):

            print(
                f"{key:<28}: {value}"
            )

    print()

    # -----------------------------------------------------
    # SAVE
    # -----------------------------------------------------

    output_path = save_results(
        result_df,
        symbol,
    )

    if output_path:

        print(
            f"📁 Sonuç CSV: "
            f"{output_path}"
        )

    print()

    print(
        "Optimizer V2 tamamlandı."
    )

    print()


if __name__ == "__main__":
    main()
