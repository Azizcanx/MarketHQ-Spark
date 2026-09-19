import assert from "node:assert/strict";
import { chmod, mkdir, mkdtemp, rm, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { execFile } from "node:child_process";
import { promisify } from "node:util";
import test from "node:test";
import { WorkerRuntime } from "./worker-runtime";
import type { WorkerTask } from "./worker-types";

const execFileAsync = promisify(execFile);

async function git(root: string, ...args: string[]) {
  await execFileAsync("git", args, { cwd: root, windowsHide: true });
}

async function fixture() {
  const root = await mkdtemp(path.join(os.tmpdir(), "markethq-cursor-runtime-"));
  await git(root, "init");
  await git(root, "config", "user.email", "test@markethq.invalid");
  await git(root, "config", "user.name", "MarketHQ Test");
  await mkdir(path.join(root, "components", "workers"), { recursive: true });
  await writeFile(path.join(root, ".gitignore"), ".markethq-worktrees/\n", "utf8");
  await writeFile(path.join(root, "README.md"), "fixture\n", "utf8");
  await writeFile(path.join(root, "components", "workers", ".keep"), "fixture\n", "utf8");
  const bin = path.join(root, "fake-cursor-agent");
  await writeFile(bin, "#!/bin/sh\nif [ \"$1\" = \"--version\" ]; then echo fake-cursor-agent 3.0.0; exit 0; fi\nif [ \"$1\" = \"status\" ]; then echo authenticated; exit 0; fi\nworkspace=\"\"\nprevious=\"\"\nfor arg in \"$@\"; do\n  if [ \"$previous\" = \"--workspace\" ]; then workspace=\"$arg\"; fi\n  previous=\"$arg\"\ndone\nif [ -z \"$workspace\" ]; then echo missing workspace >&2; exit 2; fi\nprintf '%s\\n' 'runtime cursor e2e' > \"$workspace/components/workers/runtime-generated.txt\"\nexit 0\n", "utf8");
  await chmod(bin, 0o755);
  await git(root, "add", ".gitignore", "README.md", "components/workers/.keep", "fake-cursor-agent");
  await git(root, "commit", "-m", "fixture");
  return { root, bin };
}

function task(): WorkerTask {
  return {
    taskId: "cursor-runtime-e2e-task",
    runId: "cursor-runtime-e2e-run",
    title: "Cursor runtime E2E fixture",
    instructions: "Create the requested fixture output.",
    targetPaths: ["components/workers"],
    provider: "cursor",
    validationCommand: "node -e process.exit(0)",
    maxAttempts: 1,
  };
}

test("WorkerRuntime executes Cursor provider through preflight, isolated worktree, validation and evidence", async () => {
  const previous = process.env.CURSOR_AGENT_PATH;
  const previousDb = process.env.MARKETHQ_WORKER_DB_PATH;
  const f = await fixture();
  const dbRoot = await mkdtemp(path.join(os.tmpdir(), "markethq-cursor-runtime-db-"));
  const db = path.join(dbRoot, "worker-runtime.sqlite");
  try {
    process.env.CURSOR_AGENT_PATH = f.bin;
    process.env.MARKETHQ_WORKER_DB_PATH = db;
    const runtime = new WorkerRuntime({
      repoRoot: f.root,
      queueDbPath: db,
      enabled: true,
      maxConcurrency: 1,
      defaultMaxAttempts: 1,
    });
    const queued = await runtime.dispatch(task());
    assert.equal(queued.status, "QUEUED");
    await runtime.drain();

    const finalRecord = runtime.store.latest(task().taskId);
    assert.ok(finalRecord);
    assert.equal(finalRecord.status, "ACCEPTED");
    assert.equal(finalRecord.attempt, 1);
    assert.deepEqual(finalRecord.changedFiles, ["components/workers/runtime-generated.txt"]);
    assert.equal(finalRecord.validation?.passed, true);

    const evidence = runtime.store.listEvidence(task().taskId);
    assert.equal(evidence.length, 1);
    assert.equal(evidence[0].status, "PATCH_READY");
    assert.equal(evidence[0].success, true);
    assert.equal(evidence[0].safety.researchOnly, true);
    assert.equal(evidence[0].safety.isolatedWorktree, true);
    assert.equal(evidence[0].safety.mainRepoMutation, false);
    assert.equal(evidence[0].safety.automaticPr, false);
    assert.equal(evidence[0].safety.automaticMerge, false);

    const feedback = runtime.store.latestFeedbackForContext({
      strategyId: undefined,
      symbol: undefined,
      timeframe: undefined,
    });
    assert.ok(feedback);
    assert.equal(feedback.taskId, task().taskId);
    assert.equal(feedback.kind, "IMPLEMENTATION_VERIFIED");
    assert.equal(feedback.learningEligible, false);
    assert.equal(feedback.researchImpact, "IMPLEMENTATION_ONLY");

    const mainStatus = await execFileAsync("git", ["status", "--porcelain"], { cwd: f.root });
    assert.equal(mainStatus.stdout.trim(), "");
  } finally {
    if (previous === undefined) delete process.env.CURSOR_AGENT_PATH;
    else process.env.CURSOR_AGENT_PATH = previous;
    if (previousDb === undefined) delete process.env.MARKETHQ_WORKER_DB_PATH;
    else process.env.MARKETHQ_WORKER_DB_PATH = previousDb;
    await rm(dbRoot, { recursive: true, force: true });
    await rm(f.root, { recursive: true, force: true });
  }
});
