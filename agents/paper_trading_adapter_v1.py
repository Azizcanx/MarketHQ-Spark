"""
MarketHQ Paper Trading Adapter V1
=================================

Research-only historical paper simulation adapter.

Architecture:
    Experiment Definition
        -> Signal / Intent
        -> Mandatory Risk Gate
        -> Paper Order
        -> Fill Simulator
        -> Position
        -> Portfolio / Equity
        -> Paper Result

Safety:
    - no broker
    - no live execution
    - no operational DB writes
    - research-storage persistence is handled by Result Ingestion
    - kill switch can halt new paper entries
"""

from __future__ import annotations

import importlib.util
import json
import math
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Ensure the MarketHQ project root is importable when this adapter is
# launched directly as a subprocess from the agents directory.
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

ADAPTER_VERSION = "V1"
DEFAULT_PERIOD = "3y"
DEFAULT_INTERVAL = "1d"

RESEARCH_ONLY = True
EXECUTION_ENABLED = False
BROKER_EXECUTION_ENABLED = False
DATABASE_WRITE_ENABLED = False

DEFAULT_MAX_DRAWDOWN_PERCENT = 25.0
DEFAULT_MAX_POSITION_SIZE_PERCENT = 10.0
DEFAULT_MAX_CONSECUTIVE_LOSSES = 5


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def is_record(value: Any) -> bool:
    return isinstance(value, dict)


