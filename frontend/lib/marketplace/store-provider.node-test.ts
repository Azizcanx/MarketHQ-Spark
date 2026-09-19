import assert from "node:assert/strict";
import test from "node:test";
import { resolveStoreClient, MockStoreClient, type StoreSource } from "./store-provider";

const CREDENTIALS = {
  MARKETHQ_TRENDYOL_SELLER_ID: "12345",
  MARKETHQ_TRENDYOL_API_KEY: "key",
  MARKETHQ_TRENDYOL_API_SECRET: "secret",
};

test("auto mode falls back to mock when credentials are missing", async () => {
  const resolved = resolveStoreClient({ MARKETHQ_STORE_MODE: "auto" });
  assert.ok(resolved);
  assert.equal<StoreSource>(resolved.source, "mock");
});

test("auto mode prefers live when credentials exist", () => {
  const resolved = resolveStoreClient({ ...CREDENTIALS, MARKETHQ_STORE_MODE: "auto" });
  assert.ok(resolved);
  assert.equal<StoreSource>(resolved.source, "live");
});

test("live mode without credentials resolves to null", () => {
  assert.equal(resolveStoreClient({ MARKETHQ_STORE_MODE: "live" }), null);
});

test("off mode resolves to null even with credentials", () => {
  assert.equal(resolveStoreClient({ ...CREDENTIALS, MARKETHQ_STORE_MODE: "off" }), null);
});

test("mock mode always resolves", () => {
  const resolved = resolveStoreClient({ MARKETHQ_STORE_MODE: "mock" });
  assert.ok(resolved);
  assert.equal<StoreSource>(resolved.source, "mock");
});

test("mock products paginate like the Trendyol page contract", async () => {
  const client = new MockStoreClient();
  const first = await client.listProducts({ approved: true, page: 0, size: 20 });
  assert.equal(first.content.length, 20);
  assert.equal(first.totalElements, 24);
  assert.equal(first.totalPages, 2);
  const second = await client.listProducts({ approved: true, page: 1, size: 20 });
  assert.equal(second.content.length, 4);
  const barcode = String(first.content[0].barcode);
  assert.match(barcode, /^868\d{10}$/);
  assert.ok(first.content[0].title);
  assert.ok(typeof first.content[0].salePrice === "number");
});

test("mock product barcode filter works exact and partial", async () => {
  const client = new MockStoreClient();
  const all = await client.listProducts({ page: 0, size: 50 });
  const target = String(all.content[3].barcode);
  const exact = await client.listProducts({ barcode: target });
  assert.equal(exact.content.length, 1);
  const partial = await client.listProducts({ barcode: target.slice(0, 6) });
  assert.ok(partial.content.length >= 1);
  const missing = await client.listProducts({ barcode: "9999999999999" });
  assert.equal(missing.content.length, 0);
  assert.equal(missing.totalElements, 0);
});

test("mock orders are deterministic, filterable and sorted newest first", async () => {
  const client = new MockStoreClient();
  const a = await client.listOrders({ page: 0, size: 50 });
  const b = await client.listOrders({ page: 0, size: 50 });
  assert.deepEqual(a.content.map((order) => order.orderNumber), b.content.map((order) => order.orderNumber));
  assert.equal(a.content.length, 16);
  const dates = a.content.map((order) => Date.parse(String(order.orderDate)));
  assert.ok(dates.every((value, index) => index === 0 || dates[index - 1] >= value));
  const delivered = await client.listOrders({ status: "Delivered", size: 50 });
  assert.ok(delivered.content.length >= 4);
  assert.ok(delivered.content.every((order) => order.status === "Delivered"));
  const cancelled = await client.listOrders({ status: "Cancelled", size: 50 });
  assert.ok(cancelled.content.every((order) => order.status === "Cancelled" || order.shipmentPackageStatus === "Cancelled"));
});

test("mock orders carry the fields the store UI reads", async () => {
  const client = new MockStoreClient();
  const page = await client.listOrders({ page: 0, size: 5 });
  for (const order of page.content) {
    assert.ok(order.orderNumber);
    assert.ok(order.orderDate);
    assert.ok(order.status);
    assert.ok(order.shipmentPackageStatus);
    assert.ok(order.customerFirstName);
    assert.ok(order.customerLastName);
    assert.equal(order.currencyCode, "TRY");
    assert.ok(typeof order.totalPrice === "number" && (order.totalPrice as number) > 0);
  }
});

test("mock resolves through resolveStoreClient identically to the singleton", async () => {
  const resolved = resolveStoreClient({ MARKETHQ_STORE_MODE: "mock" });
  assert.ok(resolved);
  const page = await resolved.client.listProducts({ approved: true, page: 0, size: 5 });
  assert.equal(page.content.length, 5);
});
