# -*- coding: utf-8 -*-
"""
MarketHQ Independent Strategy Evidence Runner V1
=================================================

Amaç
-----
Paper-trading sonucunu tekrar kullanmak yerine, seçilmiş stratejinin
parametrelerini okuyup bağımsız olarak backtest ve rolling holdout
çalıştırır.

Research only:
    EXECUTION_ENABLED = False
    gerçek emir / broker bağlantısı yoktur.

Çalıştırma
-----------
.\\.venv\\Scripts\\python.exe .\\agents\\independent_strategy_evidence_runner_v1.py

Belirli strateji:
.\\.venv\\Scripts\\python.exe .\\agents\\independent_strategy_evidence_runner_v1.py ^
    --strategy-id STR-43839FA9C6

Bu modül:
    - latest strategy selection JSON'u bulur.
    - STR-43839FA9C6 gibi strategy_id'yi çözer.
    - aynı signal/risk parametrelerini çıkarır.
    - 8 BIST sembolünde 1y full backtest yapar.
    - 3y veriyi 252 train / 63 holdout ile rolling şekilde değerlendirir.
    - maliyet öncesi ve maliyetli sonuçları ayrı raporlar.
    - her sembol için basit rejim ayrıştırması verir:
          UP_TREND / DOWN_OR_SIDEWAYS
      (20 günlük SMA'nın 100 günlük SMA üzeri olup olmamasına göre).
    - sonucu bağımsız evidence JSON olarak kaydeder.

Not:
    Bu bağımsız test "verified rule" üretmez.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd


# ============================================================================
# CONFIG
# ============================================================================

PROJECT_ROOT = Path(__file__).resolve().parents[1]

# Ensure the MarketHQ project root is importable when this script is executed
# directly from the agents directory.
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

SELECTION_DIR = PROJECT_ROOT / "strategy_selection_results"
OUTPUT_DIR = PROJECT_ROOT / "independent_strategy_evidence_results"

RESEARCH_ONLY = True
EXECUTION_ENABLED = False

DEFAULT_SYMBOLS = [
    "THYAO.IS",
    "ASELS.IS",
    "EREGL.IS",
    "TUPRS.IS",
    "AKBNK.IS",
    "GARAN.IS",
    "SISE.IS",
    "BIMAS.IS",
]

FULL_PERIOD = "1y"
HOLDOUT_PERIOD = "3y"
TRAIN_BARS = 252
HOLDOUT_BARS = 63
STEP_BARS = 63

BASE_COMMISSION = 0.10
BASE_SLIPPAGE = 0.05
ZERO_COMMISSION = 0.0
ZERO_SLIPPAGE = 0.0

STRATEGY_ID_PATTERN = re.compile(
    r"\bSTR-[A-Z0-9]{6,20}\b",
    re.IGNORECASE,
)


# ============================================================================
# IMPORTS FROM EXISTING MARKET HQ ENGINES
# ============================================================================

from agents.market_data_agent import get_bist_history
from backtest_engine import run_backtest


# ============================================================================
# HELPERS
# ============================================================================


# ============================================================================
# STRATEGY PARAMETER EXTRACTION
# ============================================================================

def recursively_find_dicts(value: Any) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []

    if isinstance(value, dict):
        found.append(value)
        for child in value.values():
            found.extend(recursively_find_dicts(child))

    elif isinstance(value, list):
        for child in value:
            found.extend(recursively_find_dicts(child))

    return found


def extract_parameters(strategy: dict[str, Any]) -> dict[str, Any]:
    """Collect parameter-like fields from the selected strategy record."""
    result: dict[str, Any] = {}

    for obj in recursively_find_dicts(strategy):
        for key, value in obj.items():
            key_text = str(key).strip()

            if key_text in {
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
                "stop_atr_multiple",
                "target_atr_multiple",
            }:
                result[key_text] = value
                continue

            # Compact keys used by MarketHQ strategy records, e.g.
            # sma_fast10, sma_slow100, rsi_period14.
            match = re.fullmatch(
                r"(sma_fast|sma_slow|ema_fast|ema_slow|rsi_period|"
                r"macd_fast|macd_slow|macd_signal|bollinger_period|"
                r"bollinger_std|atr_period|volume_period|"
                r"buy_threshold|sell_threshold|stop_atr_multiple|"
                r"target_atr_multiple)([-+]?\\d+(?:\\.\\d+)?)",
                key_text.lower(),
            )

            if match:
                base_key = match.group(1)
                suffix = match.group(2)
                result[base_key] = (
                    float(suffix)
                    if "." in suffix
                    else int(suffix)
                )

    return result


def normalize_strategy_parameters(
    strategy: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Split signal parameters from risk parameters."""
    raw = {}

    explicit = strategy.get("parameters")
    if isinstance(explicit, dict):
        raw.update(explicit)

    raw.update(
        {
            key: value
            for key, value in extract_parameters(strategy).items()
            if key not in raw
        }
    )

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
    }

    risk_keys = {
        "stop_atr_multiple",
        "target_atr_multiple",
    }

    signal_config = {
        key: raw[key]
        for key in signal_keys
        if key in raw
    }

    risk_config = {
        key: raw[key]
        for key in risk_keys
        if key in raw
    }

    return signal_config, risk_config

