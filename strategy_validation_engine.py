from __future__ import annotations

import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agents.market_data_agent import get_signal_data
from backtest_engine import DEFAULT_BACKTEST_CONFIG, run_backtest
from strategy_adapter import adapt_strategy, load_strategy_by_id


# ============================================================
# MARKET HQ - STRATEGY VALIDATION ENGINE V1.1
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parent

VALIDATION_RESULTS_DIR = (
    PROJECT_ROOT / "validation_results"
)

DEFAULT_VALIDATION_CONFIG = {
    "period": "1y",
    "min_trades": 5,
    "symbols": [
        "THYAO.IS",
        "ASELS.IS",
        "GARAN.IS",
        "AKBNK.IS",
        "EREGL.IS",
        "TUPRS.IS",
        "SISE.IS",
        "BIMAS.IS",
    ],
    "save_json": True,
}


# ============================================================
# HELPERS
# ============================================================

def safe_float(
    value: Any,
    default: float = 0.0,
) -> float:

    try:
        number = float(value)

        if not math.isfinite(number):
            return default

        return number

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


def utc_timestamp() -> str:
    return datetime.now(
        timezone.utc
    ).isoformat()


def ensure_output_directory() -> None:

    VALIDATION_RESULTS_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )


# ============================================================
# STRATEGY RESOLUTION
# ============================================================

def resolve_strategy(
    strategy_id: str,
) -> dict[str, Any]:

    if not strategy_id:
        raise ValueError(
            "Strategy ID belirtilmedi."
        )

    strategy = load_strategy_by_id(
        strategy_id
    )

    if not strategy:
        raise ValueError(
            f"Strategy bulunamadı: {strategy_id}"
        )

    adapted = adapt_strategy(
        strategy
    )

    if not isinstance(adapted, dict):
        raise ValueError(
            "Strategy Adapter geçerli bir sonuç döndürmedi."
        )

    signal_config = adapted.get(
        "signal_engine_config",
        {},
    )

    backtest_config = adapted.get(
        "backtest_config",
        {},
    )

    if not isinstance(
        signal_config,
        dict,
    ):
        signal_config = {}

    if not isinstance(
        backtest_config,
        dict,
    ):
        backtest_config = {}

    # --------------------------------------------------------
    # ÖNEMLİ:
    #
    # Adapter'ın valid=False dönmesi tek başına backtest
    # yapılmasını engellemez.
    #
    # Çünkü strategy_adapter içindeki bazı belirsizlikler
    # araştırma uyarısı olabilir. Backtest Runner V2 de aynı
    # stratejiyi başarıyla çalıştırabiliyor.
    #
    # Burada yalnızca gerçekten gerekli config'in mevcut
    # olup olmadığını kontrol ediyoruz.
    # --------------------------------------------------------

    adapted["signal_engine_config"] = (
        signal_config
    )

    adapted["backtest_config"] = (
        backtest_config
    )

    return adapted


# ============================================================
# CONFIG
# ============================================================

def get_signal_config(
    adapted_strategy: dict[str, Any],
) -> dict[str, Any]:

    config = dict(
        adapted_strategy.get(
            "signal_engine_config",
            {},
        )
    )

    return config


def get_backtest_config(
    adapted_strategy: dict[str, Any],
) -> dict[str, Any]:

    config = dict(
        DEFAULT_BACKTEST_CONFIG
    )

    adapted_config = adapted_strategy.get(
        "backtest_config",
        {},
    )

    if isinstance(
        adapted_config,
        dict,
    ):
        config.update(
            adapted_config
        )

    return config


# ============================================================
# SINGLE SYMBOL VALIDATION
# ============================================================

