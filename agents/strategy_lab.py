import math
import sys
from pathlib import Path
from typing import Any

import pandas as pd
import yfinance as yf


# =========================================================
# PROJECT ROOT
# =========================================================

PROJECT_ROOT = Path(__file__).resolve().parent.parent

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from database import (
    add_experiment_result,
    create_learning_experiment,
    init_db,
    save_learned_rule,
    update_experiment_status,
)


# =========================================================
# CONFIG
# =========================================================

DEFAULT_PERIOD = "5y"

MIN_DATA_ROWS = 250

TIMEFRAME = "1d"

METHOD_NAME = (
    "FIN_SYS_PUBLIC_BASELINE_V4_4_PURGED_RESEARCH"
)

HOLDING_DAYS = 20

PURGE_DAYS = HOLDING_DAYS
EMBARGO_DAYS = HOLDING_DAYS

TRAIN_RATIO = 0.60
VALIDATION_RATIO = 0.20
TEST_RATIO = 0.20

ROUND_TRIP_COST_PCT = 0.20

MIN_TEST_TRADES_WARNING = 5


# =========================================================
# BENCHMARKS
# =========================================================

BIST_BENCHMARK = "XU100.IS"
US_BENCHMARK = "^GSPC"


# =========================================================
# SYMBOLS
# =========================================================

BIST_SYMBOLS = [
    "THYAO.IS",
    "ASELS.IS",
    "GARAN.IS",
    "AKBNK.IS",
    "EREGL.IS",
    "TUPRS.IS",
    "SISE.IS",
    "BIMAS.IS",
    "FROTO.IS",
    "KCHOL.IS",
    "SAHOL.IS",
    "TCELL.IS",
    "TAVHL.IS",
    "PGSUS.IS",
    "TOASO.IS",
    "ENKAI.IS",
    "EKGYO.IS",
    "MGROS.IS",
    "PETKM.IS",
    "SASA.IS",
]


US_SYMBOLS = [
    "AAPL",
    "MSFT",
    "NVDA",
    "AMZN",
    "GOOGL",
    "META",
    "TSLA",
    "AVGO",
    "AMD",
    "QCOM",
    "NFLX",
    "ORCL",
    "MU",
    "INTC",
    "COST",
]


# =========================================================
# HELPERS
# =========================================================

def is_valid_number(value: Any) -> bool:
    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


def clean_symbol(symbol: str) -> str:
    return symbol.upper().strip()


def market_from_symbol(symbol: str) -> str:
    if symbol.endswith(".IS"):
        return "BIST"

    return "US"


def get_benchmark(symbol: str) -> str:
    if market_from_symbol(symbol) == "BIST":
        return BIST_BENCHMARK

    return US_BENCHMARK


def format_percent(value: float | None) -> str:
    if value is None:
        return "Veri yok"

    return f"%{value:.2f}"


def calculate_average(
    values: list[float],
) -> float | None:

    if not values:
        return None

    return sum(values) / len(values)


def calculate_accuracy(
    values: list[float],
) -> float | None:

    if not values:
        return None

    positive = sum(
        1
        for value in values
        if value > 0
    )

    return (
        positive
        / len(values)
        * 100.0
    )


def calculate_confidence(
    sample_size: int,
) -> float:

    if sample_size >= 500:
        return 0.95

    if sample_size >= 250:
        return 0.90

    if sample_size >= 100:
        return 0.80

    if sample_size >= 50:
        return 0.65

    if sample_size >= 20:
        return 0.50

    return 0.25


# =========================================================
# DOWNLOAD WITH TIMEOUT / RETRY
# =========================================================

def download_history(
    symbol: str,
    period: str = DEFAULT_PERIOD,
    retries: int = 3,
) -> pd.DataFrame:

    symbol = clean_symbol(symbol)

    print(
        f"   🌐 Veri indiriliyor: {symbol}"
    )

    last_error = None

    for attempt in range(
        1,
        retries + 1,
    ):

        try:

            print(
                f"      Deneme "
                f"{attempt}/{retries}..."
            )

            ticker = yf.Ticker(
                symbol
            )

            data = ticker.history(
                period=period,
                auto_adjust=False,
                timeout=15,
            )

            if (
                data is None
                or data.empty
            ):

                print(
                    f"      ⚠️ Boş veri: "
                    f"{symbol}"
                )

                if attempt < retries:
                    continue

                return pd.DataFrame()

            required = [
                "Open",
                "High",
                "Low",
                "Close",
                "Volume",
            ]

            missing_columns = [
                column
                for column in required
                if column not in data.columns
            ]

            if missing_columns:

                print(
                    f"      ❌ Eksik kolonlar: "
                    f"{missing_columns}"
                )

                return pd.DataFrame()

            data = data[
                required
            ].copy()

            data = data.dropna(
                subset=[
                    "Open",
                    "High",
                    "Low",
                    "Close",
                ]
            )

            for column in [
                "Open",
                "High",
                "Low",
                "Close",
            ]:

                data = data[
                    data[column].apply(
                        is_valid_number
                    )
                ]

            data = data.sort_index()

            if getattr(
                data.index,
                "tz",
                None,
            ) is not None:

                data.index = (
                    data.index.tz_localize(
                        None
                    )
                )

            print(
                f"      ✅ Veri geldi: "
                f"{len(data)} satır"
            )

            return data

        except Exception as error:

            last_error = error

            print(
                f"      ❌ Veri hatası: "
                f"{error}"
            )

            if attempt < retries:

                print(
                    "      🔄 Yeniden deneniyor..."
                )

    print(
        f"   ❌ {symbol} veri alınamadı."
    )

    if last_error is not None:

        print(
            f"      Son hata: "
            f"{last_error}"
        )

    return pd.DataFrame()


# =========================================================
# SLOPE
# =========================================================

def calculate_slope(
    values,
) -> float:

    if len(values) < 2:
        return float("nan")

    if any(
        not is_valid_number(value)
        for value in values
    ):

        return float("nan")

    x = list(
        range(
            len(values)
        )
    )

    x_mean = (
        sum(x)
        / len(x)
    )

    y_mean = (
        sum(values)
        / len(values)
    )

    numerator = sum(
        (
            x_value
            - x_mean
        )
        *
        (
            y_value
            - y_mean
        )
        for (
            x_value,
            y_value,
        )
        in zip(
            x,
            values,
        )
    )

    denominator = sum(
        (
            x_value
            - x_mean
        ) ** 2
        for x_value in x
    )

    if denominator == 0:
        return float("nan")

    return (
        numerator
        / denominator
    )


# =========================================================
# INDICATORS
# =========================================================

