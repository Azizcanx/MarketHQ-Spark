import type { AgentContext } from "../agents/agent-types";
import type { WorkerDispatchPolicy } from "./autonomous-worker-orchestrator";
import type { WorkerFeedback, WorkerRecord } from "./worker-types";
import { runScheduledAutonomousCycle, type AutonomousCycleSchedulerOptions } from "./autonomous-cycle-scheduler";

export type AutonomousCycleLoopResult = {
  executedCycles: number;
  stopped: boolean;
  reason: string;
  lastCycle?: Awaited<ReturnType<typeof runScheduledAutonomousCycle>>;
};

/** Runs a bounded sequence; each cycle remains lease/guard protected. */
export async function runBoundedAutonomousCycleLoop(input: {
  context: AgentContext;
  policy: WorkerDispatchPolicy;
  worker?: WorkerRecord | null;
  feedback?: WorkerFeedback | null;
  options?: AutonomousCycleSchedulerOptions & { maxIterations?: number };
}): Promise<AutonomousCycleLoopResult> {
  const maxIterations = Math.min(Math.max(Number(input.options?.maxIterations ?? 10), 1), 100);
  let context = input.context;
  let worker = input.worker;
  let feedback = input.feedback;
  let lastCycle: Awaited<ReturnType<typeof runScheduledAutonomousCycle>> | undefined;

  for (let iteration = 0; iteration < maxIterations; iteration += 1) {
    const cycleNumber = Number(context.metadata?.cycleNumber ?? iteration + 1);
    const result = await runScheduledAutonomousCycle({
      context: { ...context, metadata: { ...(context.metadata ?? {}), cycleNumber } },
      policy: input.policy,
      worker,
      feedback,
      options: input.options,
    });
    lastCycle = result;
    if (!result.executed) return { executedCycles: iteration, stopped: true, reason: result.reason, lastCycle };

    const cycle = result.cycle;
    // Undefined deliberately means the runner may rehydrate durable worker/feedback state.
    worker = cycle?.cycle.worker ?? undefined;
    feedback = undefined;

    if (cycle?.state.status === "ACCEPTED" || cycle?.state.status === "REVIEW_REQUIRED" || cycle?.state.status === "FAILED" || cycle?.state.status === "BUDGET_EXCEEDED") {
      return { executedCycles: iteration + 1, stopped: true, reason: cycle.state.status, lastCycle };
    }
    if (!cycle?.cycle.decision.nextCycleAllowed) return { executedCycles: iteration + 1, stopped: true, reason: cycle?.cycle.decision.reason ?? "NEXT_CYCLE_NOT_ALLOWED", lastCycle };

    context = {
      ...context,
      runId: `${context.runId}:cycle-${cycleNumber + 1}`,
      metadata: { ...(context.metadata ?? {}), cycleNumber: cycleNumber + 1, cycleId: cycle.state.cycleId, autonomousLoopIteration: iteration + 2, previousCycleReason: cycle.cycle.decision.reason, nextCycleAllowed: true },
    };
  }
  return { executedCycles: maxIterations, stopped: true, reason: "AUTONOMOUS_LOOP_ITERATION_BUDGET_EXCEEDED", lastCycle };
}
