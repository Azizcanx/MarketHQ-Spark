import assert from "node:assert/strict";
import { planNextAutonomousCycle } from "./autonomous-cycle-plan";

const context = { runId: "plan-run", metadata: { cycleId: "plan-cycle", cycleNumber: 1, maxCycles: 2 } };
const decision = { action: "CONTINUE_RESEARCH" as const, cycleId: "plan-cycle", reason: "MORE_RESEARCH_REQUIRED", implementationIntent: "ITERATE", retryRecommended: false, nextCycleAllowed: true };
const feedback = { taskId: "task-1", runId: "plan-run", kind: "IMPLEMENTATION_VERIFIED" as const, recommendation: "FEED_BACK" as const, retryRecommended: true, attempts: 1, researchImpact: "IMPLEMENTATION_ONLY" as const, learningEligible: false, summary: "validated", nextCycleInput: { finding: "ok" } };

const next = planNextAutonomousCycle({ context, decision, feedback });
assert.equal(next.terminal, false);
assert.equal(next.handoff.context.metadata?.cycleNumber, 2);

const terminal = planNextAutonomousCycle({ context, decision: { ...decision, action: "STOP_ACCEPTED", reason: "ACCEPTED" } });
assert.equal(terminal.terminal, true);
assert.equal(terminal.handoff.allowed, false);

console.log("AUTONOMOUS_CYCLE_PLAN_TESTS PASS");
