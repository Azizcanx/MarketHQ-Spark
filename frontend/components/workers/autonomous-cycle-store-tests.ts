import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { AutonomousCycleStore } from "./autonomous-cycle-store";

const dir = fs.mkdtempSync(path.join(os.tmpdir(), "mhq-cycle-store-"));
const dbPath = path.join(dir, "cycle.sqlite");
const state = {
  cycleId: "durable-cycle-v1",
  runId: "durable-run-v1",
  cycleNumber: 2,
  maxCycles: 5,
  status: "DISPATCHED",
  lastAction: "DISPATCH_IMPLEMENTATION",
  lastReason: "EXPLICIT_IMPLEMENTATION_INTENT_READY",
  workerTaskId: "task-durable-1",
  workerStatus: "RUNNING",
  attempts: 1,
  updatedAt: new Date().toISOString(),
} as const;

const first = new AutonomousCycleStore(dbPath);
first.upsert(state);
assert.deepEqual(first.get(state.cycleId), state);
first.close();

const second = new AutonomousCycleStore(dbPath);
assert.deepEqual(second.get(state.cycleId), state);
assert.equal(second.list(10).length, 1);
second.close();

fs.rmSync(dir, { recursive: true, force: true });
console.log("autonomous-cycle-store-tests: PASS");
