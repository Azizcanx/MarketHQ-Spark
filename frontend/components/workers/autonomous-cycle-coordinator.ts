import type { AgentContext } from "../agents/agent-types";
import type { WorkerFeedback, WorkerRecord } from "./worker-types";
import { coordinateAutonomousCycleV2, type AutonomousCycleCoordinatorResult } from "./autonomous-cycle-coordinator-v2";
import type { WorkerDispatchPolicy } from "./autonomous-worker-orchestrator";

/**
 * Compatibility wrapper for the original coordinator entrypoint.
 * The locked V2 coordinator is now the single execution path so callers cannot
 * accidentally bypass cycle locking or the research/implementation boundary.
 */
export async function coordinateAutonomousCycle(
  context: AgentContext,
  worker: WorkerRecord | null | undefined,
  feedback: WorkerFeedback | null | undefined,
  policy: WorkerDispatchPolicy,
): Promise<AutonomousCycleCoordinatorResult> {
  return coordinateAutonomousCycleV2(context, worker, feedback, policy);
}
