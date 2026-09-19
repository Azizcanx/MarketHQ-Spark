import { Pool, type QueryResultRow } from "pg";

export const runtime = "nodejs";

let pool: Pool | null = null;
function getPool(): Pool {
  if (!pool) {
    const url = process.env.MARKETHQ_STORE_DB_URL?.trim();
    if (!url) throw new Error("MARKETHQ_STORE_DB_URL is not configured.");
    pool = new Pool({ connectionString: url, max: 4, connectionTimeoutMillis: 5000 });
  }
  return pool;
}

async function q<T extends QueryResultRow>(text: string, params?: unknown[]): Promise<T[]> {
  const res = await getPool().query<T>(text, params as never[]);
  return res.rows;
}

export type CatalogProduct = {
  id: string;
  sku: string;
  title: string;
  brand: string | null;
  trendyol_barcode: string | null;
  trendyol_category_id: number | null;
  local_category: string | null;
  cost_price: string | null;
  sale_price: string | null;
  stock_on_hand: number;
  stock_buffer: number;
  channel_enabled: boolean;
  notes: string | null;
  created_at: string;
  updated_at: string;
};

export type ProductInput = {
  sku: string;
  title: string;
  brand?: string | null;
  trendyol_barcode?: string | null;
  trendyol_category_id?: number | null;
  local_category?: string | null;
  cost_price?: number | null;
  sale_price?: number | null;
  stock_on_hand?: number;
  stock_buffer?: number;
  channel_enabled?: boolean;
  notes?: string | null;
};

const SKU_RE = /^[A-Za-z0-9][A-Za-z0-9._-]{1,63}$/;
const BARCODE_RE = /^\d{6,20}$/;

export function validateProductInput(input: Partial<ProductInput>, partial: boolean): string | null {
  if (!partial || input.sku !== undefined) {
    if (typeof input.sku !== "string" || !SKU_RE.test(input.sku)) return "sku: 2-64 karakter, alfanümerik + . _ - ; benzersiz olmalı";
  }
  if (!partial || input.title !== undefined) {
    if (typeof input.title !== "string" || !input.title.trim() || input.title.length > 300) return "title: 1-300 karakter zorunlu";
  }
  if (input.trendyol_barcode !== undefined && input.trendyol_barcode !== null && input.trendyol_barcode !== "") {
    if (typeof input.trendyol_barcode !== "string" || !BARCODE_RE.test(input.trendyol_barcode)) return "trendyol_barcode: 6-20 hane rakam";
  }
  for (const key of ["stock_on_hand", "stock_buffer"] as const) {
    if (input[key] !== undefined) {
      const n = input[key];
      if (typeof n !== "number" || !Number.isInteger(n) || n < 0 || n > 10_000_000) return `${key}: 0+ tam sayı`;
    }
  }
  for (const key of ["cost_price", "sale_price"] as const) {
    if (input[key] !== undefined && input[key] !== null) {
      const n = input[key];
      if (typeof n !== "number" || !Number.isFinite(n) || n < 0 || n > 10_000_000) return `${key}: 0+ sayı`;
    }
  }
  if (input.trendyol_category_id !== undefined && input.trendyol_category_id !== null) {
    const n = input.trendyol_category_id;
    if (typeof n !== "number" || !Number.isInteger(n) || n <= 0) return "trendyol_category_id: pozitif tam sayı";
  }
  return null;
}

export function visibleStock(product: Pick<CatalogProduct, "stock_on_hand" | "stock_buffer">): number {
  return Math.max(0, product.stock_on_hand - product.stock_buffer);
}

