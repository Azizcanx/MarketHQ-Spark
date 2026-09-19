import path from "node:path";
import type { AgentContext } from "../agents/agent-types";
import type { WorkerFeedback, WorkerRecord } from "./worker-types";
import { coordinateAutonomousCycleV2, type AutonomousCycleCoordinatorResult } from "./autonomous-cycle-coordinator-v2";
import type { WorkerDispatchPolicy } from "./autonomous-worker-orchestrator";
import { getAutonomousCycleState, recordAutonomousCycleState, type AutonomousCycleState } from "./autonomous-cycle-state";
import { WorkerStore } from "./worker-store";

export type AutonomousCycleRunResult = {
  state: AutonomousCycleState;
  cycle: AutonomousCycleCoordinatorResult;
};

function cycleIdFrom(context: AgentContext): string {
  const candidate = context.metadata?.cycleId;
  return typeof candidate === "string" && candidate.trim() ? candidate.trim() : `cycle-${context.runId}`;
}

function durableWorkerDbPath(): string {
  const repoRoot = path.resolve(process.env.MARKETHQ_REPO_ROOT ?? path.resolve(process.cwd(), ".."));
  return process.env.MARKETHQ_WORKER_DB_PATH ?? path.join(repoRoot, "automation", "worker-runtime.sqlite");
}

function rehydrateDurableWorkerContext(context: AgentContext, worker: WorkerRecord | null | undefined, feedback: WorkerFeedback | null | undefined): { worker: WorkerRecord | null | undefined; feedback: WorkerFeedback | null | undefined; metadata: Record<string, unknown> } {
  if (worker !== undefined && feedback !== undefined) return { worker, feedback, metadata: {} };

  const store = new WorkerStore(durableWorkerDbPath());
  try {
    const durableFeedback = feedback === undefined
      ? store.latestFeedbackForContext({ strategyId: context.strategyId, symbol: context.symbol, timeframe: context.timeframe })
      : null;
    const resolvedFeedback = feedback === undefined ? durableFeedback : feedback;
    const resolvedWorker = worker === undefined && resolvedFeedback ? store.latest(resolvedFeedback.taskId) : worker;
    if (!resolvedFeedback && !resolvedWorker) return { worker, feedback, metadata: {} };
    return {
      worker: resolvedWorker,
      feedback: resolvedFeedback,
      metadata: {
        workerFeedback: resolvedFeedback?.nextCycleInput ?? null,
        workerFeedbackRecord: resolvedFeedback ?? null,
        workerFeedbackSource: resolvedFeedback ? "DURABLE_WORKER_STORE" : "NONE",
        workerStateSource: resolvedWorker ? "DURABLE_WORKER_STORE" : "NONE",
      },
    };
  } finally {
    store.close();
  }
}

export async function runOneAutonomousCycle(input: {
  context: AgentContext;
  worker?: WorkerRecord | null;
  feedback?: WorkerFeedback | null;
  policy: WorkerDispatchPolicy;
}): Promise<AutonomousCycleRunResult> {
  const cycleId = cycleIdFrom(input.context);
  const existing = getAutonomousCycleState(cycleId);
  const cycleNumber = Number(input.context.metadata?.cycleNumber ?? existing?.cycleNumber ?? 1);
  const maxCycles = Number(input.context.metadata?.maxCycles ?? existing?.maxCycles ?? 10);
  const durable = rehydrateDurableWorkerContext(input.context, input.worker, input.feedback);
  const context: AgentContext = {
    ...input.context,
    metadata: {
      ...(input.context.metadata ?? {}),
      ...durable.metadata,
      cycleId,
      cycleNumber: Number.isFinite(cycleNumber) ? cycleNumber : 1,
      maxCycles: Number.isFinite(maxCycles) ? Math.min(Math.max(maxCycles, 1), 100) : 10,
    },
  };

  const result = await coordinateAutonomousCycleV2(context, durable.worker, durable.feedback, input.policy);
  const state = recordAutonomousCycleState({
    cycleId,
    runId: context.runId,
    cycleNumber: Number(context.metadata?.cycleNumber ?? 1),
    maxCycles: Number(context.metadata?.maxCycles ?? 10),
    decision: result.decision,
    worker: result.worker,
    feedback: durable.feedback,
  });
  return { state, cycle: result };
}