def validate_symbol(
    adapted_strategy: dict[str, Any],
    symbol: str,
    period: str,
    min_trades: int,
) -> dict[str, Any]:

    print()
    print("=" * 70)
    print(
        f"🔍 SYMBOL VALIDATION: {symbol}"
    )
    print("=" * 70)

    print()
    print(
        "📊 MARKET DATA ALINIYOR..."
    )

    print(
        f"   Symbol : {symbol}"
    )

    print(
        f"   Period : {period}"
    )

    data = get_signal_data(
        symbol,
        period=period,
    )

    if data is None:
        raise ValueError(
            f"Market data None döndü: {symbol}"
        )

    if len(data) == 0:
        raise ValueError(
            f"Market data boş: {symbol}"
        )

    print(
        f"   Bar sayısı : {len(data)}"
    )

    signal_config = get_signal_config(
        adapted_strategy
    )

    backtest_config = get_backtest_config(
        adapted_strategy
    )

    print()
    print(
        "🧪 BACKTEST ÇALIŞTIRILIYOR..."
    )

    result = run_backtest(
        data=data,
        symbol=symbol,
        signal_config=signal_config,
        backtest_config=backtest_config,
    )

    if not isinstance(
        result,
        dict,
    ):
        raise ValueError(
            "Backtest Engine geçerli sonuç döndürmedi."
        )

    metrics = result.get(
        "metrics",
        {},
    )

    if not isinstance(
        metrics,
        dict,
    ):
        metrics = {}

    total_trades = safe_int(
        metrics.get(
            "total_trades"
        )
    )

    winning_trades = safe_int(
        metrics.get(
            "winning_trades"
        )
    )

    losing_trades = safe_int(
        metrics.get(
            "losing_trades"
        )
    )

    win_rate = safe_float(
        metrics.get(
            "win_rate_percent"
        )
    )

    profit_factor = safe_float(
        metrics.get(
            "profit_factor"
        )
    )

    net_pnl = safe_float(
        metrics.get(
            "net_pnl"
        )
    )

    total_return = safe_float(
        metrics.get(
            "total_return_percent"
        )
    )

    max_drawdown = safe_float(
        metrics.get(
            "max_drawdown_percent"
        )
    )

    average_trade = safe_float(
        metrics.get(
            "average_trade"
        )
    )

    avg_holding_bars = safe_float(
        metrics.get(
            "avg_holding_bars"
        )
    )

    # --------------------------------------------------------
    # VALIDATION CLASSIFICATION
    # --------------------------------------------------------

    if total_trades < min_trades:

        validation_status = (
            "INCONCLUSIVE"
        )

    elif (
        profit_factor > 1.0
        and total_return > 0
    ):

        validation_status = (
            "POSITIVE"
        )

    else:

        validation_status = (
            "NEGATIVE"
        )

    result_record = {
        "symbol": symbol,
        "period": period,
        "bars": len(data),

        "total_trades": total_trades,

        "winning_trades":
            winning_trades,

        "losing_trades":
            losing_trades,

        "win_rate_percent":
            win_rate,

        "profit_factor":
            profit_factor,

        "net_pnl":
            net_pnl,

        "total_return_percent":
            total_return,

        "max_drawdown_percent":
            max_drawdown,

        "average_trade":
            average_trade,

        "avg_holding_bars":
            avg_holding_bars,

        "validation_status":
            validation_status,

        "research_only":
            True,

        "execution_enabled":
            False,
    }

    print()
    print(
        "RESULT"
    )

    print(
        "-" * 70
    )

    print(
        f"Trades           : {total_trades}"
    )

    print(
        f"Wins             : {winning_trades}"
    )

    print(
        f"Losses           : {losing_trades}"
    )

    print(
        f"Win Rate         : {win_rate:.2f}%"
    )

    print(
        f"Profit Factor    : {profit_factor:.3f}"
    )

    print(
        f"Net PnL          : {net_pnl:,.2f}"
    )

    print(
        f"Total Return     : {total_return:.2f}%"
    )

    print(
        f"Max Drawdown     : {max_drawdown:.2f}%"
    )

    print(
        f"Validation       : {validation_status}"
    )

    return result_record


# ============================================================
# AGGREGATE ANALYSIS
# ============================================================