def add_indicators(
    data: pd.DataFrame,
) -> pd.DataFrame:

    df = data.copy()

    df["EMA20"] = (
        df["Close"]
        .ewm(
            span=20,
            adjust=False,
        )
        .mean()
    )

    df["EMA50"] = (
        df["Close"]
        .ewm(
            span=50,
            adjust=False,
        )
        .mean()
    )

    df["EMA200"] = (
        df["Close"]
        .ewm(
            span=200,
            adjust=False,
        )
        .mean()
    )

    df["ROC20"] = (
        df["Close"]
        .pct_change(20)
        * 100.0
    )

    df["VolumeMA20"] = (
        df["Volume"]
        .rolling(20)
        .mean()
    )

    previous_close = (
        df["Close"]
        .shift(1)
    )

    true_range = pd.concat(
        [
            df["High"] - df["Low"],

            (
                df["High"]
                - previous_close
            ).abs(),

            (
                df["Low"]
                - previous_close
            ).abs(),
        ],
        axis=1,
    ).max(
        axis=1
    )

    df["ATR14"] = (
        true_range
        .rolling(14)
        .mean()
    )

    df["REG_SLOPE20"] = (
        df["Close"]
        .rolling(20)
        .apply(
            calculate_slope,
            raw=True,
        )
    )

    df["SUPPORT20"] = (
        df["Low"]
        .rolling(20)
        .min()
        .shift(1)
    )

    df["RESISTANCE20"] = (
        df["High"]
        .rolling(20)
        .max()
        .shift(1)
    )

    return df


# =========================================================
# WEEKLY TREND
# =========================================================

def build_weekly_trend(
    daily: pd.DataFrame,
) -> pd.Series:

    weekly_close = (
        daily["Close"]
        .resample("W-FRI")
        .last()
        .dropna()
    )

    weekly_ema20 = (
        weekly_close
        .ewm(
            span=20,
            adjust=False,
        )
        .mean()
    )

    weekly_ema40 = (
        weekly_close
        .ewm(
            span=40,
            adjust=False,
        )
        .mean()
    )

    weekly_bull = (
        weekly_ema20
        >
        weekly_ema40
    )

    previous_week_bull = (
        weekly_bull.shift(1)
    )

    return previous_week_bull.reindex(
        daily.index,
        method="ffill",
    )


# =========================================================
# SIGNAL
# =========================================================

def calculate_signal(
    df: pd.DataFrame,
) -> pd.DataFrame:

    result = df.copy()

    result["WEEKLY_BULL"] = (
        build_weekly_trend(
            result
        )
    )

    trend = (
        (
            result["Close"]
            >
            result["EMA20"]
        )
        &
        (
            result["EMA20"]
            >
            result["EMA50"]
        )
        &
        (
            result["EMA50"]
            >
            result["EMA200"]
        )
        &
        (
            result["REG_SLOPE20"]
            > 0
        )
        &
        (
            result["WEEKLY_BULL"]
            == True
        )
    )

    momentum = (
        result["ROC20"] > 0
    )

    volume = (
        result["Volume"]
        >
        result["VolumeMA20"]
    )

    support = (
        result["Close"]
        >
        result["SUPPORT20"]
    )

    resistance = (
        result["Close"]
        <
        result["RESISTANCE20"]
        * 1.03
    )

    structure = (
        support
        &
        resistance
    )

    result["TREND_SCORE"] = (
        trend.astype(int)
    )

    result["MOMENTUM_SCORE"] = (
        momentum.astype(int)
    )

    result["VOLUME_SCORE"] = (
        volume.astype(int)
    )

    result["STRUCTURE_SCORE"] = (
        structure.astype(int)
    )

    result["TOTAL_SCORE"] = (
        result["TREND_SCORE"]
        +
        result["MOMENTUM_SCORE"]
        +
        result["VOLUME_SCORE"]
        +
        result["STRUCTURE_SCORE"]
    )

    result["SIGNAL"] = (
        result["TOTAL_SCORE"] == 4
    )

    return result


# =========================================================
# MARKET STATE
# =========================================================

def detect_market_regime(
    row: pd.Series,
) -> str:

    close = row.get("Close")
    ema50 = row.get("EMA50")
    ema200 = row.get("EMA200")
    slope = row.get("REG_SLOPE20")

    if not all(
        is_valid_number(value)
        for value in (
            close,
            ema50,
            ema200,
            slope,
        )
    ):

        return "Bilinmiyor"

    if (
        close > ema50
        and ema50 > ema200
        and slope > 0
    ):

        return "Yukselen_Trend"

    if (
        close < ema50
        and ema50 < ema200
        and slope < 0
    ):

        return "Dusen_Trend"

    return "Yatay_Karisik"


def detect_volume_state(
    row: pd.Series,
) -> str:

    volume = row.get("Volume")
    volume_ma = row.get("VolumeMA20")

    if not all(
        is_valid_number(value)
        for value in (
            volume,
            volume_ma,
        )
    ):

        return "Bilinmiyor"

    if volume > volume_ma:
        return "Yuksek"

    return "Normal_Dusuk"


def detect_volatility_state(
    row: pd.Series,
) -> str:

    atr = row.get("ATR14")
    close = row.get("Close")

    if not all(
        is_valid_number(value)
        for value in (
            atr,
            close,
        )
    ):

        return "Bilinmiyor"

    if close <= 0:
        return "Bilinmiyor"

    atr_ratio = (
        atr
        / close
        * 100.0
    )

    if atr_ratio >= 4:
        return "Yuksek"

    if atr_ratio >= 2:
        return "Orta"

    return "Dusuk"


# =========================================================
# RETURNS
# =========================================================

def calculate_return(
    entry: float | None,
    exit_price: float | None,
) -> float | None:

    if not is_valid_number(entry):
        return None

    if not is_valid_number(exit_price):
        return None

    entry = float(entry)
    exit_price = float(exit_price)

    if entry <= 0:
        return None

    return (
        (
            exit_price
            - entry
        )
        / entry
        * 100.0
    )


def apply_round_trip_cost(
    gross_return_pct: float | None,
) -> float | None:

    if gross_return_pct is None:
        return None

    return (
        gross_return_pct
        - ROUND_TRIP_COST_PCT
    )


# =========================================================
# SPLIT
# =========================================================

def split_boundaries(
    data_length: int,
) -> tuple[int, int]:

    train_end = int(
        data_length
        * TRAIN_RATIO
    )

    validation_end = int(
        data_length
        * (
            TRAIN_RATIO
            +
            VALIDATION_RATIO
        )
    )

    return (
        train_end,
        validation_end,
    )


def classify_trade_split(
    signal_index: int,
    entry_index: int,
    exit_index: int,
    data_length: int,
) -> tuple[str | None, str | None]:

    train_end, validation_end = (
        split_boundaries(
            data_length
        )
    )

    train_finish_limit = max(
        0,
        train_end
        - PURGE_DAYS,
    )

    validation_start = min(
        data_length,
        train_end
        + EMBARGO_DAYS,
    )

    validation_finish_limit = max(
        validation_start,
        validation_end
        - PURGE_DAYS,
    )

    test_start = min(
        data_length,
        validation_end
        + EMBARGO_DAYS,
    )

    if (
        signal_index < train_finish_limit
        and entry_index < train_end
        and exit_index < train_finish_limit
    ):

        return (
            "train",
            None,
        )

    if (
        signal_index >= train_end
        and entry_index >= validation_start
        and exit_index < validation_end
        and exit_index < validation_finish_limit
    ):

        return (
            "validation",
            None,
        )

    if (
        signal_index >= validation_end
        and entry_index >= test_start
        and exit_index < data_length
    ):

        return (
            "test",
            None,
        )

    return (
        None,
        "purged_or_embargoed",
    )


