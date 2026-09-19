import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import test from "node:test";

const tempRoot = fs.mkdtempSync(path.join(os.tmpdir(), "markethq-hq-overview-"));
process.env.MARKETHQ_REPO_ROOT = tempRoot;
process.env.VERCEL = "0";
process.env.MARKETHQ_HERMES_WORKER_ENABLE = "true";
process.env.MARKETHQ_HERMES_API_URL = "http://127.0.0.1:8642";
process.env.MARKETHQ_HERMES_API_KEY = "test-key";

const { getHQBusinessOverview } = await import("./hq-overview");
const { saveHQRunHistory } = await import("./hq-run-store");
const { saveHQWorkerSession } = await import("./hq-worker-session-store");

test("HQ business overview exposes normalized activity without secrets", () => {
  saveHQRunHistory({
    plan: {
      runId: "overview-run-1",
      command: "Trendyol durum nasıl?",
      intent: "TRENDYOL_STATUS",
      manager: "hq-manager",
      tasks: [],
      mode: "RESEARCH_ONLY",
      executionEnabled: false,
      brain: { provider: "hermes", rationale: "test" },
    },
    status: "COMPLETED",
    tasks: [],
    context: {
      runId: "overview-run-1",
      command: "Trendyol durum nasıl?",
      intent: "TRENDYOL_STATUS",
      mode: "RESEARCH_ONLY",
      executionEnabled: false,
      evidence: [],
    },
    startedAt: "2026-09-15T00:00:00.000Z",
    completedAt: "2026-09-15T00:00:01.000Z",
  });

  saveHQWorkerSession({
    sessionId: "worker-overview-1",
    runId: "overview-run-1",
    taskId: "task-1",
    providerId: "hermes",
    status: "RUNNING",
    completedSteps: 2,
    totalSteps: 4,
    currentStep: "validating",
    updatedAt: "2026-09-15T00:00:01.000Z",
  });

  const overview = getHQBusinessOverview();
  assert.equal(overview.business.recentRuns, 1);
  assert.equal(overview.business.activeWorkers, 1);
  assert.equal(overview.activity.recentRuns[0]?.runId, "overview-run-1");
  assert.equal(overview.activity.workers[0]?.providerId, "hermes");
  assert.equal(overview.activity.workers[0]?.currentStep, "validating");
  assert.equal(overview.operations.trendyol.state, "NOT_CONFIGURED");
  assert.equal(overview.security.executionEnabled, false);
  assert.equal(overview.security.databaseWriteEnabled, false);
  assert.equal(JSON.stringify(overview).includes("test-key"), false);
});