def clean_number(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
        if math.isfinite(number):
            return number
    except (TypeError, ValueError):
        pass
    return default


def text(value: Any, fallback: str = "") -> str:
    if isinstance(value, str) and value.strip():
        return value.strip()
    if isinstance(value, (int, float)) and math.isfinite(float(value)):
        return str(value)
    return fallback


REQUIRED_ENGINE_FUNCTIONS = (
    "load_history",
    "normalize_strategy_parameters",
    "prepare_signal_history",
    "get_signal_for_row",
    "open_position",
    "check_risk_exit",
    "close_position",
    "unrealized_pnl",
    "calculate_metrics",
    "clean_number",
)


def load_engine_module() -> tuple[Any, str]:
    candidates = [
        PROJECT_ROOT / "paper_trading_engine_v1.py",
        PROJECT_ROOT / "paper_trading_engine_v1_3.py",
        PROJECT_ROOT / "paper_trading_engine_v1_2.py",
        PROJECT_ROOT / "agents" / "paper_trading_engine_v1.py",
        PROJECT_ROOT / "agents" / "paper_trading_engine_v1_3.py",
        PROJECT_ROOT / "agents" / "paper_trading_engine_v1_2.py",
        PROJECT_ROOT / "agents" / "paper_trading_engine.py",
    ]

    checked: list[str] = []
    rejected: list[str] = []

    for engine_path in candidates:
        if not engine_path.exists():
            continue

        checked.append(str(engine_path))
        module_name = "markethq_existing_paper_engine"
        spec = importlib.util.spec_from_file_location(
            module_name,
            engine_path,
        )
        if spec is None or spec.loader is None:
            rejected.append(f"{engine_path}: invalid import spec")
            continue

        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module

        try:
            spec.loader.exec_module(module)
        except Exception as exc:
            rejected.append(f"{engine_path}: import failed: {exc}")
            sys.modules.pop(module_name, None)
            continue

        missing = [
            name
            for name in REQUIRED_ENGINE_FUNCTIONS
            if not callable(getattr(module, name, None))
        ]

        if missing:
            rejected.append(
                f"{engine_path}: missing callable API {missing}"
            )
            sys.modules.pop(module_name, None)
            continue

        return module, str(engine_path)

    raise RuntimeError(
        "No compatible MarketHQ Paper Trading Engine found. "
        f"Checked={checked}; rejected={rejected}"
    )


def normalize_history(
    raw: pd.DataFrame,
    start_date: str,
    end_date: str,
) -> pd.DataFrame:
    data = raw.copy()

    if "Datetime" in data.columns:
        data["Datetime"] = pd.to_datetime(
            data["Datetime"],
            errors="coerce",
            utc=True,
        )
        data = data.dropna(subset=["Datetime"]).set_index("Datetime")

    data.index = pd.to_datetime(
        data.index,
        errors="coerce",
        utc=True,
    )
    data = data[~data.index.isna()]
    data = data.sort_index()

    start = pd.Timestamp(start_date, tz="UTC")
    end = pd.Timestamp(end_date, tz="UTC")

    data = data[(data.index >= start) & (data.index <= end)]

    if len(data) < 30:
        raise ValueError(
            "Independent paper slice contains fewer than 30 usable bars: "
            f"{len(data)}."
        )

    return data


def get_experiment(payload: dict[str, Any]) -> dict[str, Any]:
    experiment = payload.get("experiment")
    if not is_record(experiment):
        raise ValueError("Missing experiment object.")
    return experiment


def get_market(experiment: dict[str, Any]) -> dict[str, Any]:
    market = experiment.get("market")
    if not is_record(market):
        raise ValueError("Experiment market definition is missing.")
    return market


def get_strategy(experiment: dict[str, Any]) -> dict[str, Any]:
    strategy = experiment.get("strategy")
    if not is_record(strategy):
        raise ValueError("Experiment strategy definition is missing.")
    return strategy


def get_date_scope(experiment: dict[str, Any]) -> dict[str, Any]:
    scope = experiment.get("dateScope")
    if not is_record(scope):
        raise ValueError("Experiment dateScope is missing.")
    return scope


def validate_experiment(experiment: dict[str, Any]) -> None:
    constraints = experiment.get("constraints")
    if not is_record(constraints):
        raise ValueError("Experiment constraints are missing.")

    if constraints.get("researchOnly") is not True:
        raise RuntimeError("Paper Trading requires researchOnly=true.")

    if constraints.get("executionEnabled") is not False:
        raise RuntimeError("Paper Trading requires executionEnabled=false.")

    if constraints.get("brokerExecutionEnabled") is not False:
        raise RuntimeError(
            "Paper Trading requires brokerExecutionEnabled=false."
        )

    if constraints.get("databaseWriteEnabled") is not False:
        raise RuntimeError(
            "Paper Trading requires databaseWriteEnabled=false."
        )

    market = get_market(experiment)
    timeframe = text(market.get("timeframe"), "1d")
    if timeframe != "1d":
        raise ValueError(
            f"Paper Trading V1 currently requires timeframe=1d; got {timeframe}."
        )

    scope = get_date_scope(experiment)
    if scope.get("selectionStatus") != "RESOLVED":
        raise ValueError(
            "Paper Trading requires a RESOLVED experiment date scope."
        )

    if scope.get("exactDatesRequired") is not True:
        raise ValueError(
            "Paper Trading requires exact historical dates."
        )

    if scope.get("independentSliceRequired") is not True:
        raise ValueError(
            "Paper Trading requires an independent slice."
        )

    if not text(scope.get("independentSliceStartDate")):
        raise ValueError("Independent slice start date is missing.")

    if not text(scope.get("independentSliceEndDate")):
        raise ValueError("Independent slice end date is missing.")


def parse_positive_env(name: str, default: float) -> float:
    value = clean_number(os.getenv(name), default)
    return value if value > 0 else default


def parse_positive_int_env(name: str, default: int) -> int:
    value = clean_number(os.getenv(name), float(default))
    integer = int(value)
    return integer if integer > 0 else default


def risk_gate(
    *,
    signal: str,
    position: Any,
    equity: float,
    peak_equity: float,
    consecutive_losses: int,
    position_size_percent: float,
    max_position_size_percent: float,
    max_drawdown_percent: float,
    max_consecutive_losses: int,
    kill_switch: bool,
) -> tuple[bool, list[str]]:
    reasons: list[str] = []

    if kill_switch:
        reasons.append("KILL_SWITCH_ACTIVE")

    if signal not in {"BUY", "SELL"}:
        reasons.append("NO_ENTRY_SIGNAL")

    if position is not None:
        reasons.append("ONE_POSITION_AT_A_TIME")

    if position_size_percent > max_position_size_percent:
        reasons.append("POSITION_SIZE_LIMIT")

    if peak_equity > 0:
        drawdown = (peak_equity - equity) / peak_equity * 100.0
        if drawdown >= max_drawdown_percent:
            reasons.append("MAX_DRAWDOWN_LIMIT")

    if consecutive_losses >= max_consecutive_losses:
        reasons.append("MAX_CONSECUTIVE_LOSSES")

    return len(reasons) == 0, reasons


def run_paper_simulation(
    *,
    engine: Any,
    experiment: dict[str, Any],
    history: pd.DataFrame,
) -> dict[str, Any]:
    strategy = get_strategy(experiment)

    signal_config, risk_config = engine.normalize_strategy_parameters(
        strategy
    )

    leaked = set(signal_config) & set(engine.RISK_CONFIG_KEYS)
    if leaked:
        raise RuntimeError(
            "STOP: risk parameters leaked into Signal Engine config: "
            f"{sorted(leaked)}"
        )

    data = engine.prepare_signal_history(
        history,
        signal_config,
    )

    trades: list[Any] = []
    equity_curve: list[dict[str, Any]] = []
    order_lifecycle: list[dict[str, Any]] = []
    risk_events: list[dict[str, Any]] = []

    signal_counts = {
        "BUY": 0,
        "SELL": 0,
        "WAIT": 0,
        "ERROR": 0,
    }

    position = None
    next_trade_id = 1
    realized_pnl = 0.0
    peak_equity = engine.INITIAL_CAPITAL
    consecutive_losses = 0

    position_size_percent = parse_positive_env(
        "MARKETHQ_PAPER_POSITION_SIZE_PERCENT",
        float(engine.POSITION_SIZE_PERCENT),
    )
    max_position_size_percent = parse_positive_env(
        "MARKETHQ_PAPER_MAX_POSITION_SIZE_PERCENT",
        DEFAULT_MAX_POSITION_SIZE_PERCENT,
    )
    max_drawdown_percent = parse_positive_env(
        "MARKETHQ_PAPER_MAX_DRAWDOWN_PERCENT",
        DEFAULT_MAX_DRAWDOWN_PERCENT,
    )
    max_consecutive_losses = parse_positive_int_env(
        "MARKETHQ_PAPER_MAX_CONSECUTIVE_LOSSES",
        DEFAULT_MAX_CONSECUTIVE_LOSSES,
    )
    kill_switch = (
        os.getenv("MARKETHQ_PAPER_KILL_SWITCH", "false").strip().lower()
        == "true"
    )

    if abs(position_size_percent - float(engine.POSITION_SIZE_PERCENT)) > 1e-9:
        raise ValueError(
            "Paper Trading V1 requires the existing engine position size "
            f"of {engine.POSITION_SIZE_PERCENT}%; requested "
            f"{position_size_percent}%."
        )

    for bar_index, (timestamp, row) in enumerate(data.iterrows()):
        close_price = engine.clean_number(row.get("Close"))

        if close_price <= 0:
            continue

        signal, raw_signal = engine.get_signal_for_row(
            row,
            signal_config,
        )

        signal_counts[signal] = signal_counts.get(signal, 0) + 1
        timestamp_text = str(timestamp)

        # Exit lifecycle is evaluated before a new entry on the same bar.
        if position is not None:
            exit_reason = engine.check_risk_exit(
                position,
                row,
            )

            if exit_reason is None:
                opposite_signal = (
                    position.side == "LONG" and signal == "SELL"
                ) or (
                    position.side == "SHORT" and signal == "BUY"
                )

                if opposite_signal:
                    exit_reason = "OPPOSITE_SIGNAL"

            if exit_reason is None:
                max_holding = risk_config.get("max_holding_bars")
                if max_holding is not None:
                    max_holding_int = int(
                        max(
                            1,
                            engine.clean_number(max_holding, 1.0),
                        )
                    )
                    if bar_index - position.entry_bar >= max_holding_int:
                        exit_reason = "MAX_HOLDING_BARS"

            if exit_reason is not None:
                exit_intent_id = (
                    f"{experiment['experimentId']}-EXIT-{bar_index}-"
                    f"{position.side}"
                )

                order_lifecycle.append(
                    {
                        "intentId": exit_intent_id,
                        "stage": "EXIT_INTENT",
                        "timestamp": timestamp_text,
                        "side": position.side,
                        "signal": signal,
                        "reason": exit_reason,
                    }
                )

                trade = engine.close_position(
                    position=position,
                    market_price=close_price,
                    bar_index=bar_index,
                    timestamp=timestamp_text,
                    reason=exit_reason,
                    trade_id=next_trade_id,
                )

                trades.append(trade)
                realized_pnl += trade.net_pnl

                if trade.net_pnl < 0:
                    consecutive_losses += 1
                elif trade.net_pnl > 0:
                    consecutive_losses = 0

                order_lifecycle.append(
                    {
                        "intentId": exit_intent_id,
                        "stage": "FILLED",
                        "timestamp": timestamp_text,
                        "side": position.side,
                        "fillPrice": trade.exit_price,
                        "quantity": trade.quantity,
                        "reason": exit_reason,
                        "tradeId": trade.trade_id,
                        "netPnl": trade.net_pnl,
                    }
                )

                next_trade_id += 1
                position = None

        equity = engine.INITIAL_CAPITAL + realized_pnl
        if position is not None:
            equity += engine.unrealized_pnl(
                position,
                close_price,
            )

        peak_equity = max(peak_equity, equity)

        if position is None and signal in {"BUY", "SELL"}:
            intent_id = (
                f"{experiment['experimentId']}-ENTRY-{bar_index}-{signal}"
            )

            # Duplicate-order protection.
            duplicate = any(
                item.get("intentId") == intent_id
                for item in order_lifecycle
            )

            if duplicate:
                risk_events.append(
                    {
                        "timestamp": timestamp_text,
                        "intentId": intent_id,
                        "event": "DUPLICATE_ORDER_BLOCKED",
                    }
                )
            else:
                order_lifecycle.append(
                    {
                        "intentId": intent_id,
                        "stage": "ENTRY_INTENT",
                        "timestamp": timestamp_text,
                        "signal": signal,
                        "side": "LONG" if signal == "BUY" else "SHORT",
                        "price": close_price,
                    }
                )

                approved, reasons = risk_gate(
                    signal=signal,
                    position=position,
                    equity=equity,
                    peak_equity=peak_equity,
                    consecutive_losses=consecutive_losses,
                    position_size_percent=position_size_percent,
                    max_position_size_percent=max_position_size_percent,
                    max_drawdown_percent=max_drawdown_percent,
                    max_consecutive_losses=max_consecutive_losses,
                    kill_switch=kill_switch,
                )

                if not approved:
                    risk_events.append(
                        {
                            "timestamp": timestamp_text,
                            "intentId": intent_id,
                            "event": "ENTRY_REJECTED",
                            "reasons": reasons,
                        }
                    )
                    order_lifecycle.append(
                        {
                            "intentId": intent_id,
                            "stage": "RISK_REJECTED",
                            "timestamp": timestamp_text,
                            "reasons": reasons,
                        }
                    )
                else:
                    order_lifecycle.append(
                        {
                            "intentId": intent_id,
                            "stage": "RISK_APPROVED",
                            "timestamp": timestamp_text,
                        }
                    )

                    atr = engine.clean_number(row.get("ATR"))
                    side = "LONG" if signal == "BUY" else "SHORT"

                    position = engine.open_position(
                        side=side,
                        market_price=close_price,
                        atr=atr,
                        bar_index=bar_index,
                        timestamp=timestamp_text,
                        risk_config=risk_config,
                    )

                    order_lifecycle.append(
                        {
                            "intentId": intent_id,
                            "stage": "FILLED",
                            "timestamp": timestamp_text,
                            "side": side,
                            "fillPrice": position.entry_price,
                            "quantity": position.quantity,
                            "stopPrice": position.stop_price,
                            "targetPrice": position.target_price,
                        }
                    )

        equity = engine.INITIAL_CAPITAL + realized_pnl
        if position is not None:
            equity += engine.unrealized_pnl(
                position,
                close_price,
            )

        peak_equity = max(peak_equity, equity)

        equity_curve.append(
            {
                "timestamp": timestamp_text,
                "close": round(close_price, 6),
                "signal": signal,
                "equity": round(equity, 4),
                "cash": round(engine.INITIAL_CAPITAL + realized_pnl, 4),
                "position": position.side if position is not None else None,
                "raw_signal": raw_signal,
            }
        )

    if position is not None and len(data) > 0:
        final_timestamp = data.iloc[-1].name
        final_price = engine.clean_number(data.iloc[-1].get("Close"))
        exit_intent_id = (
            f"{experiment['experimentId']}-EXIT-END-{position.side}"
        )

        order_lifecycle.append(
            {
                "intentId": exit_intent_id,
                "stage": "EXIT_INTENT",
                "timestamp": str(final_timestamp),
                "side": position.side,
                "reason": "END_OF_DATA",
            }
        )

        trade = engine.close_position(
            position=position,
            market_price=final_price,
            bar_index=len(data) - 1,
            timestamp=str(final_timestamp),
            reason="END_OF_DATA",
            trade_id=next_trade_id,
        )

        trades.append(trade)
        realized_pnl += trade.net_pnl

        order_lifecycle.append(
            {
                "intentId": exit_intent_id,
                "stage": "FILLED",
                "timestamp": str(final_timestamp),
                "side": position.side,
                "fillPrice": trade.exit_price,
                "quantity": trade.quantity,
                "reason": "END_OF_DATA",
                "tradeId": trade.trade_id,
                "netPnl": trade.net_pnl,
            }
        )

        position = None

        if equity_curve:
            equity_curve[-1]["equity"] = round(
                engine.INITIAL_CAPITAL + realized_pnl,
                4,
            )
            equity_curve[-1]["cash"] = round(
                engine.INITIAL_CAPITAL + realized_pnl,
                4,
            )
            equity_curve[-1]["position"] = None

    metrics = engine.calculate_metrics(
        trades=trades,
        equity_curve=equity_curve,
    )

    return {
        "status": "COMPLETED",
        "engine": "MarketHQ Paper Trading Engine",
        "engineVersion": getattr(engine, "__version__", "V1.3"),
        "adapter": "MarketHQ Paper Trading Adapter",
        "adapterVersion": ADAPTER_VERSION,
        "experimentId": text(experiment.get("experimentId")),
        "strategyId": text(strategy.get("strategyId")),
        "strategyName": text(strategy.get("name")),
        "symbol": text(get_market(experiment).get("symbol")),
        "timeframe": text(get_market(experiment).get("timeframe"), "1d"),
        "dateScope": get_date_scope(experiment),
        "bars": len(data),
        "start": str(data.index[0]),
        "end": str(data.index[-1]),
        "signalConfig": signal_config,
        "riskConfig": risk_config,
        "simulationConfig": {
            "initialCapital": engine.INITIAL_CAPITAL,
            "positionSizePercent": position_size_percent,
            "commissionPercent": engine.COMMISSION_PERCENT,
            "slippagePercent": engine.SLIPPAGE_PERCENT,
            "onePositionAtATime": True,
            "sameBarStopTargetRule": "STOP_FIRST",
        },
        "riskGate": {
            "enabled": True,
            "maxDrawdownPercent": max_drawdown_percent,
            "maxPositionSizePercent": max_position_size_percent,
            "maxConsecutiveLosses": max_consecutive_losses,
            "killSwitchActive": kill_switch,
        },
        "metrics": metrics,
        "signalCounts": signal_counts,
        "riskEvents": risk_events,
        "orderLifecycle": order_lifecycle,
        "trades": [
            {
                **engine.asdict(trade),
            }
            for trade in trades
        ],
        "equityCurve": equity_curve,
        "safety": {
            "researchOnly": True,
            "executionEnabled": False,
            "brokerExecutionEnabled": False,
            "databaseWriteEnabled": False,
            "brokerOrderPlaced": False,
            "operationalDatabaseWritePerformed": False,
            "researchStorageWritePerformed": False,
        },
        "persistence": {
            "mode": "RESULT_INGESTION",
            "writePerformed": False,
            "note": (
                "Paper result is returned to Result Ingestion; "
                "Research Storage persistence remains centralized there."
            ),
        },
    }


def run(payload: dict[str, Any]) -> dict[str, Any]:
    if not RESEARCH_ONLY or EXECUTION_ENABLED or BROKER_EXECUTION_ENABLED:
        raise RuntimeError(
            "SAFETY ERROR: Paper Trading Adapter must remain research-only."
        )

    experiment = get_experiment(payload)
    validate_experiment(experiment)

    market = get_market(experiment)
    symbol = text(market.get("symbol"))
    if not symbol:
        raise ValueError("Experiment market symbol is missing.")

    scope = get_date_scope(experiment)
    start_date = text(scope.get("independentSliceStartDate"))
    end_date = text(scope.get("independentSliceEndDate"))

    engine, engine_path = load_engine_module()

    # Market data in the existing BIST engine is keyed by Yahoo-style
    # tickers (for example THYAO.IS), while the Experiment Definition may
    # carry the canonical request symbol as THYAO. Keep the experiment
    # identity unchanged, but make history loading tolerant of that storage
    # convention. For non-BIST/US symbols we still try the original symbol
    # first, so we do not blindly append .IS to every ticker.
    try:
        raw_history = engine.load_history(
            symbol=symbol,
            period=DEFAULT_PERIOD,
            interval=DEFAULT_INTERVAL,
        )
    except Exception as first_exc:
        fallback_symbol = (
            symbol
            if symbol.upper().endswith(".IS")
            else f"{symbol}.IS"
        )

        if fallback_symbol.upper() == symbol.upper():
            raise

        try:
            raw_history = engine.load_history(
                symbol=fallback_symbol,
                period=DEFAULT_PERIOD,
                interval=DEFAULT_INTERVAL,
            )
        except Exception:
            # Preserve the original failure when the fallback is not usable;
            # this keeps the adapter error tied to the first requested symbol.
            raise first_exc

    history = normalize_history(
        raw_history,
        start_date,
        end_date,
    )

    result = run_paper_simulation(
        engine=engine,
        experiment=experiment,
        history=history,
    )

    result["enginePath"] = engine_path
    result["generatedAt"] = utc_now()
    result["researchExecutionPerformed"] = True
    result["backtestExecuted"] = False
    result["paperSimulationExecuted"] = True
    result["brokerOrderPlaced"] = False
    result["databaseWritePerformed"] = False

    return result


def main() -> int:
    try:
        raw = sys.stdin.read()
        if not raw.strip():
            raise ValueError("Paper Trading Adapter received empty stdin.")

        payload = json.loads(raw)
        if not is_record(payload):
            raise ValueError("Paper Trading Adapter payload must be an object.")

        output = run(payload)
        print(json.dumps(output, ensure_ascii=False, default=str))
        return 0

    except Exception as exc:
        print(
            json.dumps(
                {
                    "status": "FAILED",
                    "reason": "PAPER_TRADING_ADAPTER_ERROR",
                    "error": str(exc),
                    "researchExecutionPerformed": False,
                    "paperSimulationExecuted": False,
                    "brokerOrderPlaced": False,
                    "databaseWritePerformed": False,
                    "safety": {
                        "researchOnly": True,
                        "executionEnabled": False,
                        "brokerExecutionEnabled": False,
                        "databaseWriteEnabled": False,
                    },
                },
                ensure_ascii=False,
            )
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

