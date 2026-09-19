import { NextResponse } from "next/server";
import { execFile } from "node:child_process";
import { promisify } from "node:util";

export const dynamic = "force-dynamic";
const run = promisify(execFile);
const BACKEND = process.env.MARKETHQ_BACKEND_URL?.replace(/\/+$/, "") || "http://127.0.0.1:8010";

// GET /api/setup-from-symbol?symbol=ETH-USD&interval=1d&benchmark=BTC-USD -> { setup, validation, scoreboard } (research-only)
export async function GET(req: Request) {
  const { searchParams } = new URL(req.url);
  const symbol = searchParams.get("symbol")?.trim() || "BTC-USD";
  const interval = searchParams.get("interval")?.trim() || "1d";
  const benchmark = searchParams.get("benchmark")?.trim() || null;
  const source = searchParams.get("source")?.trim() || "binance";
  const pair = searchParams.get("pair")?.trim() || null;
  const end = new Date().toISOString().slice(0, 10);
  const dataUrl = (s: string) =>
    `${BACKEND}/api/research-data?symbol=${encodeURIComponent(s)}&start=2024-01-01&end=${end}&interval=${encodeURIComponent(interval)}&limit=250`;
  type Row = { open: number; high: number; low: number; close: number; volume: number };
  const BIN_MAP: Record<string, string> = {
    "BTC-USD": "BTCUSDT", "ETH-USD": "ETHUSDT", "SOL-USD": "SOLUSDT",
    "BTC": "BTCUSDT", "ETH": "ETHUSDT", "SOL": "SOLUSDT",
  };
  async function loadBinance(s: string): Promise<Row[]> {
    const bsym = BIN_MAP[s.toUpperCase()] ?? s.toUpperCase().replace(/[\/-]/g, "").replace(/USD$/, "USDT");
    const bint = interval === "1h" ? "1h" : interval === "15m" ? "15m" : "1d";
    const r = await fetch(`https://api.binance.com/api/v3/klines?symbol=${bsym}&interval=${bint}&limit=200`, {
      cache: "no-store", headers: { Accept: "application/json" },
    });
    if (!r.ok) throw new Error(`binance HTTP ${r.status}`);
    const raw = (await r.json()) as string[][];
    return raw.map((k) => ({ open: +k[1], high: +k[2], low: +k[3], close: +k[4], volume: +k[5] }));
  }
  async function loadRows(s: string): Promise<Row[]> {
    const r = await fetch(dataUrl(s), { cache: "no-store" });
    const body = (await r.json()) as { data?: { rows?: Row[] } };
    return body.data?.rows ?? [];
  }
  let rows: Row[];
  const useBinance = source === "binance";
  try {
    rows = useBinance ? await loadBinance(symbol) : await loadRows(symbol);
  } catch (e) {
    return NextResponse.json({ error: `data fetch failed: ${String(e).slice(0, 200)}` }, { status: 502 });
  }
  if (rows.length < 60) return NextResponse.json({ error: `yetersiz bar: ${rows.length}` }, { status: 400 });
  const bars = rows.slice(-200);
  let benchmarkCloses: number[] | null = null;
  let pairCloses: number[] | null = null;
  if (benchmark && benchmark !== symbol) {
    try {
      const bRows = useBinance ? await loadBinance(benchmark) : await loadRows(benchmark);
      const tail = bRows.slice(-200);
      if (tail.length >= 60) benchmarkCloses = tail.map((b) => b.close);
    } catch {
      benchmarkCloses = null;
    }
  }
  if (pair && pair !== symbol) {
    try {
      const pRows = useBinance ? await loadBinance(pair) : await loadRows(pair);
      const tail = pRows.slice(-200);
      if (tail.length >= 60) pairCloses = tail.map((b) => b.close);
    } catch {
      pairCloses = null;
    }
  }
  const script = `
import json,sys,pandas as pd
from setup_engine_v1 import build_setup
from setup_validation_v1 import validate_setup
from strategy_scoreboard_v1 import build_scoreboard
from strategy_evolution_v1 import build_evolution
from pair_spread_v1 import pair_spread
payload=json.load(open(sys.argv[1]))
df=pd.DataFrame([{"Open":b["open"],"High":b["high"],"Low":b["low"],"Close":b["close"],"Volume":b["volume"]} for b in payload["bars"]])
bench=payload.get("benchmark")
sym=payload.get("symbol","UNKNOWN")
fee=0.00075 if payload.get("source")=="binance" else 0.001
cfg={"fee_pct":fee}
evo=build_evolution()
pair=payload.get("pair_closes")
spread=pair_spread([b["close"] for b in payload["bars"]],pair,sym,payload.get("pair") or "?") if pair else {"available":False,"detail":"pair yok"}
print(json.dumps({"setup":build_setup(df,payload.get("timeframe","1d"),benchmark=bench,symbol=sym),"validation":validate_setup(df,payload.get("timeframe","1d"),config=cfg),"scoreboard":build_scoreboard(),"spread":spread,"evolution":{"strategies":{k:{"status":v["status"],"hit_rate":v["hit_rate"],"n":v["n"]} for k,v in evo["strategies"].items()},"observations":evo.get("observations",[]),"questions":evo.get("suggested_research_questions",[]),"brain_db":evo.get("brain_db",{})}},ensure_ascii=False))
`;
  const fs = await import("node:fs/promises");
  const os = await import("node:os");
  const path = await import("node:path");
  const tmp = path.join(os.tmpdir(), `setup-sym-${Date.now()}.json`);
  await fs.writeFile(tmp, JSON.stringify({ bars, timeframe: interval, benchmark: benchmarkCloses, symbol, pair, pair_closes: pairCloses, source }));
  try {
    const { stdout } = await run("/opt/markethq/.venv/bin/python", ["-c", script, tmp], {
      cwd: "/opt/markethq", timeout: 60000, maxBuffer: 4 * 1024 * 1024,
    });
    return NextResponse.json({ symbol, interval, benchmark, pair, source, ...(JSON.parse(stdout) as object) });
  } catch (e) {
    return NextResponse.json({ error: String(e).slice(0, 500) }, { status: 500 });
  } finally {
    await fs.unlink(tmp).catch(() => {});
  }
}
