import assert from "node:assert/strict";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import test from "node:test";
import { WorkerRuntime } from "./worker-runtime";
import type { WorkerExecutionResult, WorkerProvider, WorkerTask } from "./worker-types";

const task: WorkerTask = {
  taskId: "runtime-regression-task",
  runId: "runtime-regression-run",
  title: "Runtime retry fixture",
  instructions: "exercise the bounded worker runtime lifecycle",
  targetPaths: ["tests/cursor-worker-fixture.mjs"],
  provider: "cursor",
  maxAttempts: 2,
};

function result(task: WorkerTask, status: WorkerExecutionResult["status"], error?: string): WorkerExecutionResult {
  const timestamp = new Date().toISOString();
  return {
    success: status === "NO_PATCH",
    status,
    jobId: `job-${task.attempt ?? 1}`,
    runId: task.runId,
    taskId: task.taskId,
    changedFiles: [],
    error,
    validation: { attempted: false, passed: false },
    safety: {
      researchOnly: true,
      isolatedWorktree: true,
      mainRepoMutation: false,
      automaticMerge: false,
      automaticPr: false,
    },
    startedAt: timestamp,
    completedAt: timestamp,
    durationMs: 0,
  };
}

test("enabled worker runtime performs one bounded retry and reaches terminal state", async () => {
  const dbDir = mkdtempSync(path.join(tmpdir(), "markethq-runtime-regression-"));
  const dbPath = path.join(dbDir, "worker-runtime.sqlite");
  let calls = 0;
  const provider: WorkerProvider = {
    id: "cursor",
    async execute(currentTask) {
      calls += 1;
      if (calls === 1) return result(currentTask, "FAILED", "deterministic first-attempt failure");
      return result(currentTask, "NO_PATCH");
    },
  };

  try {
    const runtime = new WorkerRuntime({
      repoRoot: process.cwd(),
      queueDbPath: dbPath,
      enabled: true,
      maxConcurrency: 1,
      defaultMaxAttempts: 2,
      providerResolver: () => provider,
    });

    const queued = await runtime.dispatch(task);
    assert.equal(queued.status, "QUEUED");
    await runtime.drain();

    const final = runtime.store.latest(task.taskId);
    assert.equal(calls, 2);
    assert.equal(final?.status, "NO_PATCH");
    assert.equal(final?.attempt, 2);
    assert.equal(runtime.store.listEvidence(task.taskId).length, 2);
    const events = runtime.store.listEvents(task.taskId, 50);
    assert.ok(events.some((event) => event.to === "FAILED" && event.attempt === 1));
    assert.ok(events.some((event) => event.to === "NO_PATCH" && event.attempt === 2));
    runtime.store.close();
  } finally {
    rmSync(dbDir, { recursive: true, force: true });
  }
});

test("unsafe worker execution result is persisted as review required and never retried", async () => {
  const dbDir = mkdtempSync(path.join(tmpdir(), "markethq-runtime-safety-"));
  const dbPath = path.join(dbDir, "worker-runtime.sqlite");
  let calls = 0;
  const provider: WorkerProvider = {
    id: "cursor",
    async execute(currentTask) {
      calls += 1;
      return {
        ...result(currentTask, "PATCH_READY"),
        success: true,
        safety: { ...result(currentTask, "PATCH_READY").safety, mainRepoMutation: true },
      };
    },
  };

  try {
    const runtime = new WorkerRuntime({
      repoRoot: process.cwd(),
      queueDbPath: dbPath,
      enabled: true,
      maxConcurrency: 1,
      defaultMaxAttempts: 2,
      providerResolver: () => provider,
    });

    await runtime.dispatch({ ...task, taskId: "runtime-safety-task", runId: "runtime-safety-run" });
    await runtime.drain();

    const final = runtime.store.latest("runtime-safety-task");
    assert.equal(calls, 1);
    assert.equal(final?.status, "REVIEW_REQUIRED");
    assert.match(final?.error ?? "", /mainRepoMutation=true/);
    const evidence = runtime.store.listEvidence("runtime-safety-task");
    assert.equal(evidence.length, 1);
    assert.equal(evidence[0]?.success, false);
    assert.equal(evidence[0]?.safety.mainRepoMutation, true);
    runtime.store.close();
  } finally {
    rmSync(dbDir, { recursive: true, force: true });
  }
});
