import json
import math
import sys
from pathlib import Path
from typing import Any, Dict, Optional

from strategy_adapter import (
    adapt_strategy,
    load_strategy_by_id,
)

from agents.market_data_agent import (
    get_signal_data,
)

from backtest_engine import (
    run_backtest,
)

from strategy_knowledge_base import (
    add_backtest_result,
)


# ============================================================
# MARKET HQ - STRATEGY BACKTEST RUNNER V2
# ============================================================
#
# AKIŞ:
#
# Knowledge Base
#       ↓
# Strategy Adapter
#       ↓
# Market Data
#       ↓
# Backtest Engine
#       ↓
# Backtest Result
#       ↓
# Knowledge Base
#
# SADECE ARAŞTIRMA / BACKTEST
# Gerçek emir göndermez.
# Broker bağlantısı yoktur.
# ============================================================


RUNNER_VERSION = "2.0"

DEFAULT_SYMBOL = "THYAO.IS"
DEFAULT_PERIOD = "1y"

VALID_PERIODS = {
    "1mo",
    "3mo",
    "6mo",
    "1y",
    "2y",
    "5y",
    "10y",
    "max",
}


# ============================================================
# HELPERS
# ============================================================

def safe_float(
    value: Any,
    default: Optional[float] = None,
) -> Optional[float]:

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


def clean_string(
    value: Any,
    default: str = "",
) -> str:

    if value is None:
        return default

    if isinstance(value, str):

        value = value.strip()

        return value if value else default

    return str(value).strip()


def clean_dict(
    value: Any,
) -> Dict[str, Any]:

    if isinstance(value, dict):
        return value

    return {}


# ============================================================
# STRATEGY ID
# ============================================================

def resolve_strategy_id(
    strategy: Dict[str, Any],
    fallback: str,
) -> str:

    possible_keys = [
        "strategy_id",
        "id",
        "strategyId",
    ]

    for key in possible_keys:

        value = clean_string(
            strategy.get(key)
        )

        if value:
            return value

    return fallback


# ============================================================
# SYMBOL
# ============================================================

def resolve_symbol(
    adapted_strategy: Dict[str, Any],
    requested_symbol: Optional[str] = None,
) -> str:

    if requested_symbol:

        return clean_string(
            requested_symbol
        )

    symbols = adapted_strategy.get(
        "symbols",
        [],
    )

    if isinstance(
        symbols,
        list,
    ):

        for symbol in symbols:

            symbol = clean_string(
                symbol
            )

            if symbol:
                return symbol

    return DEFAULT_SYMBOL


# ============================================================
# PERIOD
# ============================================================

def resolve_period(
    period: Optional[str],
) -> str:

    if not period:
        return DEFAULT_PERIOD

    period = clean_string(
        period
    ).lower()

    if period not in VALID_PERIODS:

        print(
            f"⚠️ Geçersiz period: {period}"
        )

        print(
            f"⚠️ Default kullanılacak: "
            f"{DEFAULT_PERIOD}"
        )

        return DEFAULT_PERIOD

    return period


# ============================================================
# ADAPTER VALIDATION
# ============================================================

def validate_adapter(
    adapted_strategy: Dict[str, Any],
) -> bool:

    if not isinstance(
        adapted_strategy,
        dict,
    ):

        print(
            "❌ Adapter sonucu dictionary değil."
        )

        return False

    validation = clean_dict(
        adapted_strategy.get(
            "validation"
        )
    )

    if not validation.get(
        "valid",
        False,
    ):

        print(
            "❌ Strategy Adapter validation başarısız."
        )

        problems = validation.get(
            "problems",
            [],
        )

        for problem in problems:

            print(
                f"   - {problem}"
            )

        return False

    signal_config = clean_dict(
        adapted_strategy.get(
            "signal_config"
        )
    )

    backtest_config = clean_dict(
        adapted_strategy.get(
            "backtest_config"
        )
    )

    if not signal_config:

        print(
            "❌ Signal config boş."
        )

        return False

    if not backtest_config:

        print(
            "❌ Backtest config boş."
        )

        return False

    return True


# ============================================================
# MARKET DATA
# ============================================================