# =========================================================
# METRICS
# =========================================================

def calculate_profit_factor(
    returns: list[float],
) -> float | None:

    if not returns:
        return None

    gross_profit = sum(
        value
        for value in returns
        if value > 0
    )

    gross_loss = abs(
        sum(
            value
            for value in returns
            if value < 0
        )
    )

    if gross_loss == 0:

        if gross_profit > 0:
            return float("inf")

        return None

    return (
        gross_profit
        / gross_loss
    )


def calculate_sharpe(
    daily_returns: list[float],
) -> float | None:

    if len(daily_returns) < 2:
        return None

    series = pd.Series(
        daily_returns,
        dtype="float64",
    )

    standard_deviation = (
        series.std(
            ddof=1
        )
    )

    if not is_valid_number(
        standard_deviation
    ):

        return None

    if standard_deviation == 0:
        return None

    mean_return = (
        series.mean()
    )

    return (
        mean_return
        / standard_deviation
        * math.sqrt(252)
    )


def calculate_max_drawdown(
    daily_returns: list[float],
) -> float | None:

    if not daily_returns:
        return None

    equity = [1.0]

    for daily_return in daily_returns:

        equity.append(
            equity[-1]
            * (
                1.0
                +
                daily_return
                / 100.0
            )
        )

    series = pd.Series(
        equity,
        dtype="float64",
    )

    peak = series.cummax()

    drawdown = (
        series
        / peak
        - 1.0
    )

    minimum = drawdown.min()

    if not is_valid_number(
        minimum
    ):

        return None

    return float(
        minimum
        * 100.0
    )


def build_metrics(
    returns: list[float],
) -> dict[str, Any]:

    if not returns:

        return {
            "sample_size": 0,
            "win_rate": None,
            "average_return": None,
            "median_return": None,
            "profit_factor": None,
        }

    series = pd.Series(
        returns,
        dtype="float64",
    )

    return {
        "sample_size": len(
            returns
        ),

        "win_rate": (
            calculate_accuracy(
                returns
            )
        ),

        "average_return": (
            calculate_average(
                returns
            )
        ),

        "median_return": float(
            series.median()
        ),

        "profit_factor": (
            calculate_profit_factor(
                returns
            )
        ),
    }


# =========================================================
# RESEARCH VERDICT
# =========================================================

def build_research_verdict(
    test_metrics: dict[str, Any],
    test_sharpe: float | None,
    test_max_drawdown: float | None,
    test_relative: float | None,
) -> str:

    sample = int(
        test_metrics.get(
            "sample_size",
            0,
        )
        or 0
    )

    win_rate = (
        test_metrics.get(
            "win_rate"
        )
    )

    profit_factor = (
        test_metrics.get(
            "profit_factor"
        )
    )

    if sample < 10:
        return "INCONCLUSIVE"

    if (
        profit_factor is None
        or test_relative is None
        or test_sharpe is None
    ):

        return "INCONCLUSIVE"

    if (
        sample >= 20
        and profit_factor >= 1.50
        and test_relative > 0
        and test_sharpe >= 0.50
        and (
            test_max_drawdown is None
            or test_max_drawdown > -30
        )
    ):

        return "STRONG"

    if (
        profit_factor >= 1.20
        and test_relative > 0
        and test_sharpe > 0
        and (
            win_rate is None
            or win_rate >= 45
        )
    ):

        return "PROMISING"

    if profit_factor >= 1.0:
        return "WEAK"

    return "INCONCLUSIVE"


# =========================================================
# EXECUTABLE TRADE ENGINE
# =========================================================

def simulate_executed_trades(
    data: pd.DataFrame,
    benchmark: pd.DataFrame,
) -> dict[str, Any]:

    trades = []

    excluded_trades = []

    daily_return_map = {}

    i = 0

    while i < len(data) - 1:

        row = data.iloc[i]

        if not bool(
            row["SIGNAL"]
        ):

            i += 1
            continue

        entry_index = (
            i + 1
        )

        exit_index = (
            entry_index
            + HOLDING_DAYS
            - 1
        )

        if exit_index >= len(data):
            break

        split, exclusion_reason = (
            classify_trade_split(
                signal_index=i,
                entry_index=entry_index,
                exit_index=exit_index,
                data_length=len(data),
            )
        )

        entry_date = data.index[
            entry_index
        ]

        exit_date = data.index[
            exit_index
        ]

        entry_price = float(
            data["Open"].iloc[
                entry_index
            ]
        )

        exit_price = float(
            data["Close"].iloc[
                exit_index
            ]
        )

        gross_return = (
            calculate_return(
                entry_price,
                exit_price,
            )
        )

        net_return = (
            apply_round_trip_cost(
                gross_return
            )
        )

        benchmark_window = benchmark.loc[
            (
                benchmark.index
                >= entry_date
            )
            &
            (
                benchmark.index
                <= exit_date
            )
        ]

        benchmark_return = None

        if not benchmark_window.empty:

            benchmark_entry = float(
                benchmark_window[
                    "Open"
                ].iloc[0]
            )

            benchmark_exit = float(
                benchmark_window[
                    "Close"
                ].iloc[-1]
            )

            benchmark_return = (
                calculate_return(
                    benchmark_entry,
                    benchmark_exit,
                )
            )

        relative_return = None

        if (
            net_return is not None
            and benchmark_return is not None
        ):

            relative_return = (
                net_return
                - benchmark_return
            )

        trade = {
            "signal_index": i,
            "signal_date": data.index[i],
            "entry_index": entry_index,
            "entry_date": entry_date,
            "exit_index": exit_index,
            "exit_date": exit_date,
            "entry_price": entry_price,
            "exit_price": exit_price,
            "gross_return": gross_return,
            "net_return": net_return,
            "benchmark_return": benchmark_return,
            "relative_return": relative_return,
            "split": split,
            "eligible_for_evaluation": (
                split is not None
            ),
            "split_exclusion_reason": (
                exclusion_reason
            ),
            "regime": (
                detect_market_regime(
                    row
                )
            ),
            "volume_state": (
                detect_volume_state(
                    row
                )
            ),
            "volatility_state": (
                detect_volatility_state(
                    row
                )
            ),
        }

        if split is None:

            excluded_trades.append(
                trade
            )

            i = (
                exit_index
                + 1
            )

            continue

        trades.append(
            trade
        )

        previous_price = entry_price

        for day_index in range(
            entry_index,
            exit_index + 1,
        ):

            current_date = (
                data.index[
                    day_index
                ]
            )

            close_price = float(
                data["Close"].iloc[
                    day_index
                ]
            )

            daily_return = (
                (
                    close_price
                    / previous_price
                )
                - 1.0
            ) * 100.0

            daily_return_map[
                current_date
            ] = (
                daily_return_map.get(
                    current_date,
                    0.0,
                )
                + daily_return
            )

            previous_price = close_price

        if entry_date in daily_return_map:

            daily_return_map[
                entry_date
            ] -= (
                ROUND_TRIP_COST_PCT
                / 2.0
            )

        if exit_date in daily_return_map:

            daily_return_map[
                exit_date
            ] -= (
                ROUND_TRIP_COST_PCT
                / 2.0
            )

        i = (
            exit_index
            + 1
        )

    return {
        "trades": trades,
        "excluded_trades": excluded_trades,
        "daily_return_map": daily_return_map,
    }


