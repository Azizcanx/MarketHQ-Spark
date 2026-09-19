import type { WorkerTask } from "./worker-types";

export type WorkerRuntimeGate = {
  researchOnly: boolean;
  executionEnabled: boolean;
  databaseWriteEnabled: boolean;
  brokerExecutionEnabled: boolean;
  mainRepoMutation: boolean;
  automaticPr: boolean;
  automaticMerge: boolean;
};

export function currentWorkerRuntimeGate(): WorkerRuntimeGate {
  return {
    researchOnly: true,
    executionEnabled: false,
    databaseWriteEnabled: false,
    brokerExecutionEnabled: false,
    mainRepoMutation: false,
    automaticPr: false,
    automaticMerge: false,
  };
}

export function assertWorkerTaskSafety(task: WorkerTask, gate = currentWorkerRuntimeGate()): void {
  const metadata = task.metadata ?? {};
  const requestedMutation = metadata.mutationAuthorized === true;
  const requestedPr = metadata.automaticPr === true;
  const requestedMerge = metadata.automaticMerge === true;

  if (!gate.researchOnly || gate.executionEnabled || gate.databaseWriteEnabled || gate.brokerExecutionEnabled) {
    throw new Error("Worker runtime safety gate rejected non-research configuration.");
  }
  if (gate.mainRepoMutation || gate.automaticPr || gate.automaticMerge) {
    throw new Error("Worker runtime safety gate rejected direct repository mutation/PR/merge configuration.");
  }
  if (requestedMutation || requestedPr || requestedMerge) {
    throw new Error("Worker task requests mutation, PR, or merge authority that is not enabled in V1.");
  }
}

export function workerExecutionSafetyViolation(
  safety: {
    researchOnly: boolean;
    mainRepoMutation: boolean;
    automaticMerge: boolean;
    automaticPr: boolean;
    isolatedWorktree: boolean;
  },
  options: { requireIsolation?: boolean } = {},
): string | null {
  if (!safety.researchOnly) return "Worker execution reported researchOnly=false.";
  if (options.requireIsolation !== false && !safety.isolatedWorktree) return "Worker execution reported isolatedWorktree=false.";
  if (safety.mainRepoMutation) return "Worker execution reported mainRepoMutation=true.";
  if (safety.automaticPr) return "Worker execution reported automaticPr=true.";
  if (safety.automaticMerge) return "Worker execution reported automaticMerge=true.";
  return null;
}
