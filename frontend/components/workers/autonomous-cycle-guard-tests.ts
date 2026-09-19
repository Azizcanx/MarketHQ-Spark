import assert from "node:assert/strict";
import { guardAutonomousCycleDispatch } from "./autonomous-cycle-guard";

const context = { runId: "guard-run", metadata: { cycleId: "c1", cycleNumber: 1, maxCycles: 3 } };
const base = { cycleId: "c1", runId: "guard-run", cycleNumber: 1, maxCycles: 3, status: "RUNNING" as const, lastAction: "CONTINUE_RESEARCH" as const, lastReason: "test", attempts: 0, updatedAt: new Date().toISOString() };

assert.equal(guardAutonomousCycleDispatch(context, null).allowed, true);
assert.equal(guardAutonomousCycleDispatch(context, base).allowed, true);
assert.equal(guardAutonomousCycleDispatch(context, { ...base, status: "ACCEPTED" }).reason, "TERMINAL_CYCLE");
assert.equal(guardAutonomousCycleDispatch({ ...context, metadata: { ...context.metadata, cycleId: "other" } }, base).reason, "CYCLE_ID_MISMATCH");
assert.equal(guardAutonomousCycleDispatch({ ...context, metadata: { ...context.metadata, cycleNumber: 4 } }, base).reason, "BUDGET_EXCEEDED");
console.log("AUTONOMOUS_CYCLE_GUARD_TESTS PASS");
