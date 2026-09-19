-- MarketHQ commerce catalog (Phase C1) — idempotent
CREATE TABLE IF NOT EXISTS store_products (
  id BIGSERIAL PRIMARY KEY,
  sku TEXT NOT NULL UNIQUE,
  title TEXT NOT NULL,
  brand TEXT,
  trendyol_barcode TEXT UNIQUE,
  trendyol_category_id INTEGER,
  local_category TEXT,
  cost_price NUMERIC(12,2),
  sale_price NUMERIC(12,2),
  stock_on_hand INTEGER NOT NULL DEFAULT 0 CHECK (stock_on_hand >= 0),
  stock_buffer INTEGER NOT NULL DEFAULT 5 CHECK (stock_buffer >= 0),
  channel_enabled BOOLEAN NOT NULL DEFAULT TRUE,
  notes TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS store_products_search_idx
  ON store_products (lower(sku), lower(title));
CREATE INDEX IF NOT EXISTS store_products_barcode_idx
  ON store_products (trendyol_barcode) WHERE trendyol_barcode IS NOT NULL;

CREATE TABLE IF NOT EXISTS store_audit (
  id BIGSERIAL PRIMARY KEY,
  actor TEXT NOT NULL,
  action TEXT NOT NULL,
  entity TEXT NOT NULL,
  entity_id TEXT,
  detail JSONB,
  at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS store_audit_entity_idx ON store_audit (entity, entity_id);
