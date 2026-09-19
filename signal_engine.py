# -*- coding: utf-8 -*-

"""
MarketHQ Signal Engine V3

Amaç:
    OHLCV verisi üzerinden teknik göstergeler hesaplamak
    ve BUY / SELL / WAIT sinyali üretmek.

Bu modül:
    - SMA
    - EMA
    - RSI
    - MACD
    - Bollinger Bands
    - ATR
    - Volume Ratio
    - Signal Score
    - Stop Loss
    - Take Profit

üretir.

Gerçek emir göndermez.
Yalnızca araştırma / sinyal / backtest amaçlıdır.

ÖNEMLİ:
    Indicator kolon isimleri tek bir standartta tutulur.
    Böylece Signal Engine, Backtest Engine, Optimizer,
    Walk-Forward ve Strategy Pipeline aynı veri sözleşmesini
    kullanabilir.
"""

from __future__ import annotations

import math
from typing import Any

import pandas as pd


# =========================================================
# DEFAULT CONFIG
# =========================================================

DEFAULT_CONFIG: dict[str, Any] = {
    # Trend
    "sma_fast": 20,
    "sma_slow": 50,

    "ema_fast": 20,
    "ema_slow": 50,

    # Momentum
    "rsi_period": 14,

    # MACD
    "macd_fast": 12,
    "macd_slow": 26,
    "macd_signal": 9,

    # Bollinger
    "bollinger_period": 20,
    "bollinger_std": 2.0,

    # Volatility
    "atr_period": 14,

    # Volume
    "volume_period": 20,

    # Donchian
    "donchian_period": 20,

    # SuperTrend
    "supertrend_period": 10,
    "supertrend_mult": 3.0,

    # ADX
    "adx_period": 14,
    "adx_threshold": 20.0,

    # VWAP
    "vwap_window": 20,

    # Stochastic
    "stoch_k_period": 14,
    "stoch_d_period": 3,

    # Signal thresholds
    "buy_threshold": 3,
    "sell_threshold": -3,

    # RSI levels
    "rsi_oversold": 30,
    "rsi_overbought": 70,

    # Volume
    "minimum_volume_ratio": 1.0,

    # Risk
    "stop_atr_multiple": 2.0,
    "target_atr_multiple": 3.0,
}


# =========================================================
# BASIC HELPERS
# =========================================================

def is_valid_number(
    value: Any,
) -> bool:
    try:
        number = float(value)
        return math.isfinite(number)
    except (
        TypeError,
        ValueError,
    ):
        return False


def safe_float(
    value: Any,
    default: float | None = None,
) -> float | None:
    if value is None:
        return default

    try:
        number = float(value)

        if not math.isfinite(number):
            return default

        return number

    except (
        TypeError,
        ValueError,
    ):
        return default


# =========================================================
# OHLCV VALIDATION
# =========================================================

def validate_ohlcv(
    data: pd.DataFrame,
) -> bool:

    if data is None:
        return False

    if not isinstance(
        data,
        pd.DataFrame,
    ):
        return False

    if data.empty:
        return False

    required_columns = [
        "Open",
        "High",
        "Low",
        "Close",
        "Volume",
    ]

    for column in required_columns:
        if column not in data.columns:
            return False

    return True


def normalize_ohlcv(
    data: pd.DataFrame,
) -> pd.DataFrame:

    if not validate_ohlcv(data):
        raise ValueError(
            "Geçerli OHLCV pandas DataFrame olmalıdır."
        )

    df = data.copy()

    for column in [
        "Open",
        "High",
        "Low",
        "Close",
        "Volume",
    ]:
        df[column] = pd.to_numeric(
            df[column],
            errors="coerce",
        )

    df = df.dropna(
        subset=[
            "Open",
            "High",
            "Low",
            "Close",
        ]
    )

    df = df.sort_index()

    return df


# =========================================================
# NUMERIC SERIES
# =========================================================

def get_numeric_series(
    data: pd.DataFrame,
    column: str,
) -> pd.Series:

    if column not in data.columns:
        raise ValueError(
            f"OHLCV verisinde '{column}' kolonu bulunamadı."
        )

    return pd.to_numeric(
        data[column],
        errors="coerce",
    )


