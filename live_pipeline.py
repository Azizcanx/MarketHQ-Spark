#!/usr/bin/env python3
"""Canli Veri Akisi — MarketHQ Live Data Pipeline.

Binance public API + yerel OHLCV cache.
Veri -> Features -> Regime -> AI Gateway -> Firsat -> Setup -> Claim -> DB
"""

import sys, os, json, time, uuid, requests
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, '/opt/markethq')
os.chdir('/opt/markethq')

import numpy as np
import pandas as pd

from persistence import PersistenceLayer
from market_observation import MarketObservation
from ai_gateway.gateway import get_gateway
from ai_gateway.models import AIRequest, Purpose

DB_PATH = "/opt/markethq/market_hq.db"
OHLCV_DIR = Path("/opt/markethq/data/ohlcv")
LIVE_STATE_FILE = "/opt/markethq/data/live_state.json"
BINANCE_BASE = "https://api.binance.com/api/v3"

# Sembol esleme: MarketHQ -> Binance
BINANCE_SYMS = {"BTC-USD": "BTCUSDT", "EURUSD=X": "EURUSDT"}
BINANCE_TF = {"5m": "5m", "15m": "15m", "1h": "1h", "4h": "4h", "1d": "1d"}


def _klines_to_df(klines: list) -> pd.DataFrame:
    rows = []
    for k in klines:
        rows.append({
            "open": float(k[1]), "high": float(k[2]),
            "low": float(k[3]), "close": float(k[4]),
            "volume": float(k[5]),
        })
    df = pd.DataFrame(rows)
    df["timestamp"] = pd.to_datetime(klines[0][0], unit="ms")
    df.set_index("timestamp", inplace=True)
    return df


def _df_to_cache(df: pd.DataFrame) -> list[dict]:
    rows = []
    for idx, row in df.iterrows():
        rows.append({
            "timestamp": idx.isoformat() if hasattr(idx, "isoformat") else str(idx),
            "open": float(row.get("open", row.get("Open", 0))),
            "high": float(row.get("high", row.get("High", 0))),
            "low": float(row.get("low", row.get("Low", 0))),
            "close": float(row.get("close", row.get("Close", 0))),
            "volume": float(row.get("volume", row.get("Volume", 0))),
        })
    return rows


def save_ohlcv_cache(symbol: str, timeframe: str, df: pd.DataFrame) -> None:
    try:
        OHLCV_DIR.mkdir(parents=True, exist_ok=True)
        file_path = OHLCV_DIR / f"{symbol}__{timeframe}.json"
        bars = _df_to_cache(df)
        with open(file_path, "w") as f:
            json.dump({"bars": bars, "symbol": symbol, "timeframe": timeframe,
                       "source": "binance", "saved_at": datetime.now(timezone.utc).isoformat()},
                      f, indent=2)
    except Exception as e:
        print(f"  Cache kaydetme hatasi {symbol} {timeframe}: {e}")


def load_ohlcv(symbol: str, timeframe: str = "1h") -> pd.DataFrame | None:
    # 1. Yerel dosya
    ohlcv_file = OHLCV_DIR / f"{symbol}__{timeframe}.json"
    if ohlcv_file.exists():
        try:
            with open(ohlcv_file) as f:
                data = json.load(f)
            bars = data.get("bars", [])
            if bars:
                df = pd.DataFrame(bars)
                df["timestamp"] = pd.to_datetime(df["timestamp"])
                df.set_index("timestamp", inplace=True)
                print(f"  {symbol} {timeframe}: {len(df)} bars (yerel)")
                return df
        except Exception:
            pass

    # 2. Binance
    bsym = BINANCE_SYMS.get(symbol)
    btf = BINANCE_TF.get(timeframe)
    if bsym and btf:
        try:
            url = f"{BINANCE_BASE}/klines"
            r = requests.get(url, params={"symbol": bsym, "interval": btf, "limit": 500}, timeout=15)
            if r.status_code == 200:
                klines = r.json()
                if klines:
                    df = _klines_to_df(klines)
                    print(f"  {symbol} {timeframe}: {len(df)} bars (Binance)")
                    save_ohlcv_cache(symbol, timeframe, df)
                    return df
        except Exception as e:
            print(f"  {symbol} {timeframe}: Binance hatasi — {e}")
    else:
        print(f"  {symbol} {timeframe}: Binance desteklenmiyor")

    # 3. yfinance fallback
    tf_map = {"5m": "5m", "15m": "15m", "1h": "60m", "4h": "240m", "1d": "1d"}
    interval = tf_map.get(timeframe)
    if not interval:
        return None
    try:
        import yfinance as yf
        df = yf.download(symbol, period="60d", interval=interval, progress=False)
        if df is not None and len(df) > 0:
            print(f"  {symbol} {timeframe}: {len(df)} bars (yfinance)")
            return df
    except Exception as e:
        print(f"  {symbol} {timeframe}: yfinance hatasi — {e}")
    return None


