import { NextResponse } from "next/server";
import { execFile } from "node:child_process";
import { promisify } from "node:util";

export const dynamic = "force-dynamic";

const run = promisify(execFile);

type Bar = { open: number; high: number; low: number; close: number; volume: number };

// POST { bars: Bar[], timeframe?: string } -> { setup, validation } (research-only, no trading)
export async function POST(req: Request) {
  let body: { bars?: Bar[]; timeframe?: string };
  try {
    body = (await req.json()) as { bars?: Bar[]; timeframe?: string };
  } catch {
    return NextResponse.json({ error: "invalid json" }, { status: 400 });
  }
  const bars = body.bars ?? [];
  if (!Array.isArray(bars) || bars.length < 60) {
    return NextResponse.json({ error: "min 60 bars required" }, { status: 400 });
  }
  const timeframe = body.timeframe ?? "1h";
  const script = `
import json,sys,pandas as pd
from setup_engine_v1 import build_setup
from setup_validation_v1 import validate_setup
payload=json.load(open(sys.argv[1]))
df=pd.DataFrame([{"Open":b["open"],"High":b["high"],"Low":b["low"],"Close":b["close"],"Volume":b["volume"]} for b in payload["bars"]])
s=build_setup(df,payload.get("timeframe","1h"))
v=validate_setup(df,payload.get("timeframe","1h"))
print(json.dumps({"setup":s,"validation":v},ensure_ascii=False))
`;
  const fs = await import("node:fs/promises");
  const os = await import("node:os");
  const path = await import("node:path");
  const tmp = path.join(os.tmpdir(), `setup-${Date.now()}.json`);
  await fs.writeFile(tmp, JSON.stringify({ bars, timeframe }));
  try {
    const { stdout } = await run("/opt/markethq/.venv/bin/python", ["-c", script, tmp], {
      cwd: "/opt/markethq",
      timeout: 60000,
      maxBuffer: 4 * 1024 * 1024,
    });
    return NextResponse.json(JSON.parse(stdout));
  } catch (e) {
    return NextResponse.json({ error: String(e).slice(0, 500) }, { status: 500 });
  } finally {
    await fs.unlink(tmp).catch(() => {});
  }
}
