import assert from "node:assert/strict";
import type { AgentContext } from "../agents/agent-types";
import { runOneAutonomousCycle } from "./autonomous-cycle-runner";
import { getAutonomousCycleState } from "./autonomous-cycle-state";
import { buildNextAutonomousCycleContext } from "./autonomous-cycle-handoff";

const context: AgentContext = {
  runId: "cycle-runner-test-run",
  metadata: {
    cycleId: "cycle-runner-test",
    cycleNumber: 1,
    maxCycles: 3,
    implementationIntent: "ITERATE",
  },
  previousResults: {
    "research-decision": {
      success: true,
      agentId: "research-decision",
      runId: "cycle-runner-test-run",
      status: "COMPLETED",
      startedAt: new Date().toISOString(),
      completedAt: new Date().toISOString(),
      output: {},
    },
    "research-queue": {
      success: true,
      agentId: "research-queue",
      runId: "cycle-runner-test-run",
      status: "COMPLETED",
      startedAt: new Date().toISOString(),
      completedAt: new Date().toISOString(),
      output: { queue: { selectedTask: { metadata: { workerTargetPaths: ["tests/cursor-worker-fixture.mjs"], workerInstructions: "safe test", workerValidationCommand: "node --check tests/cursor-worker-fixture.mjs" } } } },
    },
  },
};

const result = await runOneAutonomousCycle({
  context,
  policy: {
    enabled: false,
    targetPaths: ["tests/cursor-worker-fixture.mjs"],
    instructions: "safe test",
    validationCommand: "node --check tests/cursor-worker-fixture.mjs",
    implementationIntent: "ITERATE",
  },
});

assert.equal(result.cycle.dispatched, false);
assert.equal(result.state.status, "DISPATCHED");
assert.equal(getAutonomousCycleState("cycle-runner-test")?.cycleNumber, 1);

const handoff = buildNextAutonomousCycleContext(
  context,
  {
    action: "CONTINUE_RESEARCH",
    cycleId: "cycle-runner-test",
    reason: "MORE_RESEARCH_REQUIRED",
    implementationIntent: "ITERATE",
    retryRecommended: false,
    nextCycleAllowed: true,
  },
  {
    taskId: "worker-task-1",
    runId: context.runId,
    kind: "IMPLEMENTATION_VERIFIED",
    recommendation: "FEED_BACK",
    retryRecommended: true,
    attempts: 1,
    researchImpact: "IMPLEMENTATION_ONLY",
    learningEligible: false,
    summary: "test feedback",
    nextCycleInput: { finding: "validated" },
  },
);
assert(handoff.allowed, "Expected a bounded next cycle handoff.");
assert.equal(handoff.context.metadata?.cycleNumber, 2);
assert.equal(handoff.context.metadata?.maxCycles, 3);
assert.equal(handoff.context.metadata?.previousWorkerTaskId, "worker-task-1");
assert.equal(handoff.context.metadata?.workerFeedback?.finding, "validated");

const terminal = buildNextAutonomousCycleContext(
  context,
  {
    action: "STOP_ACCEPTED",
    cycleId: "cycle-runner-test",
    reason: "ACCEPTED",
    implementationIntent: "ITERATE",
    retryRecommended: false,
    nextCycleAllowed: true,
  },
  null,
);
assert(!terminal.allowed, "Accepted cycle must not spawn another cycle.");

const budget = buildNextAutonomousCycleContext(
  { ...context, metadata: { ...context.metadata, cycleNumber: 3, maxCycles: 3 } },
  {
    action: "CONTINUE_RESEARCH",
    cycleId: "cycle-runner-test",
    reason: "MORE_RESEARCH_REQUIRED",
    implementationIntent: "ITERATE",
    retryRecommended: false,
    nextCycleAllowed: true,
  },
  null,
);
assert(!budget.allowed, "Cycle budget must block the next handoff.");

console.log("AUTONOMOUS_CYCLE_RUNNER_TESTS PASS");