def compute_features(df: pd.DataFrame) -> dict:
    close = df["close"].values.flatten() if "close" in df.columns else df["Close"].values.flatten()
    volume = df["volume"].values.flatten() if "volume" in df.columns else df["Volume"].values.flatten()

    sma_20 = pd.Series(close).rolling(20).mean().iloc[-1] if len(close) >= 20 else np.nan
    sma_50 = pd.Series(close).rolling(50).mean().iloc[-1] if len(close) >= 50 else np.nan
    current = close[-1]
    prev = close[-2] if len(close) >= 2 else current
    change_pct = ((current - prev) / prev * 100) if prev != 0 else 0

    returns = pd.Series(close).pct_change().dropna()
    volatility = float(returns.std() * np.sqrt(24)) if len(returns) > 1 else 0.0
    vol_avg = float(pd.Series(volume).rolling(20).mean().iloc[-1]) if len(volume) >= 20 else 0.0
    vol_current = float(volume[-1]) if len(volume) > 0 else 0.0

    return {
        "sma_20": round(float(sma_20), 2) if not np.isnan(sma_20) else None,
        "sma_50": round(float(sma_50), 2) if not np.isnan(sma_50) else None,
        "current_price": round(float(current), 2),
        "change_pct": round(float(change_pct), 2),
        "volatility": round(volatility, 4),
        "volume_avg": round(vol_avg, 0),
        "volume_current": round(vol_current, 0),
        "volume_ratio": round(vol_current / vol_avg, 2) if vol_avg > 0 else 0,
    }


def detect_regime(features: dict) -> str:
    sma_20 = features.get("sma_20")
    sma_50 = features.get("sma_50")
    change = features.get("change_pct", 0)
    vol = features.get("volatility", 0)
    if sma_20 and sma_50:
        if sma_20 > sma_50 and change > 0:
            return "TRENDING_UP"
        elif sma_20 < sma_50 and change < 0:
            return "TRENDING_DOWN"
    if vol > 0.02:
        return "HIGH_VOLATILITY"
    return "RANGING"


