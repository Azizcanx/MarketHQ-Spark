import assert from "node:assert/strict";
import os from "node:os";
import path from "node:path";
import fs from "node:fs";
import { AutonomousCycleStore } from "./autonomous-cycle-store";

const dir = fs.mkdtempSync(path.join(os.tmpdir(), "mhq-cycle-recovery-"));
const db = path.join(dir, "worker.sqlite");
const store = new AutonomousCycleStore(db);
const stale = {
  cycleId: "recovery-test-cycle",
  runId: "recovery-test-run",
  cycleNumber: 2,
  maxCycles: 10,
  status: "RUNNING" as const,
  lastAction: "CONTINUE_RESEARCH" as const,
  lastReason: "test",
  workerTaskId: "task-1",
  workerStatus: "RUNNING",
  attempts: 1,
  updatedAt: new Date(Date.now() - 60_000).toISOString(),
};
store.upsert(stale);
store.close();

process.env.MARKETHQ_WORKER_DB_PATH = db;
const { getAutonomousCycleStore } = await import("./autonomous-cycle-store");
const { recoverStaleAutonomousCycles } = await import("./autonomous-cycle-recovery");
const result = recoverStaleAutonomousCycles(1_000);
assert.equal(result.recovered, 1);
assert.equal(getAutonomousCycleStore().get(stale.cycleId)?.status, "REVIEW_REQUIRED");
assert.match(getAutonomousCycleStore().get(stale.cycleId)?.lastReason ?? "", /^STALE_CYCLE_RECOVERED:/);
getAutonomousCycleStore().close();
fs.rmSync(dir, { recursive: true, force: true });
console.log("AUTONOMOUS CYCLE RECOVERY TEST PASS");