def load_market_data(
    symbol: str,
    period: str,
):

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

    try:

        data = get_signal_data(
            symbol,
            period=period,
        )

    except TypeError:

        try:

            data = get_signal_data(
                symbol
            )

        except Exception as exc:

            print(
                f"❌ Market data alınamadı: {exc}"
            )

            return None

    except Exception as exc:

        print(
            f"❌ Market data alınamadı: {exc}"
        )

        return None

    if data is None:

        print(
            "❌ Market data None döndü."
        )

        return None

    try:

        bar_count = len(data)

    except Exception:

        bar_count = 0

    if bar_count == 0:

        print(
            "❌ Market data boş."
        )

        return None

    print(
        f"   Bar sayısı : {bar_count}"
    )

    return data


# ============================================================
# BACKTEST
# ============================================================

def execute_backtest(
    data,
    symbol: str,
    signal_config: Dict[str, Any],
    backtest_config: Dict[str, Any],
) -> Optional[Dict[str, Any]]:

    print()
    print(
        "🧪 BACKTEST ÇALIŞTIRILIYOR..."
    )

    print(
        f"   Symbol : {symbol}"
    )

    print(
        "   Signal config hazır."
    )

    print(
        "   Backtest config hazır."
    )

    try:

        result = run_backtest(
            data=data,
            symbol=symbol,
            signal_config=signal_config,
            backtest_config=backtest_config,
        )

    except Exception as exc:

        print()
        print(
            "❌ Backtest başarısız."
        )

        print(
            f"   Hata: {exc}"
        )

        return None

    if not isinstance(
        result,
        dict,
    ):

        print(
            "❌ Backtest sonucu dictionary değil."
        )

        return None

    return result


# ============================================================
# METRICS
# ============================================================

def get_metrics(
    result: Dict[str, Any],
) -> Dict[str, Any]:

    metrics = result.get(
        "metrics",
        {},
    )

    return clean_dict(
        metrics
    )


def metric(
    metrics: Dict[str, Any],
    key: str,
    default: Any = 0,
) -> Any:

    return metrics.get(
        key,
        default,
    )


# ============================================================
# PRINT BACKTEST RESULT
# ============================================================

def print_backtest_result(
    result: Dict[str, Any],
    strategy_id: str,
    strategy_name: str,
    symbol: str,
    period: str,
) -> None:

    metrics = get_metrics(
        result
    )

    total_trades = metric(
        metrics,
        "total_trades",
        0,
    )

    winning_trades = metric(
        metrics,
        "winning_trades",
        0,
    )

    losing_trades = metric(
        metrics,
        "losing_trades",
        0,
    )

    win_rate = metric(
        metrics,
        "win_rate_percent",
        0.0,
    )

    profit_factor = metric(
        metrics,
        "profit_factor",
        0.0,
    )

    net_pnl = metric(
        metrics,
        "net_pnl",
        0.0,
    )

    total_return = metric(
        metrics,
        "total_return_percent",
        0.0,
    )

    max_drawdown = metric(
        metrics,
        "max_drawdown_percent",
        0.0,
    )

    average_trade = metric(
        metrics,
        "average_trade_pnl",
        0.0,
    )

    average_holding = metric(
        metrics,
        "average_holding_bars",
        0.0,
    )

    stop_exits = metric(
        metrics,
        "stop_loss_exits",
        0,
    )

    target_exits = metric(
        metrics,
        "take_profit_exits",
        0,
    )

    opposite_exits = metric(
        metrics,
        "opposite_signal_exits",
        0,
    )

    max_holding_exits = metric(
        metrics,
        "max_holding_exits",
        0,
    )

    end_exits = metric(
        metrics,
        "end_of_data_exits",
        0,
    )

    print()
    print(
        "=" * 70
    )

    print(
        "📈 MARKET HQ BACKTEST RESULT"
    )

    print(
        "=" * 70
    )

    print(
        f"Strategy ID      : {strategy_id}"
    )

    print(
        f"Strategy         : {strategy_name}"
    )

    print(
        f"Symbol           : {symbol}"
    )

    print(
        f"Period           : {period}"
    )

    print()

    print(
        "PERFORMANCE"
    )

    print(
        "-" * 70
    )

    print(
        f"Trade Count      : {total_trades}"
    )

    print(
        f"Winning Trades   : {winning_trades}"
    )

    print(
        f"Losing Trades    : {losing_trades}"
    )

    print(
        f"Win Rate         : {safe_float(win_rate, 0.0):.2f}%"
    )

    if math.isinf(
        safe_float(
            profit_factor,
            0.0,
        )
        or 0.0
    ):

        print(
            "Profit Factor    : INF"
        )

    else:

        print(
            f"Profit Factor    : "
            f"{safe_float(profit_factor, 0.0):.3f}"
        )

    print(
        f"Net PnL          : "
        f"{safe_float(net_pnl, 0.0):,.2f}"
    )

    print(
        f"Total Return     : "
        f"{safe_float(total_return, 0.0):.2f}%"
    )

    print(
        f"Max Drawdown     : "
        f"{safe_float(max_drawdown, 0.0):.2f}%"
    )

    print(
        f"Average Trade    : "
        f"{safe_float(average_trade, 0.0):,.2f}"
    )

    print(
        f"Avg Holding Bars : "
        f"{safe_float(average_holding, 0.0):.2f}"
    )

    print()

    print(
        "EXIT ANALYSIS"
    )

    print(
        "-" * 70
    )

    print(
        f"Stop Loss        : {stop_exits}"
    )

    print(
        f"Take Profit      : {target_exits}"
    )

    print(
        f"Opposite Signal  : {opposite_exits}"
    )

    print(
        f"Max Holding      : {max_holding_exits}"
    )

    print(
        f"End of Data      : {end_exits}"
    )

    print()

    long_metrics = clean_dict(
        metrics.get(
            "long"
        )
    )

    short_metrics = clean_dict(
        metrics.get(
            "short"
        )
    )

    print(
        "SIDE ANALYSIS"
    )

    print(
        "-" * 70
    )

    print(
        f"LONG  → "
        f"{long_metrics.get('trades', 0)} işlem | "
        f"{long_metrics.get('wins', 0)} W | "
        f"{long_metrics.get('losses', 0)} L | "
        f"{safe_float(long_metrics.get('win_rate_percent', 0), 0):.2f}% | "
        f"PnL {safe_float(long_metrics.get('net_pnl', 0), 0):,.2f}"
    )

    print(
        f"SHORT → "
        f"{short_metrics.get('trades', 0)} işlem | "
        f"{short_metrics.get('wins', 0)} W | "
        f"{short_metrics.get('losses', 0)} L | "
        f"{safe_float(short_metrics.get('win_rate_percent', 0), 0):.2f}% | "
        f"PnL {safe_float(short_metrics.get('net_pnl', 0), 0):,.2f}"
    )

    print()

    print(
        "SAFETY"
    )

    print(
        "-" * 70
    )

    print(
        "Execution Enabled : False"
    )

    print(
        "Research Only     : True"
    )

    print(
        "=" * 70
    )


