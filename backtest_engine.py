# -*- coding: utf-8 -*-
"""
MarketHQ Backtest Engine V3
===========================

Amaç:
    Signal Engine tarafından üretilen araştırma sinyallerini geçmiş OHLCV
    verisi üzerinde tutarlı ve denetlenebilir biçimde test etmek.

Önemli:
    - Yalnızca araştırma / backtest / paper-research içindir.
    - Gerçek emir göndermez.
    - Signal Engine'in hesapladığı indikatörleri yeniden kullanır.
    - Eksik indikatörleri sessizce WAIT'e çevirmek yerine hata kaydı üretir.
    - Indicator kolon adlarında büyük/küçük harf uyumsuzluğunu tolere eder.
    - Aynı OHLCV verisi üzerinde signal_config ile backtest_config ayrıdır.
"""

from __future__ import annotations

import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from signal_engine import DEFAULT_CONFIG, add_indicators, generate_signal
from agents.market_data_agent import get_signal_data


PROJECT_ROOT = Path(__file__).resolve().parent
BACKTEST_OUTPUT_DIR = PROJECT_ROOT / "backtest_results"


DEFAULT_BACKTEST_CONFIG: dict[str, Any] = {
    "initial_capital": 100000.0,
    "position_size_percent": 10.0,
    "commission_percent": 0.10,
    "slippage_percent": 0.05,
    "allow_short": True,
    "one_position_at_a_time": True,
    "use_stop_loss": True,
    "use_take_profit": True,
    "stop_atr_multiplier": 2.0,
    "target_atr_multiplier": 3.0,
    "exit_on_opposite_signal": True,
    "max_holding_bars": 30,
    "close_at_end": True,
}


def safe_float(value: Any, default: float | None = None) -> float | None:
    try:
        if value is None:
            return default
        result = float(value)
        if not math.isfinite(result):
            return default
        return result
    except (TypeError, ValueError):
        return default


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def merge_config(
    base: dict[str, Any],
    override: dict[str, Any] | None,
) -> dict[str, Any]:
    result = dict(base)
    if override:
        result.update(override)
    return result


def validate_ohlcv(data: pd.DataFrame) -> bool:
    if not isinstance(data, pd.DataFrame) or data.empty:
        return False

    return all(
        column in data.columns
        for column in ("Open", "High", "Low", "Close", "Volume")
    )


def prepare_data(data: pd.DataFrame) -> pd.DataFrame:
    if not validate_ohlcv(data):
        raise ValueError(
            "Geçerli OHLCV DataFrame bulunamadı. "
            "Gerekli kolonlar: Open, High, Low, Close, Volume."
        )

    df = data.copy()

    for column in ("Open", "High", "Low", "Close", "Volume"):
        df[column] = pd.to_numeric(df[column], errors="coerce")

    df = df.dropna(subset=("Open", "High", "Low", "Close"))
    df = df.sort_index()

    df = df[
        (df["Open"] > 0)
        & (df["High"] > 0)
        & (df["Low"] > 0)
        & (df["Close"] > 0)
    ]

    if df.empty:
        raise ValueError("OHLCV temizleme sonrası veri kalmadı.")

    return df


def _column_lookup(data: pd.DataFrame) -> dict[str, str]:
    """
    Kolonları case-insensitive eşleştirir.

    Örnek:
        SMA_FAST -> sma_fast / SMA_fast / SMA_FAST
    """
    return {str(column).upper(): str(column) for column in data.columns}


def _find_column(data: pd.DataFrame, name: str) -> str | None:
    lookup = _column_lookup(data)
    return lookup.get(name.upper())


