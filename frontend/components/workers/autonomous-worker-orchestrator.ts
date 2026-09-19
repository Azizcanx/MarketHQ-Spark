import type { AgentContext, AgentResult } from "../agents/agent-types";
import { resolveImplementationIntent } from "./implementation-intent";
import { buildWorkerTaskFromAgentContext } from "./worker-task-builder";
import { dispatchWorkerTask } from "./dispatch-gateway";
import { currentWorkerRuntimeGate } from "./runtime-gate";
import { resolveAutonomousWorkerPolicy } from "./autonomous-worker-policy";

export type WorkerDispatchPolicy = {
  enabled: boolean;
  targetPaths: string[];
  instructions: string;
  validationCommand?: string;
  implementationIntent?: string;
};

export async function dispatchAutonomousWorker(context: AgentContext, decision: AgentResult | undefined, queue: AgentResult | undefined, policy: WorkerDispatchPolicy) {
  const resolved = resolveAutonomousWorkerPolicy(
    {
      workerEnabled: policy.enabled,
      workerTargetPaths: policy.targetPaths,
      workerInstructions: policy.instructions,
      workerValidationCommand: policy.validationCommand,
      implementationIntent: policy.implementationIntent,
    },
    queue?.output,
  );

  if (!resolved.enabled) return { requested: false, dispatched: false, reason: "WORKER_POLICY_DISABLED" as const, worker: null };
  const gate = currentWorkerRuntimeGate();
  if (!gate.researchOnly || gate.executionEnabled || gate.databaseWriteEnabled || gate.brokerExecutionEnabled || gate.mainRepoMutation || gate.automaticPr || gate.automaticMerge) return { requested: true, dispatched: false, reason: "WORKER_RUNTIME_GATE_BLOCKED", worker: null };
  if (!decision?.success || !queue?.success) return { requested: true, dispatched: false, reason: "RESEARCH_PREREQUISITES_INCOMPLETE", worker: null };
  if (!resolved.targetPaths.length) return { requested: true, dispatched: false, reason: "WORKER_TARGET_PATHS_REQUIRED", worker: null };

  const metadata = { ...(context.metadata ?? {}) };
  if (resolved.implementationIntent) metadata.implementationIntent = resolved.implementationIntent;
  const workerContext: AgentContext = { ...context, metadata };
  const intent = resolveImplementationIntent(workerContext);
  if (!intent.eligible) return { requested: true, dispatched: false, reason: `WORKER_IMPLEMENTATION_INTENT_REQUIRED:${intent.reason}`, worker: null };

  const task = buildWorkerTaskFromAgentContext({
    context: workerContext,
    targetPaths: resolved.targetPaths,
    instructions: resolved.instructions,
    validationCommand: resolved.validationCommand,
    implementationIntent: intent.intent,
  });
  const record = await dispatchWorkerTask(task);
  return {
    requested: true,
    dispatched: true,
    reason: "WORKER_DISPATCHED",
    worker: record,
    implementationIntent: intent.intent,
    implementationIntentSource: intent.source,
    policySource: resolved.source,
  };
}
