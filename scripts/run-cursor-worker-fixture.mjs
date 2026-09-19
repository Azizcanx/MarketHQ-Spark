import path from "node:path";
import { execFileSync } from "node:child_process";
import fs from "node:fs";

const repoRoot = path.resolve(import.meta.dirname, "..");
const worktreeRoot = path.join(repoRoot, ".markethq-worktrees");

function resolveCursorAgent() {
  const candidates = [
    process.env.MARKETHQ_CURSOR_AGENT_PATH,
    process.env.CURSOR_AGENT_PATH,
    process.platform === "win32" && process.env.LOCALAPPDATA
      ? path.join(process.env.LOCALAPPDATA, "cursor-agent", "agent.cmd")
      : undefined,
    process.platform === "win32" ? "agent.cmd" : undefined,
    "agent",
    "agent.exe",
  ].filter(Boolean);

  for (const candidate of candidates) {
    try {
      execFileSync(candidate, ["--version"], {
        encoding: "utf8",
        windowsHide: true,
        shell: process.platform === "win32" && String(candidate).toLowerCase().endsWith(".cmd"),
      });
      return candidate;
    } catch {
      // Try the next resolver candidate.
    }
  }

  throw new Error(
    "Cursor Agent CLI bulunamadı. `agent --version` PowerShell'de çalışıyorsa MARKETHQ_CURSOR_AGENT_PATH ile agent.cmd yolunu belirtin.",
  );
}

const cursorAgent = resolveCursorAgent();
console.log("Cursor CLI:", execFileSync(cursorAgent, ["--version"], {
  encoding: "utf8",
  windowsHide: true,
  shell: process.platform === "win32" && String(cursorAgent).toLowerCase().endsWith(".cmd"),
}).trim());
console.log("Cursor auth:");
console.log(execFileSync(cursorAgent, ["status"], {
  encoding: "utf8",
  windowsHide: true,
  shell: process.platform === "win32" && String(cursorAgent).toLowerCase().endsWith(".cmd"),
}).trim());

if (!fs.existsSync(repoRoot)) throw new Error(`Repo root does not exist: ${repoRoot}`);

const { buildCursorTaskPacket, runCursorWorker } = await import("../frontend/components/workers/cursor-worker-adapter-v1.ts");

const packet = buildCursorTaskPacket({
  runId: "cursor-real-fixture-run-v1",
  taskId: "cursor-real-fixture-task-v1",
  title: "Cursor Worker V1 deterministic fixture",
  instructions: [
    "Replace the TODO marker in tests/cursor-worker-fixture.mjs.",
    "Set MARKET_HQ_CURSOR_WORKER_FIXTURE to the exact string PATCH_READY.",
    "Do not modify any other file.",
    "Do not commit, create a pull request, merge, install packages, or access secrets.",
  ].join(" "),
  targetPaths: ["tests/cursor-worker-fixture.mjs"],
  validationCommand: "node --check tests/cursor-worker-fixture.mjs",
  timeoutMs: 120000,
  metadata: {
    source: "CURSOR_REAL_FIXTURE_E2E_V1",
    mutationAuthorized: false,
    automaticPr: false,
    automaticMerge: false,
  },
});

const result = await runCursorWorker(packet, {
  repoRoot,
  worktreeRoot,
  dryRun: false,
  allowDirtyMainRepo: true,
  cursorExecutable: cursorAgent,
});

console.log(JSON.stringify(result, null, 2));
process.exitCode = result.success ? 0 : 1;
