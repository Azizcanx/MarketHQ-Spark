import type { AgentContext } from "@/components/agents/agent-types";
import { dispatchWorkerTask } from "./dispatch-gateway";
import {
  buildImplementationWorkerTask,
  type ImplementationWorkerTaskSpec,
} from "./implementation-intent";
import type { WorkerRecord } from "./worker-types";

export type ResearchImplementationDispatch = {
  dispatched: boolean;
  reason: string;
  intent: string;
  record: WorkerRecord | null;
};

/**
 * Explicit bridge from research context to the Worker Runtime.
 * Research Decision actions are never treated as implementation authority.
 * A Worker task is created only when implementation-intent.ts resolves an
 * explicit implementation intent from an allowed source.
 */
export async function dispatchResearchImplementation(
  context: AgentContext,
  spec: ImplementationWorkerTaskSpec,
): Promise<ResearchImplementationDispatch> {
  const task = buildImplementationWorkerTask(context, spec);
  if (!task) {
    return {
      dispatched: false,
      reason: "NO_EXPLICIT_IMPLEMENTATION_INTENT",
      intent: "NONE",
      record: null,
    };
  }

  const record = await dispatchWorkerTask(task);
  return {
    dispatched: true,
    reason: "IMPLEMENTATION_INTENT_ACCEPTED",
    intent: String(task.metadata?.implementationIntent ?? "NONE"),
    record,
  };
}
