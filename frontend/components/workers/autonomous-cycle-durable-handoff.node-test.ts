import assert from "node:assert/strict";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import test from "node:test";
import type { AgentContext } from "../agents/agent-types";
import { runOneAutonomousCycle } from "./autonomous-cycle-runner";
import { WorkerStore } from "./worker-store";
import type { WorkerFeedback, WorkerRecord, WorkerTask } from "./worker-types";

const task: WorkerTask = {
  taskId: "durable-handoff-task",
  runId: "durable-worker-run",
  title: "Durable handoff fixture",
  instructions: "deterministic durable handoff fixture",
  targetPaths: ["tests/cursor-worker-fixture.mjs"],
  provider: "cursor",
  attempt: 1,
  maxAttempts: 2,
  metadata: { strategyId: "strategy-durable", symbol: "THYAO.IS", timeframe: "1d" },
};

const feedback: WorkerFeedback = {
  taskId: task.taskId,
  runId: task.runId,
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
  summary: "durable feedback fixture",
  failureDetails: [],
  nextCycleInput: { durableMarker: "survives-process-restart", retryRecommended: false },
  createdAt: "2026-01-01T00:00:02.000Z",
};

const explicitFeedback: WorkerFeedback = {
  ...feedback,
  kind: "IMPLEMENTATION_BLOCKED",
  recommendation: "FEED_BACK",
  validationFailures: 1,
  validationPasses: 0,
  failureCount: 1,
  evidenceQuality: "MEDIUM",
  summary: "explicit feedback must win over durable feedback",
  nextCycleInput: { durableMarker: "explicit-wins", retryRecommended: true },
};

const acceptedWorker: WorkerRecord = {
  taskId: task.taskId,
  runId: task.runId,
  status: "ACCEPTED",
  attempt: 1,
  maxAttempts: 2,
  provider: "cursor",
  changedFiles: [],
  createdAt: "2026-01-01T00:00:01.000Z",
  startedAt: "2026-01-01T00:00:01.000Z",
  completedAt: "2026-01-01T00:00:02.000Z",
};

function context(symbol = "THYAO.IS"): AgentContext {
  return {
    runId: "durable-handoff-next-run",
    strategyId: "strategy-durable",
    symbol,
    timeframe: "1d",
    metadata: { cycleId: "durable-handoff-cycle", cycleNumber: 2, maxCycles: 3, implementationIntent: "ITERATE" },
    previousResults: {
      "research-decision": {
        success: true,
        agentId: "research-decision",
        runId: "research-run",
        status: "COMPLETED",
        startedAt: "2026-01-01T00:00:00.000Z",
        completedAt: "2026-01-01T00:00:01.000Z",
        output: {},
      },
      "research-queue": {
        success: true,
        agentId: "research-queue",
        runId: "research-run",
        status: "COMPLETED",
        startedAt: "2026-01-01T00:00:00.000Z",
        completedAt: "2026-01-01T00:00:01.000Z",
        output: {
          queue: {
            selectedTask: {
              metadata: {
                workerTargetPaths: ["tests/cursor-worker-fixture.mjs"],
                workerInstructions: "durable fixture",
                workerValidationCommand: "node --check tests/cursor-worker-fixture.mjs",
              },
            },
          },
        },
      },
    },
  };
}

function setupDb(prefix: string) {
  const dbDir = mkdtempSync(path.join(tmpdir(), prefix));
  const dbPath = path.join(dbDir, "worker-runtime.sqlite");
  process.env.MARKETHQ_WORKER_DB_PATH = dbPath;
  process.env.MARKETHQ_AUTONOMOUS_CYCLE_SCHEDULER = "false";
  return { dbDir, dbPath };
}

test("autonomous cycle rehydrates persisted worker feedback and worker state", async () => {
  const { dbDir, dbPath } = setupDb("markethq-durable-handoff-");
  try {
    const store = new WorkerStore(dbPath);
    store.upsertTask(task, "ACCEPTED");
    store.recordFeedback(feedback);
    store.close();

    const result = await runOneAutonomousCycle({
      context: context(),
      policy: { enabled: false, targetPaths: task.targetPaths, instructions: task.instructions, implementationIntent: "ITERATE" },
    });

    assert.equal(result.cycle.decision.action, "STOP_ACCEPTED");
    assert.equal(result.cycle.reason, "IMPLEMENTATION_VERIFIED");
    assert.equal(result.cycle.worker?.taskId, task.taskId);
    assert.equal(result.cycle.decision.nextCycleAllowed, false);
  } finally {
    rmSync(dbDir, { recursive: true, force: true });
  }
});

test("explicit worker feedback takes precedence over persisted feedback", async () => {
  const { dbDir, dbPath } = setupDb("markethq-explicit-feedback-");
  try {
    const store = new WorkerStore(dbPath);
    store.upsertTask(task, "ACCEPTED");
    store.recordFeedback(feedback);
    store.close();

    const result = await runOneAutonomousCycle({
      context: context(),
      worker: acceptedWorker,
      feedback: explicitFeedback,
      policy: { enabled: false, targetPaths: task.targetPaths, instructions: task.instructions, implementationIntent: "ITERATE" },
    });

    assert.notEqual(result.cycle.reason, "IMPLEMENTATION_VERIFIED");
    assert.equal(result.cycle.decision.action, "DISPATCH_IMPLEMENTATION");
    assert.equal(result.cycle.decision.reason, "WORKER_FEEDBACK_REQUESTS_BOUNDED_RETRY");
    assert.equal(result.cycle.decision.retryRecommended, true);
    assert.equal(result.cycle.decision.nextCycleAllowed, true);
    assert.equal(result.state.lastReason, "WORKER_FEEDBACK_REQUESTS_BOUNDED_RETRY");
  } finally {
    rmSync(dbDir, { recursive: true, force: true });
  }
});

test("durable accepted feedback does not bypass a mismatched symbol", async () => {
  const { dbDir, dbPath } = setupDb("markethq-durable-scope-");
  try {
    const store = new WorkerStore(dbPath);
    store.upsertTask(task, "ACCEPTED");
    store.recordFeedback(feedback);
    store.close();

    const result = await runOneAutonomousCycle({
      context: context("ASELS.IS"),
      policy: { enabled: false, targetPaths: task.targetPaths, instructions: task.instructions, implementationIntent: "ITERATE" },
    });

    assert.notEqual(result.cycle.decision.action, "STOP_ACCEPTED");
    assert.equal(result.cycle.reason, "WORKER_POLICY_DISABLED");
  } finally {
    rmSync(dbDir, { recursive: true, force: true });
  }
});
