# -*- coding: utf-8 -*-
"""
MarketHQ Binance Data V1 (research-only, public klines — anahtar gerekmez).

Binance Spot REST'ten OHLCV ceker, backend satir formatina donusturur:
  {timestamp, open, high, low, close, volume}
Kripto sembol esleme: BTC-USD -> BTCUSDT (USDT market varsayimi).
"""

from __future__ import annotations

import json
import urllib.request
from datetime import datetime, timezone
from typing import Any

BASE = "https://api.binance.com"

SYMBOL_MAP = {
    "BTC-USD": "BTCUSDT",
    "ETH-USD": "ETHUSDT",
    "SOL-USD": "SOLUSDT",
    "BTC": "BTCUSDT",
    "ETH": "ETHUSDT",
    "SOL": "SOLUSDT",
}

INTERVAL_MAP = {
    "15m": "15m", "30m": "30m", "1h": "1h", "4h": "4h",
    "1d": "1d", "1D": "1d", "1w": "1w",
}


def to_binance_symbol(symbol: str) -> str | None:
    s = symbol.strip().upper().replace("/", "").replace("-", "")
    if s.endswith("USDT") and len(s) > 4:
        return s
    mapped = SYMBOL_MAP.get(symbol.strip().upper()) or SYMBOL_MAP.get(s)
    if mapped:
        return mapped
    if s.endswith("USD"):
        return s[:-3] + "USDT"
    return None


def fetch_klines(symbol: str, interval: str = "1d", limit: int = 200, timeout: int = 30) -> list[dict[str, Any]]:
    bsym = to_binance_symbol(symbol)
    if bsym is None:
        raise ValueError(f"binance eslemesi yok: {symbol}")
    bint = INTERVAL_MAP.get(interval, "1d")
    lim = max(60, min(limit, 1000))
    url = f"{BASE}/api/v3/klines?symbol={bsym}&interval={bint}&limit={lim}"
    req = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": "MarketHQ-research/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = json.load(r)
    rows = []
    for k in raw:
        rows.append({
            "timestamp": datetime.fromtimestamp(k[0] / 1000, tz=timezone.utc).isoformat(),
            "open": float(k[1]),
            "high": float(k[2]),
            "low": float(k[3]),
            "close": float(k[4]),
            "volume": float(k[5]),
        })
    return rows