def get_indicator_schema_status(data: pd.DataFrame) -> dict[str, Any]:
    """
    Backtest'in ihtiyaç duyduğu indikatör kolonlarının gerçek durumunu raporlar.
    """
    required = [
        "SMA_FAST",
        "SMA_SLOW",
        "EMA_FAST",
        "EMA_SLOW",
        "RSI",
        "MACD",
        "MACD_SIGNAL",
        "MACD_HIST",
        "BB_UPPER",
        "BB_MIDDLE",
        "BB_LOWER",
        "ATR",
        "VOLUME_RATIO",
    ]

    lookup = _column_lookup(data)

    found = []
    missing = []

    for name in required:
        if name.upper() in lookup:
            found.append(lookup[name.upper()])
        else:
            missing.append(name)

    return {
        "required": required,
        "found": found,
        "missing": missing,
        "complete": len(missing) == 0,
    }


def validate_indicator_frame(data: pd.DataFrame) -> None:
    status = get_indicator_schema_status(data)

    if not status["complete"]:
        raise ValueError(
            "Signal Engine indicator şeması eksik. "
            f"Eksik: {', '.join(status['missing'])}"
        )


def prepare_signal_data(
    data: pd.DataFrame,
    signal_config: dict[str, Any] | None = None,
) -> pd.DataFrame:
    df = prepare_data(data)

    config = merge_config(DEFAULT_CONFIG, signal_config)

    df = add_indicators(df, config)

    # Signal Engine'in kendi kolonlarını case-insensitive olarak doğrula.
    status = get_indicator_schema_status(df)

    # Bazı Signal Engine sürümlerinde indikatör isimleri farklı biçimde
    # üretilebilir. Case farkını standartlaştırıyoruz.
    aliases = {
        "SMA_FAST": "SMA_FAST",
        "SMA_SLOW": "SMA_SLOW",
        "EMA_FAST": "EMA_FAST",
        "EMA_SLOW": "EMA_SLOW",
        "RSI": "RSI",
        "MACD": "MACD",
        "MACD_SIGNAL": "MACD_SIGNAL",
        "MACD_HIST": "MACD_HIST",
        "BB_UPPER": "BB_UPPER",
        "BB_MIDDLE": "BB_MIDDLE",
        "BB_LOWER": "BB_LOWER",
        "ATR": "ATR",
        "VOLUME_RATIO": "VOLUME_RATIO",
    }

    for canonical, target in aliases.items():
        actual = _find_column(df, canonical)
        if actual and target not in df.columns:
            df[target] = df[actual]

    # RSI/MACD/ATR gibi kolonlar mevcut olup diğerleri gerçekten yoksa,
    # sessizce devam etmek yerine bunu üst katmana görünür yapıyoruz.
    status = get_indicator_schema_status(df)

    if not status["complete"]:
        raise ValueError(
            "add_indicators() sonrası beklenen indicator kolonları oluşmadı. "
            f"Eksik: {', '.join(status['missing'])}. "
            f"Mevcut kolonlar: {list(df.columns)}"
        )

    return df


