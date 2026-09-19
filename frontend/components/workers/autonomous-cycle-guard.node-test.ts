import assert from "node:assert/strict";
import test from "node:test";
import { guardAutonomousCycleDispatch } from "./autonomous-cycle-guard";

test("guard allows an unpersisted cycle", () => {
  const decision = guardAutonomousCycleDispatch({ runId: "run-1", metadata: { cycleId: "cycle-1" } }, null);
  assert.equal(decision.allowed, true);
});

test("guard rejects a mismatched cycle id", () => {
  const decision = guardAutonomousCycleDispatch(
    { runId: "run-1", metadata: { cycleId: "cycle-1" } },
    {
      cycleId: "cycle-2", runId: "run-1", cycleNumber: 1, maxCycles: 2,
      status: "ACTIVE", lastAction: "dispatch", lastReason: "running", attempts: 1,
      updatedAt: "2026-09-14T10:00:00.000Z",
    },
  );
  assert.deepEqual(decision, { allowed: false, reason: "CYCLE_ID_MISMATCH" });
});

test("guard rejects terminal states", () => {
  for (const status of ["ACCEPTED", "REVIEW_REQUIRED", "FAILED", "BUDGET_EXCEEDED"] as const) {
    const decision = guardAutonomousCycleDispatch(
      { runId: "run-1", metadata: { cycleId: "cycle-1" } },
      {
        cycleId: "cycle-1", runId: "run-1", cycleNumber: 1, maxCycles: 2,
        status, lastAction: "complete", lastReason: "terminal", attempts: 1,
        updatedAt: "2026-09-14T10:00:00.000Z",
      },
    );
    assert.deepEqual(decision, { allowed: false, reason: "TERMINAL_CYCLE" });
  }
});

test("guard rejects a cycle beyond its budget", () => {
  const decision = guardAutonomousCycleDispatch(
    { runId: "run-1", metadata: { cycleId: "cycle-1" } },
    {
      cycleId: "cycle-1", runId: "run-1", cycleNumber: 3, maxCycles: 2,
      status: "ACTIVE", lastAction: "dispatch", lastReason: "running", attempts: 3,
      updatedAt: "2026-09-14T10:00:00.000Z",
    },
  );
  assert.deepEqual(decision, { allowed: false, reason: "BUDGET_EXCEEDED" });
});

test("guard allows an active cycle within budget", () => {
  const decision = guardAutonomousCycleDispatch(
    { runId: "run-1", metadata: { cycleId: "cycle-1" } },
    {
      cycleId: "cycle-1", runId: "run-1", cycleNumber: 1, maxCycles: 2,
      status: "ACTIVE", lastAction: "dispatch", lastReason: "running", attempts: 1,
      updatedAt: "2026-09-14T10:00:00.000Z",
    },
  );
  assert.deepEqual(decision, { allowed: true, reason: "ACTIVE_CYCLE" });
});
