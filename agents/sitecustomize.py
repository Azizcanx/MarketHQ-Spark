"""Research adapter startup bridge.

Only patches the legacy BIST history loader when the research execution
adapter is launched. The adapter then consumes the same read-only backend
historical-data path used by the date resolver, avoiding a second yfinance
fetch path.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path


BIST_SYMBOLS = (
    "AEFES.IS", "AKBNK.IS", "ASELS.IS", "ASTOR.IS", "BIMAS.IS",
    "EKGYO.IS", "ENKAI.IS", "EREGL.IS", "FROTO.IS", "GARAN.IS",
    "GUBRF.IS", "HALKB.IS", "ISCTR.IS", "KCHOL.IS", "KRDMD.IS",
    "MGROS.IS", "PASEU.IS", "PETKM.IS", "PGSUS.IS", "SAHOL.IS",
    "SASA.IS", "SISE.IS", "TAVHL.IS", "TCELL.IS", "THYAO.IS",
    "TOASO.IS", "TTKOM.IS", "TUPRS.IS", "ULKER.IS", "YKBNK.IS",
)

BACKEND_BASE = "http://127.0.0.1:8010"


def _ensure_project_venv() -> None:
    """Restart the adapter with the project's canonical Python interpreter."""
    if Path(sys.argv[0]).name.lower() != "research_execution_adapter_v1.py":
        return

    project_root = Path(__file__).resolve().parents[1]
    venv_python = project_root / ".venv" / "Scripts" / "python.exe"

    if not venv_python.exists():
        return

    try:
        current_python = Path(sys.executable).resolve()
        target_python = venv_python.resolve()
    except OSError:
        current_python = Path(sys.executable)
        target_python = venv_python

    if current_python != target_python:
        os.execv(str(target_python), [str(target_python), *sys.argv[1:]])


_ensure_project_venv()

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import pandas as pd


def _fetch(symbol: str, start: str, end: str, interval: str):
    query = urlencode({
        "symbol": symbol,
        "start": start,
        "end": end,
        "interval": interval,
        "limit": 5000,
    })
    request = Request(
        f"{BACKEND_BASE}/api/research-data?{query}",
        headers={"Accept": "application/json"},
    )
    with urlopen(request, timeout=30) as response:
        body = json.loads(response.read().decode("utf-8"))

    if body.get("success") is not True:
        return symbol, pd.DataFrame()

    rows = body.get("data", {}).get("rows", [])
    if not rows:
        return symbol, pd.DataFrame()

    frame = pd.DataFrame(rows)
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], errors="coerce")
    frame = frame.dropna(subset=["timestamp"]).set_index("timestamp").sort_index()
    frame = frame.rename(columns={
        "open": "Open",
        "high": "High",
        "low": "Low",
        "close": "Close",
        "volume": "Volume",
    })
    return symbol, frame[["Open", "High", "Low", "Close", "Volume"]]


def _backend_get_bist_history(period="1y", interval="1d"):
    if interval != "1d":
        return {}

    years = 3
    if isinstance(period, str) and period.endswith("y"):
        try:
            years = max(1, int(period[:-1]))
        except ValueError:
            pass

    end = datetime.now(timezone.utc).date()
    start = end - timedelta(days=365 * years + 7)

    results = {}
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = {
            pool.submit(
                _fetch,
                symbol,
                start.isoformat(),
                end.isoformat(),
                interval,
            ): symbol
            for symbol in BIST_SYMBOLS
        }
        for future in as_completed(futures):
            try:
                symbol, frame = future.result()
            except Exception:
                continue
            if not frame.empty:
                results[symbol] = frame

    return results


def _patch_vectorbt_defaults() -> None:
    """Fallback-normalize missing VectorBT params and expose selected metrics."""
    if Path(sys.argv[0]).name.lower() != "research_execution_adapter_v1.py":
        return
    try:
        import agents.vectorbt_engine_v1 as _vectorbt_engine

        original = getattr(_vectorbt_engine, "run_vectorbt_backtest", None)
        if original is None or getattr(original, "_markethq_defaults_patched", False):
            return

        def run_vectorbt_backtest_with_defaults(*args, **kwargs):
            strategy = kwargs.get("strategy")
            if strategy is None and len(args) >= 2:
                strategy = args[1]
            if not isinstance(strategy, dict):
                strategy = {}

            normalized_strategy = dict(strategy)
            raw_parameters = normalized_strategy.get("parameters")
            parameters = dict(raw_parameters) if isinstance(raw_parameters, dict) else {}

            aliases = {
                "sma_fast": ("sma_fast", "fast_sma", "fast_period", "short_period"),
                "sma_slow": ("sma_slow", "slow_sma", "slow_period", "long_period"),
                "rsi_period": ("rsi_period", "rsi_length"),
                "rsi_entry": ("rsi_entry", "rsi_threshold", "rsi_entry_threshold"),
            }
            defaults = {
                "sma_fast": 10,
                "sma_slow": 50,
                "rsi_period": 14,
                "rsi_entry": 55.0,
            }

            for canonical, candidates in aliases.items():
                for key in candidates:
                    value = parameters.get(key)
                    if value not in (None, ""):
                        parameters[canonical] = value
                        break
                else:
                    parameters[canonical] = defaults[canonical]

            normalized_strategy["parameters"] = parameters
            if "strategy" in kwargs:
                kwargs["strategy"] = normalized_strategy
                result = original(*args, **kwargs)
            elif len(args) >= 2:
                args = list(args)
                args[1] = normalized_strategy
                result = original(*args, **kwargs)
            else:
                kwargs["strategy"] = normalized_strategy
                result = original(*args, **kwargs)

            # AgentRunner already expects a top-level metrics object. The
            # VectorBT engine stores selected metrics under best.metrics, so
            # promote that canonical selected result without changing the
            # engine's underlying result structure.
            if isinstance(result, dict) and not isinstance(result.get("metrics"), dict):
                best = result.get("best")
                best_metrics = best.get("metrics") if isinstance(best, dict) else None
                if isinstance(best_metrics, dict):
                    result["metrics"] = dict(best_metrics)
            return result

        run_vectorbt_backtest_with_defaults._markethq_defaults_patched = True
        _vectorbt_engine.run_vectorbt_backtest = run_vectorbt_backtest_with_defaults
    except Exception:
        pass


try:
    if Path(sys.argv[0]).name.lower() == "research_execution_adapter_v1.py":
        project_root = Path(__file__).resolve().parents[1]
        if str(project_root) not in sys.path:
            sys.path.insert(0, str(project_root))
        import agents.market_data_agent as _market_data_agent
        _market_data_agent.get_bist_history = _backend_get_bist_history
        _patch_vectorbt_defaults()
except Exception:
    pass
