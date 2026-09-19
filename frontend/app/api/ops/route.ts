import { NextResponse } from "next/server";
import { execFile } from "node:child_process";
import { promisify } from "node:util";

export const dynamic = "force-dynamic";
const run = promisify(execFile);

// GET /api/ops -> otonom sistem durum panosu (research-only, salt-okunur)
export async function GET() {
  const script = `
import json
from strategy_scoreboard_v1 import build_scoreboard
from strategy_evolution_v1 import build_evolution
from pathlib import Path
ops = Path("agentspace/agentspace/logs/ops_runs.jsonl")
runs = []
if ops.exists():
    lines = ops.read_text(encoding="utf-8").strip().split("\\n")
    for ln in lines[-10:]:
        try: runs.append(json.loads(ln))
        except Exception: pass
sb = build_scoreboard()
evo = build_evolution()
print(json.dumps({"runs": runs, "decided": sb.get("decided"), "pending": sb.get("pending"),
  "ranking": sb.get("ranking", [])[:5], "symbols": sb.get("symbols", {}),
  "observations": evo.get("observations", []), "questions": evo.get("suggested_research_questions", [])}, ensure_ascii=False))
`;
  let data: Record<string, unknown> = {};
  try {
    const { stdout } = await run("/opt/markethq/.venv/bin/python", ["-c", script], {
      cwd: "/opt/markethq", timeout: 60000, maxBuffer: 4 * 1024 * 1024,
    });
    data = JSON.parse(stdout) as Record<string, unknown>;
  } catch (e) {
    return NextResponse.json({ error: String(e).slice(0, 300) }, { status: 500 });
  }
  let backend = false;
  try {
    const r = await fetch("http://127.0.0.1:8010/api/research-data?symbol=BTC-USD&start=2026-09-15&end=2026-09-16&interval=1d&limit=1", { cache: "no-store" });
    backend = r.ok;
  } catch {
    backend = false;
  }
  let binance = false;
  try {
    const r = await fetch("https://api.binance.com/api/v3/ping", { cache: "no-store" });
    binance = r.ok;
  } catch {
    binance = false;
  }
  return NextResponse.json({ web: true, backend, binance, ...data });
}