# =========================================================
# DATABASE OBSERVATION
# =========================================================

def save_observation(
    experiment_id,
    data: pd.DataFrame,
    benchmark: pd.DataFrame,
    i: int,
) -> None:

    if experiment_id is None:
        return

    if i + 1 >= len(data):
        return

    signal_date = data.index[i]

    entry_index = (
        i + 1
    )

    entry_price = float(
        data["Open"].iloc[
            entry_index
        ]
    )

    exit_1d_index = (
        entry_index
    )

    exit_5d_index = (
        entry_index
        + 4
    )

    exit_20d_index = (
        entry_index
        + HOLDING_DAYS
        - 1
    )

    price_1d = None

    if exit_1d_index < len(data):

        price_1d = float(
            data["Close"].iloc[
                exit_1d_index
            ]
        )

    price_5d = None

    if exit_5d_index < len(data):

        price_5d = float(
            data["Close"].iloc[
                exit_5d_index
            ]
        )

    price_20d = None

    if exit_20d_index < len(data):

        price_20d = float(
            data["Close"].iloc[
                exit_20d_index
            ]
        )

    r1 = calculate_return(
        entry_price,
        price_1d,
    )

    r5 = calculate_return(
        entry_price,
        price_5d,
    )

    r20 = calculate_return(
        entry_price,
        price_20d,
    )

    exit_date = data.index[
        min(
            exit_20d_index,
            len(data) - 1,
        )
    ]

    entry_date = data.index[
        entry_index
    ]

    benchmark_window = benchmark.loc[
        (
            benchmark.index
            >= entry_date
        )
        &
        (
            benchmark.index
            <= exit_date
        )
    ]

    b1 = None
    b5 = None
    b20 = None

    if not benchmark_window.empty:

        benchmark_entry = float(
            benchmark_window[
                "Open"
            ].iloc[0]
        )

        b1 = calculate_return(
            benchmark_entry,
            benchmark_window[
                "Close"
            ].iloc[0],
        )

        if len(
            benchmark_window
        ) >= 5:

            b5 = calculate_return(
                benchmark_entry,
                benchmark_window[
                    "Close"
                ].iloc[4],
            )

        if len(
            benchmark_window
        ) >= HOLDING_DAYS:

            b20 = calculate_return(
                benchmark_entry,
                benchmark_window[
                    "Close"
                ].iloc[
                    HOLDING_DAYS - 1
                ],
            )

    rel1 = (
        r1 - b1
        if (
            r1 is not None
            and b1 is not None
        )
        else None
    )

    rel5 = (
        r5 - b5
        if (
            r5 is not None
            and b5 is not None
        )
        else None
    )

    rel20 = (
        r20 - b20
        if (
            r20 is not None
            and b20 is not None
        )
        else None
    )

    row = data.iloc[i]

    add_experiment_result(
        experiment_id=experiment_id,
        observation_date=(
            signal_date.strftime(
                "%Y-%m-%d"
            )
        ),
        entry_price=entry_price,
        price_1d=price_1d,
        price_5d=price_5d,
        price_20d=price_20d,
        return_1d=r1,
        return_5d=r5,
        return_20d=r20,
        result_1d=(
            "Avantaj"
            if (
                rel1 is not None
                and rel1 > 0
            )
            else "Dezavantaj"
            if (
                rel1 is not None
                and rel1 < 0
            )
            else "Veri Yok"
        ),
        result_5d=(
            "Avantaj"
            if (
                rel5 is not None
                and rel5 > 0
            )
            else "Dezavantaj"
            if (
                rel5 is not None
                and rel5 < 0
            )
            else "Veri Yok"
        ),
        result_20d=(
            "Avantaj"
            if (
                rel20 is not None
                and rel20 > 0
            )
            else "Dezavantaj"
            if (
                rel20 is not None
                and rel20 < 0
            )
            else "Veri Yok"
        ),
        market_regime=(
            detect_market_regime(
                row
            )
        ),
        volume_state=(
            detect_volume_state(
                row
            )
        ),
        volatility_state=(
            detect_volatility_state(
                row
            )
        ),
        metadata={
            "benchmark_return_1d": b1,
            "benchmark_return_5d": b5,
            "benchmark_return_20d": b20,
            "relative_return_1d": rel1,
            "relative_return_5d": rel5,
            "relative_return_20d": rel20,
            "total_score": int(
                row["TOTAL_SCORE"]
            ),
            "entry_definition": (
                "next_trading_day_open"
            ),
            "weekly_definition": (
                "previous_completed_week"
            ),
            "research_version": "V4.4",
        },
    )


# =========================================================
# SINGLE EXPERIMENT
# =========================================================

