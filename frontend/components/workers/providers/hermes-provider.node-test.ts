import assert from "node:assert/strict";
import test from "node:test";
import { HermesProvider } from "./hermes-provider";
import type { WorkerTask } from "../worker-types";

const task: WorkerTask = {
  taskId: "hermes-test-task",
  runId: "hermes-test-run",
  title: "Hermes provider contract",
  instructions: "Return a concise research recommendation.",
  targetPaths: ["frontend/components/workers"],
  provider: "hermes",
  timeoutMs: 1_000,
};

test("Hermes provider fails closed when API key is missing", async () => {
  const previous = process.env.MARKETHQ_HERMES_API_KEY;
  delete process.env.MARKETHQ_HERMES_API_KEY;
  try {
    const result = await new HermesProvider({ baseUrl: "http://127.0.0.1:9" }).execute(task);
    assert.equal(result.success, false);
    assert.equal(result.status, "FAILED");
    assert.match(result.error ?? "", /API_KEY is not configured/i);
    assert.equal(result.safety.researchOnly, true);
    assert.equal(result.safety.mainRepoMutation, false);
    assert.equal(result.safety.automaticPr, false);
    assert.equal(result.safety.automaticMerge, false);
    assert.equal(result.safety.isolatedWorktree, false);
  } finally {
    if (previous === undefined) delete process.env.MARKETHQ_HERMES_API_KEY;
    else process.env.MARKETHQ_HERMES_API_KEY = previous;
  }
});

test("Hermes provider returns research response without mutation authority", async () => {
  const previousFetch = globalThis.fetch;
  try {
    let request: Request | undefined;
    globalThis.fetch = async (input, init) => {
      request = new Request(input, init);
      return new Response(JSON.stringify({ choices: [{ message: { content: "research evidence" } }] }), {
        status: 200,
        headers: { "content-type": "application/json" },
      });
    };

    const result = await new HermesProvider({
      baseUrl: "http://hermes.test",
      apiKey: "test-key",
      model: "test-model",
    }).execute(task);

    assert.equal(result.success, true);
    assert.equal(result.status, "NO_PATCH");
    assert.deepEqual(result.changedFiles, []);
    assert.match(result.diff ?? "", /research evidence/);
    assert.equal(result.safety.researchOnly, true);
    assert.equal(result.safety.mainRepoMutation, false);
    assert.equal(result.safety.automaticPr, false);
    assert.equal(result.safety.automaticMerge, false);
    assert.equal(request?.url, "http://hermes.test/v1/chat/completions");
    assert.equal(request?.headers.get("authorization"), "Bearer test-key");
    const body = JSON.parse(await request!.text()) as { model: string; temperature: number; messages: Array<{ role: string; content: string }> };
    assert.equal(body.model, "test-model");
    assert.equal(body.temperature, 0);
    assert.equal(body.messages[0]?.role, "system");
    assert.match(body.messages[0]?.content ?? "", /research-only worker/i);
  } finally {
    globalThis.fetch = previousFetch;
  }
});

test("Hermes provider converts API errors into FAILED evidence", async () => {
  const previousFetch = globalThis.fetch;
  try {
    globalThis.fetch = async () => new Response("upstream unavailable", { status: 503 });
    const result = await new HermesProvider({ baseUrl: "http://hermes.test", apiKey: "test-key" }).execute(task);
    assert.equal(result.success, false);
    assert.equal(result.status, "FAILED");
    assert.match(result.error ?? "", /Hermes API 503/);
    assert.match(result.error ?? "", /upstream unavailable/);
    assert.equal(result.changedFiles.length, 0);
    assert.equal(result.safety.researchOnly, true);
    assert.equal(result.safety.mainRepoMutation, false);
  } finally {
    globalThis.fetch = previousFetch;
  }
});
