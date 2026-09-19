import assert from "node:assert/strict";
import test from "node:test";
import { coordinateAutonomousCycle } from "./autonomous-cycle-coordinator";
import type { AgentContext } from "../agents/agent-types";

const context = (metadata: Record<string, unknown> = {}): AgentContext => ({
  runId: "coordinator-test-run",
  metadata,
});

test("autonomous cycle coordinator regression", async () => {
  {
    const result = await coordinateAutonomousCycle(
      context({ implementationIntent: "ITERATE" }),
      null,
      null,
      { enabled: false, targetPaths: ["tests/cursor-worker-fixture.mjs"], instructions: "test", implementationIntent: "ITERATE" },
    );
    assert.equal(result.decision.action, "DISPATCH_IMPLEMENTATION");
    assert.equal(result.dispatched, false);
    assert.equal(result.reason, "WORKER_POLICY_DISABLED");
  }

  {
    const result = await coordinateAutonomousCycle(
      context({ maxCycles: 1, cycleNumber: 2, implementationIntent: "ITERATE" }),
      null,
      null,
      { enabled: true, targetPaths: ["tests/cursor-worker-fixture.mjs"], instructions: "test", implementationIntent: "ITERATE" },
    );
    assert.equal(result.decision.action, "STOP_CYCLE_BUDGET");
    assert.equal(result.dispatched, false);
  }

  console.log("AUTONOMOUS_CYCLE_COORDINATOR_TESTS PASS");
});