# =========================================================
# SMA
# =========================================================

def calculate_sma(
    series: pd.Series,
    period: int,
) -> pd.Series:

    period = max(
        int(period),
        1,
    )

    return series.rolling(
        window=period,
        min_periods=period,
    ).mean()


# =========================================================
# EMA
# =========================================================

def calculate_ema(
    series: pd.Series,
    period: int,
) -> pd.Series:

    period = max(
        int(period),
        1,
    )

    return series.ewm(
        span=period,
        adjust=False,
        min_periods=period,
    ).mean()


# =========================================================
# RSI
# =========================================================

def calculate_rsi(
    series: pd.Series,
    period: int = 14,
) -> pd.Series:

    period = max(
        int(period),
        1,
    )

    delta = series.diff()

    gain = delta.clip(
        lower=0,
    )

    loss = -delta.clip(
        upper=0,
    )

    average_gain = gain.ewm(
        alpha=1 / period,
        adjust=False,
        min_periods=period,
    ).mean()

    average_loss = loss.ewm(
        alpha=1 / period,
        adjust=False,
        min_periods=period,
    ).mean()

    rs = (
        average_gain
        / average_loss.replace(
            0,
            pd.NA,
        )
    )

    rsi = (
        100
        - (
            100
            / (
                1
                + rs
            )
        )
    )

    # Kayıp yoksa RSI 100.
    rsi = rsi.mask(
        (
            average_loss == 0
        )
        & (
            average_gain > 0
        ),
        100,
    )

    # Kazanç ve kayıp yoksa nötr 50.
    rsi = rsi.mask(
        (
            average_loss == 0
        )
        & (
            average_gain == 0
        ),
        50,
    )

    return rsi.astype(
        "float64"
    )


# =========================================================
# MACD
# =========================================================

def calculate_macd(
    series: pd.Series,
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
) -> tuple[
    pd.Series,
    pd.Series,
    pd.Series,
]:

    fast = max(
        int(fast),
        1,
    )

    slow = max(
        int(slow),
        fast + 1,
    )

    signal = max(
        int(signal),
        1,
    )

    ema_fast = calculate_ema(
        series,
        fast,
    )

    ema_slow = calculate_ema(
        series,
        slow,
    )

    macd_line = (
        ema_fast
        - ema_slow
    )

    signal_line = calculate_ema(
        macd_line,
        signal,
    )

    histogram = (
        macd_line
        - signal_line
    )

    return (
        macd_line,
        signal_line,
        histogram,
    )


# =========================================================
# BOLLINGER BANDS
# =========================================================

def calculate_bollinger(
    series: pd.Series,
    period: int = 20,
    std_multiplier: float = 2.0,
) -> tuple[
    pd.Series,
    pd.Series,
    pd.Series,
]:

    period = max(
        int(period),
        1,
    )

    std_multiplier = float(
        std_multiplier
    )

    middle = series.rolling(
        window=period,
        min_periods=period,
    ).mean()

    std = series.rolling(
        window=period,
        min_periods=period,
    ).std()

    upper = (
        middle
        + (
            std
            * std_multiplier
        )
    )

    lower = (
        middle
        - (
            std
            * std_multiplier
        )
    )

    return (
        middle,
        upper,
        lower,
    )


# =========================================================
# ATR
# =========================================================

def calculate_atr(
    data: pd.DataFrame,
    period: int = 14,
) -> pd.Series:

    period = max(
        int(period),
        1,
    )

    high = get_numeric_series(
        data,
        "High",
    )

    low = get_numeric_series(
        data,
        "Low",
    )

    close = get_numeric_series(
        data,
        "Close",
    )

    previous_close = close.shift(
        1
    )

    range_1 = (
        high
        - low
    )

    range_2 = (
        high
        - previous_close
    ).abs()

    range_3 = (
        low
        - previous_close
    ).abs()

    true_range = pd.concat(
        [
            range_1,
            range_2,
            range_3,
        ],
        axis=1,
    ).max(
        axis=1
    )

    atr = true_range.ewm(
        alpha=1 / period,
        adjust=False,
        min_periods=period,
    ).mean()

    return atr


