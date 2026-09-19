# -*- coding: utf-8 -*-
"""
MarketHQ Walk-Forward Engine V3
================================

Walk-Forward Validation + Strategy Knowledge Base.

Amaç:
    Optimize edilen teknik stratejileri train döneminde seçmek,
    validation döneminde test etmek ve sonuçları Knowledge Base'e
    kaydetmek.

GÜVENLİK:
    Bu dosya gerçek emir göndermez.
    Broker bağlantısı yapmaz.
    Yalnızca araştırma / backtest / validation yapar.
"""

from __future__ import annotations

import csv
import math
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

from agents.market_data_agent import get_signal_data
from backtest_engine import (
    DEFAULT_BACKTEST_CONFIG,
    run_backtest,
)

from strategy_knowledge_base import (
    add_strategy,
    add_observation,
    add_walk_forward_result,
    create_strategy,
    set_strategy_parameters,
    update_learning_status,
)


# =========================================================
# CONFIG
# =========================================================

DEFAULT_WFO_CONFIG = {
    "train_bars": 252,
    "validation_bars": 63,
    "step_bars": 63,
    "minimum_train_trades": 8,
    "minimum_validation_trades": 3,
}


# =========================================================
# PATHS
# =========================================================

PROJECT_ROOT = Path(__file__).resolve().parent

WFO_RESULTS_DIR = (
    PROJECT_ROOT / "walk_forward_results"
)

WFO_RESULTS_DIR.mkdir(
    parents=True,
    exist_ok=True,
)


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

    except (TypeError, ValueError):
        return default


def safe_int(
    value: Any,
    default: int = 0,
) -> int:

    try:
        return int(value)

    except (TypeError, ValueError):
        return default


def get_metrics(
    result: dict[str, Any],
) -> dict[str, Any]:

    metrics = result.get(
        "metrics",
        {},
    )

    if isinstance(metrics, dict):
        return metrics

    return {}


def get_metric(
    result: dict[str, Any],
    *names: str,
    default: float = 0.0,
) -> float:

    metrics = get_metrics(result)

    for name in names:

        if name in metrics:

            return safe_float(
                metrics[name],
                default,
            )

    return default


def get_trade_count(
    result: dict[str, Any],
) -> int:

    metrics = get_metrics(result)

    for key in (
        "total_trades",
        "trade_count",
        "trades",
    ):

        if key in metrics:

            return safe_int(
                metrics[key]
            )

    return 0


def get_winning_trades(
    result: dict[str, Any],
) -> int:

    metrics = get_metrics(result)

    for key in (
        "winning_trades",
        "wins",
        "winning",
    ):

        if key in metrics:

            return safe_int(
                metrics[key]
            )

    return 0


def get_losing_trades(
    result: dict[str, Any],
) -> int:

    metrics = get_metrics(result)

    for key in (
        "losing_trades",
        "losses",
        "losing",
    ):

        if key in metrics:

            return safe_int(
                metrics[key]
            )

    return 0


def get_win_rate(
    result: dict[str, Any],
) -> float:

    return get_metric(
        result,
        "win_rate_percent",
        "win_rate",
    )


def get_profit_factor(
    result: dict[str, Any],
) -> float:

    return get_metric(
        result,
        "profit_factor",
    )


def get_return(
    result: dict[str, Any],
) -> float:

    return get_metric(
        result,
        "total_return_percent",
        "return_percent",
        "return",
    )


def get_drawdown(
    result: dict[str, Any],
) -> float:

    return get_metric(
        result,
        "max_drawdown_percent",
        "max_drawdown",
        "drawdown",
    )


def get_net_pnl(
    result: dict[str, Any],
) -> float:

    return get_metric(
        result,
        "net_pnl",
        "total_pnl",
    )


# =========================================================
# PARAMETER GRID
# =========================================================

