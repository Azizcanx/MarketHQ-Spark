import { NextResponse } from "next/server";
import { execFile } from "node:child_process";
import { promisify } from "node:util";

export const dynamic = "force-dynamic";
const run = promisify(execFile);

// GET /api/health — system health check
export async function GET() {
  const checks: Record<string, boolean | string | number> = {};

  // Disk
  try {
    const { stdout } = await run("df", ["/opt/markethq", "--output=pcent"]);
    const pct = stdout.trim().split("\n")[1]?.trim() || "";
    checks.disk = pct;
  } catch {
    checks.disk = "unknown";
  }

  // Agentspace evidence count
  try {
    const { stdout } = await run("ls", ["/opt/markethq/agentspace/evidence"]);
    const count = stdout.trim().split("\n").filter(Boolean).length;
    checks.evidence_files = count;
  } catch {
    checks.evidence_files = "unknown";
  }

  // Queue status
  try {
    const fs = await import("node:fs");
    const q = JSON.parse(fs.readFileSync("/opt/markethq/agentspace/logs/agentspace_queue.json", "utf-8"));
    const running = q.filter((e: any) => e.status === "running").length;
    const queued = q.filter((e: any) => e.status === "queued").length;
    checks.queue_running = running;
    checks.queue_queued = queued;
  } catch {
    checks.queue_running = 0;
    checks.queue_queued = 0;
  }

  // Python/Hermes
  try {
    await run("/opt/markethq/.venv/bin/python3", ["-c", "import hermes_tools"]);
    checks.hermes = true;
  } catch {
    checks.hermes = false;
  }

  // UFW
  try {
    const { stdout } = await run("sudo", ["ufw", "status"]);
    checks.ufw = stdout.includes("active") ? "active" : "inactive";
  } catch {
    checks.ufw = "unknown";
  }

  const allGood = Object.values(checks).every((v) => v === true || v === "active" || typeof v === "number");

  return NextResponse.json({
    status: allGood ? "ok" : "degraded",
    timestamp: new Date().toISOString(),
    checks,
  });
}