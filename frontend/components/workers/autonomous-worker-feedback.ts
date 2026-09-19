import { evaluateWorkerEvidence } from "./worker-evaluation";
import { buildWorkerFeedback } from "./worker-feedback";
import type { WorkerFeedback, WorkerRecord } from "./worker-types";
import { WorkerStore } from "./worker-store";

export function collectAutonomousWorkerFeedback(store: WorkerStore, record: WorkerRecord): WorkerFeedback {
  const evaluation = evaluateWorkerEvidence(record, store.listEvidence(record.taskId));
  const feedback = buildWorkerFeedback(record, evaluation);
  store.recordFeedback(feedback);
  return feedback;
}
