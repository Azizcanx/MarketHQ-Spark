import path from "node:path";
import type { AgentContext } from "@/components/agents/agent-types";
import { WorkerStore } from "./worker-store";
import type { WorkerFeedback } from "./worker-types";

export type WorkerFeedbackContextOptions = { repoRoot: string; queueDbPath?: string };

export function loadLatestWorkerFeedbackForContext(context: AgentContext, options: WorkerFeedbackContextOptions): WorkerFeedback | null {
  const store = new WorkerStore(options.queueDbPath ?? path.join(options.repoRoot, "automation", "worker-runtime.sqlite"));
  try { return store.latestFeedbackForContext({ strategyId: context.strategyId, symbol: context.symbol, timeframe: context.timeframe }); }
  finally { store.close(); }
}

export function rehydrateWorkerFeedback(context: AgentContext, options: WorkerFeedbackContextOptions): AgentContext {
  const feedback = loadLatestWorkerFeedbackForContext(context, options);
  if (!feedback) return context;
  return { ...context, metadata: { ...(context.metadata ?? {}), workerFeedback: feedback.nextCycleInput, workerFeedbackRecord: feedback, workerFeedbackSource: "DURABLE_WORKER_STORE" } };
}
