import type { AgentContext } from "../agents/agent-types";
import type { WorkerFeedback } from "./worker-types";
import type { AutonomousCycleDecision } from "./autonomous-cycle-controller";

export type AutonomousCycleHandoff = {
  allowed: boolean;
  reason: string;
  context: AgentContext;
};

function positiveInteger(value: unknown, fallback: number): number {
  const parsed = typeof value === "number" ? value : Number(value);
  return Number.isInteger(parsed) && parsed > 0 ? parsed : fallback;
}

function nextRunId(runId: string, cycleNumber: number): string {
  return `${runId}:cycle-${cycleNumber}`;
}

/**
 * Converts implementation feedback into the next bounded research context.
 * This is deliberately side-effect free and never executes another cycle.
 */
export function buildNextAutonomousCycleContext(
  context: AgentContext,
  decision: AutonomousCycleDecision,
  feedback: WorkerFeedback | null | undefined,
): AutonomousCycleHandoff {
  const metadata = context.metadata ?? {};
  const current = positiveInteger(metadata.cycleNumber, 1);
  const max = Math.min(positiveInteger(metadata.maxCycles, 10), 100);
  const next = current + 1;
  const terminalAction = decision.action === "STOP_ACCEPTED" || decision.action === "STOP_REVIEW" || decision.action === "STOP_FAILURE" || decision.action === "STOP_CYCLE_BUDGET";

  if (!decision.nextCycleAllowed || terminalAction) {
    return { allowed: false, reason: "CURRENT_CYCLE_TERMINAL", context };
  }
  if (next > max) {
    return {
      allowed: false,
      reason: `NEXT_CYCLE_BUDGET_EXCEEDED:${max}`,
      context: { ...context, metadata: { ...metadata, cycleNumber: next, maxCycles: max } },
    };
  }

  const input = feedback?.nextCycleInput ?? {};
  const nextCycleId = `${String(metadata.cycleId ?? `cycle-${context.runId}`)}:cycle-${next}`;
  const nextMetadata: Record<string, unknown> = {
    ...metadata,
    cycleId: nextCycleId,
    cycleNumber: next,
    maxCycles: max,
    previousCycleId: String(metadata.cycleId ?? `cycle-${context.runId}`),
    previousRunId: context.runId,
    previousWorkerTaskId: feedback?.taskId ?? null,
    previousWorkerRecommendation: feedback?.recommendation ?? null,
    implementationIntent: decision.implementationIntent,
    autonomousHandoff: true,
    autonomousHandoffReason: decision.reason,
    workerFeedback: input,
  };

  return {
    allowed: true,
    reason: "NEXT_CYCLE_CONTEXT_READY",
    context: {
      ...context,
      runId: nextRunId(context.runId, next),
      metadata: nextMetadata,
      input: {
        ...(context.input ?? {}),
        autonomousCycle: {
          cycleId: nextCycleId,
          cycleNumber: next,
          maxCycles: max,
          previousRunId: context.runId,
          workerFeedback: input,
        },
      },
    },
  };
}
