import assert from "node:assert/strict";
import { chmod, mkdtemp, rm, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { execFile } from "node:child_process";
import { promisify } from "node:util";
import test from "node:test";
import { buildCursorTaskPacket, runCursorWorker } from "./cursor-worker-adapter-v1";

const execFileAsync = promisify(execFile);

async function git(root: string, ...args: string[]) {
  await execFileAsync("git", args, { cwd: root, windowsHide: true });
}

async function fixture() {
  const root = await mkdtemp(path.join(os.tmpdir(), "markethq-cursor-adapter-"));
  await git(root, "init");
  await git(root, "config", "user.email", "test@markethq.invalid");
  await git(root, "config", "user.name", "MarketHQ Test");
  await execFileAsync("mkdir", ["-p", path.join(root, "components", "workers")], { cwd: root });
  await writeFile(path.join(root, "README.md"), "fixture\n", "utf8");
  await writeFile(path.join(root, "components", "workers", ".keep"), "fixture\n", "utf8");
  const bin = path.join(root, "fake-cursor-agent");
  await writeFile(bin, "#!/bin/sh\nif [ \"$1\" = \"--version\" ]; then echo fake-cursor-agent 2.0.0; exit 0; fi\nworkspace=\"\"\nfor arg in \"$@\"; do\n  if [ \"$previous\" = \"--workspace\" ]; then workspace=\"$arg\"; fi\n  previous=\"$arg\"\ndone\nif [ -z \"$workspace\" ]; then echo missing workspace >&2; exit 2; fi\nprintf '%s\\n' 'adapter fixture change' > \"$workspace/components/workers/generated.txt\"\necho '{\"status\":\"ok\"}'\nexit 0\n", "utf8");
  await chmod(bin, 0o755);
  await git(root, "add", "README.md", "components/workers/.keep", "fake-cursor-agent");
  await git(root, "commit", "-m", "fixture");
  return { root, bin };
}

async function worktreeRoot() {
  return mkdtemp(path.join(os.tmpdir(), "markethq-cursor-worktrees-"));
}

test("Cursor adapter executes only in an isolated worktree and returns PATCH_READY", async () => {
  const previous = process.env.CURSOR_AGENT_PATH;
  const f = await fixture();
  const wtRoot = await worktreeRoot();
  try {
    process.env.CURSOR_AGENT_PATH = f.bin;
    const packet = buildCursorTaskPacket({
      runId: "adapter-run",
      taskId: "adapter-task",
      title: "Adapter fixture",
      instructions: "Create the fixture output file.",
      targetPaths: ["components/workers"],
      validationCommand: "node -e process.exit(0)",
    });
    const result = await runCursorWorker(packet, {
      repoRoot: f.root,
      worktreeRoot: wtRoot,
    });
    assert.equal(result.success, true);
    assert.equal(result.status, "PATCH_READY");
    assert.equal(result.validation?.attempted, true);
    assert.equal(result.validation?.passed, true);
    assert.equal(result.safety.researchOnly, true);
    assert.equal(result.safety.isolatedWorktree, true);
    assert.equal(result.safety.mainRepoMutation, false);
    assert.deepEqual(result.changedFiles, ["components/workers/generated.txt"]);
    assert.equal(await execFileAsync("git", ["status", "--porcelain"], { cwd: f.root }).then(x => x.stdout.trim()), "");
  } finally {
    if (previous === undefined) delete process.env.CURSOR_AGENT_PATH;
    else process.env.CURSOR_AGENT_PATH = previous;
    await rm(wtRoot, { recursive: true, force: true });
    await rm(f.root, { recursive: true, force: true });
  }
});

test("Cursor adapter refuses a dirty main repository", async () => {
  const previous = process.env.CURSOR_AGENT_PATH;
  const f = await fixture();
  try {
    process.env.CURSOR_AGENT_PATH = f.bin;
    await writeFile(path.join(f.root, "dirty.txt"), "dirty\n", "utf8");
    const packet = buildCursorTaskPacket({
      runId: "dirty-run",
      taskId: "dirty-task",
      title: "Dirty repo fixture",
      instructions: "Should not execute.",
      targetPaths: ["components/workers"],
    });
    const result = await runCursorWorker(packet, { repoRoot: f.root });
    assert.equal(result.status, "FAILED");
    assert.match(result.error ?? "", /dirty/i);
    assert.equal(result.worktreePath, undefined);
  } finally {
    if (previous === undefined) delete process.env.CURSOR_AGENT_PATH;
    else process.env.CURSOR_AGENT_PATH = previous;
    await rm(f.root, { recursive: true, force: true });
  }
});

test("Cursor adapter rejects validation failure without reporting a ready patch", async () => {
  const previous = process.env.CURSOR_AGENT_PATH;
  const f = await fixture();
  const wtRoot = await worktreeRoot();
  try {
    process.env.CURSOR_AGENT_PATH = f.bin;
    const packet = buildCursorTaskPacket({
      runId: "validation-run",
      taskId: "validation-task",
      title: "Validation fixture",
      instructions: "Create the fixture output file.",
      targetPaths: ["components/workers"],
      validationCommand: "node -e process.exit(1)",
    });
    const result = await runCursorWorker(packet, {
      repoRoot: f.root,
      worktreeRoot: wtRoot,
    });
    assert.equal(result.success, false);
    assert.equal(result.status, "PATCH_REJECTED");
    assert.equal(result.validation?.attempted, true);
    assert.equal(result.validation?.passed, false);
    assert.equal(result.changedFiles.length, 1);
  } finally {
    if (previous === undefined) delete process.env.CURSOR_AGENT_PATH;
    else process.env.CURSOR_AGENT_PATH = previous;
    await rm(wtRoot, { recursive: true, force: true });
    await rm(f.root, { recursive: true, force: true });
  }
});
