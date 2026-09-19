import assert from "node:assert/strict";
import test from "node:test";
import { validateProductInput, visibleStock } from "./db";

test("validateProductInput accepts a good product", () => {
  const error = validateProductInput({ sku: "MHQ-001", title: "Test ürün", trendyol_barcode: "8680123456789", stock_on_hand: 10, stock_buffer: 5, sale_price: 99.9 }, false);
  assert.equal(error, null);
});

test("validateProductInput rejects bad sku/title/barcode/negatives", () => {
  assert.ok(validateProductInput({ sku: "", title: "x" }, false));
  assert.ok(validateProductInput({ sku: "A", title: "x" }, false));
  assert.ok(validateProductInput({ sku: "MHQ-1", title: "" }, false));
  assert.ok(validateProductInput({ sku: "MHQ-1", title: "x", trendyol_barcode: "abc" }, false));
  assert.ok(validateProductInput({ sku: "MHQ-1", title: "x", stock_on_hand: -5 }, false));
  assert.ok(validateProductInput({ sku: "MHQ-1", title: "x", stock_buffer: 1.5 }, false));
  assert.ok(validateProductInput({ sku: "MHQ-1", title: "x", sale_price: -1 }, false));
});

test("validateProductInput partial mode allows single-field patches", () => {
  assert.equal(validateProductInput({ stock_on_hand: 12 }, true), null);
  assert.equal(validateProductInput({ title: "yeni ad" }, true), null);
  assert.ok(validateProductInput({ stock_on_hand: -3 }, true));
});

test("empty barcode string is allowed (means unmapped)", () => {
  assert.equal(validateProductInput({ sku: "MHQ-2", title: "x", trendyol_barcode: "" }, false), null);
});

test("visibleStock floors at zero and subtracts buffer", () => {
  assert.equal(visibleStock({ stock_on_hand: 10, stock_buffer: 5 }), 5);
  assert.equal(visibleStock({ stock_on_hand: 3, stock_buffer: 5 }), 0);
  assert.equal(visibleStock({ stock_on_hand: 0, stock_buffer: 0 }), 0);
});