def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
        return number if math.isfinite(number) else default
    except (TypeError, ValueError):
        return default


def safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def save_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)


def recursively_find_strategy_records(
    value: Any,
    target_id: str,
) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []

    if isinstance(value, dict):
        sid = str(
            value.get("strategy_id")
            or value.get("id")
            or ""
        ).strip().upper()

        if sid == target_id.upper():
            found.append(value)

        for child in value.values():
            found.extend(
                recursively_find_strategy_records(
                    child,
                    target_id,
                )
            )

    elif isinstance(value, list):
        for child in value:
            found.extend(
                recursively_find_strategy_records(
                    child,
                    target_id,
                )
            )

    return found


def find_latest_selection_file() -> Path:
    files = sorted(
        SELECTION_DIR.glob("*.json"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )

    if not files:
        raise FileNotFoundError(
            f"Selection JSON bulunamadı: {SELECTION_DIR}"
        )

    return files[0]


def resolve_strategy_record(
    strategy_id: str,
    selection_file: Path,
) -> dict[str, Any]:
    selection = load_json(selection_file)
    matches = recursively_find_strategy_records(
        selection,
        strategy_id,
    )

    if matches:
        return matches[0]

    raise KeyError(
        f"{strategy_id} selection dosyasında bulunamadı: "
        f"{selection_file}"
    )


def extract_metrics(result: dict[str, Any]) -> dict[str, Any]:
    """Normalize the actual backtest_engine metrics schema."""
    metrics = result.get("metrics")

    if not isinstance(metrics, dict):
        metrics = {}

    return {
        "trades": safe_int(
            metrics.get("total_trades")
        ),
        "wins": safe_int(
            metrics.get("winning_trades")
            or metrics.get("wins")
        ),
        "losses": safe_int(
            metrics.get("losing_trades")
            or metrics.get("losses")
        ),
        "win_rate": safe_float(
            metrics.get("win_rate_percent")
            or metrics.get("win_rate")
        ),
        "profit_factor": safe_float(
            metrics.get("profit_factor")
            or metrics.get("pf")
        ),
        "net_pnl": safe_float(
            metrics.get("net_pnl")
        ),
        "return_percent": safe_float(
            metrics.get("total_return_percent")
            or metrics.get("return_percent")
        ),
        "max_drawdown_percent": safe_float(
            metrics.get("max_drawdown_percent")
            or metrics.get("max_drawdown")
        ),
        "avg_trade": safe_float(
            metrics.get("average_trade_pnl")
            or metrics.get("avg_trade")
        ),
    }


def make_backtest_config(
    commission_percent: float,
    slippage_percent: float,
    risk_config: dict[str, Any],
) -> dict[str, Any]:
    return {
        "initial_capital": 100000,
        "position_size_percent": 10.0,
        "commission_percent": commission_percent,
        "slippage_percent": slippage_percent,
        "allow_short": True,
        "one_position_at_a_time": True,
        "use_stop_loss": True,
        "use_take_profit": True,
        "stop_loss_atr_multiple": safe_float(
            risk_config.get("stop_atr_multiple"),
            2.0,
        ),
        "take_profit_atr_multiple": safe_float(
            risk_config.get("target_atr_multiple"),
            3.0,
        ),
        "exit_on_opposite_signal": True,
        "max_holding_bars": 30,
        "close_at_end": True,
    }


def add_regime_labels(
    data: pd.DataFrame,
) -> pd.DataFrame:
    df = data.copy()

    close = pd.to_numeric(
        df["Close"],
        errors="coerce",
    )

    sma20 = close.rolling(20).mean()
    sma100 = close.rolling(100).mean()

    df["__REGIME"] = "UNKNOWN"
    valid = sma100.notna()

    df.loc[
        valid & (sma20 >= sma100),
        "__REGIME",
    ] = "UP_TREND"

    df.loc[
        valid & (sma20 < sma100),
        "__REGIME",
    ] = "DOWN_OR_SIDEWAYS"

    return df


def regime_breakdown(
    data: pd.DataFrame,
    signal_config: dict[str, Any],
    backtest_config: dict[str, Any],
    symbol: str,
) -> dict[str, Any]:
    df = add_regime_labels(data)

    output: dict[str, Any] = {}

    for regime in (
        "UP_TREND",
        "DOWN_OR_SIDEWAYS",
    ):
        part = df.loc[
            df["__REGIME"] == regime
        ].drop(
            columns=["__REGIME"],
            errors="ignore",
        )

        if len(part) < 30:
            output[regime] = {
                "bars": int(len(part)),
                "status": "INSUFFICIENT",
                "metrics": {},
            }
            continue

        result = run_backtest(
            data=part,
            symbol=symbol,
            signal_config=signal_config,
            backtest_config=backtest_config,
        )

        output[regime] = {
            "bars": int(len(part)),
            "status": result.get(
                "status",
                "UNKNOWN",
            ),
            "metrics": extract_metrics(result),
        }

    return output


def run_backtest_bundle(
    *,
    data: pd.DataFrame,
    symbol: str,
    signal_config: dict[str, Any],
    risk_config: dict[str, Any],
) -> dict[str, Any]:
    base_config = make_backtest_config(
        BASE_COMMISSION,
        BASE_SLIPPAGE,
        risk_config,
    )

    zero_cost_config = make_backtest_config(
        ZERO_COMMISSION,
        ZERO_SLIPPAGE,
        risk_config,
    )

    with_cost = run_backtest(
        data=data,
        symbol=symbol,
        signal_config=signal_config,
        backtest_config=base_config,
    )

    cost_free = run_backtest(
        data=data,
        symbol=symbol,
        signal_config=signal_config,
        backtest_config=zero_cost_config,
    )

    return {
        "with_costs": {
            "status": with_cost.get("status", "UNKNOWN"),
            "metrics": extract_metrics(with_cost),
        },
        "cost_free": {
            "status": cost_free.get("status", "UNKNOWN"),
            "metrics": extract_metrics(cost_free),
        },
        "regime_with_costs": regime_breakdown(
            data,
            signal_config,
            base_config,
            symbol,
        ),
    }


def rolling_holdout(
    data: pd.DataFrame,
    symbol: str,
    signal_config: dict[str, Any],
    risk_config: dict[str, Any],
) -> dict[str, Any]:
    if len(data) < TRAIN_BARS + HOLDOUT_BARS:
        return {
            "status": "INSUFFICIENT_HISTORY",
            "folds": [],
        }

    folds: list[dict[str, Any]] = []
    start = 0
    fold_no = 0
    config = make_backtest_config(
        BASE_COMMISSION,
        BASE_SLIPPAGE,
        risk_config,
    )

    while start + TRAIN_BARS + HOLDOUT_BARS <= len(data):
        fold_no += 1

        train = data.iloc[
            start:start + TRAIN_BARS
        ].copy()

        holdout = data.iloc[
            start + TRAIN_BARS:
            start + TRAIN_BARS + HOLDOUT_BARS
        ].copy()

        # Fixed selected strategy is evaluated on the train and then untouched
        # holdout. No parameter tuning is performed in this independent test.
        train_result = run_backtest(
            data=train,
            symbol=symbol,
            signal_config=signal_config,
            backtest_config=config,
        )

        holdout_result = run_backtest(
            data=holdout,
            symbol=symbol,
            signal_config=signal_config,
            backtest_config=config,
        )

        folds.append(
            {
                "fold": fold_no,
                "train_start": str(train.index.min()),
                "train_end": str(train.index.max()),
                "holdout_start": str(holdout.index.min()),
                "holdout_end": str(holdout.index.max()),
                "train_metrics": extract_metrics(
                    train_result
                ),
                "holdout_metrics": extract_metrics(
                    holdout_result
                ),
            }
        )

        start += STEP_BARS

    positive = sum(
        1
        for fold in folds
        if safe_float(
            fold["holdout_metrics"].get(
                "return_percent"
            )
        ) > 0
    )

    negative = sum(
        1
        for fold in folds
        if safe_float(
            fold["holdout_metrics"].get(
                "return_percent"
            )
        ) < 0
    )

    return {
        "status": "OK",
        "folds": folds,
        "positive_folds": positive,
        "negative_folds": negative,
        "total_folds": len(folds),
    }


# ============================================================================
# MAIN
# ============================================================================

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--strategy-id",
        default="STR-43839FA9C6",
    )
    parser.add_argument(
        "--symbols",
        nargs="+",
        default=DEFAULT_SYMBOLS,
    )
    args = parser.parse_args()

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    selection_file = find_latest_selection_file()
    strategy = resolve_strategy_record(
        args.strategy_id,
        selection_file,
    )

    signal_config, risk_config = normalize_strategy_parameters(
        strategy
    )

    strategy_id = (
        str(
            strategy.get("strategy_id")
            or args.strategy_id
        )
        .strip()
        .upper()
    )

    strategy_name = str(
        strategy.get("strategy_name")
        or strategy.get("name")
        or "UNKNOWN_STRATEGY"
    ).strip()

    print("=" * 76)
    print("MARKETHQ INDEPENDENT STRATEGY EVIDENCE RUNNER V1.4")
    print("=" * 76)
    print(f"Strategy ID        : {strategy_id}")
    print(f"Strategy           : {strategy_name}")
    print(f"Selection file     : {selection_file.name}")
    print(f"Full period        : {FULL_PERIOD}")
    print(f"Holdout period     : {HOLDOUT_PERIOD}")
    print(f"Research Only      : {RESEARCH_ONLY}")
    print(f"Execution Enabled  : {EXECUTION_ENABLED}")
    print()

    all_results: dict[str, Any] = {}

    for symbol in args.symbols:
        print(
            f"[RUN] {symbol}"
        )

        try:
            full_data = get_bist_history(
                period=FULL_PERIOD,
                interval="1d",
            )

            holdout_data = get_bist_history(
                period=HOLDOUT_PERIOD,
                interval="1d",
            )

            def select_symbol(
                data: Any,
                wanted: str,
            ) -> pd.DataFrame:
                """Normalize get_bist_history output to one OHLCV DataFrame."""
                if isinstance(data, dict):
                    # Most direct form: {"THYAO.IS": DataFrame, ...}
                    for key in (
                        wanted,
                        wanted.upper(),
                        wanted.lower(),
                    ):
                        value = data.get(key)
                        if isinstance(value, pd.DataFrame):
                            return value.copy()

                    # Case-insensitive fallback.
                    for key, value in data.items():
                        if (
                            str(key).strip().upper()
                            == wanted.upper()
                            and isinstance(value, pd.DataFrame)
                        ):
                            return value.copy()

                    return pd.DataFrame()

                if not isinstance(data, pd.DataFrame):
                    return pd.DataFrame()

                if data.empty:
                    return data.copy()

                columns = list(data.columns)

                # MultiIndex columns from yfinance/multi-symbol downloads.
                if isinstance(data.columns, pd.MultiIndex):
                    wanted_upper = wanted.upper()
                    matches = []

                    for col in columns:
                        parts = [
                            str(x).strip()
                            for x in col
                        ]
                        if any(
                            part.upper() == wanted_upper
                            for part in parts
                        ):
                            matches.append(col)

                    if matches:
                        part = data.loc[:, matches].copy()

                        # Collapse a single-symbol OHLCV slice.
                        if isinstance(
                            part.columns,
                            pd.MultiIndex,
                        ) and len(matches) > 0:
                            flattened = []
                            for col in part.columns:
                                flattened.append(
                                    str(col[-1])
                                )
                            part.columns = flattened

                        return part

                required = {
                    "Open",
                    "High",
                    "Low",
                    "Close",
                    "Volume",
                }

                if required.issubset(
                    {str(x) for x in columns}
                ):
                    return data.copy()

                # Flat columns such as THYAO.IS_Close.
                prefix = wanted + "_"
                wanted_cols = [
                    col
                    for col in columns
                    if str(col).startswith(prefix)
                ]

                if wanted_cols:
                    part = data[wanted_cols].copy()
                    part.columns = [
                        str(col)[len(prefix):]
                        for col in part.columns
                    ]
                    return part

                return pd.DataFrame()

            full_data = get_bist_history(
                period=FULL_PERIOD,
                interval="1d",
            )

            holdout_data = get_bist_history(
                period=HOLDOUT_PERIOD,
                interval="1d",
            )

            full_symbol = select_symbol(
                full_data,
                symbol,
            )

            holdout_symbol = select_symbol(
                holdout_data,
                symbol,
            )

            if full_symbol.empty or holdout_symbol.empty:
                all_results[symbol] = {
                    "status": "NO_DATA",
                }
                print(
                    "  status=NO_DATA"
                )
                continue

            full_symbol.index = pd.to_datetime(
                full_symbol.index
            )
            holdout_symbol.index = pd.to_datetime(
                holdout_symbol.index
            )

            bundle = run_backtest_bundle(
                data=full_symbol,
                symbol=symbol,
                signal_config=signal_config,
                risk_config=risk_config,
            )

            holdout = rolling_holdout(
                data=holdout_symbol,
                symbol=symbol,
                signal_config=signal_config,
                risk_config=risk_config,
            )

            all_results[symbol] = {
                "bars_full": int(len(full_symbol)),
                "bars_holdout": int(len(holdout_symbol)),
                "full_backtest": bundle,
                "rolling_holdout": holdout,
            }

            print(
                "  cost_return="
                f"{bundle['with_costs']['metrics'].get('return_percent', 0):+.4f}% | "
                "PF="
                f"{bundle['with_costs']['metrics'].get('profit_factor', 0):.4f}"
            )
            print(
                "  cost_free_return="
                f"{bundle['cost_free']['metrics'].get('return_percent', 0):+.4f}%"
            )
            print(
                "  holdout_folds="
                f"{holdout.get('total_folds', 0)} | "
                f"positive={holdout.get('positive_folds', 0)} | "
                f"negative={holdout.get('negative_folds', 0)}"
            )

        except Exception as exc:
            all_results[symbol] = {
                "status": "ERROR",
                "error": f"{type(exc).__name__}: {exc}",
            }
            print(
                f"  ERROR: {type(exc).__name__}: {exc}"
            )

    positive_runs = 0
    negative_runs = 0
    cost_survivors = 0
    total_holdout_folds = 0
    total_positive_holdouts = 0

    for result in all_results.values():
        if result.get("status") in {
            "NO_DATA",
            "ERROR",
        }:
            continue

        return_percent = safe_float(
            result.get("full_backtest", {})
            .get("with_costs", {})
            .get("metrics", {})
            .get("return_percent")
        )

        zero_cost_return = safe_float(
            result.get("full_backtest", {})
            .get("cost_free", {})
            .get("metrics", {})
            .get("return_percent")
        )

        if return_percent > 0:
            positive_runs += 1
        elif return_percent < 0:
            negative_runs += 1

        if (
            return_percent > 0
            and zero_cost_return > 0
        ):
            cost_survivors += 1

        rolling = result.get(
            "rolling_holdout",
            {},
        )

        total_holdout_folds += safe_int(
            rolling.get("total_folds")
        )
        total_positive_holdouts += safe_int(
            rolling.get("positive_folds")
        )

    summary = {
        "symbols_tested": len(all_results),
        "positive_full_runs": positive_runs,
        "negative_full_runs": negative_runs,
        "cost_survivors": cost_survivors,
        "total_holdout_folds": total_holdout_folds,
        "positive_holdout_folds": total_positive_holdouts,
    }

    evidence = {
        "engine": "MARKETHQ_INDEPENDENT_STRATEGY_EVIDENCE_RUNNER",
        "version": "V1.3",
        "research_only": RESEARCH_ONLY,
        "execution_enabled": EXECUTION_ENABLED,
        "created_at": utc_now(),
        "strategy_id": strategy_id,
        "strategy_name": strategy_name,
        "selection_file": str(selection_file),
        "symbols": args.symbols,
        "signal_config": signal_config,
        "risk_config": risk_config,
        "cost_assumptions": {
            "base": {
                "commission_percent": BASE_COMMISSION,
                "slippage_percent": BASE_SLIPPAGE,
            },
            "cost_free": {
                "commission_percent": ZERO_COMMISSION,
                "slippage_percent": ZERO_SLIPPAGE,
            },
        },
        "periods": {
            "full_backtest": FULL_PERIOD,
            "rolling_holdout": HOLDOUT_PERIOD,
            "train_bars": TRAIN_BARS,
            "holdout_bars": HOLDOUT_BARS,
            "step_bars": STEP_BARS,
        },
        "regime_definition": (
            "UP_TREND when SMA20 >= SMA100; "
            "DOWN_OR_SIDEWAYS otherwise."
        ),
        "summary": summary,
        "results": all_results,
        "epistemic_status": (
            "Independent historical evidence only; "
            "not a verified rule and not a live signal."
        ),
    }

    timestamp = datetime.now().strftime(
        "%Y%m%d_%H%M%S"
    )

    output_path = (
        OUTPUT_DIR
        / f"independent_evidence_{strategy_id}_{timestamp}.json"
    )

    save_json(
        output_path,
        evidence,
    )

    print()
    print("=" * 76)
    print("INDEPENDENT EVIDENCE SUMMARY")
    print("=" * 76)
    print(
        f"Positive full runs     : {positive_runs}"
    )
    print(
        f"Negative full runs     : {negative_runs}"
    )
    print(
        f"Cost survivors         : {cost_survivors}"
    )
    print(
        f"Holdout folds          : {total_holdout_folds}"
    )
    print(
        f"Positive holdout folds : {total_positive_holdouts}"
    )
    print()
    print(
        f"Saved: {output_path}"
    )


if __name__ == "__main__":
    main()

