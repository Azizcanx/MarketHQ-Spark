import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { runScheduledAutonomousCycle } from "./autonomous-cycle-scheduler";
import { upsertAutonomousCycleState } from "./autonomous-cycle-state";
import { getAutonomousCycleStore } from "./autonomous-cycle-store";

const context = {
  runId: "scheduler-test-run",
  strategyId: "test-strategy",
  symbol: "THYAO.IS",
  timeframe: "1d",
  metadata: { cycleId: "scheduler-test-cycle", cycleNumber: 1, maxCycles: 2, implementationIntent: "ITERATE" },
};

const disabled = await runScheduledAutonomousCycle({
  context,
  policy: { enabled: false } as any,
  options: { enabled: false, recoveryMaxAgeMs: 60_000 },
});

assert.equal(disabled.executed, false);
assert.equal(disabled.reason, "SCHEDULER_DISABLED");
assert.ok(disabled.recovery);

const dbPath = path.join(os.tmpdir(), `markethq-scheduler-${Date.now()}-${Math.random().toString(16).slice(2)}.sqlite`);
process.env.MARKETHQ_WORKER_DB_PATH = dbPath;
const store = getAutonomousCycleStore();

upsertAutonomousCycleState({
  cycleId: context.metadata.cycleId,
  runId: context.runId,
  cycleNumber: 1,
  maxCycles: 2,
  status: "ACCEPTED",
  lastAction: "STOP_ACCEPTED",
  lastReason: "already accepted",
  attempts: 1,
  updatedAt: new Date().toISOString(),
});

const guarded = await runScheduledAutonomousCycle({
  context,
  policy: { enabled: false } as any,
  options: { enabled: true, recoveryMaxAgeMs: 60_000 },
});
assert.equal(guarded.executed, false);
assert.equal(guarded.reason, "GUARD_TERMINAL_CYCLE");

const leaseContext = {
  ...context,
  runId: "scheduler-lease-run",
  metadata: { ...context.metadata, cycleId: "scheduler-lease-cycle" },
};
const held = store.acquireLease(leaseContext.metadata.cycleId, "other-scheduler", 60_000);
assert.ok(held);

const leaseBlocked = await runScheduledAutonomousCycle({
  context: leaseContext,
  policy: { enabled: false } as any,
  options: { enabled: true, recoveryMaxAgeMs: 60_000, ownerId: "test-scheduler" },
});
assert.equal(leaseBlocked.executed, false);
assert.equal(leaseBlocked.reason, "CYCLE_LEASE_HELD");
assert.equal(store.getLease(leaseContext.metadata.cycleId)?.ownerId, "other-scheduler");
store.releaseLease(leaseContext.metadata.cycleId, "other-scheduler");
store.close();

const storeFiles = [dbPath, `${dbPath}-wal`, `${dbPath}-shm`];
for (const file of storeFiles) {
  try { fs.rmSync(file, { force: true }); } catch {}
}
console.log("AUTONOMOUS CYCLE SCHEDULER TEST PASS");
