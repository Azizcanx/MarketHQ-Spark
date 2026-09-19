import type { AgentContext } from "../agents/agent-types";
import type { AutonomousCycleState } from "./autonomous-cycle-state";

export type AutonomousCycleGuardDecision = {
  allowed: boolean;
  reason: "ACTIVE_CYCLE" | "TERMINAL_CYCLE" | "BUDGET_EXCEEDED" | "CYCLE_ID_MISMATCH";
};

const terminal = new Set<AutonomousCycleState["status"]>(["ACCEPTED", "REVIEW_REQUIRED", "FAILED", "BUDGET_EXCEEDED"]);

/** Pure guard used before a scheduler/coordinator dispatch. */
export function guardAutonomousCycleDispatch(context: AgentContext, state: AutonomousCycleState | null): AutonomousCycleGuardDecision {
  if (!state) return { allowed: true, reason: "ACTIVE_CYCLE" };
  const cycleId = typeof context.metadata?.cycleId === "string" ? context.metadata.cycleId : "";
  if (cycleId && cycleId !== state.cycleId) return { allowed: false, reason: "CYCLE_ID_MISMATCH" };
  if (terminal.has(state.status)) return { allowed: false, reason: "TERMINAL_CYCLE" };
  const cycleNumber = Number(context.metadata?.cycleNumber ?? state.cycleNumber);
  if (Number.isInteger(cycleNumber) && cycleNumber > state.maxCycles) return { allowed: false, reason: "BUDGET_EXCEEDED" };
  return { allowed: true, reason: "ACTIVE_CYCLE" };
}
