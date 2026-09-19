export type WorkerProviderId = "cursor" | "hermes" | "claude" | "other";

export type WorkerStatus =
  | "QUEUED"
  | "DISPATCHED"
  | "STARTING"
  | "RUNNING"
  | "PATCH_READY"
  | "PATCH_INTAKE"
  | "VALIDATING"
  | "ACCEPTED"
  | "NO_PATCH"
  | "PATCH_REJECTED"
  | "TIMEOUT"
  | "FAILED"
  | "FAILED_FINAL"
  | "REVIEW_REQUIRED";

export type WorkerLogKind = "system" | "delta" | "tool" | "reasoning" | "error";

export type WorkerLogEntry = {
  taskId: string;
  runId: string;
  attempt: number;
  kind: WorkerLogKind;
  message: string;
  at: string;
};

export type WorkerProgressCallback = (log: { kind: WorkerLogKind; message: string; at?: string }) => void;

export interface WorkerProvider {
  readonly id: WorkerProviderId;
  execute(task: WorkerTask, onProgress?: WorkerProgressCallback): Promise<WorkerExecutionResult>;
}

export type WorkerTask = {
  taskId: string;
  runId: string;
  title: string;
  instructions: string;
  targetPaths: string[];
  provider: WorkerProviderId;
  validationCommand?: string;
  timeoutMs?: number;
  attempt?: number;
  maxAttempts?: number;
  metadata?: Record<string, unknown>;
};

export type WorkerExecutionResult = {
  success: boolean;
  status: "PATCH_READY" | "NO_PATCH" | "FAILED" | "TIMEOUT" | "PATCH_REJECTED";
  jobId: string;
  runId: string;
  taskId: string;
  worktreePath?: string;
  changedFiles: string[];
  diff?: string;
  validation?: { attempted: boolean; passed: boolean; command?: string; exitCode?: number; stdout?: string; stderr?: string };
  error?: string;
  startedAt: string;
  completedAt: string;
  durationMs: number;
  safety: { researchOnly: boolean; mainRepoMutation: boolean; automaticMerge: boolean; automaticPr: boolean; isolatedWorktree: boolean };
};

export type PatchIntakeResult = { accepted: boolean; status: "ACCEPTED" | "REJECTED"; changedFiles: string[]; reason?: string };

export type WorkerEvidence = {
  taskId: string; runId: string; attempt: number; jobId?: string;
  status: WorkerExecutionResult["status"]; success: boolean; changedFiles: string[];
  diff?: string; validation?: WorkerExecutionResult["validation"]; error?: string;
  safety: WorkerExecutionResult["safety"]; capturedAt: string;
};

export type WorkerEvaluation = {
  taskId: string; runId: string; attempts: number; finalStatus: WorkerStatus;
  accepted: boolean; patchReadyAttempts: number; validationPasses: number;
  validationFailures: number; failureCount: number; changedFiles: string[];
  evidenceQuality: "HIGH" | "MEDIUM" | "LOW";
  recommendation: "FEED_BACK" | "REVIEW" | "ACCEPT" | "NO_PATCH";
  evaluatedAt: string;
};

export type WorkerFeedbackKind = "IMPLEMENTATION_VERIFIED" | "IMPLEMENTATION_BLOCKED" | "IMPLEMENTATION_NO_PATCH" | "IMPLEMENTATION_REVIEW";

export type WorkerFeedback = {
  taskId: string; runId: string; kind: WorkerFeedbackKind;
  recommendation: WorkerEvaluation["recommendation"];
  attempts: number; validationFailures: number; validationPasses: number; failureCount: number;
  changedFiles: string[]; evidenceQuality: WorkerEvaluation["evidenceQuality"];
  learningEligible: false; researchImpact: "NONE" | "IMPLEMENTATION_ONLY";
  summary: string; failureDetails?: string[]; nextCycleInput: Record<string, unknown>; createdAt: string;
};

export type WorkerRecord = {
  taskId: string; runId: string; provider: WorkerProviderId; attempt: number; maxAttempts: number;
  status: WorkerStatus; jobId?: string; worktreePath?: string; changedFiles: string[];
  validation?: WorkerExecutionResult["validation"]; error?: string; createdAt: string; startedAt?: string; completedAt?: string;
};

export type WorkerLifecycleEvent = { taskId: string; runId: string; attempt: number; from: WorkerStatus | null; to: WorkerStatus; at: string; message?: string };

export type WorkerRuntimeOptions = {
  repoRoot: string; queueDbPath?: string; maxConcurrency?: number; defaultTimeoutMs?: number;
  defaultMaxAttempts?: number; enabled?: boolean;
  providerResolver?: (id: WorkerProviderId, repoRoot: string) => WorkerProvider;
};
