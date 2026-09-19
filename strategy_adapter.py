import json
import math
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from strategy_knowledge_base import (
    get_strategy,
    search_strategies,
)


# ============================================================
# MARKET HQ - STRATEGY ADAPTER V1
# ============================================================
#
# Görev:
#
# Strategy Knowledge Base
#          ↓
#   Strategy Adapter
#          ↓
#   Signal Engine Config
#          ↓
#   Backtest Config
#
# Bu dosya:
# - Knowledge Base'den strateji okur
# - Parametre isimlerini normalize eder
# - Signal Engine config oluşturur
# - Backtest config oluşturur
# - Strateji koşullarını taşır
# - Eksik / belirsiz alanları bildirir
#
# Bu dosya gerçek emir göndermez.
# Broker bağlantısı yoktur.
# Araştırma / backtest amaçlıdır.
# ============================================================


ADAPTER_VERSION = "1.0"


# ============================================================
# DEFAULT SIGNAL ENGINE CONFIG
# ============================================================

DEFAULT_SIGNAL_CONFIG = {
    "sma_fast": 20,
    "sma_slow": 50,

    "ema_fast": 20,
    "ema_slow": 50,

    "rsi_period": 14,
    "rsi_oversold": 30,
    "rsi_overbought": 70,

    "macd_fast": 12,
    "macd_slow": 26,
    "macd_signal": 9,

    "bollinger_period": 20,
    "bollinger_std": 2.0,

    "atr_period": 14,

    "volume_period": 20,

    "buy_threshold": 3,
    "sell_threshold": -3,

    "minimum_volume_ratio": 1.0,
}


# ============================================================
# DEFAULT BACKTEST CONFIG
# ============================================================

DEFAULT_BACKTEST_CONFIG = {
    "stop_atr_multiplier": 2.0,
    "target_atr_multiplier": 3.0,
}


# ============================================================
# PARAMETER ALIASES
# ============================================================

PARAMETER_ALIASES = {

    # -------------------------
    # SMA
    # -------------------------

    "sma_fast": "sma_fast",
    "sma_fast_period": "sma_fast",
    "sma_short": "sma_fast",
    "short_sma": "sma_fast",

    "sma_slow": "sma_slow",
    "sma_slow_period": "sma_slow",
    "sma_long": "sma_slow",
    "long_sma": "sma_slow",

    # -------------------------
    # EMA
    # -------------------------

    "ema_fast": "ema_fast",
    "ema_fast_period": "ema_fast",
    "ema_filter_fast": "ema_fast",
    "ema_short": "ema_fast",

    "ema_slow": "ema_slow",
    "ema_slow_period": "ema_slow",
    "ema_filter_slow": "ema_slow",
    "ema_long": "ema_slow",

    # -------------------------
    # RSI
    # -------------------------

    "rsi_period": "rsi_period",

    "rsi_oversold": "rsi_oversold",
    "rsi_oversold_level": "rsi_oversold",

    "rsi_recovery_level": "rsi_oversold",
    "rsi_recovery_from_level": "rsi_oversold",

    "rsi_overbought": "rsi_overbought",
    "rsi_overbought_level": "rsi_overbought",

    # -------------------------
    # MACD
    # -------------------------

    "macd_fast": "macd_fast",
    "macd_slow": "macd_slow",
    "macd_signal": "macd_signal",

    # -------------------------
    # Bollinger
    # -------------------------

    "bollinger_period": "bollinger_period",
    "bb_period": "bollinger_period",

    "bollinger_std": "bollinger_std",
    "bb_std": "bollinger_std",

    # -------------------------
    # ATR
    # -------------------------

    "atr_period": "atr_period",
    "atr_length": "atr_period",

    # -------------------------
    # Volume
    # -------------------------

    "volume_period": "volume_period",

    # -------------------------
    # Signal thresholds
    # -------------------------

    "buy_threshold": "buy_threshold",
    "sell_threshold": "sell_threshold",

    "minimum_volume_ratio": "minimum_volume_ratio",
}