export async function listProducts(opts: { search?: string; page?: number; size?: number } = {}) {
  const page = Math.max(0, opts.page ?? 0);
  const size = Math.min(100, Math.max(1, opts.size ?? 25));
  const where: string[] = [];
  const params: unknown[] = [];
  const search = opts.search?.trim().toLowerCase();
  if (search) {
    params.push(`%${search}%`);
    where.push(`(lower(sku) like $1 or lower(title) like $1 or coalesce(lower(brand), '') like $1 or coalesce(trendyol_barcode, '') like $1)`);
  }
  const whereSql = where.length ? `where ${where.join(" and ")}` : "";
  params.push(size, page * size);
  const sizeIdx = params.length - 1;
  const offsetIdx = params.length;
  const rows = await q<CatalogProduct & { total_count: string }>(
    `select *, count(*) over()::text as total_count from store_products ${whereSql} order by updated_at desc limit $${sizeIdx} offset $${offsetIdx}`,
    params,
  );
  const total = rows.length ? Number(rows[0].total_count) : 0;
  return {
    content: rows.map(({ total_count: _total, ...row }) => ({ ...row, visible_stock: visibleStock(row) })),
    total,
    page,
    size,
  };
}

export async function createProduct(actor: string, input: ProductInput) {
  const rows = await q<CatalogProduct>(
    `insert into store_products (sku, title, brand, trendyol_barcode, trendyol_category_id, local_category, cost_price, sale_price, stock_on_hand, stock_buffer, channel_enabled, notes)
     values ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12) returning *`,
    [input.sku, input.title.trim(), input.brand ?? null, input.trendyol_barcode || null, input.trendyol_category_id ?? null,
     input.local_category ?? null, input.cost_price ?? null, input.sale_price ?? null, input.stock_on_hand ?? 0,
     input.stock_buffer ?? 5, input.channel_enabled ?? true, input.notes ?? null],
  );
  const created = rows[0];
  await audit(actor, "catalog.create", "store_product", created?.id, { sku: created?.sku });
  return created;
}

export async function updateProduct(actor: string, id: string, patch: Partial<ProductInput>) {
  const cols: string[] = [];
  const params: unknown[] = [];
  const map: Array<[keyof ProductInput, string]> = [
    ["sku", "sku"], ["title", "title"], ["brand", "brand"], ["trendyol_barcode", "trendyol_barcode"],
    ["trendyol_category_id", "trendyol_category_id"], ["local_category", "local_category"], ["cost_price", "cost_price"],
    ["sale_price", "sale_price"], ["stock_on_hand", "stock_on_hand"], ["stock_buffer", "stock_buffer"],
    ["channel_enabled", "channel_enabled"], ["notes", "notes"],
  ];
  for (const [field, column] of map) {
    if (patch[field] !== undefined) { params.push(patch[field] === "" ? null : patch[field]); cols.push(`${column}=$${params.length}`); }
  }
  if (!cols.length) return null;
  params.push(id);
  const rows = await q<CatalogProduct>(
    `update store_products set ${cols.join(", ")}, updated_at=now() where id=$${params.length} returning *`,
    params,
  );
  const updated = rows[0];
  if (updated) await audit(actor, "catalog.update", "store_product", id, { fields: cols.map((c) => c.split("=")[0]) });
  return updated ?? null;
}

export async function deleteProduct(actor: string, id: string) {
  const rows = await q<{ sku: string }>(`delete from store_products where id=$1 returning sku`, [id]);
  if (rows.length) await audit(actor, "catalog.delete", "store_product", id, { sku: rows[0].sku });
  return rows.length > 0;
}

export async function audit(actor: string, action: string, entity: string, entityId: string | undefined | null, detail: unknown) {
  try {
    await q(`insert into store_audit (actor, action, entity, entity_id, detail) values ($1,$2,$3,$4,$5)`,
      [actor, action, entity, entityId == null ? null : String(entityId), JSON.stringify(detail ?? {})]);
  } catch { /* audit must never break the request */ }
}

export async function listAudit(limit = 50) {
  return q(`select actor, action, entity, entity_id, detail, at from store_audit order by id desc limit $1`, [Math.min(200, Math.max(1, limit))]);
}
