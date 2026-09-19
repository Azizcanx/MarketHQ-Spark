import type { AgentContext } from "@/components/agents/agent-types";
import type { WorkerProviderId, WorkerTask } from "./worker-types";

type RecordLike = Record<string, unknown>;

export type ImplementationIntent = "NONE" | "IMPLEMENT" | "ITERATE" | "EXPERIMENT" | "RESEARCH_AND_IMPLEMENT";

export type ImplementationIntentResult = {
  intent: ImplementationIntent;
  eligible: boolean;
  reason: string;
  source: "EXPLICIT_METADATA" | "QUEUE_TASK" | "WORKER_FEEDBACK" | "NONE";
};

function record(value: unknown): RecordLike {
  return value && typeof value === "object" && !Array.isArray(value) ? value as RecordLike : {};
}
function text(value: unknown): string { return typeof value === "string" ? value.trim().toUpperCase() : ""; }
function output(context: AgentContext, id: string): RecordLike {
  return record(context.previousResults?.[id as keyof typeof context.previousResults]?.output);
}
function normalizeIntent(value: unknown): ImplementationIntent | null {
  const normalized = text(value);
  if (normalized === "IMPLEMENT" || normalized === "ITERATE" || normalized === "EXPERIMENT" || normalized === "RESEARCH_AND_IMPLEMENT") return normalized;
  if (normalized === "NONE") return "NONE";
  return null;
}

/** Research Decision actions are research-domain actions and never implementation permission. */
export function resolveImplementationIntent(context: AgentContext): ImplementationIntentResult {
  const metadata = record(context.metadata);
  const queueOutput = output(context, "research-queue");
  const queue = record(queueOutput.queue);
  const selectedTask = record(queue.selectedTask);
  const queueMetadata = record(selectedTask.metadata);
  const feedback = record(metadata.workerFeedback);
  const nextCycleInput = record(feedback.nextCycleInput);

  const candidates: Array<{ value: unknown; source: ImplementationIntentResult["source"] }> = [
    { value: metadata.implementationIntent, source: "EXPLICIT_METADATA" },
    { value: queueMetadata.implementationIntent, source: "QUEUE_TASK" },
    { value: queueMetadata.workerIntent, source: "QUEUE_TASK" },
    { value: nextCycleInput.implementationIntent, source: "WORKER_FEEDBACK" },
  ];
  for (const candidate of candidates) {
    const intent = normalizeIntent(candidate.value);
    if (!intent) continue;
    if (intent === "NONE") return { intent, eligible: false, reason: "IMPLEMENTATION_INTENT_NONE", source: candidate.source };
    return { intent, eligible: true, reason: "EXPLICIT_IMPLEMENTATION_INTENT", source: candidate.source };
  }
  return { intent: "NONE", eligible: false, reason: "NO_EXPLICIT_IMPLEMENTATION_INTENT", source: "NONE" };
}

export type ImplementationWorkerTaskSpec = {
  taskId: string;
  runId: string;
  title: string;
  instructions: string;
  targetPaths: string[];
  validationCommand?: string;
  timeoutMs?: number;
  maxAttempts?: number;
  metadata?: Record<string, unknown>;
  provider?: WorkerProviderId;
};

/**
 * Creates a bounded WorkerTask only when an explicit implementation intent
 * has already been authorized by metadata, queue state, or worker feedback.
 * Research Decision values/actions are deliberately not interpreted here.
 */
export function buildImplementationWorkerTask(
  context: AgentContext,
  spec: ImplementationWorkerTaskSpec,
): WorkerTask | null {
  const resolved = resolveImplementationIntent(context);
  if (!resolved.eligible || resolved.intent === "NONE") return null;
  if (!spec.targetPaths.length) return null;
  const provider = spec.provider ?? (process.env.MARKETHQ_DEFAULT_WORKER_PROVIDER as WorkerProviderId | undefined) ?? "hermes";

  return {
    taskId: spec.taskId,
    runId: spec.runId,
    title: spec.title,
    instructions: spec.instructions,
    targetPaths: spec.targetPaths,
    provider,
    validationCommand: spec.validationCommand,
    timeoutMs: spec.timeoutMs,
    maxAttempts: Math.min(spec.maxAttempts ?? 2, 2),
    metadata: {
      ...(spec.metadata ?? {}),
      implementationIntent: resolved.intent,
      implementationIntentSource: resolved.source,
      implementationIntentReason: resolved.reason,
      mutationAuthorized: false,
      automaticPr: false,
      automaticMerge: false,
    },
  };
}
