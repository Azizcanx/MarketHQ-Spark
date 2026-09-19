import path from "node:path";

const repoRoot = path.resolve(import.meta.dirname, "..");
process.env.MARKETHQ_REPO_ROOT = repoRoot;
process.env.MARKETHQ_CURSOR_WORKER_ENABLE = "true";
process.env.MARKETHQ_CURSOR_WORKER_ALLOW_DIRTY_MAIN_REPO = "true";
process.env.MARKETHQ_WORKER_MAX_CONCURRENCY = "1";
process.env.MARKETHQ_WORKER_TIMEOUT_MS = "120000";

const { dispatchWorkerTask, getWorkerRecord, listWorkerEvidence, listWorkerEvents, getWorkerFeedback, getWorkerRuntime } = await import(
  "../frontend/components/workers/dispatch-gateway.ts"
);

const runNonce = `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`;
const task = {
  taskId: `cursor-runtime-e2e-task-v1-${runNonce}`,
  runId: `cursor-runtime-e2e-run-v1-${runNonce}`,
  title: "Cursor Worker Runtime V1 deterministic fixture",
  instructions: [
    "Replace the TODO marker in tests/cursor-worker-fixture.mjs.",
    "Set MARKET_HQ_CURSOR_WORKER_FIXTURE to the exact string PATCH_READY.",
    "Do not modify any other file.",
    "Do not commit, create a pull request, merge, install packages, or access secrets.",
  ].join(" "),
  targetPaths: ["tests/cursor-worker-fixture.mjs"],
  provider: "cursor",
  validationCommand: "node --check tests/cursor-worker-fixture.mjs",
  timeoutMs: 120000,
  maxAttempts: 2,
  metadata: {
    source: "CURSOR_WORKER_RUNTIME_REAL_E2E_V1",
    mutationAuthorized: false,
    automaticPr: false,
    automaticMerge: false,
    implementationIntent: "ITERATE",
  },
};

const queued = await dispatchWorkerTask(task);
console.log("DISPATCHED:", JSON.stringify(queued, null, 2));

await getWorkerRuntime().drain();

const record = getWorkerRecord(task.taskId);
const evidence = listWorkerEvidence(task.taskId);
const events = listWorkerEvents(task.taskId, 100);
const feedback = getWorkerFeedback(task.taskId);

const result = {
  success: record?.status === "ACCEPTED",
  record,
  evidence,
  events,
  feedback,
  safety: {
    researchOnly: true,
    mainRepoMutation: false,
    automaticPr: false,
    automaticMerge: false,
    isolatedWorktree: evidence.length > 0 && evidence.every((item) => item.safety.isolatedWorktree),
  },
};

console.log(JSON.stringify(result, null, 2));
process.exitCode = result.success ? 0 : 1;
