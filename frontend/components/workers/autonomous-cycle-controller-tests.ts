import assert from "node:assert/strict";
import { decideNextAutonomousCycle } from "./autonomous-cycle-controller";
import type { AgentContext } from "../agents/agent-types";
import type { WorkerFeedback, WorkerRecord } from "./worker-types";

const context = (metadata: Record<string, unknown> = {}): AgentContext => ({
  runId: "cycle-test-run",
  metadata,
});

const accepted: WorkerRecord = {
  taskId: "task",
  runId: "run",
  provider: "cursor",
  attempt: 1,
  maxAttempts: 2,
  status: "ACCEPTED",
  jobId: "job",
  changedFiles: [],
  createdAt: "2026-01-01T00:00:00.000Z",
  startedAt: "2026-01-01T00:00:01.000Z",
  completedAt: "2026-01-01T00:00:02.000Z",
};

const feedback = (recommendation: WorkerFeedback["recommendation"], retryRecommended = false): WorkerFeedback => ({
  taskId: "task",
  runId: "run",
  kind: recommendation === "ACCEPT" ? "IMPLEMENTATION_VERIFIED" : "IMPLEMENTATION_REVIEW",
  recommendation,
  attempts: 1,
  validationFailures: recommendation === "ACCEPT" ? 0 : 1,
  validationPasses: recommendation === "ACCEPT" ? 1 : 0,
  failureCount: recommendation === "ACCEPT" ? 0 : 1,
  changedFiles: [],
  evidenceQuality: "HIGH",
  learningEligible: false,
  researchImpact: "IMPLEMENTATION_ONLY",
  summary: "test",
  failureDetails: recommendation === "ACCEPT" ? [] : ["test failure"],
  nextCycleInput: {
    implementationStatus: recommendation === "ACCEPT" ? "IMPLEMENTATION_VERIFIED" : "IMPLEMENTATION_BLOCKED",
    implementationIntent: "ITERATE",
    recommendation,
    retryRecommended,
    changedFiles: [],
  },
  createdAt: "2026-01-01T00:00:02.000Z",
});

{
  const result = decideNextAutonomousCycle(context({ cycleId: "c1", implementationIntent: "ITERATE" }), null, null);
  assert.equal(result.action, "DISPATCH_IMPLEMENTATION");
  assert.equal(result.implementationIntent, "ITERATE");
}

{
  const result = decideNextAutonomousCycle(context({ cycleId: "c2" }), accepted, feedback("ACCEPT"));
  assert.equal(result.action, "STOP_ACCEPTED");
  assert.equal(result.nextCycleAllowed, false);
}

{
  const failed = { ...accepted, status: "FAILED_FINAL" as const };
  const result = decideNextAutonomousCycle(context({ cycleId: "c3" }), failed, feedback("REVIEW", true));
  assert.equal(result.action, "STOP_FAILURE");
  assert.equal(result.nextCycleAllowed, false);
}

{
  const result = decideNextAutonomousCycle(context({ cycleId: "c4" }), null, null);
  assert.equal(result.action, "CONTINUE_RESEARCH");
  assert.equal(result.nextCycleAllowed, true);
}

{
  const result = decideNextAutonomousCycle(context({ cycleId: "c5", cycleNumber: 11, maxCycles: 10 }), null, null);
  assert.equal(result.action, "STOP_CYCLE_BUDGET");
  assert.equal(result.nextCycleAllowed, false);
}

console.log("AUTONOMOUS_CYCLE_CONTROLLER_TESTS PASS");
