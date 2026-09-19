import type { AgentContext } from "../agents/agent-types";
import type { WorkerFeedback, WorkerRecord } from "./worker-types";
import { decideNextAutonomousCycle, type AutonomousCycleDecision } from "./autonomous-cycle-controller";
import { dispatchAutonomousWorker, type WorkerDispatchPolicy } from "./autonomous-worker-orchestrator";
import { acquireAutonomousCycleLock, releaseAutonomousCycleLock } from "./autonomous-cycle-lock";
import { recordAutonomousCycleState } from "./autonomous-cycle-state";

export type AutonomousCycleCoordinatorResult = {
  decision: AutonomousCycleDecision;
  dispatched: boolean;
  worker: WorkerRecord | null;
  reason: string;
};

function durableFeedbackFromContext(context: AgentContext): WorkerFeedback | null {
  const candidate = context.metadata?.workerFeedbackRecord;
  if (!candidate || typeof candidate !== "object" || Array.isArray(candidate)) return null;
  return candidate as WorkerFeedback;
}

export async function coordinateAutonomousCycleV2(
  context: AgentContext,
  worker: WorkerRecord | null | undefined,
  feedback: WorkerFeedback | null | undefined,
  policy: WorkerDispatchPolicy,
): Promise<AutonomousCycleCoordinatorResult> {
  const resolvedFeedback = feedback ?? durableFeedbackFromContext(context);
  const decision = decideNextAutonomousCycle(context, worker, resolvedFeedback);
  const cycleNumber = typeof context.metadata?.cycleNumber === "number" ? context.metadata.cycleNumber : Number(context.metadata?.cycleNumber ?? 1);
  const maxCycles = typeof context.metadata?.maxCycles === "number" ? context.metadata.maxCycles : Number(context.metadata?.maxCycles ?? 10);

  if (decision.action !== "DISPATCH_IMPLEMENTATION") {
    const result = { decision, dispatched: false, worker: worker ?? null, reason: decision.reason };
    recordAutonomousCycleState({ cycleId: decision.cycleId, runId: context.runId, cycleNumber, maxCycles, decision, worker, feedback: resolvedFeedback });
    return result;
  }
  if (!decision.implementationIntent) {
    const result = { decision, dispatched: false, worker: null, reason: "IMPLEMENTATION_INTENT_MISSING" };
    recordAutonomousCycleState({ cycleId: decision.cycleId, runId: context.runId, cycleNumber, maxCycles, decision, worker: null, feedback: resolvedFeedback });
    return result;
  }
  if (!acquireAutonomousCycleLock(decision.cycleId)) {
    const result = { decision, dispatched: false, worker: null, reason: "AUTONOMOUS_CYCLE_ALREADY_RUNNING" };
    recordAutonomousCycleState({ cycleId: decision.cycleId, runId: context.runId, cycleNumber, maxCycles, decision, worker: null, feedback: resolvedFeedback });
    return result;
  }

  try {
    const previous = context.previousResults ?? {};
    const dispatch = await dispatchAutonomousWorker(
      context,
      previous["research-decision"],
      previous["research-queue"],
      { ...policy, implementationIntent: decision.implementationIntent },
    );
    const result = {
      decision,
      dispatched: dispatch.dispatched,
      worker: dispatch.worker ?? null,
      reason: dispatch.reason,
    };
    recordAutonomousCycleState({ cycleId: decision.cycleId, runId: context.runId, cycleNumber, maxCycles, decision, worker: dispatch.worker ?? null, feedback: resolvedFeedback });
    return result;
  } finally {
    releaseAutonomousCycleLock(decision.cycleId);
  }
}