def run_experiment(
    symbol: str,
    period: str = DEFAULT_PERIOD,
) -> dict[str, Any]:

    symbol = clean_symbol(
        symbol
    )

    benchmark_symbol = (
        get_benchmark(
            symbol
        )
    )

    print()

    print(
        f"🔬 Deney başlıyor: "
        f"{symbol}"
    )

    print(
        f"   Benchmark: "
        f"{benchmark_symbol}"
    )

    print(
        f"   📥 {symbol} ana veri çekiliyor..."
    )

    asset = download_history(
        symbol,
        period=period,
    )

    if asset.empty:

        print(
            f"   ❌ {symbol} ana veri başarısız."
        )

        return {
            "symbol": symbol,
            "status": "no_asset_data",
        }

    print(
        f"   📊 {symbol} benchmark çekiliyor..."
    )

    benchmark = download_history(
        benchmark_symbol,
        period=period,
    )

    if benchmark.empty:

        print(
            f"   ❌ {benchmark_symbol} "
            f"benchmark başarısız."
        )

        return {
            "symbol": symbol,
            "status": "no_benchmark_data",
        }

    if len(asset) < MIN_DATA_ROWS:

        print(
            f"⚠️ Yetersiz hisse verisi: "
            f"{len(asset)}"
        )

        return {
            "symbol": symbol,
            "status": (
                "insufficient_asset_data"
            ),
        }

    # -----------------------------------------------------
    # INDICATORS
    # -----------------------------------------------------

    print(
        f"   🧮 {symbol} indikatörleri hesaplanıyor..."
    )

    data = add_indicators(
        asset
    )

    data = calculate_signal(
        data
    )

    data = data.dropna(
        subset=[
            "EMA20",
            "EMA50",
            "EMA200",
            "ROC20",
            "VolumeMA20",
            "ATR14",
            "REG_SLOPE20",
            "SUPPORT20",
            "RESISTANCE20",
        ]
    )

    if data.empty:

        return {
            "symbol": symbol,
            "status": (
                "no_valid_indicator_data"
            ),
        }

    train_end, validation_end = (
        split_boundaries(
            len(data)
        )
    )

    if (
        train_end <= 0
        or validation_end >= len(data)
    ):

        return {
            "symbol": symbol,
            "status": (
                "invalid_data_split"
            ),
        }

    effective_test_start_index = min(
        len(data) - 1,
        validation_end
        + EMBARGO_DAYS,
    )

    train_start_date = (
        data.index[0]
    )

    train_end_date = (
        data.index[
            train_end - 1
        ]
    )

    validation_start_date = (
        data.index[
            min(
                train_end
                + EMBARGO_DAYS,
                len(data) - 1,
            )
        ]
    )

    validation_end_date = (
        data.index[
            validation_end - 1
        ]
    )

    test_start_date = (
        data.index[
            effective_test_start_index
        ]
    )

    test_end_date = (
        data.index[-1]
    )

    # -----------------------------------------------------
    # DATABASE
    # -----------------------------------------------------

    print(
        f"   💾 {symbol} deney kaydı oluşturuluyor..."
    )

    market = market_from_symbol(
        symbol
    )

    experiment_id = (
        create_learning_experiment(
            method_name=METHOD_NAME,
            symbol=symbol,
            method_type=(
                "multi_factor_strategy_v4_4"
            ),
            market=market,
            timeframe=TIMEFRAME,
            signal_direction="Pozitif",
            start_date=(
                data.index[0]
                .strftime(
                    "%Y-%m-%d"
                )
            ),
            end_date=(
                data.index[-1]
                .strftime(
                    "%Y-%m-%d"
                )
            ),
            parameters={
                "benchmark": (
                    benchmark_symbol
                ),
                "holding_days": (
                    HOLDING_DAYS
                ),
                "purge_days": (
                    PURGE_DAYS
                ),
                "embargo_days": (
                    EMBARGO_DAYS
                ),
                "entry": (
                    "next_trading_day_open"
                ),
                "exit": (
                    "close_after_20_sessions"
                ),
                "round_trip_cost_pct": (
                    ROUND_TRIP_COST_PCT
                ),
                "train_ratio": (
                    TRAIN_RATIO
                ),
                "validation_ratio": (
                    VALIDATION_RATIO
                ),
                "test_ratio": (
                    TEST_RATIO
                ),
                "weekly_signal": (
                    "previous_completed_week"
                ),
                "aggregate": {
                    "type": (
                        "equal_weight_fixed_allocation"
                    ),
                    "cash_when_no_position": True,
                    "non_overlapping_per_symbol": True,
                },
            },
        )
    )

    # -----------------------------------------------------
    # EXECUTION
    # -----------------------------------------------------

    print(
        f"   ⚙️ {symbol} işlemler simüle ediliyor..."
    )

    execution = (
        simulate_executed_trades(
            data,
            benchmark,
        )
    )

    trades = execution[
        "trades"
    ]

    excluded_trades = execution[
        "excluded_trades"
    ]

    daily_return_map = execution[
        "daily_return_map"
    ]

    # -----------------------------------------------------
    # DATABASE OBSERVATIONS
    # -----------------------------------------------------

    print(
        f"   🗄️ {symbol} gözlemleri kaydediliyor..."
    )

    for trade in trades:

        save_observation(
            experiment_id=experiment_id,
            data=data,
            benchmark=benchmark,
            i=trade["signal_index"],
        )

    # -----------------------------------------------------
    # SPLITS
    # -----------------------------------------------------

    train_trades = [
        trade
        for trade in trades
        if trade["split"] == "train"
    ]

    validation_trades = [
        trade
        for trade in trades
        if trade["split"] == "validation"
    ]

    test_trades = [
        trade
        for trade in trades
        if trade["split"] == "test"
    ]

    # -----------------------------------------------------
    # RETURNS
    # -----------------------------------------------------

    train_returns = [
        float(
            trade["net_return"]
        )
        for trade in train_trades
        if trade["net_return"] is not None
    ]

    validation_returns = [
        float(
            trade["net_return"]
        )
        for trade in validation_trades
        if trade["net_return"] is not None
    ]

    test_returns = [
        float(
            trade["net_return"]
        )
        for trade in test_trades
        if trade["net_return"] is not None
    ]

    test_relative_returns = [
        float(
            trade["relative_return"]
        )
        for trade in test_trades
        if trade["relative_return"] is not None
    ]

    # -----------------------------------------------------
    # METRICS
    # -----------------------------------------------------

    train_metrics = build_metrics(
        train_returns
    )

    validation_metrics = build_metrics(
        validation_returns
    )

    test_metrics = build_metrics(
        test_returns
    )

    # -----------------------------------------------------
    # TEST DAILY SERIES
    # -----------------------------------------------------

    actual_test_dates = (
        data.index[
            (
                data.index
                >= test_start_date
            )
            &
            (
                data.index
                <= test_end_date
            )
        ]
    )

    test_daily_values = [
        float(
            daily_return_map.get(
                current_date,
                0.0,
            )
        )
        for current_date
        in actual_test_dates
    ]

    test_sharpe = calculate_sharpe(
        test_daily_values
    )

    test_max_drawdown = (
        calculate_max_drawdown(
            test_daily_values
        )
    )

    # -----------------------------------------------------
    # BENCHMARK
    # -----------------------------------------------------

    benchmark_window = benchmark.loc[
        (
            benchmark.index
            >= test_start_date
        )
        &
        (
            benchmark.index
            <= test_end_date
        )
    ]

    test_benchmark_return = None

    if not benchmark_window.empty:

        benchmark_entry = float(
            benchmark_window[
                "Open"
            ].iloc[0]
        )

        benchmark_exit = float(
            benchmark_window[
                "Close"
            ].iloc[-1]
        )

        test_benchmark_return = (
            calculate_return(
                benchmark_entry,
                benchmark_exit,
            )
        )

    test_relative_average = (
        calculate_average(
            test_relative_returns
        )
    )

    # -----------------------------------------------------
    # RESEARCH VERDICT
    # -----------------------------------------------------

    research_verdict = (
        build_research_verdict(
            test_metrics=test_metrics,
            test_sharpe=test_sharpe,
            test_max_drawdown=(
                test_max_drawdown
            ),
            test_relative=(
                test_relative_average
            ),
        )
    )

    # -----------------------------------------------------
    # REGIME ANALYSIS
    # -----------------------------------------------------

    regime_results = {}

    for trade in trades:

        value = trade.get(
            "net_return"
        )

        if value is None:
            continue

        key = (
            trade.get(
                "regime",
                "Bilinmiyor",
            ),
            trade.get(
                "volume_state",
                "Bilinmiyor",
            ),
            trade.get(
                "volatility_state",
                "Bilinmiyor",
            ),
        )

        regime_results.setdefault(
            key,
            [],
        ).append(
            float(value)
        )

    for (
        regime_key,
        returns,
    ) in regime_results.items():

        if len(returns) < 10:
            continue

        condition_name = (
            f"{regime_key[0]}"
            f"__"
            f"{regime_key[1]}"
            f"__"
            f"{regime_key[2]}"
        )

        save_learned_rule(
            method_name=METHOD_NAME,
            method_type=(
                "regime_analysis_v4_4"
            ),
            symbol=symbol,
            market=market,
            timeframe=TIMEFRAME,
            condition_name=condition_name,
            sample_size=len(
                returns
            ),
            success_rate=(
                calculate_accuracy(
                    returns
                )
            ),
            average_return_20d=(
                calculate_average(
                    returns
                )
            ),
            best_return=max(
                returns
            ),
            worst_return=min(
                returns
            ),
            confidence=(
                calculate_confidence(
                    len(returns)
                )
            ),
            observation=(
                "Executable net 20D return "
                "under this regime."
            ),
        )

    # -----------------------------------------------------
    # LEARN TEST RULE
    # -----------------------------------------------------

    save_learned_rule(
        method_name=METHOD_NAME,
        method_type=(
            "chronological_test_v4_4"
        ),
        symbol=symbol,
        market=market,
        timeframe=TIMEFRAME,
        condition_name=(
            "out_of_sample_test"
        ),
        sample_size=len(
            test_returns
        ),
        success_rate=(
            test_metrics["win_rate"]
        ),
        average_return=(
            test_metrics["average_return"]
        ),
        average_return_5d=None,
        average_return_20d=(
            test_metrics["average_return"]
        ),
        best_return=(
            max(test_returns)
            if test_returns
            else None
        ),
        worst_return=(
            min(test_returns)
            if test_returns
            else None
        ),
        confidence=(
            calculate_confidence(
                len(test_returns)
            )
        ),
        observation=(
            f"TestAvg20G="
            f"{format_percent(test_metrics['average_return'])}; "
            f"TestMedian20G="
            f"{format_percent(test_metrics['median_return'])}; "
            f"TestWinRate="
            f"{format_percent(test_metrics['win_rate'])}; "
            f"TestPF="
            f"{test_metrics['profit_factor']}; "
            f"TestSharpe="
            f"{test_sharpe}; "
            f"TestMaxDD="
            f"{format_percent(test_max_drawdown)}; "
            f"TestBenchmark="
            f"{format_percent(test_benchmark_return)}; "
            f"TestRelative="
            f"{format_percent(test_relative_average)}; "
            f"Verdict="
            f"{research_verdict}."
        ),
    )

    # -----------------------------------------------------
    # DATABASE STATUS
    # -----------------------------------------------------

    update_experiment_status(
        experiment_id,
        "completed",
    )

    # -----------------------------------------------------
    # CONSOLE
    # -----------------------------------------------------

    print(
        f"✅ {symbol} tamamlandı"
    )

    print(
        f"   Sinyal: "
        f"{int(data['SIGNAL'].sum())}"
    )

    print(
        f"   Değerlendirilen işlem: "
        f"{len(trades)}"
    )

    print(
        f"   Purge/Embargo dışı bırakılan: "
        f"{len(excluded_trades)}"
    )

    print(
        f"   Train işlem: "
        f"{len(train_trades)}"
    )

    print(
        f"   Validation işlem: "
        f"{len(validation_trades)}"
    )

    print(
        f"   Test işlem: "
        f"{len(test_trades)}"
    )

    print(
        f"   Test net ort. 20G: "
        f"{format_percent(test_metrics['average_return'])}"
    )

    print(
        f"   Test median 20G: "
        f"{format_percent(test_metrics['median_return'])}"
    )

    print(
        f"   Test win rate: "
        f"{format_percent(test_metrics['win_rate'])}"
    )

    print(
        f"   Test profit factor: "
        f"{test_metrics['profit_factor']}"
    )

    print(
        f"   Test Sharpe: "
        f"{test_sharpe}"
    )

    print(
        f"   Test max drawdown: "
        f"{format_percent(test_max_drawdown)}"
    )

    print(
        f"   Test benchmark: "
        f"{format_percent(test_benchmark_return)}"
    )

    print(
        f"   Test göreli sonuç: "
        f"{format_percent(test_relative_average)}"
    )

    print(
        f"   Research verdict: "
        f"{research_verdict}"
    )

    if (
        len(test_trades)
        < MIN_TEST_TRADES_WARNING
    ):

        print(
            f"   ⚠️ UYARI: "
            f"Test örneklemi yalnızca "
            f"{len(test_trades)} işlem."
        )

    return {
        "symbol": symbol,
        "market": market,
        "status": "completed",

        "experiment_id": (
            experiment_id
        ),

        "signals": int(
            data["SIGNAL"].sum()
        ),

        "executed_trades": len(
            trades
        ),

        "excluded_trades": len(
            excluded_trades
        ),

        "train_trades": len(
            train_trades
        ),

        "validation_trades": len(
            validation_trades
        ),

        "test_trades": len(
            test_trades
        ),

        "train": train_metrics,

        "validation": validation_metrics,

        "test": test_metrics,

        "purged_test": test_metrics,

        "research_verdict": (
            research_verdict
        ),

        "research_integrity": {
            "version": "V4.4",

            "purge_days": (
                PURGE_DAYS
            ),

            "embargo_days": (
                EMBARGO_DAYS
            ),

            "executed_trades": (
                len(trades)
            ),

            "excluded_trades": (
                len(excluded_trades)
            ),

            "test_trades": (
                len(test_trades)
            ),

            "test_start_index": (
                effective_test_start_index
            ),

            "train_end_index": (
                train_end
            ),

            "validation_end_index": (
                validation_end
            ),
        },

        "test_daily_series": {
            date.strftime(
                "%Y-%m-%d"
            ): float(
                daily_return_map.get(
                    date,
                    0.0,
                )
            )
            for date in actual_test_dates
        },

        "raw_trades": trades,

        "test_sharpe": (
            test_sharpe
        ),

        "purged_test_sharpe": (
            test_sharpe
        ),

        "test_max_drawdown": (
            test_max_drawdown
        ),

        "purged_test_max_drawdown": (
            test_max_drawdown
        ),

        "test_benchmark": (
            test_benchmark_return
        ),

        "test_relative": (
            test_relative_average
        ),

        "test_start_date": (
            test_start_date
        ),

        "test_end_date": (
            test_end_date
        ),

        "train_start_date": (
            train_start_date
        ),

        "train_end_date": (
            train_end_date
        ),

        "validation_start_date": (
            validation_start_date
        ),

        "validation_end_date": (
            validation_end_date
        ),

        "round_trip_cost_pct": (
            ROUND_TRIP_COST_PCT
        ),
    }