def calculate_validation_summary(
    symbol_results: list[dict[str, Any]],
) -> dict[str, Any]:

    valid_results = [
        item
        for item in symbol_results
        if item.get(
            "validation_status"
        )
        in {
            "POSITIVE",
            "NEGATIVE",
            "INCONCLUSIVE",
        }
    ]

    if not valid_results:

        return {
            "symbols_tested": 0,
            "positive_symbols": 0,
            "negative_symbols": 0,
            "inconclusive_symbols": 0,
            "error_symbols": len(
                symbol_results
            ),

            "total_trades": 0,
            "winning_trades": 0,
            "losing_trades": 0,

            "aggregate_win_rate_percent":
                0.0,

            "average_profit_factor":
                0.0,

            "average_return_percent":
                0.0,

            "best_return_percent":
                0.0,

            "worst_return_percent":
                0.0,

            "average_max_drawdown_percent":
                0.0,

            "consistency_percent":
                0.0,

            "validation_status":
                "INCONCLUSIVE",
        }

    positive = [
        item
        for item in valid_results
        if item.get(
            "validation_status"
        ) == "POSITIVE"
    ]

    negative = [
        item
        for item in valid_results
        if item.get(
            "validation_status"
        ) == "NEGATIVE"
    ]

    inconclusive = [
        item
        for item in valid_results
        if item.get(
            "validation_status"
        ) == "INCONCLUSIVE"
    ]

    error_count = len(
        symbol_results
    ) - len(
        valid_results
    )

    total_trades = sum(
        safe_int(
            item.get(
                "total_trades"
            )
        )
        for item in valid_results
    )

    winning_trades = sum(
        safe_int(
            item.get(
                "winning_trades"
            )
        )
        for item in valid_results
    )

    losing_trades = sum(
        safe_int(
            item.get(
                "losing_trades"
            )
        )
        for item in valid_results
    )

    if total_trades > 0:

        aggregate_win_rate = (
            winning_trades
            / total_trades
            * 100.0
        )

    else:

        aggregate_win_rate = 0.0

    profit_factors = [
        safe_float(
            item.get(
                "profit_factor"
            )
        )
        for item in valid_results
        if safe_float(
            item.get(
                "profit_factor"
            )
        ) > 0
    ]

    returns = [
        safe_float(
            item.get(
                "total_return_percent"
            )
        )
        for item in valid_results
    ]

    drawdowns = [
        safe_float(
            item.get(
                "max_drawdown_percent"
            )
        )
        for item in valid_results
    ]

    average_profit_factor = (
        sum(profit_factors)
        / len(profit_factors)
        if profit_factors
        else 0.0
    )

    average_return = (
        sum(returns)
        / len(returns)
        if returns
        else 0.0
    )

    best_return = (
        max(returns)
        if returns
        else 0.0
    )

    worst_return = (
        min(returns)
        if returns
        else 0.0
    )

    average_drawdown = (
        sum(drawdowns)
        / len(drawdowns)
        if drawdowns
        else 0.0
    )

    tested_count = len(
        valid_results
    )

    consistency = (
        len(positive)
        / tested_count
        * 100.0
        if tested_count > 0
        else 0.0
    )

    # --------------------------------------------------------
    # Genel araştırma sınıflandırması
    # --------------------------------------------------------

    if (
        len(positive) >= 5
        and consistency >= 60.0
    ):

        validation_status = (
            "PROMISING"
        )

    elif (
        len(positive) >= 3
        and consistency >= 40.0
    ):

        validation_status = (
            "MIXED"
        )

    else:

        validation_status = (
            "WEAK"
        )

    return {
        "symbols_tested":
            tested_count,

        "positive_symbols":
            len(positive),

        "negative_symbols":
            len(negative),

        "inconclusive_symbols":
            len(inconclusive),

        "error_symbols":
            error_count,

        "total_trades":
            total_trades,

        "winning_trades":
            winning_trades,

        "losing_trades":
            losing_trades,

        "aggregate_win_rate_percent":
            aggregate_win_rate,

        "average_profit_factor":
            average_profit_factor,

        "average_return_percent":
            average_return,

        "best_return_percent":
            best_return,

        "worst_return_percent":
            worst_return,

        "average_max_drawdown_percent":
            average_drawdown,

        "consistency_percent":
            consistency,

        "validation_status":
            validation_status,
    }


# ============================================================
# MAIN VALIDATION
# ============================================================