# ============================================================
# BACKTEST PARAMETER ALIASES
# ============================================================

BACKTEST_PARAMETER_ALIASES = {

    "stop_atr_multiplier": "stop_atr_multiplier",
    "stop_atr_multiple": "stop_atr_multiplier",
    "atr_stop_multiple": "stop_atr_multiplier",

    "target_atr_multiplier": "target_atr_multiplier",
    "target_atr_multiple": "target_atr_multiplier",
    "atr_target_multiple": "target_atr_multiplier",
}


# ============================================================
# INTEGER PARAMETERS
# ============================================================

INTEGER_SIGNAL_PARAMETERS = {
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

    "atr_period",

    "volume_period",

    "buy_threshold",
    "sell_threshold",
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


def safe_int(
    value: Any,
    default: Optional[int] = None,
) -> Optional[int]:

    try:
        return int(float(value))

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
        return value.strip()

    return str(value).strip()


def clean_dict(
    value: Any,
) -> Dict[str, Any]:

    if isinstance(value, dict):
        return value

    return {}


def clean_list(
    value: Any,
) -> List[Any]:

    if isinstance(value, list):
        return value

    return []


# ============================================================
# PARAMETER NAME NORMALIZATION
# ============================================================

def normalize_parameter_name(
    name: str,
) -> str:

    normalized = clean_string(
        name
    ).lower()

    return PARAMETER_ALIASES.get(
        normalized,
        normalized,
    )


def normalize_backtest_parameter_name(
    name: str,
) -> str:

    normalized = clean_string(
        name
    ).lower()

    return BACKTEST_PARAMETER_ALIASES.get(
        normalized,
        normalized,
    )


# ============================================================
# EXTRACT RAW STRATEGY PARAMETERS
# ============================================================

def get_strategy_parameters(
    strategy: Dict[str, Any],
) -> Dict[str, Any]:

    strategy = clean_dict(
        strategy
    )

    return clean_dict(
        strategy.get(
            "parameters"
        )
    )


# ============================================================
# SIGNAL PARAMETERS
# ============================================================

def extract_signal_parameters(
    strategy: Dict[str, Any],
) -> Dict[str, Any]:

    raw_parameters = get_strategy_parameters(
        strategy
    )

    config = dict(
        DEFAULT_SIGNAL_CONFIG
    )

    extracted = {}

    for raw_name, raw_value in raw_parameters.items():

        parameter_name = normalize_parameter_name(
            raw_name
        )

        if parameter_name not in config:
            continue

        if isinstance(
            raw_value,
            bool,
        ):
            continue

        numeric_value = safe_float(
            raw_value
        )

        if numeric_value is None:
            continue

        if parameter_name in INTEGER_SIGNAL_PARAMETERS:
            numeric_value = safe_int(
                numeric_value
            )

        config[
            parameter_name
        ] = numeric_value

        extracted[
            parameter_name
        ] = numeric_value

    return {
        "config": config,
        "extracted": extracted,
    }


# ============================================================
# BACKTEST PARAMETERS
# ============================================================

def extract_backtest_parameters(
    strategy: Dict[str, Any],
) -> Dict[str, Any]:

    raw_parameters = get_strategy_parameters(
        strategy
    )

    config = dict(
        DEFAULT_BACKTEST_CONFIG
    )

    extracted = {}

    for raw_name, raw_value in raw_parameters.items():

        parameter_name = (
            normalize_backtest_parameter_name(
                raw_name
            )
        )

        if parameter_name not in config:
            continue

        numeric_value = safe_float(
            raw_value
        )

        if numeric_value is None:
            continue

        config[
            parameter_name
        ] = numeric_value

        extracted[
            parameter_name
        ] = numeric_value

    return {
        "config": config,
        "extracted": extracted,
    }


# ============================================================
# CONDITIONS
# ============================================================

def extract_conditions(
    strategy: Dict[str, Any],
) -> Dict[str, Any]:

    strategy = clean_dict(
        strategy
    )

    conditions = clean_dict(
        strategy.get(
            "conditions"
        )
    )

    rules = clean_dict(
        strategy.get(
            "rules"
        )
    )

    return {
        "logic": clean_string(
            conditions.get(
                "logic"
            ),
            "UNKNOWN",
        ).upper(),

        "required": clean_list(
            conditions.get(
                "required"
            )
        ),

        "confirmation": clean_list(
            conditions.get(
                "confirmation"
            )
        ),

        "optional": clean_list(
            conditions.get(
                "optional"
            )
        ),

        "entry": clean_list(
            rules.get(
                "entry"
            )
        ),

        "confirmation_rules": clean_list(
            rules.get(
                "confirmation"
            )
        ),

        "exit": clean_list(
            rules.get(
                "exit"
            )
        ),

        "risk": clean_list(
            rules.get(
                "risk"
            )
        ),

        "filters": clean_list(
            rules.get(
                "filters"
            )
        ),
    }


# ============================================================
# STRATEGY VALIDATION
# ============================================================

def validate_strategy(
    strategy: Dict[str, Any],
) -> Dict[str, Any]:

    strategy = clean_dict(
        strategy
    )

    problems = []
    warnings = []

    strategy_id = clean_string(
        strategy.get(
            "id"
        )
    )

    strategy_name = clean_string(
        strategy.get(
            "name"
        )
    )

    if not strategy_name:
        problems.append(
            "Strategy name bulunamadı."
        )

    parameters = get_strategy_parameters(
        strategy
    )

    if not parameters:
        warnings.append(
            "Stratejide parametre bulunmuyor."
        )

    conditions = extract_conditions(
        strategy
    )

    if not conditions["entry"]:
        warnings.append(
            "ENTRY kuralı bulunmuyor."
        )

    if not conditions["exit"]:
        warnings.append(
            "EXIT kuralı bulunmuyor."
        )

    if not conditions["risk"]:
        warnings.append(
            "RISK kuralı bulunmuyor."
        )

    signal_data = extract_signal_parameters(
        strategy
    )

    backtest_data = extract_backtest_parameters(
        strategy
    )

    # --------------------------------------------------------
    # Signal config validation
    # --------------------------------------------------------

    signal_config = signal_data[
        "config"
    ]

    if signal_config["sma_fast"] >= signal_config["sma_slow"]:
        warnings.append(
            "SMA fast >= SMA slow."
        )

    if signal_config["ema_fast"] >= signal_config["ema_slow"]:
        warnings.append(
            "EMA fast >= EMA slow."
        )

    if not (
        0 < signal_config["rsi_oversold"] < 100
    ):
        problems.append(
            "RSI oversold değeri geçersiz."
        )

    if not (
        0 < signal_config["rsi_overbought"] < 100
    ):
        problems.append(
            "RSI overbought değeri geçersiz."
        )

    if (
        signal_config["rsi_oversold"]
        >=
        signal_config["rsi_overbought"]
    ):
        warnings.append(
            "RSI oversold >= overbought."
        )

    # --------------------------------------------------------
    # Backtest config validation
    # --------------------------------------------------------

    backtest_config = backtest_data[
        "config"
    ]

    if (
        backtest_config[
            "stop_atr_multiplier"
        ]
        <= 0
    ):
        problems.append(
            "Stop ATR multiplier 0'dan büyük olmalıdır."
        )

    if (
        backtest_config[
            "target_atr_multiplier"
        ]
        <= 0
    ):
        problems.append(
            "Target ATR multiplier 0'dan büyük olmalıdır."
        )

    return {
        "valid": len(problems) == 0,

        "strategy_id": strategy_id,

        "problems": problems,

        "warnings": warnings,
    }


# ============================================================
# BUILD ADAPTED STRATEGY
# ============================================================

def adapt_strategy(
    strategy: Dict[str, Any],
) -> Dict[str, Any]:

    strategy = clean_dict(
        strategy
    )

    validation = validate_strategy(
        strategy
    )

    signal_data = extract_signal_parameters(
        strategy
    )

    backtest_data = extract_backtest_parameters(
        strategy
    )

    conditions = extract_conditions(
        strategy
    )

    result = {
        "adapter_version": ADAPTER_VERSION,

        "strategy_id": clean_string(
            strategy.get(
                "id"
            )
        ),

        "strategy_name": clean_string(
            strategy.get(
                "name"
            ),
            "Unnamed Strategy",
        ),

        "status": clean_string(
            strategy.get(
                "status"
            ),
            "HYPOTHESIS",
        ),

        "market": clean_string(
            strategy.get(
                "market"
            ),
            "Unknown",
        ),

        "symbols": clean_list(
            strategy.get(
                "symbols"
            )
        ),

        "tags": clean_list(
            strategy.get(
                "tags"
            )
        ),

        "signal_config": signal_data[
            "config"
        ],

        "backtest_config": backtest_data[
            "config"
        ],

        "extracted_signal_parameters": (
            signal_data[
                "extracted"
            ]
        ),

        "extracted_backtest_parameters": (
            backtest_data[
                "extracted"
            ]
        ),

        "conditions": conditions,

        "validation": validation,

        # Güvenlik
        "research_only": True,

        "execution_enabled": False,
    }

    return result


# ============================================================
# KNOWLEDGE BASE'DEN STRATEGY AL
# ============================================================

def load_strategy_by_id(
    strategy_id: str,
) -> Optional[Dict[str, Any]]:

    strategy_id = clean_string(
        strategy_id
    )

    if not strategy_id:
        return None

    try:

        strategy = get_strategy(
            strategy_id
        )

    except Exception as exc:

        print(
            f"❌ Strategy alınamadı: {exc}"
        )

        return None

    if not strategy:
        return None

    return strategy


# ============================================================
# STRATEGY SEARCH
# ============================================================

def find_strategy(
    query: str,
) -> Optional[Dict[str, Any]]:

    query = clean_string(
        query
    )

    if not query:
        return None

    try:

        strategies = search_strategies(
            query
        )

    except Exception as exc:

        print(
            f"❌ Strategy search hatası: {exc}"
        )

        return None

    if not strategies:
        return None

    return strategies[0]


# ============================================================
# FIND + ADAPT
# ============================================================

def find_and_adapt_strategy(
    query: str,
) -> Optional[Dict[str, Any]]:

    strategy = find_strategy(
        query
    )

    if strategy is None:
        return None

    return adapt_strategy(
        strategy
    )


# ============================================================
# SAVE JSON
# ============================================================

def save_adapter_json(
    adapted_strategy: Dict[str, Any],
    output_path: str,
) -> str:

    path = (
        Path(
            output_path
        )
        .expanduser()
        .resolve()
    )

    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    path.write_text(
        json.dumps(
            adapted_strategy,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    return str(path)


# ============================================================
# PRINT LIST
# ============================================================

def print_list(
    title: str,
    values: List[Any],
    indent: int = 2,
) -> None:

    print()
    print(
        " " * indent
        + title
    )

    if not values:
        print(
            " " * (indent + 2)
            + "- Yok"
        )

        return

    for value in values:

        print(
            " " * (indent + 2)
            + f"- {value}"
        )


# ============================================================
# PRINT ADAPTED STRATEGY
# ============================================================

def print_adapted_strategy(
    adapted: Dict[str, Any],
) -> None:

    print()
    print(
        "=" * 70
    )

    print(
        "🔌 STRATEGY ADAPTER V1"
    )

    print(
        "=" * 70
    )

    print(
        f"Strategy ID : "
        f"{adapted.get('strategy_id', '-')}"
    )

    print(
        f"Strategy    : "
        f"{adapted.get('strategy_name', '-')}"
    )

    print(
        f"Status      : "
        f"{adapted.get('status', '-')}"
    )

    print(
        f"Market      : "
        f"{adapted.get('market', '-')}"
    )

    symbols = adapted.get(
        "symbols",
        [],
    )

    print(
        "Symbols     : "
        + (
            ", ".join(
                str(symbol)
                for symbol in symbols
            )
            if symbols
            else "-"
        )
    )

    # --------------------------------------------------------
    # Signal config
    # --------------------------------------------------------

    print()
    print(
        "SIGNAL ENGINE CONFIG:"
    )

    signal_config = adapted.get(
        "signal_config",
        {},
    )

    for key, value in signal_config.items():

        print(
            f"  - {key}: {value}"
        )

    # --------------------------------------------------------
    # Backtest config
    # --------------------------------------------------------

    print()
    print(
        "BACKTEST CONFIG:"
    )

    backtest_config = adapted.get(
        "backtest_config",
        {},
    )

    for key, value in backtest_config.items():

        print(
            f"  - {key}: {value}"
        )

    # --------------------------------------------------------
    # Conditions
    # --------------------------------------------------------

    print()
    print(
        "CONDITION STRUCTURE:"
    )

    conditions = adapted.get(
        "conditions",
        {},
    )

    print(
        f"  Logic: "
        f"{conditions.get('logic', 'UNKNOWN')}"
    )

    print_list(
        "REQUIRED:",
        conditions.get(
            "required",
            [],
        ),
        indent=2,
    )

    print_list(
        "CONFIRMATION:",
        conditions.get(
            "confirmation",
            [],
        ),
        indent=2,
    )

    print_list(
        "ENTRY:",
        conditions.get(
            "entry",
            [],
        ),
        indent=2,
    )

    print_list(
        "CONFIRMATION RULES:",
        conditions.get(
            "confirmation_rules",
            [],
        ),
        indent=2,
    )

    print_list(
        "FILTERS:",
        conditions.get(
            "filters",
            [],
        ),
        indent=2,
    )

    print_list(
        "EXIT:",
        conditions.get(
            "exit",
            [],
        ),
        indent=2,
    )

    print_list(
        "RISK:",
        conditions.get(
            "risk",
            [],
        ),
        indent=2,
    )

    # --------------------------------------------------------
    # Validation
    # --------------------------------------------------------

    print()
    print(
        "VALIDATION:"
    )

    validation = adapted.get(
        "validation",
        {},
    )

    print(
        f"  Valid    : "
        f"{validation.get('valid', False)}"
    )

    problems = validation.get(
        "problems",
        [],
    )

    warnings = validation.get(
        "warnings",
        [],
    )

    if problems:

        print()
        print(
            "  PROBLEMS:"
        )

        for problem in problems:

            print(
                f"    ❌ {problem}"
            )

    if warnings:

        print()
        print(
            "  WARNINGS:"
        )

        for warning in warnings:

            print(
                f"    ⚠️ {warning}"
            )

    if not problems and not warnings:

        print(
            "  Problems : Yok"
        )

        print(
            "  Warnings : Yok"
        )

    # --------------------------------------------------------
    # Safety
    # --------------------------------------------------------

    print()
    print(
        f"Research Only       : "
        f"{adapted.get('research_only', True)}"
    )

    print(
        f"Execution Enabled   : "
        f"{adapted.get('execution_enabled', False)}"
    )

    print(
        "=" * 70
    )


# ============================================================
# DEMO STRATEGY
# ============================================================

DEMO_STRATEGY = {

    "id": "STR-DEMO-001",

    "name": (
        "SMA 10/100 Trend Takip Stratejisi"
    ),

    "status": "HYPOTHESIS",

    "market": "BIST",

    "symbols": [
        "THYAO.IS",
    ],

    "tags": [
        "trend-following",
        "SMA",
        "EMA",
        "RSI",
        "ATR",
    ],

    "parameters": {

        "sma_fast": 10,

        "sma_slow": 100,

        "ema_fast": 20,

        "ema_slow": 30,

        "rsi_period": 14,

        "rsi_recovery_level": 30,

        "rsi_confirmation_level": 50,

        "stop_atr_multiple": 1.5,

        "target_atr_multiple": 3,
    },

    "conditions": {

        "logic": "UNKNOWN",

        "required": [
            (
                "SMA 10'un SMA 100'ün üzerine "
                "çıkması ana long giriş koşuludur."
            ),
        ],

        "confirmation": [
            (
                "RSI 14'ün 30 seviyesinin altından "
                "toparlanarak 50 seviyesinin üzerine "
                "çıkması momentum teyididir."
            ),
        ],

        "optional": [],
    },

    "rules": {

        "entry": [
            (
                "SMA 10, SMA 100'ün üzerine "
                "çıktığında long giriş düşünülür."
            ),
        ],

        "confirmation": [
            (
                "RSI 14, 30 seviyesinden toparlanıp "
                "50 seviyesinin üzerine çıktığında "
                "momentum teyidi sağlanır."
            ),
        ],

        "exit": [
            "Giriş fiyatından 1.5 ATR uzaklıkta stop.",
            "Giriş fiyatından 3 ATR uzaklıkta hedef.",
        ],

        "risk": [
            "Stop mesafesi 1.5 ATR.",
            "Hedef mesafesi 3 ATR.",
        ],

        "filters": [
            "EMA 20 > EMA 30 long trend filtresi.",
        ],
    },
}


# ============================================================
# DEMO
# ============================================================

def run_demo() -> None:

    print()
    print(
        "🧪 Demo Strategy Adapter çalışıyor..."
    )

    adapted = adapt_strategy(
        DEMO_STRATEGY
    )

    print_adapted_strategy(
        adapted
    )

    output_path = save_adapter_json(
        adapted,
        "strategy_adapter_output.json",
    )

    print()
    print(
        "💾 JSON kaydedildi:"
    )

    print(
        output_path
    )


# ============================================================
# RUN STRATEGY BY ID
# ============================================================

def run_strategy_by_id(
    strategy_id: str,
) -> None:

    print()
    print(
        f"🔎 Strategy aranıyor: "
        f"{strategy_id}"
    )

    strategy = load_strategy_by_id(
        strategy_id
    )

    if strategy is None:

        print()
        print(
            "❌ Strategy bulunamadı."
        )

        print(
            "Kontrol et:"
        )

        print(
            "- Strategy ID doğru mu?"
        )

        print(
            "- Knowledge Base çalışıyor mu?"
        )

        return

    adapted = adapt_strategy(
        strategy
    )

    print_adapted_strategy(
        adapted
    )

    output_name = (
        f"strategy_adapter_"
        f"{strategy_id}.json"
    )

    output_path = save_adapter_json(
        adapted,
        output_name,
    )

    print()
    print(
        "💾 Adapter çıktısı:"
    )

    print(
        output_path
    )


# ============================================================
# MAIN
# ============================================================

def main() -> None:

    print()
    print(
        "=" * 70
    )

    print(
        "MARKETHQ STRATEGY ADAPTER V1"
    )

    print(
        "=" * 70
    )

    # --------------------------------------------------------
    # Komut satırından Strategy ID geldiyse
    # --------------------------------------------------------

    if len(sys.argv) > 1:

        strategy_id = clean_string(
            sys.argv[1]
        )

        if not strategy_id:

            print(
                "❌ Geçersiz Strategy ID."
            )

            return

        run_strategy_by_id(
            strategy_id
        )

        return

    # --------------------------------------------------------
    # ID verilmediyse demo çalıştır
    # --------------------------------------------------------

    run_demo()


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":
    main()