# =========================================================
# VOLUME RATIO
# =========================================================

def calculate_volume_ratio(
    volume: pd.Series,
    period: int = 20,
) -> pd.Series:

    period = max(
        int(period),
        1,
    )

    average_volume = volume.rolling(
        window=period,
        min_periods=period,
    ).mean()

    ratio = (
        volume
        / average_volume.replace(
            0,
            pd.NA,
        )
    )

    return pd.to_numeric(ratio, errors="coerce")


# =========================================================
# DONCHIAN CHANNEL
# =========================================================

def calculate_donchian(
    high: pd.Series,
    low: pd.Series,
    period: int = 20,
) -> tuple[pd.Series, pd.Series]:

    period = max(int(period), 1)

    don_high = (
        high.rolling(window=period, min_periods=period).max()
    )
    don_low = (
        low.rolling(window=period, min_periods=period).min()
    )

    return don_high, don_low


# =========================================================
# SUPERTREND
# =========================================================

def calculate_supertrend(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    period: int = 10,
    multiplier: float = 3.0,
) -> tuple[pd.Series, pd.Series]:

    period = max(int(period), 1)
    hl2 = (high + low) / 2.0
    atr = (high - low).rolling(period).mean()

    upper = hl2 + multiplier * atr
    lower = hl2 - multiplier * atr

    st_line = pd.Series(index=close.index, dtype=float)
    direction = pd.Series(index=close.index, dtype=float)

    for i in range(len(close)):
        if i == 0:
            st_line.iloc[i] = lower.iloc[i]
            direction.iloc[i] = 1.0
            continue

        prev_st = st_line.iloc[i - 1]
        c = close.iloc[i]
        ub = upper.iloc[i]
        lb = lower.iloc[i]

        if pd.isna(ub) or pd.isna(lb) or pd.isna(c):
            st_line.iloc[i] = prev_st
            direction.iloc[i] = direction.iloc[i - 1]
            continue

        if direction.iloc[i - 1] == 1.0:
            lb = max(lb, prev_st) if pd.notna(prev_st) else lb
            if c < lb:
                direction.iloc[i] = -1.0
                st_line.iloc[i] = ub
            else:
                direction.iloc[i] = 1.0
                st_line.iloc[i] = lb
        else:
            ub = min(ub, prev_st) if pd.notna(prev_st) else ub
            if c > ub:
                direction.iloc[i] = 1.0
                st_line.iloc[i] = lb
            else:
                direction.iloc[i] = -1.0
                st_line.iloc[i] = ub

    return st_line, direction


# =========================================================
# ADX
# =========================================================

def calculate_adx(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    period: int = 14,
) -> tuple[pd.Series, pd.Series, pd.Series]:

    period = max(int(period), 1)

    up = high.diff()
    dn = -low.diff()

    plus_dm = ((up > dn) & (up > 0)).astype(float) * up
    minus_dm = ((dn > up) & (dn > 0)).astype(float) * dn

    tr = pd.concat(
        [
            (high - low),
            (high - close.shift()).abs(),
            (low - close.shift()).abs(),
        ],
        axis=1,
    ).max(axis=1)

    atr_w = tr.ewm(
        alpha=1 / period,
        min_periods=period,
        adjust=False,
    ).mean()

    plus_di = (
        100
        * plus_dm.ewm(
            alpha=1 / period,
            min_periods=period,
            adjust=False,
        ).mean()
        / atr_w
    )
    minus_di = (
        100
        * minus_dm.ewm(
            alpha=1 / period,
            min_periods=period,
            adjust=False,
        ).mean()
        / atr_w
    )
    dx = (
        100
        * (plus_di - minus_di).abs()
        / (plus_di + minus_di).replace(0, float("nan"))
    )
    adx = dx.ewm(
        alpha=1 / period,
        min_periods=period,
        adjust=False,
    ).mean()

    return adx, plus_di, minus_di


# =========================================================
# VWAP
# =========================================================

def calculate_vwap(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    volume: pd.Series,
    period: int = 20,
) -> pd.Series:

    period = max(int(period), 1)

    tp = (high + low + close) / 3.0
    pv = tp * volume.replace(0, float("nan"))
    vwap = (
        pv.rolling(period).sum()
        / volume.rolling(period).sum()
    )

    return vwap


