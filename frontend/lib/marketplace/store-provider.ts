import { TrendyolClient, trendyolClientFromEnv, type TrendyolPage } from "./trendyol-client";

/**
 * Store provider abstraction (e-commerce infrastructure, research-only/read-only).
 *
 * `auto` mode: real Trendyol seller API when credentials exist, deterministic
 * mock fixtures otherwise — so the store UI and routes can be built, tested and
 * demoed before a Trendyol seller account is activated. When credentials are
 * added to .env, every route switches to live without code changes.
 */

export type StoreSource = "live" | "mock";

export type StoreReadClient = {
  listProducts(params?: {
    approved?: boolean;
    barcode?: string;
    page?: number;
    size?: number;
  }): Promise<TrendyolPage<Record<string, unknown>>>;
  listOrders(params?: {
    page?: number;
    size?: number;
    orderByField?: string;
    orderByDirection?: "ASC" | "DESC";
    startDate?: number;
    endDate?: number;
    status?: string;
  }): Promise<TrendyolPage<Record<string, unknown>>>;
};

export type ResolvedStoreClient = {
  client: StoreReadClient;
  source: StoreSource;
};

// ── deterministic fixtures ────────────────────────────────────────────────

function mulberry32(seed: number): () => number {
  let a = seed >>> 0;
  return () => {
    a |= 0;
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

const MOCK_PRODUCT_DEFS: Array<{ title: string; brand: string; cat1: number; cat2: number; price: number }> = [
  { title: "Nitron NC-400 Kablosuz Kulaklık Aktif Gürültü Engelleme", brand: "Nitron", cat1: 12, cat2: 2610, price: 2499 },
  { title: "Vellora Termo Çift Kapaklı Matara 750 ml", brand: "Vellora", cat1: 26, cat2: 2015, price: 449 },
  { title: "Kobalt Mekanik Klavye TKL Hot-Swap Kahverengi Switch", brand: "Kobalt", cat1: 12, cat2: 2624, price: 1899 },
  { title: "Asteris LED Ring Light 45 cm Tripod Seti", brand: "Asteris", cat1: 12, cat2: 3050, price: 1249 },
  { title: "Pomova Elektrikli Cezve 800 ml Paslanmaz", brand: "Pomova", cat1: 47, cat2: 2953, price: 1099 },
  { title: "Silvaner Termos Çelik 1 Litre Vakum Kapaklı", brand: "Silvaner", cat1: 26, cat2: 2017, price: 699 },
  { title: "Nitron PowerBank 20000 mAh PD 30W Hızlı Şarj", brand: "Nitron", cat1: 12, cat2: 2602, price: 899 },
  { title: "Lumenarc Akıllı Saat AMOLED GPS Spor Modu", brand: "Lumenarc", cat1: 12, cat2: 2611, price: 2199 },
  { title: "Kobalt Kablosuz Mouse Ergonomik Sessiz Tık", brand: "Kobalt", cat1: 12, cat2: 2622, price: 349 },
  { title: "Asteris Mikrofon Kolu Masa Tipi Anti-Vibrasyon", brand: "Asteris", cat1: 12, cat2: 3051, price: 599 },
  { title: "Pomova Türk Kahvesi Makinesi 4 Fincanlık", brand: "Pomova", cat1: 47, cat2: 2954, price: 2899 },
  { title: "Vellora Sırt Çantası USB Portlu 30 Litre", brand: "Vellora", cat1: 21, cat2: 2212, price: 949 },
  { title: "Silvaner Döküm Tencere Seti 5 Parça", brand: "Silvaner", cat1: 47, cat2: 2960, price: 2799 },
  { title: "Lumenarc Bluetooth Hoparlör IPX7 20W", brand: "Lumenarc", cat1: 12, cat2: 2614, price: 799 },
  { title: "Nitron USB-C Hub 8-in-1 HDMI 4K", brand: "Nitron", cat1: 12, cat2: 2625, price: 649 },
  { title: "Kobalt Oyuncu Kulaklığı Sanal 7.1 Işıklı", brand: "Kobalt", cat1: 12, cat2: 2610, price: 1049 },
  { title: "Asteris Webcam 2K Otomatik Fokus HDR", brand: "Asteris", cat1: 12, cat2: 3052, price: 1349 },
  { title: "Pomova Çay Makinesi Çift Demlik 1.8 L", brand: "Pomova", cat1: 47, cat2: 2951, price: 1599 },
  { title: "Vellora Yağmurluk Unisex Katlanabilir", brand: "Vellora", cat1: 21, cat2: 2220, price: 399 },
  { title: "Silvaner Bıçak Seti Şef系列 6 Parça", brand: "Silvaner", cat1: 47, cat2: 2961, price: 1299 },
  { title: "Lumenarc Akıllı Bileklik Nabız Oksijen Ölçer", brand: "Lumenarc", cat1: 12, cat2: 2611, price: 749 },
  { title: "Nitron Telefon Tutucu Araç İçi Vakumlu", brand: "Nitron", cat1: 21, cat2: 2233, price: 219 },
  { title: "Kobalt Monitör Kol Full Motion 32 Inch", brand: "Kobalt", cat1: 12, cat2: 2626, price: 1799 },
  { title: "Asteris XLR Ses Arayüzü 2x2", brand: "Asteris", cat1: 12, cat2: 3053, price: 2399 },
];

const MOCK_ORDER_DEFS: Array<{ status: string; package: string; daysAgo: number }> = [
  { status: "Created", package: "Created", daysAgo: 0 },
  { status: "Awaiting", package: "Inbound", daysAgo: 0 },
  { status: "Awaiting", package: "Inbound", daysAgo: 1 },
  { status: "InProcess", package: "InProcess", daysAgo: 1 },
  { status: "Shipped", package: "Shipped", daysAgo: 2 },
  { status: "Shipped", package: "InboundShippedToTrendyol", daysAgo: 2 },
  { status: "Delivered", package: "Delivered", daysAgo: 3 },
  { status: "Delivered", package: "Delivered", daysAgo: 4 },
  { status: "Delivered", package: "Delivered", daysAgo: 5 },
  { status: "Delivered", package: "Delivered", daysAgo: 6 },
  { status: "Delivered", package: "Delivered", daysAgo: 8 },
  { status: "Delivered", package: "Delivered", daysAgo: 10 },
  { status: "Returned", package: "ReturnedFromCustomer", daysAgo: 12 },
  { status: "Returned", package: "ReturnedToCustomer", daysAgo: 15 },
  { status: "Cancelled", package: "Cancelled", daysAgo: 17 },
  { status: "Unpacked", package: "Unpacked", daysAgo: 19 },
];

const MOCK_CUSTOMER_NAMES: Array<[string, string]> = [
  ["Demo", "Yılmaz"], ["Örnek", "Kaya"], ["Sanal", "Demir"], ["Test", "Şahin"],
  ["Demo", "Çelik"], ["Örnek", "Aydın"], ["Sanal", "Öztürk"], ["Test", "Arslan"],
];

const MOCK_BASE_DATE = Date.parse("2026-09-18T09:00:00Z");

function mockBarcode(seed: number, index: number): string {
  const body = String(100000000000 + Math.floor(seed * 1000) + index * 37 + 8680000000000).slice(-10);
  return `868${body}`;
}

function buildMockProducts(): Record<string, unknown>[] {
  const rng = mulberry32(20260918);
  return MOCK_PRODUCT_DEFS.map((def, index) => {
    const quantity = Math.floor(rng() * 60) + (index % 7 === 3 ? 0 : 3);
    const listPrice = def.price;
    const discount = rng() < 0.35 ? Math.round(listPrice * (0.05 + rng() * 0.2) * 100) / 100 : 0;
    const salePrice = Math.round((listPrice - discount) * 100) / 100;
    const created = new Date(MOCK_BASE_DATE - (index + 5) * 86400000).toISOString();
    return {
      itemId: 900000000 + index,
      id: 70000000 + index,
      barcode: mockBarcode(20260918, index),
      title: def.title,
      name: def.title,
      brand: def.brand,
      categoryId: def.cat2,
      category1: def.cat1,
      category2: def.cat2,
      quantity,
      stockUnits: "Adet",
      approved: true,
      archived: false,
      pimPublished: true,
      listingType: "TRENDYOL",
      onSaleSalesPrice: salePrice,
      onSaleExpirationDate: discount > 0 ? new Date(MOCK_BASE_DATE + 7 * 86400000).toISOString() : null,
      listPrice,
      salePrice,
      discountedPrice: discount > 0 ? salePrice : null,
      vatRate: 20,
      images: [{ url: `https://demo.mock.local/products/${index}.jpg` }],
      createDateTime: created,
      lastModifiedDate: created,
      supplierId: "MOCK-SELLER",
    };
  });
}

function buildMockOrders(products: Record<string, unknown>[]): Record<string, unknown>[] {
  const rng = mulberry32(20260919);
  return MOCK_ORDER_DEFS.map((def, index) => {
    const [first, last] = MOCK_CUSTOMER_NAMES[index % MOCK_CUSTOMER_NAMES.length];
    const lineCount = 1 + Math.floor(rng() * 2);
    const lines = Array.from({ length: lineCount }, (_, lineIndex) => {
      const product = products[(index * 3 + lineIndex * 5) % products.length];
      const quantity = 1 + Math.floor(rng() * 2);
      const price = (product.salePrice as number) * quantity;
      return {
        id: 550000000 + index * 10 + lineIndex,
        lineDepartmentNumber: String(index * 10 + lineIndex),
        quantity,
        salesPrice: Math.round(price * 100) / 100,
        price: Math.round(price * 100) / 100,
        discount: 0,
        tax: Math.round(price * 0.2 * 100) / 100,
        node: { name: product.title },
        product: { barcode: product.barcode, name: product.title, brand: product.brand, vendorId: "MOCK-SELLER" },
      };
    });
    const totalPrice = Math.round(lines.reduce((sum, line) => sum + line.price, 0) * 100) / 100;
    const orderDate = new Date(MOCK_BASE_DATE - def.daysAgo * 86400000 - Math.floor(rng() * 36000000)).toISOString();
    const completed = def.status === "Delivered" || def.status === "Returned"
      ? new Date(Date.parse(orderDate) + 2 * 86400000).toISOString()
      : null;
    const order: Record<string, unknown> = {
      orderNumber: `MOCK${String(202600000 + index * 7919).slice(-9)}`,
      orderDate,
      orderAlphanumericDate: orderDate.slice(0, 10),
      supplierId: "MOCK-SELLER",
      orderCountryCode: "TR",
      customerFirstName: first,
      customerLastName: last,
      email: `${first.toLocaleLowerCase("tr-TR")}.${last.toLocaleLowerCase("tr-TR")}@demo.mock.local`,
      phone: `5${index}0 555 ${String(1000 + index).padStart(4, "0")}`,
      notes: "",
      invoice: { invoiceType: "Receipt", email: "muhasebe@demo.mock.local" },
      orderShippingDate: completed,
      completedDate: completed,
      deliveriedFirstName: first,
      totalPrice,
      approved: true,
      currencyCode: "TRY",
      allocatedCurrencyCode: "TRY",
      orderShippingCost: 0,
      status: def.status,
      shipmentPackageStatus: def.package,
      orderLines: lines,
      shipmentPackages: [{
        id: 440000000 + index,
        statusCode: def.package,
        status: def.package,
        packageLineStatus: def.status,
        shippedDate: def.status === "Created" || def.status === "Awaiting" ? null : new Date(Date.parse(orderDate) + 86400000).toISOString(),
        deliveredDate: completed,
        carrierId: 20,
        trackingNo: `TR${index}MOCK${String(100000 + index * 137).slice(-6)}`,
        trackingUrl: null,
      }],
    };
    if (def.status === "Cancelled") {
      order.canceller = "Customer";
      order.cancelTime = orderDate;
      order.cancelledTime = orderDate;
    }
    return order;
  });
}

function paginate<T>(rows: T[], page: number, size: number): TrendyolPage<T> {
  const safePage = Math.max(0, Math.floor(page) || 0);
  const safeSize = Math.min(200, Math.max(1, Math.floor(size) || 20));
  const start = safePage * safeSize;
  return {
    content: rows.slice(start, start + safeSize),
    totalPages: Math.max(1, Math.ceil(rows.length / safeSize)),
    totalElements: rows.length,
    page: safePage,
    size: safeSize,
  };
}

export class MockStoreClient implements StoreReadClient {
  readonly source = "mock" as const;
  private readonly products = buildMockProducts();
  private readonly orders = buildMockOrders(this.products);

  async listProducts(params: {
    approved?: boolean;
    barcode?: string;
    page?: number;
    size?: number;
  } = {}): Promise<TrendyolPage<Record<string, unknown>>> {
    let rows = this.products;
    if (params.approved !== undefined) {
      rows = rows.filter((item) => Boolean(item.approved) === params.approved);
    }
    const needle = params.barcode?.trim();
    if (needle) {
      // Trendyol live API matches barcodes exactly; the mock also allows
      // substring matches so the demo UI stays explorable without full codes.
      rows = rows.filter((item) => {
        const barcode = String(item.barcode ?? "");
        return barcode === needle || barcode.includes(needle);
      });
    }
    return paginate(rows, params.page ?? 0, params.size ?? 20);
  }

  async listOrders(params: {
    page?: number;
    size?: number;
    orderByField?: string;
    orderByDirection?: "ASC" | "DESC";
    startDate?: number;
    endDate?: number;
    status?: string;
  } = {}): Promise<TrendyolPage<Record<string, unknown>>> {
    let rows = this.orders;
    const status = params.status?.trim();
    if (status) {
      const wanted = status.toLowerCase();
      rows = rows.filter((order) =>
        String(order.status).toLowerCase() === wanted
        || String(order.shipmentPackageStatus).toLowerCase() === wanted);
    }
    if (params.startDate || params.endDate) {
      const start = params.startDate ?? 0;
      const end = params.endDate ?? Number.MAX_SAFE_INTEGER;
      rows = rows.filter((order) => {
        const at = Date.parse(String(order.orderDate));
        return at >= start && at <= end;
      });
    }
    const direction = params.orderByDirection === "ASC" ? 1 : -1;
    rows = [...rows].sort((a, b) =>
      direction * (Date.parse(String(a.orderDate)) - Date.parse(String(b.orderDate))));
    return paginate(rows, params.page ?? 0, params.size ?? 20);
  }

  getBrands(): unknown[] {
    return Array.from(new Set(this.products.map((item) => String(item.brand)))).map((brand) => ({ name: brand }));
  }

  getCategories(): unknown[] {
    return Array.from(new Set(this.products.map((item) => Number(item.category2)))).map((id) => ({ id }));
  }

  getAddresses(): Record<string, unknown>[] {
    return [{ id: 1, title: "Demo Deposu", address: "Mock Sok. No:1, İstanbul", contactName: "MOCK" }];
  }
}

const mockClientSingleton = new MockStoreClient();

/**
 * Resolve the store data client from environment.
 * - live: require Trendyol credentials (null when missing → routes report NOT_CONFIGURED)
 * - mock: deterministic fixtures, no network
 * - auto (default): credentials → live, otherwise → mock
 * - off: never provide a client (routes report NOT_CONFIGURED even with credentials)
 */
export function resolveStoreClient(env: NodeJS.ProcessEnv = process.env): ResolvedStoreClient | null {
  const mode = (env.MARKETHQ_STORE_MODE?.trim() || "auto").toLowerCase();
  if (mode === "off") return null;
  const live = trendyolClientFromEnv(env);
  if (mode === "live") return live ? { client: live as StoreReadClient, source: "live" } : null;
  if (mode === "mock") return { client: mockClientSingleton, source: "mock" };
  if (live) return { client: live as StoreReadClient, source: "live" };
  return { client: mockClientSingleton, source: "mock" };
}

export type { TrendyolClient };