def run_research_cycle(symbols: list = None) -> dict:
    print("\n" + "="*60)
    print("KANAL 1: CANLI VERI AKISI (Binance)")
    print("="*60)

    timeframes = ["15m", "1h", "4h"]
    target_symbols = symbols or ["THYAO.IS", "AAPL", "BTC-USD", "EURUSD=X"]

    results = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "observations": [],
        "opportunities": [],
        "setups": [],
        "claims": [],
        "ai_requests": [],
        "errors": [],
    }

    persistence = PersistenceLayer(db_path=DB_PATH)
    gateway = get_gateway()

    for symbol in target_symbols:
        for tf in timeframes:
            print(f"\n  -- {symbol} {tf} --")

            df = load_ohlcv(symbol, tf)
            if df is None or df.empty:
                print(f"    UNAVAILABLE: veri yok")
                results["errors"].append(f"{symbol} {tf}: no data")
                continue

            features = compute_features(df)
            regime = detect_regime(features)

            print(f"    Regime: {regime}")
            print(f"    Price: {features.get('current_price')} ({features.get('change_pct')}%)")

            obs = MarketObservation(
                symbol=symbol,
                timeframe=tf,
                regime=regime,
                timestamp=datetime.now(timezone.utc).isoformat(),
            )
            obs.ohlcv_available = True
            obs.bar_count = len(df)
            obs.volatility = features.get("volatility", 0.0)
            obs.trend = regime
            obs.momentum = features.get("change_pct", 0.0)

            # AI Gateway research request
            req_id = f"REQ-{uuid.uuid4().hex[:8]}"
            ai_req = AIRequest(
                request_id=req_id,
                agent_id="live-pipeline",
                task_id=f"research-{symbol}-{tf}",
                purpose=Purpose.RESEARCH,
                user_input=f"Analyze {symbol} {tf} -- regime: {regime}",
                context={"symbol": symbol, "timeframe": tf, "features": features},
                fallback_enabled=True,
            )

            from ai_gateway.mock import MockFreeProviderAdapter
            from ai_gateway.models import ProviderSpec, ModelSpec, Tier
            provider = ProviderSpec(
                provider_id="FREE-A", name="Free A", tier=Tier.FREE, configured=True)
            model = ModelSpec(model_id="FREE-A-M1", provider_id="FREE-A", tier=Tier.FREE)
            adapter = MockFreeProviderAdapter(provider, model, behavior="SUCCESS")
            response, decision = gateway.generate(ai_req, lambda p, m, r: adapter.generate(r))

            results["ai_requests"].append({
                "request_id": req_id,
                "symbol": symbol,
                "timeframe": tf,
                "provider": response.provider_id,
                "success": response.success,
                "fallback_used": decision.fallback_used,
                "fallback_depth": decision.fallback_depth,
                "latency_ms": response.latency_ms,
            })
            print(f"    AI: {response.provider_id} -> success={response.success} fallback={decision.fallback_used}")

            # Opportunity
            if response.success and regime in ("TRENDING_UP", "TRENDING_DOWN", "HIGH_VOLATILITY"):
                opp_id = f"OPP-{uuid.uuid4().hex[:6].upper()}"
                results["opportunities"].append({
                    "opportunity_id": opp_id,
                    "symbol": symbol,
                    "timeframe": tf,
                    "type": "REGIME_CHANGE" if regime != "RANGING" else "VOLATILITY",
                    "regime": regime,
                    "confidence": 0.65,
                    "status": "DETECTED",
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "provenance": {
                        "symbol": symbol,
                        "timeframe": tf,
                        "data_range": f"{df.index[0]} to {df.index[-1]}",
                        "sample_size": len(df),
                    },
                })
                print(f"    Firsat: {opp_id} -- {regime}")

                setup_id = f"SETUP-{uuid.uuid4().hex[:6].upper()}"
                results["setups"].append({
                    "setup_id": setup_id,
                    "symbol": symbol,
                    "timeframe": tf,
                    "direction": "LONG" if regime == "TRENDING_UP" else "SHORT" if regime == "TRENDING_DOWN" else "NEUTRAL",
                    "regime": regime,
                    "entry_zone": round(float(features.get("current_price", 0)) * 0.995, 2),
                    "status": "PROPOSED",
                })
                print(f"    Setup: {setup_id} -- {regime}")

                claim_id = f"CLM-{uuid.uuid4().hex[:6].upper()}"
                results["claims"].append({
                    "claim_id": claim_id,
                    "symbol": symbol,
                    "timeframe": tf,
                    "statement": f"{symbol} {tf} -- {regime} regime detected, confidence 0.65",
                    "status": "UNTESTED",
                    "confidence": 0.65,
                })
                print(f"    Claim: {claim_id}")

    # Save live state
    live_state = {
        "last_run": datetime.now(timezone.utc).isoformat(),
        "symbols_processed": target_symbols,
        "opportunities_count": len(results["opportunities"]),
        "setups_count": len(results["setups"]),
        "claims_count": len(results["claims"]),
        "ai_requests_count": len(results["ai_requests"]),
        "errors": results["errors"],
    }
    os.makedirs(os.path.dirname(LIVE_STATE_FILE), exist_ok=True)
    with open(LIVE_STATE_FILE, "w") as f:
        json.dump(live_state, f, indent=2, default=str)

    print("\n" + "="*60)
    print("CANLI VERI AKISI SONUCI")
    print("="*60)
    print(f"  Semboller: {len(target_symbols)}")
    print(f"  Timeframe'ler: {len(timeframes)}")
    print(f"  Opportunities: {len(results['opportunities'])}")
    print(f"  Setups: {len(results['setups'])}")
    print(f"  Claims: {len(results['claims'])}")
    print(f"  AI Requests: {len(results['ai_requests'])}")
    print(f"  Errors: {len(results['errors'])}")

    return results


if __name__ == "__main__":
    results = run_research_cycle()
    print(f"\nDone. {len(results.get('opportunities', []))} opportunities saved.")