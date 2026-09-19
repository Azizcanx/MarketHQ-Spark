from __future__ import annotations

import json
import math
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd


# ============================================================================
# PATH / PROJECT IMPORTS
# ============================================================================

PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from agents.market_data_agent import get_bist_history
from backtest_engine import run_backtest
from paper_trading_engine_v1 import normalize_strategy_parameters


# ============================================================================
# ENGINE IDENTITY
# ============================================================================

ENGINE_NAME = "MarketHQ Research Execution Adapter"
ENGINE_VERSION = "1.0.0"


# ============================================================================
# HARD SAFETY CONTRACT
# ============================================================================

RESEARCH_ONLY = True
EXECUTION_ENABLED = False
DATABASE_WRITE_ENABLED = False
BROKER_EXECUTION_ENABLED = False


# ============================================================================
# DEFAULT BACKTEST CONFIG
# ============================================================================

DEFAULT_INITIAL_CAPITAL = 100_000.0
DEFAULT_POSITION_SIZE_PERCENT = 10.0

DEFAULT_COMMISSION_PERCENT = 0.10
DEFAULT_SLIPPAGE_PERCENT = 0.05

DEFAULT_STOP_ATR_MULTIPLE = 2.0
DEFAULT_TARGET_ATR_MULTIPLE = 3.0

DEFAULT_MAX_HOLDING_BARS = 30


# ============================================================================
# GENERIC HELPERS
# ============================================================================


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def safe_str(value: Any) -> str:
    if value is None:
        return ""

    return str(value).strip()


def safe_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value

    if isinstance(value, str):
        normalized = value.strip().lower()

        if normalized in {
            "true",
            "1",
            "yes",
            "y",
            "on",
        }:
            return True

        if normalized in {
            "false",
            "0",
            "no",
            "n",
            "off",
        }:
            return False

    return bool(value)


def safe_float(
    value: Any,
    default: float,
) -> float:
    try:
        if value is None:
            return default

        result = float(value)

        if not math.isfinite(result):
            return default

        return result

    except (
        TypeError,
        ValueError,
    ):
        return default


def json_safe(value: Any) -> Any:
    """
    Recursively convert pandas/numpy/scalar/date-like values into
    JSON-serializable Python values.
    """

    if value is None:
        return None

    if isinstance(value, dict):
        return {
            str(key): json_safe(item)
            for key, item in value.items()
        }

    if isinstance(value, (list, tuple, set)):
        return [
            json_safe(item)
            for item in value
        ]

    if isinstance(value, pd.Timestamp):
        return value.isoformat()

    if isinstance(value, pd.DatetimeIndex):
        return [
            item.isoformat()
            for item in value
        ]

    if isinstance(value, pd.Series):
        return {
            str(key): json_safe(item)
            for key, item in value.to_dict().items()
        }

    if isinstance(value, pd.DataFrame):
        return {
            "columns": [
                str(column)
                for column in value.columns
            ],
            "records": [
                json_safe(record)
                for record in value.to_dict(
                    orient="records"
                )
            ],
        }

    if hasattr(value, "item"):
        try:
            return json_safe(value.item())
        except Exception:
            pass

    if hasattr(value, "tolist"):
        try:
            return json_safe(value.tolist())
        except Exception:
            pass

    if isinstance(value, float):
        if not math.isfinite(value):
            return None

    if isinstance(value, (str, int, float, bool)):
        return value

    return str(value)


def first_non_empty(
    *values: Any,
) -> Any:
    for value in values:
        if value is None:
            continue

        if isinstance(value, str):
            if not value.strip():
                continue

        return value

    return None


# ============================================================================
# INPUT EXTRACTION
# ============================================================================


def extract_experiment(
    payload: dict[str, Any],
) -> dict[str, Any]:
    experiment = payload.get("experiment")

    if isinstance(experiment, dict):
        return experiment

    # Allow the adapter to receive the experiment object directly.
    return payload


def extract_experiment_id(
    experiment: dict[str, Any],
    payload: dict[str, Any],
) -> str:
    return safe_str(
        first_non_empty(
            experiment.get("experimentId"),
            experiment.get("experiment_id"),
            payload.get("experimentId"),
            payload.get("experiment_id"),
        )
    )


def extract_strategy(
    experiment: dict[str, Any],
) -> dict[str, Any]:
    strategy = experiment.get("strategy")

    if isinstance(strategy, dict):
        return strategy

    return {}


def extract_strategy_id(
    strategy: dict[str, Any],
) -> str:
    return safe_str(
        first_non_empty(
            strategy.get("strategyId"),
            strategy.get("strategy_id"),
            strategy.get("id"),
        )
    )


