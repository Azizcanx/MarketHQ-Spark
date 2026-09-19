import { NextResponse } from "next/server";
import fs from "fs";
import path from "path";

const OHLCV_DIR = "/opt/markethq/data/ohlcv";
const LIVE_STATE_FILE = "/opt/markethq/data/live_state.json";

const BINANCE_SYMS: Record<string, string> = {
  "BTC-USD": "BTCUSDT",
  "EURUSD=X": "EURUSDT",
};

function readLiveState(): Record<string, unknown> | null {
  try {
    if (!fs.existsSync(LIVE_STATE_FILE)) return null;
    const raw = fs.readFileSync(LIVE_STATE_FILE, "utf-8");
    return JSON.parse(raw);
  } catch {
    return null;
  }
}

function readLatestBar(symbol: string, timeframe: string): Record<string, unknown> | null {
  const fileName = `${symbol}__${timeframe}.json`;
  const filePath = path.join(OHLCV_DIR, fileName);
  try {
    if (!fs.existsSync(filePath)) return null;
    const raw = fs.readFileSync(filePath, "utf-8");
    const data = JSON.parse(raw);
    const bars: unknown[] = data.bars || [];
    if (bars.length === 0) return null;
    const lastBar = bars[bars.length - 1] as Record<string, unknown>;
    return {
      timestamp: lastBar.t || lastBar.timestamp || lastBar[0],
      open: lastBar.o || lastBar.open,
      high: lastBar.h || lastBar.high,
      low: lastBar.l || lastBar.low,
      close: lastBar.c || lastBar.close,
      volume: lastBar.v || lastBar.volume,
    };
  } catch {
    return null;
  }
}

function resolveBinanceSymbol(symbol: string): string | null {
  return BINANCE_SYMS[symbol] || null;
}

export async function GET() {
  const requestedAt = new Date().toISOString();
  const liveState = readLiveState();
  const symbols = (liveState?.symbols_processed as string[]) || [];
  const timeframe = "1h";

  const marketState = symbols.map((symbol) => {
    const bar = readLatestBar(symbol, timeframe);
    const binanceSym = resolveBinanceSymbol(symbol);
    return {
      symbol,
      binance_symbol: binanceSym,
      price: bar?.close ?? null,
      open: bar?.open ?? null,
      high: bar?.high ?? null,
      low: bar?.low ?? null,
      volume: bar?.volume ?? null,
      timeframe,
      timestamp: bar?.timestamp ?? null,
      data_source: "binance_ohlcv_cache",
      last_update: requestedAt,
    };
  });

  const lastRun = liveState?.last_run ?? null;
  const dataAgeMs = lastRun
    ? Date.now() - new Date(lastRun as string).getTime()
    : null;
  const isStale = dataAgeMs !== null && dataAgeMs > 3600_000; // > 1 hour

  return NextResponse.json({
    success: true,
    market_state: marketState,
    latest: marketState[0] ?? null,
    data_source: "binance_ohlcv_cache",
    last_run: lastRun,
    data_age_ms: dataAgeMs,
    is_stale: isStale,
    symbols_count: marketState.length,
    requested_at: requestedAt,
  });
}