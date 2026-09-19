import assert from "node:assert/strict";
import test from "node:test";
import { coordinateAutonomousCycleV2 } from "./autonomous-cycle-coordinator-v2";
import type { AgentContext } from "../agents/agent-types";

const ok = (agentId: "research-decision" | "research-queue") => ({
  success: true,
  agentId,
  runId: "coordinator-v2-test-run",
  status: "COMPLETED" as const,
  startedAt: new Date().toISOString(),
  completedAt: new Date().toISOString(),
  output: agentId === "research-queue"
    ? { queue: { selectedTask: { metadata: { workerTargetPaths: ["tests/cursor-worker-fixture.mjs"], workerInstructions: "safe test", workerValidationCommand: "node --check tests/cursor-worker-fixture.mjs" } } } }
    : {},
});

const context: AgentContext = {
  runId: "coordinator-v2-test-run",
  metadata: { implementationIntent: "ITERATE", cycleId: "cycle-v2-test" },
  previousResults: {
    "research-decision": ok("research-decision"),
    "research-queue": ok("research-queue"),
  },
};

test("autonomous cycle coordinator v2 regression", async () => {
  const result = await coordinateAutonomousCycleV2(
    context,
    null,
    null,
    { enabled: false, targetPaths: ["tests/cursor-worker-fixture.mjs"], instructions: "safe test", implementationIntent: "ITERATE" },
  );

  assert.equal(result.decision.action, "DISPATCH_IMPLEMENTATION");
  assert.equal(result.dispatched, false);
  assert.equal(result.reason, "WORKER_POLICY_DISABLED");

  const budget = await coordinateAutonomousCycleV2(
    { ...context, metadata: { ...context.metadata, cycleNumber: 11, maxCycles: 10 } },
    null,
    null,
    { enabled: true, targetPaths: ["tests/cursor-worker-fixture.mjs"], instructions: "safe test", implementationIntent: "ITERATE" },
  );
  assert.equal(budget.decision.action, "STOP_CYCLE_BUDGET");

  console.log("AUTONOMOUS_CYCLE_COORDINATOR_V2_TESTS PASS");
});
