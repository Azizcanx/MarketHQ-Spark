import type { AgentContext } from "../agents/agent-types";
import type { AutonomousCycleDecision } from "./autonomous-cycle-controller";
import type { WorkerFeedback } from "./worker-types";
import { buildNextAutonomousCycleContext, type AutonomousCycleHandoff } from "./autonomous-cycle-handoff";

export type AutonomousCyclePlan = {
  currentCycleId: string;
  currentCycleNumber: number;
  maxCycles: number;
  decision: AutonomousCycleDecision;
  handoff: AutonomousCycleHandoff;
  terminal: boolean;
};

const positive = (value: unknown, fallback: number) => {
  const n = typeof value === "number" ? value : Number(value);
  return Number.isInteger(n) && n > 0 ? n : fallback;
};

/** Plans exactly one next step; it never executes a worker or recursively runs cycles. */
export function planNextAutonomousCycle(input: {
  context: AgentContext;
  decision: AutonomousCycleDecision;
  feedback?: WorkerFeedback | null;
}): AutonomousCyclePlan {
  const metadata = input.context.metadata ?? {};
  const currentCycleNumber = positive(metadata.cycleNumber, 1);
  const maxCycles = Math.min(positive(metadata.maxCycles, 10), 100);
  const handoff = buildNextAutonomousCycleContext(input.context, input.decision, input.feedback);
  return {
    currentCycleId: String(metadata.cycleId ?? `cycle-${input.context.runId}`),
    currentCycleNumber,
    maxCycles,
    decision: input.decision,
    handoff,
    terminal: !handoff.allowed,
  };
}