def extract_market_scope(
    experiment: dict[str, Any],
) -> tuple[str, str]:
    """
    Canonical Experiment Generator contract:

        experiment.market.symbol
        experiment.market.timeframe

    Legacy/fallback marketScope support is retained only for compatibility.
    """

    market = experiment.get("market")

    if not isinstance(market, dict):
        market = {}

    legacy_market = experiment.get("marketScope")

    if not isinstance(legacy_market, dict):
        legacy_market = {}

    symbol = safe_str(
        first_non_empty(
            market.get("symbol"),
            market.get("ticker"),
            market.get("instrument"),
            legacy_market.get("symbol"),
            legacy_market.get("ticker"),
            legacy_market.get("instrument"),
        )
    )

    timeframe = safe_str(
        first_non_empty(
            market.get("timeframe"),
            market.get("interval"),
            legacy_market.get("timeframe"),
            legacy_market.get("interval"),
        )
    )

    return symbol, timeframe


def extract_date_scope(
    experiment: dict[str, Any],
    payload: dict[str, Any],
) -> dict[str, Any]:
    """
    Canonical Generator contract:

        experiment.dateScope.selectionStatus
        experiment.dateScope.independentSliceStartDate
        experiment.dateScope.independentSliceEndDate

    Resolver aliases are accepted only as compatibility fallbacks.
    The adapter NEVER chooses dates itself.
    """

    experiment_scope = experiment.get("dateScope")

    if not isinstance(experiment_scope, dict):
        experiment_scope = {}

    payload_scope = payload.get("dateScope")

    if not isinstance(payload_scope, dict):
        payload_scope = {}

    merged = {}

    merged.update(payload_scope)
    merged.update(experiment_scope)

    selection_status = safe_str(
        first_non_empty(
            merged.get("selectionStatus"),
            merged.get("selection_status"),
        )
    ).upper()

    selection_source = safe_str(
        first_non_empty(
            merged.get("selectionSource"),
            merged.get("selection_source"),
        )
    )

    independent_start = first_non_empty(
        merged.get("independentSliceStartDate"),
        merged.get("independent_slice_start_date"),
        merged.get("independentStartDate"),
        merged.get("independent_start_date"),
        merged.get("independentStart"),
        merged.get("independent_start"),
    )

    independent_end = first_non_empty(
        merged.get("independentSliceEndDate"),
        merged.get("independent_slice_end_date"),
        merged.get("independentEndDate"),
        merged.get("independent_end_date"),
        merged.get("independentEnd"),
        merged.get("independent_end"),
    )

    return {
        "selectionStatus": selection_status,
        "selectionSource": selection_source,
        "independentSliceStartDate": (
            safe_str(independent_start)
            if independent_start is not None
            else ""
        ),
        "independentSliceEndDate": (
            safe_str(independent_end)
            if independent_end is not None
            else ""
        ),
        "startDate": safe_str(
            first_non_empty(
                merged.get("startDate"),
                merged.get("start_date"),
            )
        ),
        "endDate": safe_str(
            first_non_empty(
                merged.get("endDate"),
                merged.get("end_date"),
            )
        ),
        "validationStartDate": safe_str(
            first_non_empty(
                merged.get("validationStartDate"),
                merged.get("validation_start_date"),
            )
        ),
        "validationEndDate": safe_str(
            first_non_empty(
                merged.get("validationEndDate"),
                merged.get("validation_end_date"),
            )
        ),
        "holdoutStartDate": safe_str(
            first_non_empty(
                merged.get("holdoutStartDate"),
                merged.get("holdout_start_date"),
            )
        ),
        "holdoutEndDate": safe_str(
            first_non_empty(
                merged.get("holdoutEndDate"),
                merged.get("holdout_end_date"),
            )
        ),
    }


# ============================================================================
# SAFETY VALIDATION
# ============================================================================


def validate_safety_contract(
    experiment: dict[str, Any],
) -> list[str]:
    errors: list[str] = []

    constraints = experiment.get("constraints")

    if not isinstance(constraints, dict):
        constraints = {}

    research_only = constraints.get(
        "researchOnly",
        True,
    )

    execution_enabled = constraints.get(
        "executionEnabled",
        False,
    )

    database_write_enabled = constraints.get(
        "databaseWriteEnabled",
        False,
    )

    broker_execution_enabled = constraints.get(
        "brokerExecutionEnabled",
        False,
    )

    if safe_bool(research_only) is not True:
        errors.append(
            "constraints.researchOnly must be true"
        )

    if safe_bool(execution_enabled) is not False:
        errors.append(
            "constraints.executionEnabled must be false"
        )

    if safe_bool(database_write_enabled) is not False:
        errors.append(
            "constraints.databaseWriteEnabled must be false"
        )

    if safe_bool(broker_execution_enabled) is not False:
        errors.append(
            "constraints.brokerExecutionEnabled must be false"
        )

    return errors