# =========================================================
# GROUP
# =========================================================

def run_symbol_group(
    symbols: list[str],
    period: str = DEFAULT_PERIOD,
) -> list[dict[str, Any]]:

    results = []

    for symbol in symbols:

        try:

            result = run_experiment(
                symbol,
                period=period,
            )

            results.append(
                result
            )

        except Exception as error:

            print(
                f"❌ {symbol} hata: "
                f"{error}"
            )

            results.append(
                {
                    "symbol": symbol,
                    "status": "error",
                    "error": str(error),
                }
            )

    return results


# =========================================================
# AGGREGATE DAILY FRAME
# =========================================================

def build_daily_frame(
    results: list[dict[str, Any]],
) -> pd.DataFrame:

    series_map = {}

    for result in results:

        if result.get(
            "status"
        ) != "completed":

            continue

        symbol = result.get(
            "symbol"
        )

        series = result.get(
            "test_daily_series",
            {}
        )

        if not series:
            continue

        frame = pd.Series(
            series,
            dtype="float64",
            name=symbol,
        )

        frame.index = pd.to_datetime(
            frame.index
        )

        frame = frame.sort_index()

        series_map[
            symbol
        ] = frame

    if not series_map:
        return pd.DataFrame()

    combined = pd.concat(
        series_map.values(),
        axis=1,
        join="outer",
        sort=True,
    )

    combined = combined.fillna(
        0.0
    )

    return combined.sort_index()


