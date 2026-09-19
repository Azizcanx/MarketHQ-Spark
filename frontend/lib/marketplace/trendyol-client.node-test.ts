import assert from "node:assert/strict";
import test from "node:test";

import { TrendyolClient } from "./trendyol-client";

test("TrendyolClient read-only product and order calls use V2-safe endpoints", async () => {
  const requests: Array<{ url: string; method?: string; headers: HeadersInit }> = [];
  const client = new TrendyolClient({
    sellerId: "123",
    apiKey: "key",
    apiSecret: "secret",
    storeFrontCode: "TR",
    baseUrl: "https://example.test/integration",
    fetchImpl: async (input, init) => {
      requests.push({ url: String(input), method: init?.method, headers: init?.headers ?? {} });
      return new Response(JSON.stringify({ content: [] }), { status: 200, headers: { "content-type": "application/json" } });
    },
  });

  await client.listProducts({ approved: true, page: 0, size: 20 });
  await client.listOrders({ page: 0, size: 20, orderByField: "PackageLastModifiedDate", orderByDirection: "DESC" });

  assert.equal(requests.length, 2);
  assert.match(requests[0].url, /\/product\/sellers\/123\/products\?/);
  assert.match(requests[1].url, /\/order\/sellers\/123\/v2\/orders\?/);
  for (const request of requests) {
    assert.equal(request.method, "GET");
    const headers = new Headers(request.headers);
    assert.equal(headers.get("storeFrontCode"), "TR");
    assert.ok(headers.get("Authorization")?.startsWith("Basic "));
  }
});

test("TrendyolClient read-only endpoints never issue mutation methods", async () => {
  const methods: string[] = [];
  const client = new TrendyolClient({
    sellerId: "123",
    apiKey: "key",
    apiSecret: "secret",
    fetchImpl: async (_input, init) => {
      methods.push(init?.method ?? "GET");
      return new Response("{}", { status: 200 });
    },
  });

  await client.getBrands();
  await client.getCategories();
  await client.getProduct("barcode-1");
  await client.listProducts({ approved: true });
  await client.listOrders({ size: 1 });
  await client.getAddresses();

  assert.deepEqual(methods, ["GET", "GET", "GET", "GET", "GET", "GET"]);
});