# ============================================================================
# DATA HELPERS
# ============================================================================


def normalize_symbol(
    symbol: str,
) -> str:
    value = safe_str(symbol).upper()

    if value.endswith(".IS"):
        return value[:-3]

    return value


def select_symbol_history(
    history_results: Any,
    requested_symbol: str,
) -> pd.DataFrame | None:
    """
    get_bist_history() returns a dictionary keyed by BIST symbol.

    The helper also tolerates MultiIndex/single-symbol/prefixed formats
    because the underlying market-data implementation has historically
    exposed those variants.
    """

    requested = safe_str(
        requested_symbol
    ).upper()

    requested_clean = normalize_symbol(
        requested
    )

    if isinstance(history_results, dict):
        # Exact key first.
        for key, value in history_results.items():
            key_string = safe_str(key).upper()

            if key_string == requested:
                if isinstance(value, pd.DataFrame):
                    return value.copy()

            if normalize_symbol(key_string) == requested_clean:
                if isinstance(value, pd.DataFrame):
                    return value.copy()

        # Some providers return prefixed keys.
        for key, value in history_results.items():
            key_string = safe_str(key).upper()

            if requested_clean in normalize_symbol(
                key_string
            ):
                if isinstance(value, pd.DataFrame):
                    return value.copy()

        return None

    if isinstance(history_results, pd.DataFrame):
        return history_results.copy()

    return None


def normalize_ohlcv(
    data: pd.DataFrame,
) -> pd.DataFrame:
    frame = data.copy()

    # Handle MultiIndex columns.
    if isinstance(
        frame.columns,
        pd.MultiIndex,
    ):
        flattened: list[str] = []

        for column in frame.columns:
            parts = [
                safe_str(part)
                for part in column
                if safe_str(part)
            ]

            flattened.append(
                "_".join(parts)
            )

        frame.columns = flattened

    # Build case-insensitive column map.
    column_map = {
        safe_str(column).strip().lower(): column
        for column in frame.columns
    }

    required = [
        "open",
        "high",
        "low",
        "close",
        "volume",
    ]

    rename_map: dict[Any, str] = {}

    for required_column in required:
        source = column_map.get(
            required_column
        )

        if source is None:
            # Try common prefixed forms.
            candidates = [
                key
                for key in column_map
                if key.endswith(
                    f"_{required_column}"
                )
                or key.startswith(
                    f"{required_column}_"
                )
            ]

            if candidates:
                source = column_map[
                    candidates[0]
                ]

        if source is None:
            raise ValueError(
                f"OHLCV column missing: "
                f"{required_column}"
            )

        rename_map[source] = (
            required_column.capitalize()
        )

    frame = frame.rename(
        columns=rename_map
    )

    frame = frame[
        [
            "Open",
            "High",
            "Low",
            "Close",
            "Volume",
        ]
    ].copy()

    for column in [
        "Open",
        "High",
        "Low",
        "Close",
        "Volume",
    ]:
        frame[column] = pd.to_numeric(
            frame[column],
            errors="coerce",
        )

    frame = frame.replace(
        [float("inf"), float("-inf")],
        pd.NA,
    )

    frame = frame.dropna(
        subset=[
            "Open",
            "High",
            "Low",
            "Close",
        ]
    )

    frame = frame.sort_index()

    frame = frame[
        ~frame.index.duplicated(
            keep="last"
        )
    ]

    return frame


def slice_exact_dates(
    data: pd.DataFrame,
    start_date: str,
    end_date: str,
) -> pd.DataFrame:
    if not start_date or not end_date:
        raise ValueError(
            "Independent slice dates are required"
        )

    try:
        start = pd.Timestamp(
            start_date
        )

        end = pd.Timestamp(
            end_date
        )

    except Exception as exc:
        raise ValueError(
            "Invalid independent slice dates: "
            f"{start_date} -> {end_date}"
        ) from exc

    if start > end:
        raise ValueError(
            "Independent slice start date is "
            "after end date"
        )

    frame = data.copy()

    if not isinstance(
        frame.index,
        pd.DatetimeIndex,
    ):
        frame.index = pd.to_datetime(
            frame.index,
            errors="coerce",
        )

    frame = frame[
        ~frame.index.isna()
    ].copy()

    # Normalize timezone if necessary.
    try:
        if frame.index.tz is not None:
            frame.index = (
                frame.index.tz_localize(
                    None
                )
            )
    except Exception:
        pass

    start = start.tz_localize(None) \
        if start.tzinfo is not None \
        else start

    end = end.tz_localize(None) \
        if end.tzinfo is not None \
        else end

    frame = frame.sort_index()

    sliced = frame.loc[
        (frame.index >= start)
        & (frame.index <= end)
    ].copy()

    return sliced