# =========================================================
# STOCHASTIC
# =========================================================

def calculate_stochastic(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    k_period: int = 14,
    d_period: int = 3,
) -> tuple[pd.Series, pd.Series]:

    k_period = max(int(k_period), 1)
    d_period = max(int(d_period), 1)

    ll = low.rolling(k_period).min()
    hh = high.rolling(k_period).max()
    rng = (hh - ll).replace(0, float("nan"))

    stoch_k = 100 * (close - ll) / rng
    stoch_d = stoch_k.rolling(d_period).mean()

    return stoch_k, stoch_d


# =========================================================
# ADD ALL INDICATORS
# =========================================================

def add_indicators(
    data: pd.DataFrame,
    config: dict[str, Any] | None = None,
) -> pd.DataFrame:

    cfg = dict(
        DEFAULT_CONFIG
    )

    if config:
        cfg.update(config)

    df = normalize_ohlcv(
        data
    )

    close = get_numeric_series(
        df,
        "Close",
    )

    volume = get_numeric_series(
        df,
        "Volume",
    )

    # -----------------------------------------------------
    # SMA
    # -----------------------------------------------------

    df["SMA_FAST"] = calculate_sma(
        close,
        cfg["sma_fast"],
    )

    df["SMA_SLOW"] = calculate_sma(
        close,
        cfg["sma_slow"],
    )

    # -----------------------------------------------------
    # EMA
    # -----------------------------------------------------

    df["EMA_FAST"] = calculate_ema(
        close,
        cfg["ema_fast"],
    )

    df["EMA_SLOW"] = calculate_ema(
        close,
        cfg["ema_slow"],
    )

    # -----------------------------------------------------
    # RSI
    # -----------------------------------------------------

    df["RSI"] = calculate_rsi(
        close,
        cfg["rsi_period"],
    )

    # -----------------------------------------------------
    # MACD
    # -----------------------------------------------------

    (
        df["MACD"],
        df["MACD_SIGNAL"],
        df["MACD_HIST"],
    ) = calculate_macd(
        close,
        cfg["macd_fast"],
        cfg["macd_slow"],
        cfg["macd_signal"],
    )

    # -----------------------------------------------------
    # BOLLINGER
    # -----------------------------------------------------

    (
        df["BB_MIDDLE"],
        df["BB_UPPER"],
        df["BB_LOWER"],
    ) = calculate_bollinger(
        close,
        cfg["bollinger_period"],
        cfg["bollinger_std"],
    )

    # ----------------------------------------------------
    # ATR
    # ----------------------------------------------------

    df["ATR"] = calculate_atr(
        df,
        cfg["atr_period"],
    )

    # ----------------------------------------------------
    # VOLUME RATIO
    # ----------------------------------------------------

    df["VOLUME_RATIO"] = calculate_volume_ratio(
        volume,
        cfg["volume_period"],
    )

    # ----------------------------------------------------
    # DONCHIAN
    # ----------------------------------------------------

    (
        df["DONCHIAN_HIGH"],
        df["DONCHIAN_LOW"],
    ) = calculate_donchian(
        df["High"],
        df["Low"],
        cfg["donchian_period"],
    )

    # ----------------------------------------------------
    # SUPERTREND
    # ----------------------------------------------------

    (
        df["ST_LINE"],
        df["ST_DIR"],
    ) = calculate_supertrend(
        df["High"],
        df["Low"],
        df["Close"],
        cfg["supertrend_period"],
        cfg["supertrend_mult"],
    )

    # ----------------------------------------------------
    # ADX
    # ----------------------------------------------------

    (
        df["ADX"],
        df["PLUS_DI"],
        df["MINUS_DI"],
    ) = calculate_adx(
        df["High"],
        df["Low"],
        df["Close"],
        cfg["adx_period"],
    )

    # ----------------------------------------------------
    # VWAP
    # ----------------------------------------------------

    df["VWAP"] = calculate_vwap(
        df["High"],
        df["Low"],
        df["Close"],
        df["Volume"],
        cfg["vwap_window"],
    )

    # ----------------------------------------------------
    # STOCHASTIC
    # ----------------------------------------------------

    (
        df["STOCH_K"],
        df["STOCH_D"],
    ) = calculate_stochastic(
        df["High"],
        df["Low"],
        df["Close"],
        cfg["stoch_k_period"],
        cfg["stoch_d_period"],
    )

    return df