def generate_parameter_grid() -> list[dict[str, Any]]:
    """
    WFO'nun kullandığı aday parametre havuzu.

    3 x 3 x 3 x 3 x 1 x 3 x 3 x 3 x 3
    şeklinde çok büyük bir havuz oluşmaması için
    önceki MarketHQ Optimizer V2 mantığı korunur.

    Toplam:
        192 aday

    ATR parametreleri backtest_config'e,
    diğer teknik parametreler signal_config'e gider.
    """

    sma_fast_values = [
        10,
        15,
        20,
    ]

    sma_slow_values = [
        30,
        50,
        100,
    ]

    ema_fast_values = [
        10,
        15,
        20,
    ]

    ema_slow_values = [
        30,
        50,
        100,
    ]

    rsi_period_values = [
        14,
    ]

    rsi_oversold_values = [
        25,
        30,
        35,
    ]

    rsi_overbought_values = [
        65,
        70,
        75,
    ]

    stop_atr_values = [
        1.5,
        2.0,
    ]

    target_atr_values = [
        3.0,
    ]

    grid = []

    for sma_fast in sma_fast_values:

        for sma_slow in sma_slow_values:

            if sma_fast >= sma_slow:
                continue

            for ema_fast in ema_fast_values:

                for ema_slow in ema_slow_values:

                    if ema_fast >= ema_slow:
                        continue

                    for rsi_period in rsi_period_values:

                        for rsi_oversold in (
                            rsi_oversold_values
                        ):

                            for rsi_overbought in (
                                rsi_overbought_values
                            ):

                                if (
                                    rsi_oversold
                                    >= rsi_overbought
                                ):
                                    continue

                                for stop_atr in (
                                    stop_atr_values
                                ):

                                    for target_atr in (
                                        target_atr_values
                                    ):

                                        grid.append(
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

    return grid


# =========================================================
# CONFIG BUILDERS
# =========================================================

def build_signal_config(
    parameter_set: dict[str, Any],
) -> dict[str, Any]:

    signal_keys = {
        "sma_fast",
        "sma_slow",
        "ema_fast",
        "ema_slow",
        "rsi_period",
        "rsi_oversold",
        "rsi_overbought",
        "macd_fast",
        "macd_slow",
        "macd_signal",
        "bollinger_period",
        "bollinger_std",
        "atr_period",
        "volume_period",
        "buy_threshold",
        "sell_threshold",
        "minimum_volume_ratio",
    }

    return {
        key: value
        for key, value in parameter_set.items()
        if key in signal_keys
    }


def build_backtest_config(
    parameter_set: dict[str, Any],
) -> dict[str, Any]:

    config = dict(
        DEFAULT_BACKTEST_CONFIG
    )

    if "stop_atr_multiplier" in parameter_set:

        config[
            "stop_atr_multiplier"
        ] = safe_float(
            parameter_set[
                "stop_atr_multiplier"
            ]
        )

    if "target_atr_multiplier" in parameter_set:

        config[
            "target_atr_multiplier"
        ] = safe_float(
            parameter_set[
                "target_atr_multiplier"
            ]
        )

    return config


# =========================================================
# PARAMETER TEST
# =========================================================

def test_parameter_set(
    data,
    parameter_set: dict[str, Any],
) -> dict[str, Any] | None:

    signal_config = (
        build_signal_config(
            parameter_set
        )
    )

    backtest_config = (
        build_backtest_config(
            parameter_set
        )
    )

    try:

        result = run_backtest(
            data,
            signal_config=signal_config,
            backtest_config=backtest_config,
        )

        if not isinstance(
            result,
            dict,
        ):
            return None

        return result

    except Exception as exc:

        print(
            f"      ⚠️ Backtest hatası: {exc}"
        )

        return None


# =========================================================
# TRAIN SCORE
# =========================================================

def calculate_train_score(
    result: dict[str, Any],
) -> float:

    trades = get_trade_count(
        result
    )

    if trades <= 0:
        return -999999.0

    return_percent = get_return(
        result
    )

    profit_factor = get_profit_factor(
        result
    )

    win_rate = get_win_rate(
        result
    )

    average_trade = (
        return_percent / trades
    )

    drawdown = get_drawdown(
        result
    )

    trade_factor = min(
        trades / 20.0,
        1.0,
    )

    score = (
        return_percent * 2.0
        + min(profit_factor, 3.0) * 2.0
        + (win_rate / 100.0) * 2.0
        + average_trade * 5.0
        - drawdown * 1.5
        + trade_factor
    )

    return safe_float(
        score
    )


# =========================================================
# TRAIN OPTIMIZATION
# =========================================================

def optimize_train(
    train_data,
    parameter_grid: list[dict[str, Any]],
    minimum_trades: int,
) -> tuple[
    dict[str, Any] | None,
    dict[str, Any] | None,
]:

    candidates = []

    total = len(
        parameter_grid
    )

    print(
        f"   🔎 {total} aday test ediliyor..."
    )

    for index, parameter_set in enumerate(
        parameter_grid,
        start=1,
    ):

        result = test_parameter_set(
            train_data,
            parameter_set,
        )

        if result is None:
            continue

        trades = get_trade_count(
            result
        )

        if trades < minimum_trades:
            continue

        score = calculate_train_score(
            result
        )

        candidates.append(
            {
                "parameter_set": dict(
                    parameter_set
                ),
                "result": result,
                "score": score,
            }
        )

        if (
            index % 25 == 0
            or index == total
        ):

            print(
                f"      {index}/{total} tamamlandı"
            )

    if not candidates:

        return None, None

    candidates.sort(
        key=lambda item: item["score"],
        reverse=True,
    )

    best = candidates[0]

    return (
        best["parameter_set"],
        best["result"],
    )


# =========================================================
# VALIDATION VERDICT
# =========================================================

def classify_validation(
    validation_result: dict[str, Any],
    minimum_trades: int,
) -> str:

    trades = get_trade_count(
        validation_result
    )

    return_percent = get_return(
        validation_result
    )

    profit_factor = get_profit_factor(
        validation_result
    )

    if trades < minimum_trades:

        return "INCONCLUSIVE"

    if (
        return_percent > 0
        and profit_factor >= 1.0
    ):

        return "POSITIVE"

    if (
        return_percent < 0
        and (
            profit_factor < 1.0
            or profit_factor == 0
        )
    ):

        return "NEGATIVE"

    return "INCONCLUSIVE"


# =========================================================
# PARAMETER STABILITY
# =========================================================

def calculate_parameter_stability(
    folds: list[dict[str, Any]],
) -> dict[str, Any]:

    if not folds:
        return {}

    parameter_values = {}

    for fold in folds:

        parameters = fold.get(
            "train_best_parameters",
            {},
        )

        for key, value in parameters.items():

            parameter_values.setdefault(
                key,
                [],
            ).append(
                str(value)
            )

    stability = {}

    for key, values in parameter_values.items():

        if not values:
            continue

        counts = Counter(
            values
        )

        most_common_value, frequency = (
            counts.most_common(1)[0]
        )

        percentage = (
            frequency
            / len(values)
            * 100.0
        )

        stability[key] = {
            "most_common": most_common_value,
            "frequency": frequency,
            "total_folds": len(values),
            "stability_percent": round(
                percentage,
                2,
            ),
        }

    return stability


# =========================================================
# AGGREGATE
# =========================================================

def build_aggregate(
    folds: list[dict[str, Any]],
) -> dict[str, Any]:

    validation_trades = sum(
        safe_int(
            fold.get(
                "validation_trades",
                0,
            )
        )
        for fold in folds
    )

    validation_wins = sum(
        safe_int(
            fold.get(
                "validation_wins",
                0,
            )
        )
        for fold in folds
    )

    validation_losses = sum(
        safe_int(
            fold.get(
                "validation_losses",
                0,
            )
        )
        for fold in folds
    )

    validation_return_sum = sum(
        safe_float(
            fold.get(
                "validation_return",
                0.0,
            )
        )
        for fold in folds
    )

    validation_net_pnl = sum(
        safe_float(
            fold.get(
                "validation_net_pnl",
                0.0,
            )
        )
        for fold in folds
    )

    fold_returns = [
        safe_float(
            fold.get(
                "validation_return",
                0.0,
            )
        )
        for fold in folds
    ]

    fold_drawdowns = [
        safe_float(
            fold.get(
                "validation_drawdown",
                0.0,
            )
        )
        for fold in folds
    ]

    positive_folds = sum(
        1
        for fold in folds
        if fold.get(
            "verdict"
        ) == "POSITIVE"
    )

    negative_folds = sum(
        1
        for fold in folds
        if fold.get(
            "verdict"
        ) == "NEGATIVE"
    )

    inconclusive_folds = sum(
        1
        for fold in folds
        if fold.get(
            "verdict"
        ) == "INCONCLUSIVE"
    )

    if validation_trades > 0:

        validation_win_rate = (
            validation_wins
            / validation_trades
            * 100.0
        )

    else:

        validation_win_rate = 0.0

    if fold_returns:

        average_fold_return = (
            sum(fold_returns)
            / len(fold_returns)
        )

        best_fold_return = max(
            fold_returns
        )

        worst_fold_return = min(
            fold_returns
        )

    else:

        average_fold_return = 0.0
        best_fold_return = 0.0
        worst_fold_return = 0.0

    if fold_drawdowns:

        average_fold_dd = (
            sum(fold_drawdowns)
            / len(fold_drawdowns)
        )

    else:

        average_fold_dd = 0.0

    return {
        "fold_count": len(folds),

        "positive_folds": positive_folds,

        "negative_folds": negative_folds,

        "inconclusive_folds": (
            inconclusive_folds
        ),

        "validation_trades": (
            validation_trades
        ),

        "validation_wins": (
            validation_wins
        ),

        "validation_losses": (
            validation_losses
        ),

        "validation_win_rate": round(
            validation_win_rate,
            2,
        ),

        "validation_return_sum": round(
            validation_return_sum,
            4,
        ),

        "validation_net_pnl": round(
            validation_net_pnl,
            2,
        ),

        "average_fold_return": round(
            average_fold_return,
            4,
        ),

        "best_fold_return": round(
            best_fold_return,
            4,
        ),

        "worst_fold_return": round(
            worst_fold_return,
            4,
        ),

        "average_fold_dd": round(
            average_fold_dd,
            4,
        ),
    }


# =========================================================
# KNOWLEDGE BASE
# =========================================================

def save_to_knowledge_base(
    symbol: str,
    folds: list[dict[str, Any]],
    aggregate: dict[str, Any],
    parameter_stability: dict[str, Any],
) -> str | None:

    if not folds:
        return None

    # Son fold'daki seçilmiş parametreler.
    latest_parameters = folds[-1].get(
        "train_best_parameters",
        {},
    )

    market = (
        "BIST"
        if symbol.endswith(".IS")
        else "US"
    )

    strategy = create_strategy(
        name=(
            f"{symbol} "
            "Walk-Forward Research Strategy"
        ),

        description=(
            "MarketHQ WFO V3 tarafından "
            "train ve validation dönemlerinde "
            "test edilen teknik strateji adayı."
        ),

        source_type="walk_forward",

        source_name="MarketHQ WFO V3",

        market=market,

        symbols=[
            symbol,
        ],

        tags=[
            "walk-forward",
            "validation",
            "research",
            "SMA",
            "EMA",
            "RSI",
            "ATR",
        ],

        hypothesis=(
            "Train döneminde seçilen "
            "teknik gösterge parametrelerinin "
            "gelecekteki validation dönemlerinde "
            "istikrarlı sonuç üretip üretmediğini "
            "ölçmek."
        ),

        notes=(
            "Araştırma/backtest kaydıdır. "
            "Gerçek emir veya broker işlemi içermez."
        ),
    )

    strategy_id = add_strategy(
        strategy
    )

    if latest_parameters:

        set_strategy_parameters(
            strategy_id,
            latest_parameters,
        )

    wfo_result = {
        "aggregate": aggregate,

        "parameter_stability": (
            parameter_stability
        ),

        "folds": folds,
    }

    add_walk_forward_result(
        strategy_id,
        symbol,
        wfo_result,
    )

    # -----------------------------------------------------
    # Stability observations
    # -----------------------------------------------------

    for parameter, info in (
        parameter_stability.items()
    ):

        stability_percent = safe_float(
            info.get(
                "stability_percent",
                0,
            )
        )

        if stability_percent >= 70:

            observation = (
                f"{parameter} parametresi "
                f"fold'ların "
                f"%{stability_percent:.1f}"
                " oranında aynı değeri aldı. "
                f"En sık değer: "
                f"{info.get('most_common')}."
            )

            add_observation(
                strategy_id,
                observation,
                "parameter_stability",
            )

    # -----------------------------------------------------
    # Aggregate observation
    # -----------------------------------------------------

    aggregate_observation = (
        "WFO sonucu: "
        f"{aggregate['positive_folds']} pozitif, "
        f"{aggregate['negative_folds']} negatif, "
        f"{aggregate['inconclusive_folds']} belirsiz fold. "
        f"Validation işlem sayısı: "
        f"{aggregate['validation_trades']}. "
        f"Validation win rate: "
        f"%{aggregate['validation_win_rate']:.2f}. "
        f"Validation return toplamı: "
        f"{aggregate['validation_return_sum']:.2f}%."
    )

    add_observation(
        strategy_id,
        aggregate_observation,
        "walk_forward",
    )

    # -----------------------------------------------------
    # Train / validation degradation
    # -----------------------------------------------------

    for fold in folds:

        train_return = safe_float(
            fold.get(
                "train_return",
                0,
            )
        )

        validation_return = safe_float(
            fold.get(
                "validation_return",
                0,
            )
        )

        difference = (
            validation_return
            - train_return
        )

        if difference <= -1.0:

            observation = (
                f"Fold {fold.get('fold')}: "
                "train → validation return "
                f"değişimi {difference:.2f} puan. "
                "Performans bozulması gözlendi."
            )

            add_observation(
                strategy_id,
                observation,
                "overfitting_warning",
            )

    # -----------------------------------------------------
    # Learning status
    # -----------------------------------------------------

    update_learning_status(
        strategy_id
    )

    return strategy_id


# =========================================================
# CSV
# =========================================================

def save_wfo_csv(
    symbol: str,
    folds: list[dict[str, Any]],
    aggregate: dict[str, Any],
) -> str:

    timestamp = datetime.now().strftime(
        "%Y%m%d_%H%M%S"
    )

    filename = (
        f"{symbol}_wfo_v3_"
        f"{timestamp}.csv"
    )

    path = (
        WFO_RESULTS_DIR
        / filename
    )

    rows = []

    for fold in folds:

        row = {
            "fold": fold.get(
                "fold"
            ),

            "train_start": fold.get(
                "train_start"
            ),

            "train_end": fold.get(
                "train_end"
            ),

            "validation_start": fold.get(
                "validation_start"
            ),

            "validation_end": fold.get(
                "validation_end"
            ),

            "train_trades": fold.get(
                "train_trades"
            ),

            "train_win_rate": fold.get(
                "train_win_rate"
            ),

            "train_profit_factor": fold.get(
                "train_profit_factor"
            ),

            "train_return": fold.get(
                "train_return"
            ),

            "train_drawdown": fold.get(
                "train_drawdown"
            ),

            "validation_trades": fold.get(
                "validation_trades"
            ),

            "validation_wins": fold.get(
                "validation_wins"
            ),

            "validation_losses": fold.get(
                "validation_losses"
            ),

            "validation_win_rate": fold.get(
                "validation_win_rate"
            ),

            "validation_profit_factor": fold.get(
                "validation_profit_factor"
            ),

            "validation_return": fold.get(
                "validation_return"
            ),

            "validation_net_pnl": fold.get(
                "validation_net_pnl"
            ),

            "validation_drawdown": fold.get(
                "validation_drawdown"
            ),

            "return_difference": fold.get(
                "return_difference"
            ),

            "verdict": fold.get(
                "verdict"
            ),
        }

        parameters = fold.get(
            "train_best_parameters",
            {},
        )

        for key, value in parameters.items():

            row[
                f"param_{key}"
            ] = value

        rows.append(
            row
        )

    fieldnames = sorted(
        {
            key
            for row in rows
            for key in row.keys()
        }
    )

    with open(
        path,
        "w",
        newline="",
        encoding="utf-8-sig",
    ) as file:

        writer = csv.DictWriter(
            file,
            fieldnames=fieldnames,
        )

        writer.writeheader()

        writer.writerows(
            rows
        )

        writer.writerow({})

        aggregate_row = {
            "fold": "AGGREGATE",
        }

        for key, value in aggregate.items():

            if key in fieldnames:

                aggregate_row[
                    key
                ] = value

        writer.writerow(
            aggregate_row
        )

    return str(
        path
    )


# =========================================================
# WFO
# =========================================================

def run_walk_forward(
    symbol: str = "THYAO.IS",
    period: str = "3y",
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:

    wfo_config = dict(
        DEFAULT_WFO_CONFIG
    )

    if config:
        wfo_config.update(
            config
        )

    train_bars = safe_int(
        wfo_config[
            "train_bars"
        ]
    )

    validation_bars = safe_int(
        wfo_config[
            "validation_bars"
        ]
    )

    step_bars = safe_int(
        wfo_config[
            "step_bars"
        ]
    )

    minimum_train_trades = safe_int(
        wfo_config[
            "minimum_train_trades"
        ]
    )

    minimum_validation_trades = safe_int(
        wfo_config[
            "minimum_validation_trades"
        ]
    )

    print()
    print("=" * 70)
    print(
        "MarketHQ WALK-FORWARD ENGINE V3"
    )
    print("=" * 70)

    print(
        f"Symbol              : {symbol}"
    )

    print(
        f"Train               : {train_bars}"
    )

    print(
        f"Validation          : {validation_bars}"
    )

    print(
        f"Step                : {step_bars}"
    )

    print(
        f"Min train işlem     : "
        f"{minimum_train_trades}"
    )

    print(
        f"Min validation işlem: "
        f"{minimum_validation_trades}"
    )

    print("=" * 70)

    # =====================================================
    # DATA
    # =====================================================

    print()
    print(
        f"📥 Veri alınıyor: {symbol}"
    )

    data = get_signal_data(
        symbol,
        period=period,
    )

    if data is None:

        raise RuntimeError(
            "Market verisi alınamadı."
        )

    data = data.copy()

    if len(data) < (
        train_bars
        + validation_bars
    ):

        raise RuntimeError(
            "WFO için yeterli veri yok."
        )

    data = data.reset_index(
        drop=False
    )

    total_bars = len(
        data
    )

    print(
        f"Toplam bar          : "
        f"{total_bars}"
    )

    print(
        f"Veri başlangıcı     : "
        f"{data.iloc[0].get('Date', data.iloc[0].get('Datetime', ''))}"
    )

    print(
        f"Veri bitişi         : "
        f"{data.iloc[-1].get('Date', data.iloc[-1].get('Datetime', ''))}"
    )

    # =====================================================
    # GRID
    # =====================================================

    parameter_grid = (
        generate_parameter_grid()
    )

    print(
        f"Aday sayısı         : "
        f"{len(parameter_grid)}"
    )

    # =====================================================
    # FOLDS
    # =====================================================

    folds = []

    fold_number = 0

    train_start = 0

    while (
        train_start
        + train_bars
        + validation_bars
        <= total_bars
    ):

        fold_number += 1

        train_end = (
            train_start
            + train_bars
        )

        validation_end = (
            train_end
            + validation_bars
        )

        train_data = data.iloc[
            train_start:train_end
        ].copy()

        validation_data = data.iloc[
            train_end:validation_end
        ].copy()

        train_start_label = str(
            train_data.iloc[0].get(
                "Date",
                train_data.iloc[0].get(
                    "Datetime",
                    "",
                ),
            )
        )

        train_end_label = str(
            train_data.iloc[-1].get(
                "Date",
                train_data.iloc[-1].get(
                    "Datetime",
                    "",
                ),
            )
        )

        validation_start_label = str(
            validation_data.iloc[0].get(
                "Date",
                validation_data.iloc[0].get(
                    "Datetime",
                    "",
                ),
            )
        )

        validation_end_label = str(
            validation_data.iloc[-1].get(
                "Date",
                validation_data.iloc[-1].get(
                    "Datetime",
                    "",
                ),
            )
        )

        print()
        print("=" * 70)
        print(
            f"FOLD {fold_number}"
        )
        print("=" * 70)

        print(
            f"TRAIN      : "
            f"{len(train_data)} bar | "
            f"{train_start_label} → "
            f"{train_end_label}"
        )

        print(
            f"VALIDATION : "
            f"{len(validation_data)} bar | "
            f"{validation_start_label} → "
            f"{validation_end_label}"
        )

        # =================================================
        # TRAIN
        # =================================================

        print()
        print(
            "1) TRAIN OPTIMIZATION"
        )

        (
            best_parameters,
            train_result,
        ) = optimize_train(
            train_data,
            parameter_grid,
            minimum_train_trades,
        )

        if (
            best_parameters is None
            or train_result is None
        ):

            print(
                "   ⚠️ Uygun train adayı bulunamadı."
            )

            train_start += step_bars

            continue

        # =================================================
        # TRAIN BEST
        # =================================================

        print()
        print(
            "2) TRAIN BEST"
        )

        print(
            f"   SMA      : "
            f"{best_parameters.get('sma_fast')}/"
            f"{best_parameters.get('sma_slow')}"
        )

        print(
            f"   EMA      : "
            f"{best_parameters.get('ema_fast')}/"
            f"{best_parameters.get('ema_slow')}"
        )

        print(
            f"   RSI      : "
            f"{best_parameters.get('rsi_period')}/"
            f"{best_parameters.get('rsi_oversold')}/"
            f"{best_parameters.get('rsi_overbought')}"
        )

        print(
            f"   ATR      : "
            f"{best_parameters.get('stop_atr_multiplier')}/"
            f"{best_parameters.get('target_atr_multiplier')}"
        )

        print(
            f"   Train    : "
            f"{get_trade_count(train_result)} işlem | "
            f"Win {get_win_rate(train_result):.2f}% | "
            f"PF {get_profit_factor(train_result):.2f} | "
            f"Return {get_return(train_result):.2f}% | "
            f"DD {get_drawdown(train_result):.2f}%"
        )

        # =================================================
        # VALIDATION
        # =================================================

        print()
        print(
            "3) VALIDATION TEST"
        )

        validation_result = (
            test_parameter_set(
                validation_data,
                best_parameters,
            )
        )

        if validation_result is None:

            print(
                "   ❌ Validation backtest başarısız."
            )

            train_start += step_bars

            continue

        validation_trades = (
            get_trade_count(
                validation_result
            )
        )

        validation_wins = (
            get_winning_trades(
                validation_result
            )
        )

        validation_losses = (
            get_losing_trades(
                validation_result
            )
        )

        validation_win_rate = (
            get_win_rate(
                validation_result
            )
        )

        validation_profit_factor = (
            get_profit_factor(
                validation_result
            )
        )

        validation_return = (
            get_return(
                validation_result
            )
        )

        validation_net_pnl = (
            get_net_pnl(
                validation_result
            )
        )

        validation_drawdown = (
            get_drawdown(
                validation_result
            )
        )

        verdict = classify_validation(
            validation_result,
            minimum_validation_trades,
        )

        train_return = get_return(
            train_result
        )

        return_difference = (
            validation_return
            - train_return
        )

        print(
            f"   Validation: "
            f"{validation_trades} işlem | "
            f"Win {validation_win_rate:.2f}% | "
            f"PF {validation_profit_factor:.2f} | "
            f"Return {validation_return:.2f}% | "
            f"DD {validation_drawdown:.2f}%"
        )

        print(
            f"   🧪 Verdict: "
            f"{verdict}"
        )

        print(
            f"   Train → Validation "
            f"farkı: "
            f"{return_difference:.2f} puan"
        )

        # =================================================
        # FOLD RECORD
        # =================================================

        fold_record = {
            "fold": fold_number,

            "train_start": (
                train_start_label
            ),

            "train_end": (
                train_end_label
            ),

            "validation_start": (
                validation_start_label
            ),

            "validation_end": (
                validation_end_label
            ),

            "train_trades": (
                get_trade_count(
                    train_result
                )
            ),

            "train_win_rate": (
                get_win_rate(
                    train_result
                )
            ),

            "train_profit_factor": (
                get_profit_factor(
                    train_result
                )
            ),

            "train_return": (
                train_return
            ),

            "train_drawdown": (
                get_drawdown(
                    train_result
                )
            ),

            "train_net_pnl": (
                get_net_pnl(
                    train_result
                )
            ),

            "validation_trades": (
                validation_trades
            ),

            "validation_wins": (
                validation_wins
            ),

            "validation_losses": (
                validation_losses
            ),

            "validation_win_rate": (
                validation_win_rate
            ),

            "validation_profit_factor": (
                validation_profit_factor
            ),

            "validation_return": (
                validation_return
            ),

            "validation_net_pnl": (
                validation_net_pnl
            ),

            "validation_drawdown": (
                validation_drawdown
            ),

            "return_difference": (
                return_difference
            ),

            "verdict": verdict,

            "train_best_parameters": dict(
                best_parameters
            ),
        }

        folds.append(
            fold_record
        )

        train_start += step_bars

    # =====================================================
    # AGGREGATE
    # =====================================================

    aggregate = build_aggregate(
        folds
    )

    parameter_stability = (
        calculate_parameter_stability(
            folds
        )
    )

    print()
    print("=" * 70)
    print(
        "WALK-FORWARD V3 GENEL SONUÇ"
    )
    print("=" * 70)

    print(
        f"Fold sayısı             : "
        f"{aggregate['fold_count']}"
    )

    print(
        f"Pozitif fold            : "
        f"{aggregate['positive_folds']}"
    )

    print(
        f"Negatif fold            : "
        f"{aggregate['negative_folds']}"
    )

    print(
        f"Belirsiz fold           : "
        f"{aggregate['inconclusive_folds']}"
    )

    print(
        f"Validation işlem        : "
        f"{aggregate['validation_trades']}"
    )

    print(
        f"Validation kazanan      : "
        f"{aggregate['validation_wins']}"
    )

    print(
        f"Validation kaybeden     : "
        f"{aggregate['validation_losses']}"
    )

    print(
        f"Validation Win Rate     : "
        f"{aggregate['validation_win_rate']:.2f}%"
    )

    print(
        f"Validation Return Top. : "
        f"{aggregate['validation_return_sum']:.2f}%"
    )

    print(
        f"Ortalama Fold Return    : "
        f"{aggregate['average_fold_return']:.2f}%"
    )

    print(
        f"En iyi Fold Return      : "
        f"{aggregate['best_fold_return']:.2f}%"
    )

    print(
        f"En kötü Fold Return     : "
        f"{aggregate['worst_fold_return']:.2f}%"
    )

    print(
        f"Validation Net PnL      : "
        f"{aggregate['validation_net_pnl']:.2f}"
    )

    print(
        f"Ortalama Fold DD        : "
        f"{aggregate['average_fold_dd']:.2f}%"
    )

    # =====================================================
    # PARAMETER STABILITY
    # =====================================================

    print()
    print("-" * 70)
    print(
        "PARAMETRE STABİLİTESİ"
    )
    print("-" * 70)

    for parameter, info in (
        parameter_stability.items()
    ):

        print(
            f"{parameter:<23}: "
            f"{info['most_common']} "
            f"({info['stability_percent']:.1f}%)"
        )

    # =====================================================
    # KNOWLEDGE BASE
    # =====================================================

    knowledge_strategy_id = None

    if folds:

        print()
        print(
            "🧠 KNOWLEDGE BASE'E KAYDEDİLİYOR..."
        )

        knowledge_strategy_id = (
            save_to_knowledge_base(
                symbol,
                folds,
                aggregate,
                parameter_stability,
            )
        )

        print(
            f"Strategy ID             : "
            f"{knowledge_strategy_id}"
        )

        print(
            "✅ WFO sonucu Knowledge Base'e kaydedildi."
        )

    # =====================================================
    # CSV
    # =====================================================

    csv_path = save_wfo_csv(
        symbol,
        folds,
        aggregate,
    )

    print()
    print(
        f"📄 CSV                     : "
        f"{csv_path}"
    )

    print("=" * 70)

    return {
        "symbol": symbol,

        "period": period,

        "folds": folds,

        "aggregate": aggregate,

        "parameter_stability": (
            parameter_stability
        ),

        "knowledge_base_strategy_id": (
            knowledge_strategy_id
        ),

        "csv": csv_path,
    }


# =========================================================
# MAIN
# =========================================================

def main() -> None:

    result = run_walk_forward(
        symbol="THYAO.IS",
        period="3y",
    )

    print()
    print(
        "✅ Walk-forward V3 tamamlandı."
    )

    print(
        f"Fold: "
        f"{len(result['folds'])}"
    )

    print(
        f"Knowledge Strategy ID: "
        f"{result['knowledge_base_strategy_id']}"
    )


if __name__ == "__main__":
    main()