# ============================================================================
# STRATEGY / BACKTEST CONFIG
# ============================================================================


def build_backtest_config(
    strategy: dict[str, Any],
) -> dict[str, Any]:
    risk_config = strategy.get(
        "riskRules"
    )

    if not isinstance(
        risk_config,
        dict,
    ):
        risk_config = strategy.get(
            "risk_rules"
        )

    if not isinstance(
        risk_config,
        dict,
    ):
        risk_config = {}

    stop_atr_multiple = safe_float(
        first_non_empty(
            risk_config.get(
                "stop_atr_multiple"
            ),
            risk_config.get(
                "stop_atr_multiplier"
            ),
            risk_config.get(
                "stopLossAtrMultiple"
            ),
            risk_config.get(
                "stop_loss_atr_multiple"
            ),
        ),
        DEFAULT_STOP_ATR_MULTIPLE,
    )

    target_atr_multiple = safe_float(
        first_non_empty(
            risk_config.get(
                "target_atr_multiple"
            ),
            risk_config.get(
                "target_atr_multiplier"
            ),
            risk_config.get(
                "takeProfitAtrMultiple"
            ),
            risk_config.get(
                "take_profit_atr_multiple"
            ),
        ),
        DEFAULT_TARGET_ATR_MULTIPLE,
    )

    return {
        "initial_capital":
            DEFAULT_INITIAL_CAPITAL,

        "position_size_percent":
            DEFAULT_POSITION_SIZE_PERCENT,

        "commission_percent":
            DEFAULT_COMMISSION_PERCENT,

        "slippage_percent":
            DEFAULT_SLIPPAGE_PERCENT,

        "allow_short":
            True,

        "one_position_at_a_time":
            True,

        "use_stop_loss":
            True,

        "use_take_profit":
            True,

        "stop_loss_atr_multiple":
            stop_atr_multiple,

        "take_profit_atr_multiple":
            target_atr_multiple,

        "exit_on_opposite_signal":
            True,

        "max_holding_bars":
            DEFAULT_MAX_HOLDING_BARS,

        "close_at_end":
            True,
    }


def extract_numeric_metric(result: Any, *keys: str) -> float | None:
    if not isinstance(result, dict):
        return None
    candidates = [result]
    for key in ("metrics", "performance", "summary", "statistics"):
        value = result.get(key)
        if isinstance(value, dict):
            candidates.append(value)
    for obj in candidates:
        for key in keys:
            value = obj.get(key)
            if value is not None:
                number = safe_float(value, float("nan"))
                if math.isfinite(number):
                    return number
    return None


def run_walk_forward_oos(
    data: pd.DataFrame,
    symbol: str,
    signal_config: dict[str, Any],
    backtest_config: dict[str, Any],
) -> dict[str, Any]:
    """Lightweight research-grade OOS validation without changing the strategy.

    The independent slice is split chronologically into development/train and
    unseen OOS windows. Both windows use the exact same signal and backtest
    configuration.
    """
    total = len(data)
    if total < 60:
        return {
            "status": "INCONCLUSIVE",
            "reason": "WALK_FORWARD_INSUFFICIENT_BARS",
            "bars": total,
            "minimumBarsRequired": 60,
        }

    train_bars = max(30, int(total * 0.70))
    oos_bars = total - train_bars
    train = data.iloc[:train_bars].copy()
    oos = data.iloc[train_bars:].copy()

    train_result = run_backtest(
        data=train,
        symbol=symbol,
        signal_config=signal_config,
        backtest_config=backtest_config,
    )
    oos_result = run_backtest(
        data=oos,
        symbol=symbol,
        signal_config=signal_config,
        backtest_config=backtest_config,
    )

    train_metric = extract_numeric_metric(
        train_result,
        "net_return_percent", "return_percent", "total_return_percent",
        "net_pnl", "profit", "total_return",
    )
    oos_metric = extract_numeric_metric(
        oos_result,
        "net_return_percent", "return_percent", "total_return_percent",
        "net_pnl", "profit", "total_return",
    )

    stable = None
    if train_metric is not None and oos_metric is not None:
        stable = (
            train_metric > 0
            and oos_metric > 0
            and oos_metric >= train_metric * 0.50
        )

    return {
        "status": "COMPLETED",
        "method": "CHRONOLOGICAL_OOS_V1",
        "trainBars": len(train),
        "oosBars": len(oos),
        "trainStart": train.index.min().isoformat(),
        "trainEnd": train.index.max().isoformat(),
        "oosStart": oos.index.min().isoformat(),
        "oosEnd": oos.index.max().isoformat(),
        "trainMetric": train_metric,
        "oosMetric": oos_metric,
        "oosRetentionRatio": (
            oos_metric / train_metric
            if train_metric not in (None, 0) and oos_metric is not None
            else None
        ),
        "stable": stable,
        "trainResult": train_result,
        "oosResult": oos_result,
    }