# =========================================================
# INDICATOR VALIDATION
# =========================================================

def get_indicator_columns() -> list[str]:
    return [
        "SMA_FAST",
        "SMA_SLOW",
        "EMA_FAST",
        "EMA_SLOW",
        "RSI",
        "MACD",
        "MACD_SIGNAL",
        "MACD_HIST",
        "BB_MIDDLE",
        "BB_UPPER",
        "BB_LOWER",
        "ATR",
        "VOLUME_RATIO",
        "DONCHIAN_HIGH",
        "DONCHIAN_LOW",
        "ST_LINE",
        "ST_DIR",
        "ADX",
        "PLUS_DI",
        "MINUS_DI",
        "VWAP",
        "STOCH_K",
        "STOCH_D",
    ]


def validate_indicator_frame(
    data: pd.DataFrame,
) -> dict[str, Any]:

    expected = get_indicator_columns()

    found = [
        column
        for column in expected
        if column in data.columns
    ]

    missing = [
        column
        for column in expected
        if column not in data.columns
    ]

    return {
        "valid": len(missing) == 0,
        "expected": expected,
        "found": found,
        "missing": missing,
    }


# =========================================================
# SCORE LATEST ROW
# =========================================================

def score_latest_row(
    row: pd.Series,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:

    cfg = dict(
        DEFAULT_CONFIG
    )

    if config:
        cfg.update(config)

    score = 0

    reasons: list[str] = []

    # -----------------------------------------------------
    # VALUES
    # -----------------------------------------------------

    close = safe_float(
        row.get("Close")
    )

    sma_fast = safe_float(
        row.get("SMA_FAST")
    )

    sma_slow = safe_float(
        row.get("SMA_SLOW")
    )

    ema_fast = safe_float(
        row.get("EMA_FAST")
    )

    ema_slow = safe_float(
        row.get("EMA_SLOW")
    )

    rsi = safe_float(
        row.get("RSI")
    )

    macd = safe_float(
        row.get("MACD")
    )

    macd_signal = safe_float(
        row.get("MACD_SIGNAL")
    )

    bb_middle = safe_float(
        row.get("BB_MIDDLE")
    )

    volume_ratio = safe_float(
        row.get("VOLUME_RATIO")
    )

    # -----------------------------------------------------
    # SMA TREND
    # -----------------------------------------------------

    if (
        sma_fast is not None
        and sma_slow is not None
    ):

        if sma_fast > sma_slow:

            score += 2

            reasons.append(
                "SMA trend pozitif"
            )

        elif sma_fast < sma_slow:

            score -= 2

            reasons.append(
                "SMA trend negatif"
            )

    # -----------------------------------------------------
    # EMA TREND
    # -----------------------------------------------------

    if (
        ema_fast is not None
        and ema_slow is not None
    ):

        if ema_fast > ema_slow:

            score += 2

            reasons.append(
                "EMA trend pozitif"
            )

        elif ema_fast < ema_slow:

            score -= 2

            reasons.append(
                "EMA trend negatif"
            )

    # -----------------------------------------------------
    # RSI
    # -----------------------------------------------------

    if rsi is not None:

        if rsi <= cfg[
            "rsi_oversold"
        ]:

            score += 1

            reasons.append(
                "RSI aşırı satım bölgesinde"
            )

        elif rsi >= cfg[
            "rsi_overbought"
        ]:

            score -= 1

            reasons.append(
                "RSI aşırı alım bölgesinde"
            )

        elif rsi >= 50:

            score += 1

            reasons.append(
                "RSI 50 üzerinde"
            )

        else:

            score -= 1

            reasons.append(
                "RSI 50 altında"
            )

    # -----------------------------------------------------
    # MACD
    # -----------------------------------------------------

    if (
        macd is not None
        and macd_signal is not None
    ):

        if macd > macd_signal:

            score += 2

            reasons.append(
                "MACD pozitif"
            )

        elif macd < macd_signal:

            score -= 2

            reasons.append(
                "MACD negatif"
            )

    # -----------------------------------------------------
    # BOLLINGER
    # -----------------------------------------------------

    if (
        close is not None
        and bb_middle is not None
    ):

        if close > bb_middle:

            score += 1

            reasons.append(
                "Fiyat Bollinger orta bandının üzerinde"
            )

        elif close < bb_middle:

            score -= 1

            reasons.append(
                "Fiyat Bollinger orta bandının altında"
            )

    # ----------------------------------------------------
    # VOLUME
    # ----------------------------------------------------

    if volume_ratio is not None:

        if volume_ratio >= cfg[
            "minimum_volume_ratio"
        ]:

            reasons.append(
                "Hacim ortalamanın üzerinde/eşit"
            )

        else:

            reasons.append(
                "Hacim ortalamanın altında"
            )

    # ----------------------------------------------------
    # DONCHIAN
    # ----------------------------------------------------

    donchian_high = safe_float(
        row.get("DONCHIAN_HIGH")
    )
    donchian_low = safe_float(
        row.get("DONCHIAN_LOW")
    )

    if (
        donchian_high is not None
        and donchian_low is not None
        and close is not None
    ):

        if close > donchian_high:

            score += 1
            reasons.append(
                "Donchian kırılımı"
            )

        elif close < donchian_low:

            score -= 1
            reasons.append(
                "Donchian alt kırılım"
            )

    # ----------------------------------------------------
    # SUPERTREND
    # ----------------------------------------------------

    st_dir = safe_float(row.get("ST_DIR"))

    if st_dir is not None:

        if st_dir > 0:

            score += 1
            reasons.append(
                "SuperTrend LONG"
            )

        else:

            score -= 1
            reasons.append(
                "SuperTrend SHORT"
            )

    # ----------------------------------------------------
    # ADX
    # ----------------------------------------------------

    adx_val = safe_float(row.get("ADX"))
    plus_di = safe_float(row.get("PLUS_DI"))
    minus_di = safe_float(row.get("MINUS_DI"))

    if (
        adx_val is not None
        and plus_di is not None
        and minus_di is not None
    ):

        if adx_val >= cfg["adx_threshold"]:

            if plus_di > minus_di:

                score += 2
                reasons.append(
                    "ADX güçlü LONG"
                )

            else:

                score -= 2
                reasons.append(
                    "ADX güçlü SHORT"
                )

        else:

            reasons.append("ADX trendsiz")

    # ----------------------------------------------------
    # VWAP
    # ----------------------------------------------------

    vwap_val = safe_float(row.get("VWAP"))

    if (
        vwap_val is not None
        and close is not None
    ):

        if close > vwap_val:

            score += 1
            reasons.append(
                "Fiyat VWAP üstünde"
            )

        elif close < vwap_val:

            score -= 1
            reasons.append(
                "Fiyat VWAP altında"
            )

    # ----------------------------------------------------
    # STOCHASTIC
    # ----------------------------------------------------

    stoch_k = safe_float(row.get("STOCH_K"))
    stoch_d = safe_float(row.get("STOCH_D"))

    if (
        stoch_k is not None
        and stoch_d is not None
    ):

        if stoch_k < 20 and stoch_k > stoch_d:

            score += 1
            reasons.append(
                "Stokastik oversold bounce"
            )

        elif stoch_k > 80 and stoch_k < stoch_d:

            score -= 1
            reasons.append(
                "Stokastik overbought reversal"
            )

    # ----------------------------------------------------
    # SIGNAL
    # ----------------------------------------------------

    if score >= cfg[
        "buy_threshold"
    ]:

        signal = "BUY"

    elif score <= cfg[
        "sell_threshold"
    ]:

        signal = "SELL"

    else:

        signal = "WAIT"

    return {
        "signal": signal,
        "score": score,
        "reason": " | ".join(
            reasons
        ),
    }


# =========================================================
# RISK LEVELS
# =========================================================

def calculate_risk_levels(
    signal: str,
    entry_price: float | None,
    atr: float | None,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:

    cfg = dict(
        DEFAULT_CONFIG
    )

    if config:
        cfg.update(config)

    signal = str(
        signal
    ).upper()

    if (
        entry_price is None
        or entry_price <= 0
    ):

        return {
            "stop_loss": None,
            "take_profit": None,
        }

    if (
        atr is None
        or atr <= 0
    ):

        return {
            "stop_loss": None,
            "take_profit": None,
        }

    stop_multiple = safe_float(
        cfg.get(
            "stop_atr_multiple",
            2.0,
        ),
        2.0,
    )

    target_multiple = safe_float(
        cfg.get(
            "target_atr_multiple",
            3.0,
        ),
        3.0,
    )

    if stop_multiple is None:
        stop_multiple = 2.0

    if target_multiple is None:
        target_multiple = 3.0

    if signal == "BUY":

        stop_loss = (
            entry_price
            - (
                atr
                * stop_multiple
            )
        )

        take_profit = (
            entry_price
            + (
                atr
                * target_multiple
            )
        )

    elif signal == "SELL":

        stop_loss = (
            entry_price
            + (
                atr
                * stop_multiple
            )
        )

        take_profit = (
            entry_price
            - (
                atr
                * target_multiple
            )
        )

    else:

        stop_loss = None
        take_profit = None

    return {
        "stop_loss": stop_loss,
        "take_profit": take_profit,
    }


# =========================================================
# GENERATE SIGNAL
# =========================================================

def generate_signal(
    data: pd.DataFrame | pd.Series,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:

    """
    Signal üretir.

    Kabul edilen girişler:

        1. DataFrame
           Son satır kullanılır.

        2. Series
           Tek bar doğrudan kullanılır.

    Böylece Backtest Engine her barı tek tek
    Signal Engine'e gönderebilir.
    """

    # -----------------------------------------------------
    # SERIES
    # -----------------------------------------------------

    if isinstance(
        data,
        pd.Series,
    ):

        row = data

    # -----------------------------------------------------
    # DATAFRAME
    # -----------------------------------------------------

    elif isinstance(
        data,
        pd.DataFrame,
    ):

        if data.empty:

            return {
                "signal": "WAIT",
                "score": 0,
                "reason": "Boş DataFrame",
                "stop_loss": None,
                "take_profit": None,
                "entry_price": None,
                "atr": None,
            }

        row = data.iloc[-1]

    # -----------------------------------------------------
    # INVALID
    # -----------------------------------------------------

    else:

        return {
            "signal": "WAIT",
            "score": 0,
            "reason": (
                "Data pandas DataFrame "
                "veya pandas Series olmalıdır."
            ),
            "stop_loss": None,
            "take_profit": None,
            "entry_price": None,
            "atr": None,
        }

    # -----------------------------------------------------
    # SCORE
    # -----------------------------------------------------

    result = score_latest_row(
        row,
        config,
    )

    signal = result[
        "signal"
    ]

    score = result[
        "score"
    ]

    reason = result[
        "reason"
    ]

    # -----------------------------------------------------
    # PRICE
    # -----------------------------------------------------

    entry_price = safe_float(
        row.get("Close")
    )

    atr = safe_float(
        row.get("ATR")
    )

    # -----------------------------------------------------
    # RISK
    # -----------------------------------------------------

    risk = calculate_risk_levels(
        signal=signal,
        entry_price=entry_price,
        atr=atr,
        config=config,
    )

    return {
        "signal": signal,
        "score": score,
        "reason": reason,
        "entry_price": entry_price,
        "atr": atr,
        "stop_loss": risk[
            "stop_loss"
        ],
        "take_profit": risk[
            "take_profit"
        ],
    }


# =========================================================
# SIGNAL HISTORY
# =========================================================

def generate_signal_history(
    data: pd.DataFrame,
    config: dict[str, Any] | None = None,
) -> pd.DataFrame:

    if not validate_ohlcv(
        data
    ):

        raise ValueError(
            "Signal history için geçerli OHLCV DataFrame gereklidir."
        )

    df = add_indicators(
        data,
        config,
    )

    signals = []
    scores = []
    reasons = []
    entries = []
    stops = []
    targets = []
    atr_values = []

    for _, row in df.iterrows():

        result = generate_signal(
            row,
            config,
        )

        signals.append(
            result["signal"]
        )

        scores.append(
            result["score"]
        )

        reasons.append(
            result["reason"]
        )

        entries.append(
            result["entry_price"]
        )

        stops.append(
            result["stop_loss"]
        )

        targets.append(
            result["take_profit"]
        )

        atr_values.append(
            result["atr"]
        )

    df["SIGNAL"] = signals
    df["SIGNAL_SCORE"] = scores
    df["SIGNAL_REASON"] = reasons
    df["SIGNAL_ENTRY"] = entries
    df["SIGNAL_STOP"] = stops
    df["SIGNAL_TARGET"] = targets
    df["SIGNAL_ATR"] = atr_values

    return df


# =========================================================
# SIGNAL RECORD
# =========================================================

def build_signal_record(
    row: pd.Series,
    symbol: str = "UNKNOWN",
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:

    result = generate_signal(
        row,
        config,
    )

    return {
        "symbol": symbol,

        "timestamp": (
            str(row.name)
            if row.name is not None
            else None
        ),

        "signal": result[
            "signal"
        ],

        "score": result[
            "score"
        ],

        "reason": result[
            "reason"
        ],

        "entry_price": result[
            "entry_price"
        ],

        "atr": result[
            "atr"
        ],

        "stop_loss": result[
            "stop_loss"
        ],

        "take_profit": result[
            "take_profit"
        ],
    }


# =========================================================
# TEST
# =========================================================

def main():

    print()
    print("=" * 70)
    print("MARKETHQ SIGNAL ENGINE V3")
    print("=" * 70)
    print()

    try:

        from agents.market_data_agent import (
            get_signal_data,
        )

    except Exception as exc:

        print(
            f"❌ Market data import hatası: {exc}"
        )

        return

    symbol = "THYAO.IS"

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

    if data is None or data.empty:

        print(
            "❌ Veri bulunamadı."
        )

        return

    print(
        f"📊 Bar sayısı: {len(data)}"
    )

    try:

        prepared = add_indicators(
            data,
            DEFAULT_CONFIG,
        )

        diagnostic = validate_indicator_frame(
            prepared
        )

        print()
        print("=" * 70)
        print("INDICATOR DIAGNOSTIC")
        print("=" * 70)

        print(
            f"Indicator contract: "
            f"{'OK' if diagnostic['valid'] else 'ERROR'}"
        )

        print()
        print("Beklenen kolonlar:")

        for column in diagnostic[
            "expected"
        ]:

            if column in prepared.columns:

                print(
                    f"  ✅ {column}"
                )

            else:

                print(
                    f"  ❌ {column}"
                )

        if diagnostic[
            "missing"
        ]:

            print()
            print(
                "Eksik kolonlar:"
            )

            for column in diagnostic[
                "missing"
            ]:

                print(
                    f"  ❌ {column}"
                )

        latest = prepared.iloc[-1]

        result = generate_signal(
            latest,
            DEFAULT_CONFIG,
        )

    except Exception as exc:

        print(
            f"❌ Signal Engine hatası: {exc}"
        )

        return

    print()
    print("=" * 70)
    print("SON SİNYAL")
    print("=" * 70)

    print(
        f"Sembol       : {symbol}"
    )

    print(
        f"Tarih        : {latest.name}"
    )

    print(
        f"Fiyat        : "
        f"{result['entry_price']}"
    )

    print(
        f"Signal       : "
        f"{result['signal']}"
    )

    print(
        f"Score        : "
        f"{result['score']}"
    )

    print(
        f"ATR          : "
        f"{result['atr']}"
    )

    print(
        f"Stop Loss    : "
        f"{result['stop_loss']}"
    )

    print(
        f"Take Profit  : "
        f"{result['take_profit']}"
    )

    print()
    print(
        f"Sebep        : "
        f"{result['reason']}"
    )

    print()
    print(
        "Signal Engine testi tamamlandı."
    )

    print()


if __name__ == "__main__":
    main()
