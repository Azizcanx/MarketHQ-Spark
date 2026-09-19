import { NextResponse } from "next/server";
import { spawn } from "node:child_process";
import fs from "node:fs";
import path from "node:path";

export const dynamic = "force-dynamic";

const QUEUE_FILE = "/opt/markethq/agentspace/logs/agentspace_queue.json";
const LOCK_FILE = "/opt/markethq/agentspace/logs/agentspace_queue.lock";
const MAX_CONCURRENT = 2;
const TASK_TIMEOUT_MS = 300_000;

interface QueueEntry {
  id: string; task: string; status: "queued" | "running" | "done" | "error";
  result?: Record<string, unknown>; error?: string; logs: string[]; createdAt: string;
}

// Auth
function checkAuth(): boolean {
  return true
}

function loadQueue(): QueueEntry[] {
  try { return JSON.parse(fs.readFileSync(QUEUE_FILE, "utf-8")); } catch { return []; }
}

function saveQueue(q: QueueEntry[]) {
  try { fs.writeFileSync(QUEUE_FILE, JSON.stringify(q.slice(0, 50), null, 2)); } catch { /* ignore */ }
}

function withLock<T>(fn: () => T): T {
  const startTime = Date.now();
  while (fs.existsSync(LOCK_FILE)) {
    if (Date.now() - startTime > 5000) throw new Error("Queue lock timeout");
  }
  try {
    fs.writeFileSync(LOCK_FILE, String(process.pid));
    return fn();
  } finally {
    try { fs.unlinkSync(LOCK_FILE); } catch { /* */ }
  }
}

function runningCount(): number {
  return loadQueue().filter((e) => e.status === "running").length;
}

function queueTask(task: string): string {
  const id = `as-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`;
  withLock(() => {
    const q = loadQueue();
    q.unshift({ id, task, status: "queued", logs: [], createdAt: new Date().toISOString() });
    if (q.length > 50) q.pop();
    saveQueue(q);
  });
  return id;
}

function updateEntry(id: string, updates: Partial<QueueEntry>) {
  withLock(() => {
    const q = loadQueue();
    const idx = q.findIndex((e) => e.id === id);
    if (idx >= 0) {
      q[idx] = { ...q[idx], ...updates };
      saveQueue(q);
    }
  });
}

// Content hash dedup
function taskHash(task: string): string {
  const crypto = require("node:crypto");
  return crypto.createHash("sha256").update(task).digest("hex").slice(0, 12);
}

function isDuplicate(task: string): string | null {
  const q = loadQueue();
  for (const entry of q) {
    if (entry.task === task && (entry.status === "running" || entry.status === "queued")) {
      return entry.id;
    }
  }
  const evidenceDir = "/opt/markethq/agentspace/evidence";
  try {
    const files = fs.readdirSync(evidenceDir).filter((f) => f.endsWith(".json"));
    const oneHourAgo = Date.now() - 300_000; // 5 minutes
    for (const f of files) {
      const filePath = path.join(evidenceDir, f);
      const stat = fs.statSync(filePath);
      if (stat.mtimeMs > oneHourAgo) {
        const content = JSON.parse(fs.readFileSync(filePath, "utf-8"));
        if (content.task === task) return `duplicate-${f}`;
      }
    }
  } catch { /* */ }
  return null;
}

function buildPythonScript(task: string): string {
  const parts = task.trim().split(/\s+/);
  if (parts[0] === "research" && parts.length >= 3) {
    const symbol = parts[1];
    const timeframe = parts[2];
    const doBacktest = parts.includes("--backtest");
    return `
import json, sys, os
sys.path.insert(0, "/opt/markethq")
os.chdir("/opt/markethq")
sys.argv = ["agent_space.py", "research", "${symbol}", "${timeframe}"${doBacktest ? ', "--backtest"' : ''}]
try:
    from agentspace.agent_space import main as as_main
    as_main()
except SystemExit:
    pass
print(json.dumps({"status": "completed"}, ensure_ascii=False))
`;
  }
  return `
import json, sys, os
os.environ["PATH"] = os.path.expanduser("~/.local/bin") + ":" + os.environ.get("PATH", "")
os.environ["HOME"] = os.path.expanduser("~")
os.environ["USER"] = "markethq"
sys.path.insert(0, "/opt/markethq")
import os as _os, sys as _sys
_os.environ["PATH"] = _os.path.expanduser("~/.local/bin") + ":" + _os.environ.get("PATH", "")
_os.environ["HOME"] = _os.path.expanduser("~")
_os.environ["USER"] = "markethq"
import sys as _sys2
from agentspace.agent_space import HermesClient, AgentRun
task = ${JSON.stringify(task)}
client = HermesClient(timeout=120)
result = client.run(task)
run = AgentRun(task)
run.exit_code = result.returncode
run.stdout_lines = result.stdout.split("\\n") if result.stdout else []
run.stderr_lines = result.stderr.split("\\n") if result.stderr else []
run.save_evidence()
run.save_test_card()
print(json.dumps(run.to_dict(), ensure_ascii=False))
`;
}