# ============================================================================
# EXECUTION RESULT HELPERS
# ============================================================================


def build_blocked_result(
    *,
    run_id: str,
    experiment_id: str,
    reason: str,
    errors: list[str] | None = None,
    started_at: str,
) -> dict[str, Any]:
    completed_at = now_iso()

    return {
        "engine": ENGINE_NAME,
        "version": ENGINE_VERSION,

        "status": "BLOCKED",

        "runId": run_id,
        "experimentId": experiment_id,

        "reason": reason,
        "errors": errors or [],

        "safety": {
            "researchOnly":
                RESEARCH_ONLY,

            "executionEnabled":
                EXECUTION_ENABLED,

            "databaseWriteEnabled":
                DATABASE_WRITE_ENABLED,

            "brokerExecutionEnabled":
                BROKER_EXECUTION_ENABLED,
        },

        "startedAt": started_at,
        "completedAt": completed_at,
    }


# ============================================================================
# MAIN EXECUTION
# ============================================================================


def run_research_execution(
    payload: dict[str, Any],
) -> dict[str, Any]:
    started_at = now_iso()

    run_id = safe_str(
        payload.get("runId")
    )

    experiment = extract_experiment(
        payload
    )

    experiment_id = extract_experiment_id(
        experiment,
        payload,
    )

    # ------------------------------------------------------------------------
    # SAFETY
    # ------------------------------------------------------------------------

    safety_errors = (
        validate_safety_contract(
            experiment
        )
    )

    if safety_errors:
        return build_blocked_result(
            run_id=run_id,
            experiment_id=experiment_id,
            reason=(
                "UNSAFE_EXECUTION_CONTRACT"
            ),
            errors=safety_errors,
            started_at=started_at,
        )

    # ------------------------------------------------------------------------
    # EXPERIMENT IDENTITY
    # ------------------------------------------------------------------------

    if not experiment_id:
        return build_blocked_result(
            run_id=run_id,
            experiment_id="",
            reason=(
                "EXPERIMENT_ID_REQUIRED"
            ),
            started_at=started_at,
        )

    research_question = safe_str(
        first_non_empty(
            experiment.get(
                "researchQuestion"
            ),
            experiment.get(
                "research_question"
            ),
            payload.get(
                "researchQuestion"
            ),
        )
    )

    if not research_question:
        return build_blocked_result(
            run_id=run_id,
            experiment_id=experiment_id,
            reason=(
                "RESEARCH_QUESTION_REQUIRED"
            ),
            started_at=started_at,
        )

    # ------------------------------------------------------------------------
    # STRATEGY
    # ------------------------------------------------------------------------

    strategy = extract_strategy(
        experiment
    )

    strategy_id = extract_strategy_id(
        strategy
    )

    if not strategy_id:
        return build_blocked_result(
            run_id=run_id,
            experiment_id=experiment_id,
            reason=(
                "STRATEGY_ID_REQUIRED"
            ),
            started_at=started_at,
        )

    # ------------------------------------------------------------------------
    # MARKET
    # ------------------------------------------------------------------------

    symbol, timeframe = (
        extract_market_scope(
            experiment
        )
    )

    if not symbol:
        return build_blocked_result(
            run_id=run_id,
            experiment_id=experiment_id,
            reason=(
                "MARKET_SYMBOL_REQUIRED"
            ),
            started_at=started_at,
        )

    if not timeframe:
        return build_blocked_result(
            run_id=run_id,
            experiment_id=experiment_id,
            reason=(
                "MARKET_TIMEFRAME_REQUIRED"
            ),
            started_at=started_at,
        )

    normalized_timeframe = (
        timeframe.strip().lower()
    )

    if normalized_timeframe not in {
        "1d",
        "daily",
        "day",
    }:
        return build_blocked_result(
            run_id=run_id,
            experiment_id=experiment_id,
            reason=(
                "UNSUPPORTED_TIMEFRAME"
            ),
            errors=[
                (
                    "Research execution adapter "
                    "currently requires daily data; "
                    f"received '{timeframe}'"
                )
            ],
            started_at=started_at,
        )

    # ------------------------------------------------------------------------
    # DATE SCOPE
    # ------------------------------------------------------------------------

    date_scope = extract_date_scope(
        experiment,
        payload,
    )

    selection_status = safe_str(
        date_scope.get(
            "selectionStatus"
        )
    ).upper()

    if selection_status != "RESOLVED":
        return build_blocked_result(
            run_id=run_id,
            experiment_id=experiment_id,
            reason=(
                "DATE_SCOPE_NOT_RESOLVED"
            ),
            errors=[
                (
                    "Experiment Generator must "
                    "provide dateScope.selectionStatus="
                    "'RESOLVED'"
                )
            ],
            started_at=started_at,
        )

    independent_start = safe_str(
        date_scope.get(
            "independentSliceStartDate"
        )
    )

    independent_end = safe_str(
        date_scope.get(
            "independentSliceEndDate"
        )
    )

    if not independent_start:
        return build_blocked_result(
            run_id=run_id,
            experiment_id=experiment_id,
            reason=(
                "INDEPENDENT_START_DATE_REQUIRED"
            ),
            started_at=started_at,
        )

    if not independent_end:
        return build_blocked_result(
            run_id=run_id,
            experiment_id=experiment_id,
            reason=(
                "INDEPENDENT_END_DATE_REQUIRED"
            ),
            started_at=started_at,
        )

    # ------------------------------------------------------------------------
    # LOAD MARKET DATA
    # ------------------------------------------------------------------------

    history_results = get_bist_history(
        period="3y",
        interval="1d",
    )

    raw_data = select_symbol_history(
        history_results,
        symbol,
    )

    if raw_data is None:
        return build_blocked_result(
            run_id=run_id,
            experiment_id=experiment_id,
            reason=(
                "SYMBOL_HISTORY_NOT_FOUND"
            ),
            errors=[
                f"No historical data found for {symbol}"
            ],
            started_at=started_at,
        )

    # ------------------------------------------------------------------------
    # NORMALIZE OHLCV
    # ------------------------------------------------------------------------

    try:
        normalized_data = normalize_ohlcv(
            raw_data
        )

    except Exception as exc:
        return build_blocked_result(
            run_id=run_id,
            experiment_id=experiment_id,
            reason=(
                "OHLCV_NORMALIZATION_FAILED"
            ),
            errors=[
                str(exc)
            ],
            started_at=started_at,
        )

    # ------------------------------------------------------------------------
    # EXACT INDEPENDENT SLICE
    # ------------------------------------------------------------------------

    try:
        independent_data = (
            slice_exact_dates(
                normalized_data,
                independent_start,
                independent_end,
            )
        )

    except Exception as exc:
        return build_blocked_result(
            run_id=run_id,
            experiment_id=experiment_id,
            reason=(
                "INDEPENDENT_SLICE_FAILED"
            ),
            errors=[
                str(exc)
            ],
            started_at=started_at,
        )

    if independent_data.empty:
        return build_blocked_result(
            run_id=run_id,
            experiment_id=experiment_id,
            reason=(
                "INDEPENDENT_SLICE_EMPTY"
            ),
            errors=[
                (
                    "No OHLCV bars exist inside "
                    f"{independent_start} -> "
                    f"{independent_end}"
                )
            ],
            started_at=started_at,
        )

    # ------------------------------------------------------------------------
    # MINIMUM DATA SAFETY GATE
    # ------------------------------------------------------------------------

    minimum_bars = 30

    if len(independent_data) < minimum_bars:
        completed_at = now_iso()

        return {
            "engine": ENGINE_NAME,
            "version": ENGINE_VERSION,

            "status": "INCONCLUSIVE",

            "runId": run_id,
            "experimentId": experiment_id,

            "researchQuestion":
                research_question,

            "strategy": {
                "strategyId":
                    strategy_id,
            },

            "market": {
                "symbol":
                    symbol,

                "timeframe":
                    timeframe,
            },

            "dateScope": {
                "selectionStatus":
                    selection_status,

                "selectionSource":
                    date_scope.get(
                        "selectionSource"
                    ),

                "independentSliceStartDate":
                    independent_start,

                "independentSliceEndDate":
                    independent_end,
            },

            "data": {
                "bars":
                    len(independent_data),

                "minimumBarsRequired":
                    minimum_bars,

                "actualStartDate":
                    (
                        independent_data.index.min()
                        .isoformat()
                        if not independent_data.empty
                        else None
                    ),

                "actualEndDate":
                    (
                        independent_data.index.max()
                        .isoformat()
                        if not independent_data.empty
                        else None
                    ),
            },

            "reason": (
                "INSUFFICIENT_INDEPENDENT_BARS"
            ),

            "safety": {
                "researchOnly":
                    RESEARCH_ONLY,

                "executionEnabled":
                    EXECUTION_ENABLED,

                "databaseWriteEnabled":
                    DATABASE_WRITE_ENABLED,

                "brokerExecutionEnabled":
                    BROKER_EXECUTION_ENABLED,
            },

            "startedAt":
                started_at,

            "completedAt":
                completed_at,
        }

    # ------------------------------------------------------------------------
    # NORMALIZE STRATEGY PARAMETERS
    # ------------------------------------------------------------------------

    try:
        signal_config, risk_config = (
            normalize_strategy_parameters(
                strategy
            )
        )

    except Exception as exc:
        return build_blocked_result(
            run_id=run_id,
            experiment_id=experiment_id,
            reason=(
                "STRATEGY_PARAMETER_NORMALIZATION_FAILED"
            ),
            errors=[
                str(exc)
            ],
            started_at=started_at,
        )

    # ------------------------------------------------------------------------
    # BACKTEST CONFIG
    # ------------------------------------------------------------------------

    backtest_config = (
        build_backtest_config(
            strategy
        )
    )

    # Preserve normalized risk values where available.
    if isinstance(
        risk_config,
        dict,
    ):
        backtest_config[
            "stop_loss_atr_multiple"
        ] = safe_float(
            first_non_empty(
                risk_config.get(
                    "stop_atr_multiple"
                ),
                risk_config.get(
                    "stop_atr_multiplier"
                ),
            ),
            DEFAULT_STOP_ATR_MULTIPLE,
        )

        backtest_config[
            "take_profit_atr_multiple"
        ] = safe_float(
            first_non_empty(
                risk_config.get(
                    "target_atr_multiple"
                ),
                risk_config.get(
                    "target_atr_multiplier"
                ),
            ),
            DEFAULT_TARGET_ATR_MULTIPLE,
        )

    # ------------------------------------------------------------------------
    # ACTUAL RESEARCH EXECUTION
    # ------------------------------------------------------------------------

    try:
        backtest_result = run_backtest(
            data=independent_data,
            symbol=symbol,
            signal_config=signal_config,
            backtest_config=backtest_config,
        )

    except Exception as exc:
        completed_at = now_iso()

        return {
            "engine": ENGINE_NAME,
            "version": ENGINE_VERSION,

            "status": "FAILED",

            "runId": run_id,
            "experimentId": experiment_id,

            "researchQuestion":
                research_question,

            "strategy": {
                "strategyId":
                    strategy_id,

                "name":
                    strategy.get(
                        "name"
                    ),

                "parameters":
                    json_safe(
                        strategy.get(
                            "parameters",
                            {},
                        )
                    ),
            },

            "market": {
                "symbol":
                    symbol,

                "timeframe":
                    timeframe,
            },

            "dateScope": {
                "selectionStatus":
                    selection_status,

                "selectionSource":
                    date_scope.get(
                        "selectionSource"
                    ),

                "independentSliceStartDate":
                    independent_start,

                "independentSliceEndDate":
                    independent_end,
            },

            "error": str(exc),

            "traceback":
                traceback.format_exc(),

            "safety": {
                "researchOnly":
                    RESEARCH_ONLY,

                "executionEnabled":
                    EXECUTION_ENABLED,

                "databaseWriteEnabled":
                    DATABASE_WRITE_ENABLED,

                "brokerExecutionEnabled":
                    BROKER_EXECUTION_ENABLED,
            },

            "startedAt":
                started_at,

            "completedAt":
                completed_at,
        }

    # ------------------------------------------------------------------------
    # WALK-FORWARD / OOS VALIDATION
    # ------------------------------------------------------------------------

    try:
        walk_forward = run_walk_forward_oos(
            data=independent_data,
            symbol=symbol,
            signal_config=signal_config,
            backtest_config=backtest_config,
        )
    except Exception as exc:
        walk_forward = {
            "status": "FAILED",
            "reason": "WALK_FORWARD_EXECUTION_FAILED",
            "error": str(exc),
        }

    # ------------------------------------------------------------------------
    # BUILD RESULT
    # ------------------------------------------------------------------------

    completed_at = now_iso()

    result_status = "COMPLETED"

    if isinstance(
        backtest_result,
        dict,
    ):
        candidate_status = safe_str(
            backtest_result.get(
                "status"
            )
        ).upper()

        if candidate_status in {
            "FAILED",
            "ERROR",
            "BLOCKED",
            "INCONCLUSIVE",
        }:
            result_status = candidate_status

    return json_safe(
        {
            "engine": ENGINE_NAME,
            "version": ENGINE_VERSION,

            "status": result_status,

            "runId": run_id,
            "experimentId": experiment_id,

            "researchQuestion":
                research_question,

            "strategy": {
                "strategyId":
                    strategy_id,

                "name":
                    strategy.get(
                        "name"
                    ),

                "ruleDefinition":
                    json_safe(
                        strategy.get(
                            "ruleDefinition",
                            strategy.get(
                                "rule_definition",
                                {},
                            ),
                        )
                    ),

                "parameters":
                    json_safe(
                        strategy.get(
                            "parameters",
                            {},
                        )
                    ),

                "normalizedSignalConfig":
                    json_safe(
                        signal_config
                    ),

                "normalizedRiskConfig":
                    json_safe(
                        risk_config
                    ),
            },

            "market": {
                "symbol":
                    symbol,

                "timeframe":
                    timeframe,
            },

            "dateScope": {
                "selectionStatus":
                    selection_status,

                "selectionSource":
                    date_scope.get(
                        "selectionSource"
                    ),

                "independentSliceStartDate":
                    independent_start,

                "independentSliceEndDate":
                    independent_end,

                "adapterSelectedDates":
                    False,
            },

            "data": {
                "bars":
                    len(independent_data),

                "actualStartDate":
                    (
                        independent_data.index.min()
                        .isoformat()
                        if not independent_data.empty
                        else None
                    ),

                "actualEndDate":
                    (
                        independent_data.index.max()
                        .isoformat()
                        if not independent_data.empty
                        else None
                    ),

                "interval":
                    "1d",

                "source":
                    "get_bist_history",
            },

            "backtest": {
                "config":
                    backtest_config,

                "result":
                    backtest_result,
            },

            "walkForwardOOS":
                walk_forward,

            "robustnessSummary": {
                "oosValidation":
                    walk_forward.get("status") == "COMPLETED",
                "stable":
                    walk_forward.get("stable"),
                "retentionRatio":
                    walk_forward.get("oosRetentionRatio"),
            },

            "execution": {
                "researchExecutionPerformed":
                    True,

                "backtestExecuted":
                    True,

                "brokerOrderPlaced":
                    False,

                "databaseWritePerformed":
                    False,
            },

            "safety": {
                "researchOnly":
                    RESEARCH_ONLY,

                "executionEnabled":
                    EXECUTION_ENABLED,

                "databaseWriteEnabled":
                    DATABASE_WRITE_ENABLED,

                "brokerExecutionEnabled":
                    BROKER_EXECUTION_ENABLED,
            },

            "startedAt":
                started_at,

            "completedAt":
                completed_at,
        }
    )


