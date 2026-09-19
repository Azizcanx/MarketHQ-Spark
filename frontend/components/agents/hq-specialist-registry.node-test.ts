import assert from "node:assert/strict";
import test from "node:test";

import { buildHQPlan } from "./hq-agent-orchestrator";
import { executeHQPlan } from "./hq-agent-runtime";

function restore(name: string, value: string | undefined): void {
  if (value === undefined) delete process.env[name];
  else process.env[name] = value;
}

test("Trendyol specialist remains safe when credentials are absent", async () => {
  const previous = {
    seller: process.env.MARKETHQ_TRENDYOL_SELLER_ID,
    key: process.env.MARKETHQ_TRENDYOL_API_KEY,
    secret: process.env.MARKETHQ_TRENDYOL_API_SECRET,
  };
  delete process.env.MARKETHQ_TRENDYOL_SELLER_ID;
  delete process.env.MARKETHQ_TRENDYOL_API_KEY;
  delete process.env.MARKETHQ_TRENDYOL_API_SECRET;

  try {
    const plan = buildHQPlan("Trendyol durum nasıl?");
    const run = await executeHQPlan(plan);
    const trendyol = run.tasks.find((task) => task.task.agentId === "trendyol-agent");

    assert.ok(trendyol?.result);
    assert.equal(trendyol.result.status, "COMPLETED");
    assert.match(trendyol.result.summary, /credentials yapılandırılmamış/);
    assert.equal(trendyol.result.metadata?.researchOnly, true);
    assert.equal(trendyol.result.metadata?.executionEnabled, false);
  } finally {
    restore("MARKETHQ_TRENDYOL_SELLER_ID", previous.seller);
    restore("MARKETHQ_TRENDYOL_API_KEY", previous.key);
    restore("MARKETHQ_TRENDYOL_API_SECRET", previous.secret);
  }
});

test("Trendyol specialist performs only GET calls for a configured read-only snapshot", async () => {
  const previous = {
    seller: process.env.MARKETHQ_TRENDYOL_SELLER_ID,
    key: process.env.MARKETHQ_TRENDYOL_API_KEY,
    secret: process.env.MARKETHQ_TRENDYOL_API_SECRET,
  };
  process.env.MARKETHQ_TRENDYOL_SELLER_ID = "123";
  process.env.MARKETHQ_TRENDYOL_API_KEY = "key";
  process.env.MARKETHQ_TRENDYOL_API_SECRET = "secret";

  try {
    const plan = buildHQPlan("Trendyol ürün ve sipariş durumu");
    const run = await executeHQPlan(plan);
    const trendyol = run.tasks.find((task) => task.task.agentId === "trendyol-agent");

    assert.ok(trendyol?.result);
    assert.equal(trendyol.result.status, "COMPLETED");
    assert.equal(trendyol.result.metadata?.executionEnabled, false);
  } finally {
    restore("MARKETHQ_TRENDYOL_SELLER_ID", previous.seller);
    restore("MARKETHQ_TRENDYOL_API_KEY", previous.key);
    restore("MARKETHQ_TRENDYOL_API_SECRET", previous.secret);
  }
});
