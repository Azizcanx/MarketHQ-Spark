import assert from "node:assert/strict";
import test from "node:test";
import { runHermesPreflight } from "./hermes-preflight";

test("Hermes preflight fails closed when provider is disabled", async () => {
  const previousEnabled = process.env.MARKETHQ_HERMES_WORKER_ENABLE;
  delete process.env.MARKETHQ_HERMES_WORKER_ENABLE;
  try {
    const result = await runHermesPreflight();
    assert.equal(result.enabled, false);
    assert.equal(result.reachable, false);
    assert.equal(result.error, "WORKER_POLICY_DISABLED");
  } finally {
    if (previousEnabled === undefined) delete process.env.MARKETHQ_HERMES_WORKER_ENABLE;
    else process.env.MARKETHQ_HERMES_WORKER_ENABLE = previousEnabled;
  }
});

test("Hermes preflight does not expose the API key", async () => {
  const previousEnabled = process.env.MARKETHQ_HERMES_WORKER_ENABLE;
  const previousKey = process.env.MARKETHQ_HERMES_API_KEY;
  process.env.MARKETHQ_HERMES_WORKER_ENABLE = "true";
  delete process.env.MARKETHQ_HERMES_API_KEY;
  try {
    const result = await runHermesPreflight();
    assert.equal(result.configured, false);
    assert.equal(result.baseUrl, "http://127.0.0.1:8642");
    assert.equal(result.model, "hermes-agent");
    assert.ok(!JSON.stringify(result).includes("API_KEY"));
  } finally {
    if (previousEnabled === undefined) delete process.env.MARKETHQ_HERMES_WORKER_ENABLE;
    else process.env.MARKETHQ_HERMES_WORKER_ENABLE = previousEnabled;
    if (previousKey === undefined) delete process.env.MARKETHQ_HERMES_API_KEY;
    else process.env.MARKETHQ_HERMES_API_KEY = previousKey;
  }
});

test("Hermes preflight uses the cheap authenticated models endpoint", async () => {
  const previousEnabled = process.env.MARKETHQ_HERMES_WORKER_ENABLE;
  const previousKey = process.env.MARKETHQ_HERMES_API_KEY;
  const previousUrl = process.env.MARKETHQ_HERMES_API_URL;
  const previousFetch = globalThis.fetch;
  process.env.MARKETHQ_HERMES_WORKER_ENABLE = "true";
  process.env.MARKETHQ_HERMES_API_KEY = "test-key";
  process.env.MARKETHQ_HERMES_API_URL = "http://hermes.test/";
  try {
    let request: Request | undefined;
    globalThis.fetch = async (input, init) => {
      request = new Request(input, init);
      return new Response(JSON.stringify({ object: "list", data: [{ id: "hermes-agent" }] }), { status: 200 });
    };
    const result = await runHermesPreflight();
    assert.equal(result.enabled, true);
    assert.equal(result.configured, true);
    assert.equal(result.reachable, true);
    assert.equal(result.baseUrl, "http://hermes.test");
    assert.equal(request?.url, "http://hermes.test/v1/models");
    assert.equal(request?.method, "GET");
    assert.equal(request?.headers.get("authorization"), "Bearer test-key");
  } finally {
    globalThis.fetch = previousFetch;
    if (previousEnabled === undefined) delete process.env.MARKETHQ_HERMES_WORKER_ENABLE;
    else process.env.MARKETHQ_HERMES_WORKER_ENABLE = previousEnabled;
    if (previousKey === undefined) delete process.env.MARKETHQ_HERMES_API_KEY;
    else process.env.MARKETHQ_HERMES_API_KEY = previousKey;
    if (previousUrl === undefined) delete process.env.MARKETHQ_HERMES_API_URL;
    else process.env.MARKETHQ_HERMES_API_URL = previousUrl;
  }
});