# ============================================================
# KNOWLEDGE BASE RESULT
# ============================================================

def save_to_knowledge_base(
    strategy_id: str,
    symbol: str,
    result: Dict[str, Any],
) -> bool:

    print()
    print(
        "🧠 KNOWLEDGE BASE GÜNCELLENİYOR..."
    )

    metrics = get_metrics(
        result
    )

    # KB'nin beklediği gerçek metric isimleri
    kb_result = {
        "metrics": {
            "total_trades": metrics.get(
                "total_trades",
                0,
            ),

            "winning_trades": metrics.get(
                "winning_trades",
                0,
            ),

            "losing_trades": metrics.get(
                "losing_trades",
                0,
            ),

            "win_rate_percent": metrics.get(
                "win_rate_percent",
                0.0,
            ),

            "profit_factor": metrics.get(
                "profit_factor",
                0.0,
            ),

            "net_pnl": metrics.get(
                "net_pnl",
                0.0,
            ),

            "total_return_percent": metrics.get(
                "total_return_percent",
                0.0,
            ),

            "max_drawdown_percent": metrics.get(
                "max_drawdown_percent",
                0.0,
            ),
        }
    }

    try:

        success = add_backtest_result(
            strategy_id,
            symbol,
            kb_result,
        )

    except Exception as exc:

        print(
            "❌ Knowledge Base güncellenemedi."
        )

        print(
            f"   Hata: {exc}"
        )

        return False

    if success:

        print(
            "✅ Backtest sonucu Knowledge Base'e eklendi."
        )

        return True

    print(
        "⚠️ Backtest sonucu Knowledge Base'e eklenemedi."
    )

    return False


# ============================================================
# SAVE JSON
# ============================================================

def make_json_safe(
    value: Any,
) -> Any:

    if value is None:
        return None

    if isinstance(
        value,
        (
            str,
            int,
            bool,
        ),
    ):

        return value

    if isinstance(
        value,
        float,
    ):

        if math.isfinite(value):
            return value

        return str(value)

    if isinstance(
        value,
        dict,
    ):

        return {
            str(key): make_json_safe(
                item
            )
            for key, item in value.items()
        }

    if isinstance(
        value,
        (
            list,
            tuple,
        ),
    ):

        return [
            make_json_safe(
                item
            )
            for item in value
        ]

    return str(value)


