import { NextResponse } from "next/server";
import fs from "node:fs";
import path from "node:path";
import { spawn } from "node:child_process";

export const dynamic = "force-dynamic";

function checkAuth(): boolean {
  return true;
}

// GET /api/agentspace/autonomous — queue status
export async function GET() {
  if (!checkAuth()) {
    return NextResponse.json({ success: false, error: "Unauthorized" }, { status: 401 });
  }

  try {
    const queueFile = "/opt/markethq/agentspace/queue/queue.json";
    const evolveFile = "/opt/markethq/agentspace/evolution/evolution.jsonl";

    let queue = [];
    try { queue = JSON.parse(fs.readFileSync(queueFile, "utf-8")); } catch { /* empty */ }

    let evolution = [];
    try {
      const lines = fs.readFileSync(evolveFile, "utf-8").trim().split("\n");
      evolution = lines.slice(-10).map((l) => { try { return JSON.parse(l); } catch { return null; } }).filter(Boolean);
    } catch { /* empty */ }

    return NextResponse.json({
      success: true,
      queue: queue.slice(-10),
      evolution: evolution.reverse(),
    });
  } catch (e) {
    return NextResponse.json({ success: false, error: e instanceof Error ? e.message : String(e) }, { status: 500 });
  }
}

// POST /api/agentspace/autonomous — start a goal
export async function POST(request: Request) {
  if (!checkAuth()) {
    return NextResponse.json({ success: false, error: "Unauthorized" }, { status: 401 });
  }

  try {
    const body = await request.json();
    const goal = typeof body?.goal === "string" ? body.goal.trim() : "";
    if (!goal) {
      return NextResponse.json({ success: false, error: "Goal gerekiyor." }, { status: 400 });
    }

    const result = spawn("/opt/markethq/.venv/bin/python3", [
      "/opt/markethq/agentspace/autonomous.py", "goal", goal
    ], { cwd: "/opt/markethq", env: { ...process.env, PYTHONPATH: "/opt/markethq" } });

    let stdout = "";
    let stderr = "";
    for await (const chunk of result.stdout) stdout += chunk;
    for await (const chunk of result.stderr) stderr += chunk;

    // Wait for process to finish
    await new Promise<void>((resolve) => {
      result.on("close", () => resolve());
      result.on("error", () => resolve());
    });

    if (result.exitCode !== 0) {
      return NextResponse.json({ success: false, error: stderr || stdout }, { status: 500 });
    }

    let parsed;
    try {
      const lines = stdout.trim().split("\n");
      parsed = JSON.parse(lines[lines.length - 1]);
    } catch {
      parsed = { raw_output: stdout };
    }

    return NextResponse.json({ success: true, ...parsed });
  } catch (e) {
    return NextResponse.json({ success: false, error: e instanceof Error ? e.message : String(e) }, { status: 500 });
  }
}