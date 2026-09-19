import assert from "node:assert/strict";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import test from "node:test";
import { runOneAutonomousCycle } from "./autonomous-cycle-runner";
import { runScheduledAutonomousCycle } from "./autonomous-cycle-scheduler";
import { getAutonomousCycleState } from "./autonomous-cycle-state";
import type { AgentContext } from "../agents/agent-types";
import type { WorkerFeedback, WorkerRecord } from "./worker-types";

const policy = {
  enabled: false,
  targetPaths: ["tests/cursor-worker-fixture.mjs"],
  instructions: "safe deterministic E2E fixture",
  validationCommand: "node --check tests/cursor-worker-fixture.mjs",
  implementationIntent: "ITERATE",
};

const baseContext: AgentContext = {
  runId: "two-cycle-e2e-run",
  metadata: { cycleId: "two-cycle-e2e", cycleNumber: 1, maxCycles: 2, implementationIntent: "ITERATE" },
  previousResults: {
    "research-decision": { success: true, agentId: "research-decision", runId: "research-run", status: "COMPLETED", startedAt: "2026-01-01T00:00:00.000Z", completedAt: "2026-01-01T00:00:01.000Z", output: {} },
    "research-queue": { success: true, agentId: "research-queue", runId: "research-run", status: "COMPLETED", startedAt: "2026-01-01T00:00:00.000Z", completedAt: "2026-01-01T00:00:01.000Z", output: { queue: { selectedTask: { metadata: { workerTargetPaths: ["tests/cursor-worker-fixture.mjs"], workerInstructions: "safe deterministic E2E fixture", workerValidationCommand: "node --check tests/cursor-worker-fixture.mjs" } } } } },
  },
};

const acceptedWorker: WorkerRecord = {
  taskId: "two-cycle-worker-task",
  runId: "two-cycle-worker-run",
  provider: "cursor",
  attempt: 1,
  maxAttempts: 2,
  status: "ACCEPTED",
  jobId: "two-cycle-job",
  changedFiles: [],
  createdAt: "2026-01-01T00:00:00.000Z",
  startedAt: "2026-01-01T00:00:01.000Z",
  completedAt: "2026-01-01T00:00:02.000Z",
};

const acceptedFeedback: WorkerFeedback = {
  taskId: acceptedWorker.taskId,
  runId: acceptedWorker.runId,
  kind: "IMPLEMENTATION_VERIFIED",
  recommendation: "ACCEPT",
  attempts: 1,
  validationFailures: 0,
  validationPasses: 1,
  failureCount: 0,
  changedFiles: [],
  evidenceQuality: "HIGH",
  learningEligible: false,
  researchImpact: "IMPLEMENTATION_ONLY",
  summary: "deterministic two-cycle E2E acceptance",
  failureDetails: [],
  nextCycleInput: {
    implementationStatus: "IMPLEMENTATION_VERIFIED",
    implementationIntent: "ITERATE",
    recommendation: "ACCEPT",
    retryRecommended: false,
    changedFiles: [],
  },
  createdAt: "2026-01-01T00:00:02.000Z",
};

test("autonomous cycle completes deterministic two-cycle handoff and terminal guard", async () => {
  const dbDir = mkdtempSync(path.join(tmpdir(), "markethq-2cycle-"));
  process.env.MARKETHQ_WORKER_DB_PATH = path.join(dbDir, "worker-runtime.sqlite");
  process.env.MARKETHQ_AUTONOMOUS_CYCLE_SCHEDULER = "false";

  try {
    const cycle1 = await runOneAutonomousCycle({ context: baseContext, policy });
    assert.equal(cycle1.cycle.decision.action, "DISPATCH_IMPLEMENTATION");
    assert.equal(cycle1.cycle.dispatched, false);
    assert.equal(cycle1.cycle.reason, "WORKER_POLICY_DISABLED");
    assert.equal(cycle1.state.status, "DISPATCHED");
    assert.equal(cycle1.state.cycleNumber, 1);

    const cycle2 = await runOneAutonomousCycle({
      context: { ...baseContext, runId: "two-cycle-e2e-run-2", metadata: { ...baseContext.metadata, cycleNumber: 2 } },
      worker: acceptedWorker,
      feedback: acceptedFeedback,
      policy,
    });
    assert.equal(cycle2.cycle.decision.action, "STOP_ACCEPTED");
    assert.equal(cycle2.cycle.dispatched, false);
    assert.equal(cycle2.state.status, "ACCEPTED");
    assert.equal(cycle2.state.cycleNumber, 2);

    const persisted = getAutonomousCycleState("two-cycle-e2e");
    assert.equal(persisted?.status, "ACCEPTED");
    assert.equal(persisted?.cycleNumber, 2);

    const cycle3 = await runScheduledAutonomousCycle({
      context: { ...baseContext, runId: "two-cycle-e2e-run-3", metadata: { ...baseContext.metadata, cycleNumber: 3 } },
      policy,
      options: { enabled: true, ownerId: "two-cycle-e2e-owner" },
    });
    assert.equal(cycle3.executed, false);
    assert.equal(cycle3.reason, "GUARD_TERMINAL_CYCLE");

    const disabled = await runScheduledAutonomousCycle({ context: baseContext, policy });
    assert.equal(disabled.executed, false);
    assert.equal(disabled.reason, "SCHEDULER_DISABLED");

    console.log("AUTONOMOUS_CYCLE_2CYCLE_E2E PASS");
  } finally {
    rmSync(dbDir, { recursive: true, force: true });
  }
});