# ============================================================================
# CLI
# ============================================================================


def main() -> None:
    raw_input = sys.stdin.read()

    if not raw_input.strip():
        print(
            json.dumps(
                {
                    "engine":
                        ENGINE_NAME,

                    "version":
                        ENGINE_VERSION,

                    "status":
                        "BLOCKED",

                    "reason":
                        "JSON_INPUT_REQUIRED",

                    "safety": {
                        "researchOnly":
                            RESEARCH_ONLY,

                        "executionEnabled":
                            EXECUTION_ENABLED,

                        "databaseWriteEnabled":
                            DATABASE_WRITE_ENABLED,

                        "brokerExecutionEnabled":
                            BROKER_EXECUTION_ENABLED,
                    },
                },
                ensure_ascii=False,
                indent=2,
            )
        )

        return

    try:
        payload = json.loads(
            raw_input
        )

    except json.JSONDecodeError as exc:
        print(
            json.dumps(
                {
                    "engine":
                        ENGINE_NAME,

                    "version":
                        ENGINE_VERSION,

                    "status":
                        "BLOCKED",

                    "reason":
                        "INVALID_JSON_INPUT",

                    "error":
                        str(exc),
                },
                ensure_ascii=False,
                indent=2,
            )
        )

        return

    if not isinstance(
        payload,
        dict,
    ):
        print(
            json.dumps(
                {
                    "engine":
                        ENGINE_NAME,

                    "version":
                        ENGINE_VERSION,

                    "status":
                        "BLOCKED",

                    "reason":
                        "JSON_OBJECT_REQUIRED",
                },
                ensure_ascii=False,
                indent=2,
            )
        )

        return

    result = run_research_execution(
        payload
    )

    print(
        json.dumps(
            json_safe(result),
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()