# =========================================================
# AGGREGATE PORTFOLIO
# =========================================================

def build_equal_weight_portfolio(
    results: list[dict[str, Any]],
) -> pd.Series | None:

    frame = build_daily_frame(
        results
    )

    if frame.empty:
        return None

    portfolio_returns = (
        frame.mean(
            axis=1
        )
    )

    return portfolio_returns.astype(
        "float64"
    )


def calculate_portfolio_metrics(
    portfolio_returns: pd.Series | None,
) -> dict[str, Any]:

    if (
        portfolio_returns is None
        or portfolio_returns.empty
    ):

        return {
            "days": 0,
            "total_return": None,
            "sharpe": None,
            "max_drawdown": None,
            "average_daily_return": None,
        }

    values = [
        float(value)
        for value
        in portfolio_returns.values
    ]

    equity = 1.0

    for value in values:

        equity *= (
            1.0
            +
            value
            / 100.0
        )

    total_return = (
        equity
        - 1.0
    ) * 100.0

    return {
        "days": len(values),

        "total_return": (
            total_return
        ),

        "sharpe": (
            calculate_sharpe(
                values
            )
        ),

        "max_drawdown": (
            calculate_max_drawdown(
                values
            )
        ),

        "average_daily_return": (
            calculate_average(
                values
            )
        ),
    }


# =========================================================
# POOLED TEST TRADES
# =========================================================

def collect_pooled_test_trades(
    results: list[dict[str, Any]],
) -> list[dict[str, Any]]:

    pooled = []

    for result in results:

        if result.get(
            "status"
        ) != "completed":

            continue

        raw_trades = result.get(
            "raw_trades",
            []
        )

        for trade in raw_trades:

            if (
                trade.get(
                    "split"
                )
                != "test"
            ):

                continue

            copied = dict(
                trade
            )

            copied[
                "symbol"
            ] = result.get(
                "symbol"
            )

            copied[
                "market"
            ] = result.get(
                "market"
            )

            pooled.append(
                copied
            )

    pooled.sort(
        key=lambda trade: (
            trade.get(
                "entry_date"
            ),
            trade.get(
                "symbol",
                "",
            ),
        )
    )

    return pooled


# =========================================================
# MARKET AGGREGATE
# =========================================================

def build_market_aggregate(
    results: list[dict[str, Any]],
    market: str,
    period: str,
) -> dict[str, Any]:

    market_results = [
        result
        for result in results
        if (
            result.get(
                "status"
            )
            == "completed"
            and result.get(
                "market"
            )
            == market
        )
    ]

    if not market_results:

        return {
            "market": market,
            "symbol_count": 0,
            "portfolio_metrics": {},
            "benchmark_return": None,
            "relative_return": None,
            "pooled_metrics": {},
            "pooled_trade_count": 0,
        }

    portfolio = (
        build_equal_weight_portfolio(
            market_results
        )
    )

    portfolio_metrics = (
        calculate_portfolio_metrics(
            portfolio
        )
    )

    benchmark_symbol = (
        BIST_BENCHMARK
        if market == "BIST"
        else US_BENCHMARK
    )

    benchmark = download_history(
        benchmark_symbol,
        period=period,
    )

    benchmark_return = None

    if (
        portfolio is not None
        and not portfolio.empty
        and not benchmark.empty
    ):

        start_date = (
            portfolio.index[0]
        )

        end_date = (
            portfolio.index[-1]
        )

        benchmark_window = benchmark.loc[
            (
                benchmark.index
                >= start_date
            )
            &
            (
                benchmark.index
                <= end_date
            )
        ]

        if not benchmark_window.empty:

            benchmark_entry = float(
                benchmark_window[
                    "Open"
                ].iloc[0]
            )

            benchmark_exit = float(
                benchmark_window[
                    "Close"
                ].iloc[-1]
            )

            benchmark_return = (
                calculate_return(
                    benchmark_entry,
                    benchmark_exit,
                )
            )

    relative_return = None

    if (
        portfolio_metrics.get(
            "total_return"
        ) is not None
        and benchmark_return is not None
    ):

        relative_return = (
            portfolio_metrics[
                "total_return"
            ]
            -
            benchmark_return
        )

    pooled_test_trades = (
        collect_pooled_test_trades(
            market_results
        )
    )

    pooled_returns = [
        float(
            trade["net_return"]
        )
        for trade in pooled_test_trades
        if trade.get(
            "net_return"
        ) is not None
    ]

    pooled_metrics = build_metrics(
        pooled_returns
    )

    return {
        "market": market,

        "symbol_count": len(
            market_results
        ),

        "portfolio_metrics": (
            portfolio_metrics
        ),

        "benchmark_return": (
            benchmark_return
        ),

        "relative_return": (
            relative_return
        ),

        "pooled_metrics": (
            pooled_metrics
        ),

        "pooled_trade_count": len(
            pooled_test_trades
        ),

        "symbols": [
            result.get(
                "symbol"
            )
            for result in market_results
        ],
    }


# =========================================================
# GLOBAL AGGREGATE
# =========================================================

def build_global_aggregate(
    results: list[dict[str, Any]],
) -> dict[str, Any]:

    completed = [
        result
        for result in results
        if result.get(
            "status"
        ) == "completed"
    ]

    if not completed:

        return {
            "portfolio_metrics": {},
            "pooled_metrics": {},
            "trade_count": 0,
        }

    portfolio = (
        build_equal_weight_portfolio(
            completed
        )
    )

    portfolio_metrics = (
        calculate_portfolio_metrics(
            portfolio
        )
    )

    pooled_test_trades = (
        collect_pooled_test_trades(
            completed
        )
    )

    pooled_returns = [
        float(
            trade["net_return"]
        )
        for trade in pooled_test_trades
        if trade.get(
            "net_return"
        ) is not None
    ]

    pooled_metrics = build_metrics(
        pooled_returns
    )

    return {
        "portfolio_metrics": (
            portfolio_metrics
        ),

        "pooled_metrics": (
            pooled_metrics
        ),

        "trade_count": len(
            pooled_test_trades
        ),
    }


# =========================================================
# PRINT AGGREGATE
# =========================================================

