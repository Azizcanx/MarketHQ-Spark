import { buildCursorTaskPacket, runCursorWorker } from "../cursor-worker-adapter-v1";
import { runCursorWorkerPreflight, CursorWorkerPreflightBlockedError } from "../cursor-worker-preflight";
import path from "node:path";
import type { WorkerExecutionResult, WorkerProvider, WorkerTask } from "../worker-types";

export class CursorProvider implements WorkerProvider {
  readonly id = "cursor" as const;

  constructor(private readonly repoRoot: string) {}

  async execute(task: WorkerTask): Promise<WorkerExecutionResult> {
    const allowDirtyMainRepo = process.env.MARKETHQ_CURSOR_WORKER_ALLOW_DIRTY_MAIN_REPO === "true";
    const preflight = await runCursorWorkerPreflight({
      repoRoot: this.repoRoot,
      worktreeRoot: path.join(this.repoRoot, ".markethq-worktrees"),
      task,
      requireAuthentication: true,
      allowDirtyMainRepo,
    });
    if (!preflight.ready) throw new CursorWorkerPreflightBlockedError(preflight);

    return await runCursorWorker(
      buildCursorTaskPacket({
        runId: task.runId,
        taskId: task.taskId,
        title: task.title,
        instructions: task.instructions,
        targetPaths: task.targetPaths,
        validationCommand: task.validationCommand,
        timeoutMs: task.timeoutMs,
        metadata: task.metadata,
      }),
      {
        repoRoot: this.repoRoot,
        timeoutMs: task.timeoutMs,
        allowDirtyMainRepo,
      },
    ) as WorkerExecutionResult;
  }
}