def run_validation(
    strategy_id: str,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:

    validation_config = dict(
        DEFAULT_VALIDATION_CONFIG
    )

    if isinstance(
        config,
        dict,
    ):

        validation_config.update(
            config
        )

    period = str(
        validation_config.get(
            "period",
            "1y",
        )
    )

    min_trades = safe_int(
        validation_config.get(
            "min_trades",
            5,
        ),
        5,
    )

    symbols = validation_config.get(
        "symbols",
        [],
    )

    if not isinstance(
        symbols,
        list,
    ):

        raise ValueError(
            "symbols list olmalıdır."
        )

    symbols = [
        str(symbol).strip()
        for symbol in symbols
        if str(symbol).strip()
    ]

    if not symbols:

        raise ValueError(
            "Test edilecek symbol bulunamadı."
        )

    adapted_strategy = resolve_strategy(
        strategy_id
    )

    strategy_name = adapted_strategy.get(
        "strategy_name"
    )

    if not strategy_name:

        strategy_name = adapted_strategy.get(
            "name",
            "UNKNOWN",
        )

    print()
    print(
        "=" * 70
    )

    print(
        "MARKETHQ STRATEGY VALIDATION ENGINE V1.1"
    )

    print(
        "=" * 70
    )

    print()
    print(
        f"Strategy ID : {strategy_id}"
    )

    print(
        f"Strategy    : {strategy_name}"
    )

    print(
        f"Period      : {period}"
    )

    print(
        f"Symbols     : {len(symbols)}"
    )

    print(
        f"Min Trades  : {min_trades}"
    )

    print()
    print(
        "🔌 STRATEGY ADAPTER"
    )

    adapter_valid = adapted_strategy.get(
        "valid"
    )

    print(
        f"Adapter Valid Flag : "
        f"{adapter_valid}"
    )

    if adapter_valid is False:

        print(
            "⚠️ Adapter bazı belirsizlikler "
            "bildiriyor; araştırma/backtest "
            "devam ediyor."
        )

    else:

        print(
            "✅ Strategy Adapter doğrulandı."
        )

    symbol_results = []

    for index, symbol in enumerate(
        symbols,
        start=1,
    ):

        print()
        print(
            f"📌 TEST {index}/{len(symbols)}"
        )

        try:

            result = validate_symbol(
                adapted_strategy=
                    adapted_strategy,

                symbol=symbol,

                period=period,

                min_trades=min_trades,
            )

            symbol_results.append(
                result
            )

        except Exception as exc:

            print()
            print(
                f"❌ {symbol} validation başarısız:"
            )

            print(
                f"   {exc}"
            )

            symbol_results.append(
                {
                    "symbol":
                        symbol,

                    "period":
                        period,

                    "bars":
                        0,

                    "total_trades":
                        0,

                    "winning_trades":
                        0,

                    "losing_trades":
                        0,

                    "win_rate_percent":
                        0.0,

                    "profit_factor":
                        0.0,

                    "net_pnl":
                        0.0,

                    "total_return_percent":
                        0.0,

                    "max_drawdown_percent":
                        0.0,

                    "average_trade":
                        0.0,

                    "avg_holding_bars":
                        0.0,

                    "validation_status":
                        "ERROR",

                    "error":
                        str(exc),

                    "research_only":
                        True,

                    "execution_enabled":
                        False,
                }
            )

    summary = calculate_validation_summary(
        symbol_results
    )

    result = {
        "validation_engine":
            "V1.1",

        "timestamp":
            utc_timestamp(),

        "strategy_id":
            strategy_id,

        "strategy_name":
            strategy_name,

        "period":
            period,

        "min_trades":
            min_trades,

        "symbols_requested":
            symbols,

        "symbol_results":
            symbol_results,

        "summary":
            summary,

        "research_only":
            True,

        "execution_enabled":
            False,
    }

    if validation_config.get(
        "save_json",
        True,
    ):

        ensure_output_directory()

        timestamp = datetime.now().strftime(
            "%Y%m%d_%H%M%S"
        )

        output_path = (
            VALIDATION_RESULTS_DIR
            / (
                f"{strategy_id}"
                f"_validation_"
                f"{timestamp}.json"
            )
        )

        with open(
            output_path,
            "w",
            encoding="utf-8",
        ) as file:

            json.dump(
                result,
                file,
                ensure_ascii=False,
                indent=2,
            )

        result["output_path"] = str(
            output_path
        )

    # ========================================================
    # SUMMARY
    # ========================================================

    print()
    print(
        "=" * 70
    )

    print(
        "📊 STRATEGY VALIDATION SUMMARY"
    )

    print(
        "=" * 70
    )

    print()

    print(
        f"Strategy ID          : "
        f"{strategy_id}"
    )

    print(
        f"Symbols Tested       : "
        f"{summary['symbols_tested']}"
    )

    print(
        f"Positive             : "
        f"{summary['positive_symbols']}"
    )

    print(
        f"Negative             : "
        f"{summary['negative_symbols']}"
    )

    print(
        f"Inconclusive         : "
        f"{summary['inconclusive_symbols']}"
    )

    print(
        f"Errors               : "
        f"{summary['error_symbols']}"
    )

    print(
        f"Total Trades         : "
        f"{summary['total_trades']}"
    )

    print(
        f"Aggregate Win Rate   : "
        f"{summary['aggregate_win_rate_percent']:.2f}%"
    )

    print(
        f"Average PF           : "
        f"{summary['average_profit_factor']:.3f}"
    )

    print(
        f"Average Return       : "
        f"{summary['average_return_percent']:.2f}%"
    )

    print(
        f"Best Return          : "
        f"{summary['best_return_percent']:.2f}%"
    )

    print(
        f"Worst Return         : "
        f"{summary['worst_return_percent']:.2f}%"
    )

    print(
        f"Average Max DD       : "
        f"{summary['average_max_drawdown_percent']:.2f}%"
    )

    print(
        f"Consistency          : "
        f"{summary['consistency_percent']:.2f}%"
    )

    print(
        f"Validation Status    : "
        f"{summary['validation_status']}"
    )

    # ========================================================
    # SYMBOL TABLE
    # ========================================================

    print()
    print(
        "=" * 70
    )

    print(
        "📋 SYMBOL COMPARISON"
    )

    print(
        "=" * 70
    )

    print()

    header = (
        f"{'SYMBOL':<12}"
        f"{'TRADES':>8}"
        f"{'WIN%':>9}"
        f"{'PF':>8}"
        f"{'RETURN':>10}"
        f"{'MAX DD':>10}"
        f"{'STATUS':>15}"
    )

    print(header)

    print(
        "-" * len(header)
    )

    for item in symbol_results:

        status = item.get(
            "validation_status",
            "ERROR",
        )

        if status == "ERROR":

            print(
                f"{item['symbol']:<12}"
                f"{'-':>8}"
                f"{'-':>9}"
                f"{'-':>8}"
                f"{'-':>10}"
                f"{'-':>10}"
                f"{'ERROR':>15}"
            )

            continue

        print(
            f"{item['symbol']:<12}"
            f"{item['total_trades']:>8}"
            f"{item['win_rate_percent']:>8.2f}%"
            f"{item['profit_factor']:>8.3f}"
            f"{item['total_return_percent']:>9.2f}%"
            f"{item['max_drawdown_percent']:>9.2f}%"
            f"{status:>15}"
        )

    # ========================================================
    # SAFETY
    # ========================================================

    print()
    print(
        "=" * 70
    )

    print(
        "SAFETY"
    )

    print(
        "=" * 70
    )

    print(
        "Execution Enabled : False"
    )

    print(
        "Research Only      : True"
    )

    if result.get(
        "output_path"
    ):

        print()
        print(
            "💾 VALIDATION SONUCU KAYDEDİLDİ:"
        )

        print(
            result["output_path"]
        )

    print()
    print(
        "=" * 70
    )

    print(
        "✅ STRATEGY VALIDATION TAMAMLANDI"
    )

    print(
        "=" * 70
    )

    return result


# ============================================================
# CLI
# ============================================================

def main() -> None:

    if len(sys.argv) < 2:

        print(
            "Kullanım:"
        )

        print(
            "python strategy_validation_engine.py "
            "STRATEGY_ID"
        )

        print()

        print(
            "Örnek:"
        )

        print(
            "python strategy_validation_engine.py "
            "STR-30AA70EC1A"
        )

        return

    strategy_id = sys.argv[1]

    run_validation(
        strategy_id=strategy_id
    )


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":

    main()