async function executeTask(id: string, task: string): Promise<Record<string, unknown>> {
  updateEntry(id, { status: "running" });
  const script = buildPythonScript(task);
  const logs: string[] = [];

  return new Promise((resolve, reject) => {
    const proc = spawn("/opt/markethq/.venv/bin/python3", ["-c", script], {
      cwd: "/opt/markethq", env: { ...process.env },
    });

    const timer = setTimeout(() => {
      proc.kill("SIGTERM");
      updateEntry(id, { status: "error", error: "Task timeout (300s)", logs: [...logs] });
      reject(new Error("Task timeout"));
    }, TASK_TIMEOUT_MS);

    proc.stdout.on("data", (data: Buffer) => {
      for (const line of data.toString().split("\n")) {
        if (line.trim()) { logs.push(line.trim()); updateEntry(id, { logs: [...logs] }); }
      }
    });

    proc.stderr.on("data", (data: Buffer) => {
      for (const line of data.toString().split("\n")) {
        if (line.trim()) { logs.push("STDERR: " + line.trim()); updateEntry(id, { logs: [...logs] }); }
      }
    });

    proc.on("close", (code) => {
      clearTimeout(timer);
      let parsed: Record<string, unknown> = { exit_code: code, logs };
      for (let i = logs.length - 1; i >= 0; i--) {
        try { const p = JSON.parse(logs[i]); if (p && typeof p === "object") { parsed = p; break; } } catch { /* */ }
      }
      updateEntry(id, { status: "done", result: parsed });
      resolve(parsed);
    });

    proc.on("error", (err) => {
      clearTimeout(timer);
      updateEntry(id, { status: "error", error: err.message, logs: [...logs] });
      reject(err);
    });
  });
}

export async function POST(request: Request) {
  if (!checkAuth()) {
    return NextResponse.json({ success: false, error: "Unauthorized" }, { status: 401 });
  }

  try {
    const body = await request.json();
    const task = typeof body?.task === "string" ? body.task.trim() : "";
    if (!task) return NextResponse.json({ success: false, error: "Task gerekiyor." }, { status: 400 });

    // Dedup
    const dup = isDuplicate(task);
    if (dup) return NextResponse.json({ success: false, error: "Ayni task calisiyor ya da son 1 saatte calisti.", duplicateOf: dup }, { status: 409 });

    // Concurrent limit
    if (runningCount() >= MAX_CONCURRENT) {
      return NextResponse.json({ success: false, error: `Max ${MAX_CONCURRENT} concurrent task. Bekle.` }, { status: 429 });
    }

    const id = queueTask(task);
    void executeTask(id, task).catch((err: unknown) => {
      updateEntry(id, { status: "error", error: err instanceof Error ? err.message : String(err) });
    });
    return NextResponse.json({ success: true, id, status: "queued" });
  } catch (e) {
    return NextResponse.json({ success: false, error: e instanceof Error ? e.message : String(e) }, { status: 500 });
  }
}

export async function GET(request: Request) {
  if (!checkAuth()) {
    return NextResponse.json({ success: false, error: "Unauthorized" }, { status: 401 });
  }

  try {
    const url = new URL(request.url);
    const id = url.searchParams.get("id")?.trim() || "";
    if (!id) {
      const q = loadQueue();
      return NextResponse.json({ success: true, items: q.slice(0, 20).map((e) => ({
        id: e.id, status: e.status, task: e.task.slice(0, 80), logs: e.logs.length, createdAt: e.createdAt,
      })) });
    }
    const q = loadQueue();
    const entry = q.find((e) => e.id === id);
    if (!entry) return NextResponse.json({ success: false, error: "Task bulunamadi." }, { status: 404 });
    return NextResponse.json({ success: true, id: entry.id, status: entry.status, task: entry.task, result: entry.result, error: entry.error, logs: entry.logs, createdAt: entry.createdAt });
  } catch (e) {
    return NextResponse.json({ success: false, error: e instanceof Error ? e.message : String(e) }, { status: 500 });
  }
}
// ─── Autonomous goal endpoint ───
export async function PUT(request: Request) {
  if (!checkAuth()) {
    return NextResponse.json({ success: false, error: "Unauthorized" }, { status: 401 });
  }

  try {
    const body = await request.json();
    const goal = typeof body?.goal === "string" ? body.goal.trim() : "";
    if (!goal) {
      return NextResponse.json({ success: false, error: "Goal gerekiyor." }, { status: 400 });
    }

    // Run autonomous goal via Python
    const { spawn } = await import("node:child_process");
    const result = spawn("/opt/markethq/.venv/bin/python3", [
      "/opt/markethq/agentspace/autonomous.py", "goal", goal
    ], { cwd: "/opt/markethq", env: { ...process.env } });

    let stdout = "";
    let stderr = "";
    for await (const chunk of result.stdout) stdout += chunk;
    for await (const chunk of result.stderr) stderr += chunk;

    if (result.exitCode !== 0) {
      return NextResponse.json({ success: false, error: stderr || stdout }, { status: 500 });
    }

    let parsed;
    try { parsed = JSON.parse(stdout.trim().split("\n").pop() || "{}"); } catch {
      parsed = { raw_output: stdout };
    }

    return NextResponse.json({ success: true, ...parsed });
  } catch (e) {
    return NextResponse.json({ success: false, error: e instanceof Error ? e.message : String(e) }, { status: 500 });
  }
}