def get_historical_signal(
    row: pd.Series,
    signal_config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    config = merge_config(DEFAULT_CONFIG, signal_config)

    try:
        result = generate_signal(row, config)

        if isinstance(result, dict):
            normalized = dict(result)
            normalized["signal"] = str(
                normalized.get("signal", "WAIT")
            ).upper()
            return normalized

        return {
            "signal": str(result).upper(),
            "score": None,
            "reason": "",
        }

    except Exception as exc:
        # Eski sürümde hata sessizce WAIT'e çevriliyordu.
        # Bu, optimizer/WFO tarafında "0 trade" nedenini gizleyebiliyordu.
        return {
            "signal": "ERROR",
            "score": None,
            "reason": f"Signal Engine hatası: {exc}",
            "error": str(exc),
        }


def apply_entry_slippage(
    price: float,
    side: str,
    slippage_percent: float,
) -> float:
    slippage = slippage_percent / 100.0

    if side == "LONG":
        return price * (1.0 + slippage)

    return price * (1.0 - slippage)


def apply_exit_slippage(
    price: float,
    side: str,
    slippage_percent: float,
) -> float:
    slippage = slippage_percent / 100.0

    if side == "LONG":
        return price * (1.0 - slippage)

    return price * (1.0 + slippage)


def calculate_commission(
    notional: float,
    commission_percent: float,
) -> float:
    return abs(notional) * commission_percent / 100.0


def calculate_position_size(
    equity: float,
    price: float,
    position_size_percent: float,
) -> float:
    if equity <= 0 or price <= 0:
        return 0.0

    capital_for_trade = equity * position_size_percent / 100.0
    return capital_for_trade / price


def check_stop_target(
    position: dict[str, Any],
    row: pd.Series,
    config: dict[str, Any],
) -> tuple[float | None, str | None]:
    side = position["side"]

    stop_price = safe_float(position.get("stop_price"))
    target_price = safe_float(position.get("target_price"))

    high = safe_float(row.get("High"))
    low = safe_float(row.get("Low"))

    if high is None or low is None:
        return None, None

    if side == "LONG":
        stop_hit = (
            bool(config["use_stop_loss"])
            and stop_price is not None
            and low <= stop_price
        )
        target_hit = (
            bool(config["use_take_profit"])
            and target_price is not None
            and high >= target_price
        )

        if stop_hit:
            return stop_price, "STOP_LOSS"

        if target_hit:
            return target_price, "TAKE_PROFIT"

    elif side == "SHORT":
        stop_hit = (
            bool(config["use_stop_loss"])
            and stop_price is not None
            and high >= stop_price
        )
        target_hit = (
            bool(config["use_take_profit"])
            and target_price is not None
            and low <= target_price
        )

        if stop_hit:
            return stop_price, "STOP_LOSS"

        if target_hit:
            return target_price, "TAKE_PROFIT"

    return None, None


def calculate_trade_pnl(
    side: str,
    entry_price: float,
    exit_price: float,
    quantity: float,
) -> float:
    if side == "LONG":
        return (exit_price - entry_price) * quantity

    if side == "SHORT":
        return (entry_price - exit_price) * quantity

    return 0.0


def open_position(
    symbol: str,
    timestamp: Any,
    side: str,
    price: float,
    equity: float,
    config: dict[str, Any],
    atr: float | None,
    signal_result: dict[str, Any],
) -> dict[str, Any] | None:
    if price <= 0:
        return None

    entry_price = apply_entry_slippage(
        price,
        side,
        float(config["slippage_percent"]),
    )

    quantity = calculate_position_size(
        equity,
        entry_price,
        float(config["position_size_percent"]),
    )

    if quantity <= 0:
        return None

    notional = entry_price * quantity

    entry_commission = calculate_commission(
        notional,
        float(config["commission_percent"]),
    )

    stop_price = None
    target_price = None

    if atr is not None and atr > 0:
        if side == "LONG":
            if config["use_stop_loss"]:
                stop_price = (
                    entry_price
                    - atr * float(config["stop_atr_multiplier"])
                )

            if config["use_take_profit"]:
                target_price = (
                    entry_price
                    + atr * float(config["target_atr_multiplier"])
                )

        elif side == "SHORT":
            if config["use_stop_loss"]:
                stop_price = (
                    entry_price
                    + atr * float(config["stop_atr_multiplier"])
                )

            if config["use_take_profit"]:
                target_price = (
                    entry_price
                    - atr * float(config["target_atr_multiplier"])
                )

    return {
        "symbol": symbol,
        "side": side,
        "entry_time": timestamp,
        "entry_price": entry_price,
        "quantity": quantity,
        "notional": notional,
        "entry_commission": entry_commission,
        "stop_price": stop_price,
        "target_price": target_price,
        "entry_signal": signal_result.get("signal", ""),
        "entry_score": signal_result.get("score"),
        "entry_reason": signal_result.get("reason", ""),
        "bars_held": 0,
    }


def close_position(
    position: dict[str, Any],
    timestamp: Any,
    raw_exit_price: float,
    exit_reason: str,
    config: dict[str, Any],
) -> dict[str, Any]:
    side = position["side"]

    exit_price = apply_exit_slippage(
        raw_exit_price,
        side,
        float(config["slippage_percent"]),
    )

    quantity = float(position["quantity"])

    gross_pnl = calculate_trade_pnl(
        side,
        float(position["entry_price"]),
        exit_price,
        quantity,
    )

    exit_notional = exit_price * quantity

    exit_commission = calculate_commission(
        exit_notional,
        float(config["commission_percent"]),
    )

    total_commission = (
        float(position["entry_commission"])
        + exit_commission
    )

    net_pnl = gross_pnl - total_commission

    entry_notional = float(position["notional"])

    return_percent = (
        net_pnl / entry_notional * 100.0
        if entry_notional > 0
        else 0.0
    )

    return {
        "symbol": position["symbol"],
        "side": side,
        "entry_time": position["entry_time"],
        "exit_time": timestamp,
        "entry_price": position["entry_price"],
        "exit_price": exit_price,
        "quantity": quantity,
        "notional": entry_notional,
        "stop_price": position.get("stop_price"),
        "target_price": position.get("target_price"),
        "gross_pnl": gross_pnl,
        "commission": total_commission,
        "net_pnl": net_pnl,
        "return_percent": return_percent,
        "bars_held": int(position["bars_held"]),
        "exit_reason": exit_reason,
        "entry_signal": position.get("entry_signal", ""),
        "entry_score": position.get("entry_score"),
        "entry_reason": position.get("entry_reason", ""),
    }


def calculate_max_drawdown(equity_curve: pd.Series) -> float:
    if equity_curve.empty:
        return 0.0

    rolling_max = equity_curve.cummax()
    drawdown = equity_curve / rolling_max - 1.0

    return abs(float(drawdown.min()) * 100.0)


def calculate_profit_factor(trades: list[dict[str, Any]]) -> float:
    gross_profit = 0.0
    gross_loss = 0.0

    for trade in trades:
        pnl = safe_float(trade.get("net_pnl"), 0.0) or 0.0

        if pnl > 0:
            gross_profit += pnl
        elif pnl < 0:
            gross_loss += abs(pnl)

    if gross_loss == 0:
        return float("inf") if gross_profit > 0 else 0.0

    return gross_profit / gross_loss


def calculate_metrics(
    trades: list[dict[str, Any]],
    equity_curve: pd.DataFrame,
    initial_capital: float,
    final_equity: float,
) -> dict[str, Any]:
    total_trades = len(trades)

    winning_trades = [
        trade
        for trade in trades
        if (safe_float(trade.get("net_pnl"), 0.0) or 0.0) > 0
    ]

    losing_trades = [
        trade
        for trade in trades
        if (safe_float(trade.get("net_pnl"), 0.0) or 0.0) < 0
    ]

    long_trades = [
        trade for trade in trades if trade.get("side") == "LONG"
    ]

    short_trades = [
        trade for trade in trades if trade.get("side") == "SHORT"
    ]

    total_pnl = sum(
        safe_float(trade.get("net_pnl"), 0.0) or 0.0
        for trade in trades
    )

    winning_pnl = sum(
        safe_float(trade.get("net_pnl"), 0.0) or 0.0
        for trade in winning_trades
    )

    losing_pnl = sum(
        safe_float(trade.get("net_pnl"), 0.0) or 0.0
        for trade in losing_trades
    )

    win_rate = (
        len(winning_trades) / total_trades * 100.0
        if total_trades
        else 0.0
    )

    average_win = (
        winning_pnl / len(winning_trades)
        if winning_trades
        else 0.0
    )

    average_loss = (
        losing_pnl / len(losing_trades)
        if losing_trades
        else 0.0
    )

    average_trade = (
        total_pnl / total_trades
        if total_trades
        else 0.0
    )

    total_return = (
        (final_equity / initial_capital - 1.0) * 100.0
        if initial_capital > 0
        else 0.0
    )

    max_drawdown = (
        calculate_max_drawdown(equity_curve["equity"])
        if not equity_curve.empty
        else 0.0
    )

    def side_metrics(
        side_trades: list[dict[str, Any]],
    ) -> dict[str, Any]:
        side_wins = [
            t for t in side_trades
            if (safe_float(t.get("net_pnl"), 0.0) or 0.0) > 0
        ]

        side_losses = [
            t for t in side_trades
            if (safe_float(t.get("net_pnl"), 0.0) or 0.0) < 0
        ]

        side_pnl = sum(
            safe_float(t.get("net_pnl"), 0.0) or 0.0
            for t in side_trades
        )

        return {
            "trades": len(side_trades),
            "wins": len(side_wins),
            "losses": len(side_losses),
            "win_rate_percent": (
                len(side_wins) / len(side_trades) * 100.0
                if side_trades
                else 0.0
            ),
            "net_pnl": side_pnl,
        }

    return {
        "initial_capital": initial_capital,
        "final_equity": final_equity,
        "net_pnl": total_pnl,
        "total_return_percent": total_return,
        "total_trades": total_trades,
        "winning_trades": len(winning_trades),
        "losing_trades": len(losing_trades),
        "win_rate_percent": win_rate,
        "profit_factor": calculate_profit_factor(trades),
        "average_trade_pnl": average_trade,
        "average_win": average_win,
        "average_loss": average_loss,
        "max_drawdown_percent": max_drawdown,
        "average_holding_bars": (
            sum(int(t.get("bars_held", 0)) for t in trades)
            / total_trades
            if total_trades
            else 0.0
        ),
        "stop_loss_exits": sum(
            1 for t in trades if t.get("exit_reason") == "STOP_LOSS"
        ),
        "take_profit_exits": sum(
            1 for t in trades if t.get("exit_reason") == "TAKE_PROFIT"
        ),
        "opposite_signal_exits": sum(
            1
            for t in trades
            if t.get("exit_reason") == "OPPOSITE_SIGNAL"
        ),
        "max_holding_exits": sum(
            1
            for t in trades
            if t.get("exit_reason") == "MAX_HOLDING"
        ),
        "end_of_data_exits": sum(
            1
            for t in trades
            if t.get("exit_reason") == "END_OF_DATA"
        ),
        "long": side_metrics(long_trades),
        "short": side_metrics(short_trades),
    }


def run_backtest(
    data: pd.DataFrame,
    symbol: str = "UNKNOWN",
    signal_config: dict[str, Any] | None = None,
    backtest_config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    config = merge_config(DEFAULT_BACKTEST_CONFIG, backtest_config)

    df = prepare_signal_data(data, signal_config)

    initial_capital = float(config["initial_capital"])
    equity = initial_capital

    position: dict[str, Any] | None = None
    trades: list[dict[str, Any]] = []
    equity_records: list[dict[str, Any]] = []

    signal_counts = {
        "BUY": 0,
        "SELL": 0,
        "WAIT": 0,
        "ERROR": 0,
        "OTHER": 0,
    }

    signal_errors: list[dict[str, Any]] = []

    for index, row in df.iterrows():
        timestamp = index

        close_price = safe_float(row.get("Close"))
        if close_price is None or close_price <= 0:
            continue

        atr = safe_float(row.get("ATR"))

        signal_result = get_historical_signal(
            row,
            signal_config,
        )

        signal = str(
            signal_result.get("signal", "WAIT")
        ).upper()

        if signal in signal_counts:
            signal_counts[signal] += 1
        else:
            signal_counts["OTHER"] += 1

        if signal == "ERROR":
            if len(signal_errors) < 20:
                signal_errors.append(
                    {
                        "timestamp": str(timestamp),
                        "reason": signal_result.get("reason", ""),
                    }
                )

        if position is not None:
            position["bars_held"] += 1

            exit_price, exit_reason = check_stop_target(
                position,
                row,
                config,
            )

            if exit_price is not None:
                trade = close_position(
                    position,
                    timestamp,
                    exit_price,
                    exit_reason or "EXIT",
                    config,
                )

                equity += trade["net_pnl"]
                trades.append(trade)
                position = None

            elif config["exit_on_opposite_signal"]:
                opposite = (
                    position["side"] == "LONG"
                    and signal == "SELL"
                ) or (
                    position["side"] == "SHORT"
                    and signal == "BUY"
                )

                if opposite:
                    trade = close_position(
                        position,
                        timestamp,
                        close_price,
                        "OPPOSITE_SIGNAL",
                        config,
                    )

                    equity += trade["net_pnl"]
                    trades.append(trade)
                    position = None

            if (
                position is not None
                and int(config["max_holding_bars"]) > 0
                and position["bars_held"]
                >= int(config["max_holding_bars"])
            ):
                trade = close_position(
                    position,
                    timestamp,
                    close_price,
                    "MAX_HOLDING",
                    config,
                )

                equity += trade["net_pnl"]
                trades.append(trade)
                position = None

        if position is None:
            if signal == "BUY":
                position = open_position(
                    symbol=symbol,
                    timestamp=timestamp,
                    side="LONG",
                    price=close_price,
                    equity=equity,
                    config=config,
                    atr=atr,
                    signal_result=signal_result,
                )

            elif signal == "SELL" and config["allow_short"]:
                position = open_position(
                    symbol=symbol,
                    timestamp=timestamp,
                    side="SHORT",
                    price=close_price,
                    equity=equity,
                    config=config,
                    atr=atr,
                    signal_result=signal_result,
                )

        unrealized_pnl = 0.0

        if position is not None:
            unrealized_pnl = calculate_trade_pnl(
                position["side"],
                float(position["entry_price"]),
                close_price,
                float(position["quantity"]),
            )

        equity_records.append(
            {
                "timestamp": timestamp,
                "equity": equity,
                "cash_equity": equity,
                "unrealized_pnl": unrealized_pnl,
                "total_equity": equity + unrealized_pnl,
            }
        )

    if (
        position is not None
        and config["close_at_end"]
        and not df.empty
    ):
        last_timestamp = df.index[-1]
        last_close = safe_float(df.iloc[-1]["Close"])

        if last_close is not None and last_close > 0:
            trade = close_position(
                position,
                last_timestamp,
                last_close,
                "END_OF_DATA",
                config,
            )

            equity += trade["net_pnl"]
            trades.append(trade)
            position = None

            if equity_records:
                equity_records[-1]["equity"] = equity
                equity_records[-1]["cash_equity"] = equity
                equity_records[-1]["unrealized_pnl"] = 0.0
                equity_records[-1]["total_equity"] = equity

    equity_curve = pd.DataFrame(equity_records)

    if not equity_curve.empty:
        equity_curve = (
            equity_curve
            .drop_duplicates(
                subset=["timestamp"],
                keep="last",
            )
            .set_index("timestamp")
        )

    metrics = calculate_metrics(
        trades=trades,
        equity_curve=equity_curve,
        initial_capital=initial_capital,
        final_equity=equity,
    )

    return {
        "symbol": symbol,
        "bars": len(df),
        "start_date": str(df.index[0]) if not df.empty else None,
        "end_date": str(df.index[-1]) if not df.empty else None,
        "trades": trades,
        "equity_curve": equity_curve,
        "metrics": metrics,
        "config": config,
        "signal_config": merge_config(
            DEFAULT_CONFIG,
            signal_config,
        ),
        "signal_counts": signal_counts,
        "signal_errors": signal_errors,
        "indicator_schema": get_indicator_schema_status(df),
        "generated_at": utc_timestamp(),
        "research_only": True,
        "execution_enabled": False,
    }


def run_batch_backtest(
    datasets: dict[str, pd.DataFrame],
    signal_config: dict[str, Any] | None = None,
    backtest_config: dict[str, Any] | None = None,
) -> dict[str, dict[str, Any]]:
    results: dict[str, dict[str, Any]] = {}

    for symbol, data in datasets.items():
        try:
            results[symbol] = run_backtest(
                data=data,
                symbol=symbol,
                signal_config=signal_config,
                backtest_config=backtest_config,
            )
        except Exception as exc:
            results[symbol] = {
                "symbol": symbol,
                "error": str(exc),
                "trades": [],
                "equity_curve": pd.DataFrame(),
                "metrics": {},
                "research_only": True,
                "execution_enabled": False,
            }

    return results


def build_summary(
    results: dict[str, dict[str, Any]],
) -> pd.DataFrame:
    rows = []

    for symbol, result in results.items():
        metrics = result.get("metrics", {})
        pf = metrics.get("profit_factor", 0.0)

        rows.append(
            {
                "symbol": symbol,
                "bars": result.get("bars", 0),
                "trades": metrics.get("total_trades", 0),
                "win_rate_percent": round(
                    float(metrics.get("win_rate_percent", 0.0)),
                    2,
                ),
                "profit_factor": (
                    "INF"
                    if pf == float("inf")
                    else round(float(pf), 3)
                ),
                "net_pnl": round(
                    float(metrics.get("net_pnl", 0.0)),
                    2,
                ),
                "return_percent": round(
                    float(metrics.get("total_return_percent", 0.0)),
                    2,
                ),
                "max_drawdown_percent": round(
                    float(metrics.get("max_drawdown_percent", 0.0)),
                    2,
                ),
                "long_trades": metrics.get("long", {}).get("trades", 0),
                "short_trades": metrics.get("short", {}).get("trades", 0),
                "buy_signals": result.get("signal_counts", {}).get("BUY", 0),
                "sell_signals": result.get("signal_counts", {}).get("SELL", 0),
                "wait_signals": result.get("signal_counts", {}).get("WAIT", 0),
                "signal_errors": result.get("signal_counts", {}).get("ERROR", 0),
            }
        )

    return pd.DataFrame(rows)


def export_trades_csv(
    result: dict[str, Any],
    filename: str | None = None,
) -> Path | None:
    trades = result.get("trades", [])

    if not trades:
        return None

    BACKTEST_OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    symbol = str(result.get("symbol", "UNKNOWN"))

    if filename:
        output_path = BACKTEST_OUTPUT_DIR / filename
    else:
        safe_symbol = (
            symbol
            .replace("^", "")
            .replace(".", "_")
            .replace("/", "_")
        )
        output_path = (
            BACKTEST_OUTPUT_DIR
            / f"{safe_symbol}_trades.csv"
        )

    pd.DataFrame(trades).to_csv(
        output_path,
        index=False,
        encoding="utf-8-sig",
    )

    return output_path


def export_equity_csv(
    result: dict[str, Any],
    filename: str | None = None,
) -> Path | None:
    equity_curve = result.get("equity_curve")

    if equity_curve is None or equity_curve.empty:
        return None

    BACKTEST_OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    symbol = str(result.get("symbol", "UNKNOWN"))

    if filename:
        output_path = BACKTEST_OUTPUT_DIR / filename
    else:
        safe_symbol = (
            symbol
            .replace("^", "")
            .replace(".", "_")
            .replace("/", "_")
        )
        output_path = (
            BACKTEST_OUTPUT_DIR
            / f"{safe_symbol}_equity.csv"
        )

    equity_curve.to_csv(
        output_path,
        encoding="utf-8-sig",
    )

    return output_path


def print_report(result: dict[str, Any]) -> None:
    symbol = result.get("symbol", "UNKNOWN")
    metrics = result.get("metrics", {})
    counts = result.get("signal_counts", {})

    pf = metrics.get("profit_factor", 0.0)
    pf_text = (
        "INF"
        if pf == float("inf")
        else f"{float(pf):.3f}"
    )

    print()
    print("=" * 72)
    print("MARKETHQ BACKTEST ENGINE V3")
    print("=" * 72)
    print(f"Sembol              : {symbol}")
    print(f"Bar sayısı           : {result.get('bars', 0)}")
    print(f"Başlangıç sermayesi  : {metrics.get('initial_capital', 0):.2f}")
    print(f"Final equity         : {metrics.get('final_equity', 0):.2f}")
    print(f"Net PnL              : {metrics.get('net_pnl', 0):.2f}")
    print(
        f"Toplam getiri        : "
        f"{metrics.get('total_return_percent', 0):.2f}%"
    )
    print(f"İşlem sayısı         : {metrics.get('total_trades', 0)}")
    print(f"Kazanan işlem        : {metrics.get('winning_trades', 0)}")
    print(f"Kaybeden işlem       : {metrics.get('losing_trades', 0)}")
    print(f"Win Rate             : {metrics.get('win_rate_percent', 0):.2f}%")
    print(f"Profit Factor        : {pf_text}")
    print(
        f"Max Drawdown         : "
        f"{metrics.get('max_drawdown_percent', 0):.2f}%"
    )
    print(
        f"Ort. pozisyon süresi : "
        f"{metrics.get('average_holding_bars', 0):.2f} bar"
    )

    print()
    print("SIGNAL ENGINE")
    print(f"BUY                  : {counts.get('BUY', 0)}")
    print(f"SELL                 : {counts.get('SELL', 0)}")
    print(f"WAIT                 : {counts.get('WAIT', 0)}")
    print(f"ERROR                : {counts.get('ERROR', 0)}")
    print(f"OTHER                : {counts.get('OTHER', 0)}")

    schema = result.get("indicator_schema", {})
    print(
        "Indicator schema     : "
        + ("OK" if schema.get("complete") else "EKSİK")
    )

    if schema.get("missing"):
        print(
            "Eksik kolonlar       : "
            + ", ".join(schema["missing"])
        )

    print()
    print("ÇIKIŞLAR")
    print(f"Stop Loss            : {metrics.get('stop_loss_exits', 0)}")
    print(f"Take Profit          : {metrics.get('take_profit_exits', 0)}")
    print(
        f"Karşıt sinyal        : "
        f"{metrics.get('opposite_signal_exits', 0)}"
    )
    print(
        f"Max holding          : "
        f"{metrics.get('max_holding_exits', 0)}"
    )
    print(
        f"Veri sonu            : "
        f"{metrics.get('end_of_data_exits', 0)}"
    )

    if result.get("signal_errors"):
        print()
        print("İLK SIGNAL HATALARI")
        for item in result["signal_errors"][:5]:
            print(
                f"- {item['timestamp']} | "
                f"{item['reason']}"
            )

    print()
    print("Research Only        : True")
    print("Execution Enabled    : False")
    print("=" * 72)
    print()


def main() -> None:
    print()
    print("MarketHQ Backtest Engine V3")
    print("Araştırma / backtest modu")
    print()

    symbol = "THYAO.IS"

    try:
        data = get_signal_data(
            symbol,
            period="1y",
        )
    except Exception as exc:
        print(f"❌ Veri alınamadı: {exc}")
        return

    if data is None or data.empty:
        print("❌ Backtest için veri bulunamadı.")
        return

    print(f"📊 {len(data)} bar alındı.")

    try:
        result = run_backtest(
            data=data,
            symbol=symbol,
        )
    except Exception as exc:
        print(f"❌ Backtest başarısız: {exc}")
        return

    print_report(result)

    trades_path = export_trades_csv(result)
    equity_path = export_equity_csv(result)

    if trades_path:
        print(f"📁 İşlem CSV  : {trades_path}")
    else:
        print("📁 İşlem CSV  : İşlem oluşmadı.")

    if equity_path:
        print(f"📈 Equity CSV : {equity_path}")

    print()
    print("Backtest tamamlandı.")
    print()


if __name__ == "__main__":
    main()

