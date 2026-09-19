"""MarketHQ Python startup bridge for research execution."""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

PROJECT_ROOT = Path(__file__).resolve().parent
VENV_PYTHON = PROJECT_ROOT / ".venv" / "Scripts" / "python.exe"

try:
    _is_adapter = Path(sys.argv[0]).name.lower() == "research_execution_adapter_v1.py"
    _using_project_venv = Path(sys.executable).resolve() == VENV_PYTHON.resolve()
    if _is_adapter and VENV_PYTHON.exists() and not _using_project_venv:
        os.execv(str(VENV_PYTHON), [str(VENV_PYTHON), *sys.argv[1:]])
except Exception:
    pass

BACKEND_BASE = "http://127.0.0.1:8010"
BIST_SYMBOLS = (
    "AEFES.IS", "AKBNK.IS", "ASELS.IS", "ASTOR.IS", "BIMAS.IS",
    "EKGYO.IS", "ENKAI.IS", "EREGL.IS", "FROTO.IS", "GARAN.IS",
    "GUBRF.IS", "HALKB.IS", "ISCTR.IS", "KCHOL.IS", "KRDMD.IS",
    "MGROS.IS", "PASEU.IS", "PETKM.IS", "PGSUS.IS", "SAHOL.IS",
    "SASA.IS", "SISE.IS", "TAVHL.IS", "TCELL.IS", "THYAO.IS",
    "TOASO.IS", "TTKOM.IS", "TUPRS.IS", "ULKER.IS", "YKBNK.IS",
)


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
    with urlopen(request, timeout=45) as response:
        body = json.loads(response.read().decode("utf-8"))
    if body.get("success") is not True:
        return symbol, []
    return symbol, body.get("data", {}).get("rows", [])


def _backend_get_bist_history(period="1y", interval="1d"):
    if interval != "1d":
        return {}

    import pandas as pd

    years = 3
    if isinstance(period, str) and period.endswith("y"):
        try:
            years = max(1, int(period[:-1]))
        except ValueError:
            pass

    end = datetime.now(timezone.utc).date()
    start = end - timedelta(days=365 * years + 7)

    requested = os.getenv("MARKETHQ_RESEARCH_SYMBOL", "").strip().upper()
    symbols = [requested] if requested in BIST_SYMBOLS else list(BIST_SYMBOLS)

    results = {}
    for symbol in symbols:
        try:
            name, rows = _fetch(symbol, start.isoformat(), end.isoformat(), interval)
            if not rows:
                continue
            frame = pd.DataFrame(rows)
            frame["timestamp"] = pd.to_datetime(frame["timestamp"], errors="coerce")
            frame = frame.dropna(subset=["timestamp"]).set_index("timestamp").sort_index()
            frame = frame.rename(columns={
                "open": "Open", "high": "High", "low": "Low",
                "close": "Close", "volume": "Volume",
            })
            results[name] = frame[["Open", "High", "Low", "Close", "Volume"]]
        except Exception:
            continue

    return results

try:
    if Path(sys.argv[0]).name.lower() == "research_execution_adapter_v1.py":
        import agents.market_data_agent as _market_data_agent
        _market_data_agent.get_bist_history = _backend_get_bist_history
except Exception:
    pass