def save_backtest_result(
    result: Dict[str, Any],
    strategy_id: str,
    symbol: str,
) -> str:

    output_directory = Path(
        "backtest_results"
    )

    output_directory.mkdir(
        parents=True,
        exist_ok=True,
    )

    safe_strategy_id = (
        clean_string(
            strategy_id,
            "UNKNOWN",
        )
        .replace(
            "/",
            "_",
        )
        .replace(
            "\\",
            "_",
        )
    )

    safe_symbol = (
        clean_string(
            symbol,
            "UNKNOWN",
        )
        .replace(
            "/",
            "_",
        )
        .replace(
            "\\",
            "_",
        )
    )

    filename = (
        f"{safe_strategy_id}_"
        f"{safe_symbol}_backtest.json"
    )

    output_path = (
        output_directory
        / filename
    )

    safe_result = make_json_safe(
        result
    )

    output_path.write_text(
        json.dumps(
            safe_result,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    return str(
        output_path.resolve()
    )


# ============================================================
# BUILD RESULT
# ============================================================

def build_complete_result(
    adapted_strategy: Dict[str, Any],
    backtest_result: Dict[str, Any],
    strategy_id: str,
    symbol: str,
    period: str,
) -> Dict[str, Any]:

    return {
        "runner_version": RUNNER_VERSION,

        "strategy": {
            "strategy_id": strategy_id,

            "name": clean_string(
                adapted_strategy.get(
                    "strategy_name"
                )
            ),

            "status": clean_string(
                adapted_strategy.get(
                    "status"
                )
            ),

            "market": clean_string(
                adapted_strategy.get(
                    "market"
                )
            ),
        },

        "symbol": symbol,

        "period": period,

        "adapter": {
            "signal_config": adapted_strategy.get(
                "signal_config",
                {},
            ),

            "backtest_config": adapted_strategy.get(
                "backtest_config",
                {},
            ),

            "conditions": adapted_strategy.get(
                "conditions",
                {},
            ),
        },

        "backtest": backtest_result,

        "execution_enabled": False,

        "research_only": True,
    }


# ============================================================
# MAIN RUNNER
# ============================================================

def run_strategy_backtest(
    strategy_id: str,
    symbol: Optional[str] = None,
    period: str = DEFAULT_PERIOD,
) -> Optional[Dict[str, Any]]:

    print()
    print(
        "=" * 70
    )

    print(
        "MARKETHQ STRATEGY BACKTEST RUNNER V2"
    )

    print(
        "=" * 70
    )

    print(
        f"Strategy ID : {strategy_id}"
    )

    # --------------------------------------------------------
    # 1. KNOWLEDGE BASE
    # --------------------------------------------------------

    print()
    print(
        "🧠 KNOWLEDGE BASE"
    )

    strategy = load_strategy_by_id(
        strategy_id
    )

    if strategy is None:

        print(
            "❌ Strategy bulunamadı."
        )

        return None

    actual_strategy_id = resolve_strategy_id(
        strategy,
        strategy_id,
    )

    strategy_name = clean_string(
        strategy.get(
            "name"
        ),
        "Unnamed Strategy",
    )

    print(
        f"Strategy ID : {actual_strategy_id}"
    )

    print(
        f"Strategy    : {strategy_name}"
    )

    print(
        f"Status      : "
        f"{strategy.get('status', '-')}"
    )

    # --------------------------------------------------------
    # 2. ADAPTER
    # --------------------------------------------------------

    print()
    print(
        "🔌 STRATEGY ADAPTER"
    )

    adapted_strategy = adapt_strategy(
        strategy
    )

    if not validate_adapter(
        adapted_strategy
    ):

        return None

    # Adapter bazı sürümlerde ID taşımayabilir.
    # Gerçek ID'yi burada garanti ediyoruz.
    adapted_strategy[
        "strategy_id"
    ] = actual_strategy_id

    print(
        "✅ Strategy Adapter hazır."
    )

    # --------------------------------------------------------
    # 3. TARGET
    # --------------------------------------------------------

    final_symbol = resolve_symbol(
        adapted_strategy,
        symbol,
    )

    final_period = resolve_period(
        period
    )

    print()
    print(
        "🎯 BACKTEST TARGET"
    )

    print(
        f"Symbol : {final_symbol}"
    )

    print(
        f"Period : {final_period}"
    )

    # --------------------------------------------------------
    # 4. MARKET DATA
    # --------------------------------------------------------

    data = load_market_data(
        final_symbol,
        final_period,
    )

    if data is None:

        return None

    # --------------------------------------------------------
    # 5. BACKTEST ENGINE
    # --------------------------------------------------------

    backtest_result = execute_backtest(
        data=data,
        symbol=final_symbol,
        signal_config=adapted_strategy[
            "signal_config"
        ],
        backtest_config=adapted_strategy[
            "backtest_config"
        ],
    )

    if backtest_result is None:

        return None

    # --------------------------------------------------------
    # 6. RESULT
    # --------------------------------------------------------

    complete_result = build_complete_result(
        adapted_strategy=adapted_strategy,
        backtest_result=backtest_result,
        strategy_id=actual_strategy_id,
        symbol=final_symbol,
        period=final_period,
    )

    # --------------------------------------------------------
    # 7. PRINT
    # --------------------------------------------------------

    print_backtest_result(
        result=backtest_result,
        strategy_id=actual_strategy_id,
        strategy_name=strategy_name,
        symbol=final_symbol,
        period=final_period,
    )

    # --------------------------------------------------------
    # 8. SAVE JSON
    # --------------------------------------------------------

    output_path = save_backtest_result(
        complete_result,
        actual_strategy_id,
        final_symbol,
    )

    print()
    print(
        "💾 BACKTEST SONUCU KAYDEDİLDİ:"
    )

    print(
        output_path
    )

    # --------------------------------------------------------
    # 9. KNOWLEDGE BASE
    # --------------------------------------------------------

    save_to_knowledge_base(
        strategy_id=actual_strategy_id,
        symbol=final_symbol,
        result=backtest_result,
    )

    # --------------------------------------------------------
    # 10. FINAL
    # --------------------------------------------------------

    print()
    print(
        "=" * 70
    )

    print(
        "✅ BACKTEST PIPELINE TAMAMLANDI"
    )

    print(
        "=" * 70
    )

    print(
        "Knowledge Base       : OK"
    )

    print(
        "Strategy Adapter     : OK"
    )

    print(
        "Market Data          : OK"
    )

    print(
        "Backtest Engine      : OK"
    )

    print(
        "Backtest Result      : OK"
    )

    print(
        "Knowledge Base Save  : DONE"
    )

    print(
        "Execution Enabled    : False"
    )

    print(
        "Research Only        : True"
    )

    print(
        "=" * 70
    )

    return complete_result


# ============================================================
# USAGE
# ============================================================

def print_usage() -> None:

    print()
    print(
        "KULLANIM:"
    )

    print()

    print(
        "1) Strategy ID:"
    )

    print(
        "   .\\.venv\\Scripts\\python.exe "
        "strategy_backtest_runner.py "
        "STR-30AA70EC1A"
    )

    print()

    print(
        "2) Strategy + Symbol:"
    )

    print(
        "   .\\.venv\\Scripts\\python.exe "
        "strategy_backtest_runner.py "
        "STR-30AA70EC1A THYAO.IS"
    )

    print()

    print(
        "3) Strategy + Symbol + Period:"
    )

    print(
        "   .\\.venv\\Scripts\\python.exe "
        "strategy_backtest_runner.py "
        "STR-30AA70EC1A THYAO.IS 3y"
    )

    print()

    print(
        "Period seçenekleri:"
    )

    print(
        ", ".join(
            sorted(
                VALID_PERIODS
            )
        )
    )


# ============================================================
# ENTRY POINT
# ============================================================

def main() -> None:

    if len(sys.argv) < 2:

        print_usage()

        return

    strategy_id = clean_string(
        sys.argv[1]
    )

    if not strategy_id:

        print(
            "❌ Strategy ID boş."
        )

        return

    symbol = None

    if len(sys.argv) >= 3:

        symbol = clean_string(
            sys.argv[2]
        )

    period = DEFAULT_PERIOD

    if len(sys.argv) >= 4:

        period = clean_string(
            sys.argv[3]
        )

    run_strategy_backtest(
        strategy_id=strategy_id,
        symbol=symbol,
        period=period,
    )


# ============================================================
# RUN
# ============================================================

if __name__ == "__main__":
    main()
