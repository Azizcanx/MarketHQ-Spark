import assert from "node:assert/strict";
import type { AgentContext } from "../agents/agent-types";
import { buildNextAutonomousCycleContext } from "./autonomous-cycle-handoff";
import type { AutonomousCycleDecision } from "./autonomous-cycle-controller";
import type { WorkerFeedback } from "./worker-types";

const context: AgentContext = {
  runId: "handoff-run-v1",
  strategyId: "strategy-1",
  symbol: "THYAO.IS",
  timeframe: "1d",
  metadata: { cycleId: "cycle-handoff-v1", cycleNumber: 1, maxCycles: 3, implementationIntent: "ITERATE" },
};
const decision = {
  action: "CONTINUE_RESEARCH",
  cycleId: "cycle-handoff-v1",
  reason: "WORKER_FEEDBACK_REQUESTS_BOUNDED_RETRY",
  implementationIntent: "ITERATE",
  retryRecommended: true,
  nextCycleAllowed: true,
} satisfies AutonomousCycleDecision;
const feedback = {
  taskId: "task-1",
  runId: "handoff-run-v1",
  kind: "IMPLEMENTATION_REVIEW",
  recommendation: "FEED_BACK",
  attempts: 1,
  validationFailures: 1,
  validationPasses: 0,
  failureCount: 1,
  changedFiles: ["tests/example.mjs"],
  evidenceQuality: "HIGH",
  learningEligible: false,
  researchImpact: "IMPLEMENTATION_ONLY",
  summary: "Retry required.",
  nextCycleInput: { focus: "fix-validation", retryRecommended: true },
  createdAt: new Date().toISOString(),
} satisfies WorkerFeedback;

const handoff = buildNextAutonomousCycleContext(context, decision, feedback);
assert.equal(handoff.allowed, true);
assert.equal(handoff.context.metadata?.cycleNumber, 2);
assert.equal(handoff.context.metadata?.maxCycles, 3);
assert.equal(handoff.context.metadata?.previousWorkerTaskId, "task-1");
assert.equal((handoff.context.input?.autonomousCycle as any).workerFeedback.focus, "fix-validation");
assert.equal(handoff.context.runId, "handoff-run-v1:cycle-2");
assert.equal(handoff.context.metadata?.cycleId, "cycle-handoff-v1:cycle-2");

const terminal = buildNextAutonomousCycleContext(context, { ...decision, action: "STOP_ACCEPTED", nextCycleAllowed: true }, feedback);
assert.equal(terminal.allowed, false);
assert.equal(terminal.reason, "CURRENT_CYCLE_TERMINAL");

const budget = buildNextAutonomousCycleContext({ ...context, metadata: { ...context.metadata, cycleNumber: 3, maxCycles: 3 } }, decision, feedback);
assert.equal(budget.allowed, false);
assert.equal(budget.reason, "NEXT_CYCLE_BUDGET_EXCEEDED:3");

console.log("autonomous-cycle-handoff-tests: PASS");