def print_aggregate_summary(
    results: list[dict[str, Any]],
    period: str,
) -> None:

    print()

    print(
        "============================================================"
    )

    print(
        "🌐 AGGREGATE PORTFOLIO TEST V4.4"
    )

    print(
        "============================================================"
    )

    print(
        "Equal-weight fixed allocation"
    )

    print(
        "No-position sleeves remain in cash"
    )

    print(
        f"Round-trip cost assumption: "
        f"%{ROUND_TRIP_COST_PCT:.2f}"
    )

    print(
        f"Purge: "
        f"{PURGE_DAYS} işlem günü"
    )

    print(
        f"Embargo: "
        f"{EMBARGO_DAYS} işlem günü"
    )

    print()

    market_aggregates = []

    for market in [
        "BIST",
        "US",
    ]:

        aggregate = (
            build_market_aggregate(
                results,
                market,
                period,
            )
        )

        market_aggregates.append(
            aggregate
        )

        print(
            f"🌍 {market}"
        )

        print(
            f"   Sembol sayısı: "
            f"{aggregate['symbol_count']}"
        )

        portfolio_metrics = (
            aggregate[
                "portfolio_metrics"
            ]
        )

        print(
            f"   Portföy toplam test getirisi: "
            f"{format_percent(portfolio_metrics.get('total_return'))}"
        )

        print(
            f"   Portföy Sharpe: "
            f"{portfolio_metrics.get('sharpe')}"
        )

        print(
            f"   Portföy MaxDD: "
            f"{format_percent(portfolio_metrics.get('max_drawdown'))}"
        )

        print(
            f"   Benchmark: "
            f"{format_percent(aggregate['benchmark_return'])}"
        )

        print(
            f"   Benchmark farkı: "
            f"{format_percent(aggregate['relative_return'])}"
        )

        pooled = (
            aggregate[
                "pooled_metrics"
            ]
        )

        print(
            f"   Pooled test işlem: "
            f"{aggregate['pooled_trade_count']}"
        )

        print(
            f"   Pooled Win Rate: "
            f"{format_percent(pooled.get('win_rate'))}"
        )

        print(
            f"   Pooled Profit Factor: "
            f"{pooled.get('profit_factor')}"
        )

        print()

    # -----------------------------------------------------
    # GLOBAL
    # -----------------------------------------------------

    global_aggregate = (
        build_global_aggregate(
            results
        )
    )

    print(
        "============================================================"
    )

    print(
        "🌐 GLOBAL MARKET HQ PORTFOLIO V4.4"
    )

    print(
        "============================================================"
    )

    global_portfolio = (
        global_aggregate[
            "portfolio_metrics"
        ]
    )

    global_pooled = (
        global_aggregate[
            "pooled_metrics"
        ]
    )

    print(
        f"   Toplam portföy test getirisi: "
        f"{format_percent(global_portfolio.get('total_return'))}"
    )

    print(
        f"   Global Sharpe: "
        f"{global_portfolio.get('sharpe')}"
    )

    print(
        f"   Global MaxDD: "
        f"{format_percent(global_portfolio.get('max_drawdown'))}"
    )

    print(
        f"   Pooled test işlem: "
        f"{global_aggregate['trade_count']}"
    )

    print(
        f"   Pooled Win Rate: "
        f"{format_percent(global_pooled.get('win_rate'))}"
    )

    print(
        f"   Pooled Profit Factor: "
        f"{global_pooled.get('profit_factor')}"
    )

    print()

    all_test_trades = sum(
        aggregate[
            "pooled_trade_count"
        ]
        for aggregate
        in market_aggregates
    )

    if all_test_trades < 30:

        print(
            "⚠️ GLOBAL UYARI:"
        )

        print(
            f"   Toplam test işlem sayısı "
            f"{all_test_trades}."
        )

        print(
            "   Örneklem küçük olabilir."
        )

    print()


# =========================================================
# SYMBOL SUMMARY
# =========================================================

def print_symbol_summary(
    results: list[dict[str, Any]],
) -> None:

    print()

    print(
        "============================================================"
    )

    print(
        "📊 SYMBOL TEST SUMMARY V4.4"
    )

    print(
        "============================================================"
    )

    for result in results:

        if (
            result.get(
                "status"
            )
            != "completed"
        ):

            continue

        test = result.get(
            "test",
            {}
        )

        warning = ""

        if (
            result.get(
                "test_trades",
                0,
            )
            < MIN_TEST_TRADES_WARNING
        ):

            warning = (
                " ⚠️ küçük örneklem"
            )

        print(
            f"{result['symbol']} | "
            f"{result['market']} | "
            f"Test {result['test_trades']} | "
            f"20G "
            f"{format_percent(test.get('average_return'))} | "
            f"Win "
            f"{format_percent(test.get('win_rate'))} | "
            f"PF "
            f"{test.get('profit_factor')} | "
            f"Sharpe "
            f"{result.get('test_sharpe')} | "
            f"MaxDD "
            f"{format_percent(result.get('test_max_drawdown'))} | "
            f"Bench "
            f"{format_percent(result.get('test_benchmark'))} | "
            f"Rel "
            f"{format_percent(result.get('test_relative'))} | "
            f"Verdict "
            f"{result.get('research_verdict', 'INCONCLUSIVE')}"
            f"{warning}"
        )


# =========================================================
# MAIN
# =========================================================

if __name__ == "__main__":

    init_db()

    print(
        "============================================================"
    )

    print(
        "🔬 MARKET HQ STRATEGY LAB V4.4"
    )

    print(
        "============================================================"
    )

    print(
        "FIN[SYS] public-methodology baseline"
    )

    print(
        "Chronological out-of-sample research"
    )

    print(
        "Execution-aware aggregate portfolio"
    )

    print()

    print(
        f"Holding period: "
        f"{HOLDING_DAYS} işlem günü"
    )

    print(
        "Entry: next trading day OPEN"
    )

    print(
        "Weekly signal: previous completed week"
    )

    print(
        f"Round-trip cost: "
        f"%{ROUND_TRIP_COST_PCT:.2f}"
    )

    print(
        f"Purge days: "
        f"{PURGE_DAYS}"
    )

    print(
        f"Embargo days: "
        f"{EMBARGO_DAYS}"
    )

    print(
        "Split: "
        f"{TRAIN_RATIO:.0%} / "
        f"{VALIDATION_RATIO:.0%} / "
        f"{TEST_RATIO:.0%}"
    )

    print(
        "Aggregate: "
        "fixed equal-weight + cash when inactive"
    )

    print()

    print(
        "🇹🇷 BIST deneyleri başlıyor..."
    )

    bist_results = run_symbol_group(
        BIST_SYMBOLS
    )

    print()

    print(
        "🇺🇸 US deneyleri başlıyor..."
    )

    us_results = run_symbol_group(
        US_SYMBOLS
    )

    all_results = (
        bist_results
        +
        us_results
    )

    print_symbol_summary(
        all_results
    )

    print_aggregate_summary(
        all_results,
        period=DEFAULT_PERIOD,
    )

    print()

    print(
        "============================================================"
    )

    print(
        "✅ MARKET HQ STRATEGY LAB V4.4 TAMAMLANDI"
    )

    print(
        "============================================================"
    )
