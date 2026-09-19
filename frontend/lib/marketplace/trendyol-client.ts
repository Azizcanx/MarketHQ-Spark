export type TrendyolClientOptions = {
  sellerId: string;
  apiKey: string;
  apiSecret: string;
  storeFrontCode?: string;
  baseUrl?: string;
  fetchImpl?: typeof fetch;
};

export type TrendyolPage<T> = {
  content: T[];
  totalElements?: number;
  totalPages?: number;
  page?: number;
  size?: number;
};

const DEFAULT_BASE_URL = "https://apigw.trendyol.com/integration";

function toQuery(params: Record<string, string | number | boolean | undefined>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined) continue;
    search.set(key, String(value));
  }
  const query = search.toString();
  return query ? `?${query}` : "";
}

export class TrendyolClient {
  private readonly sellerId: string;
  private readonly authHeader: string;
  private readonly storeFrontCode: string;
  private readonly baseUrl: string;
  private readonly fetchImpl: typeof fetch;

  constructor(options: TrendyolClientOptions) {
    if (!options.sellerId?.trim()) throw new Error("TrendyolClient requires sellerId.");
    if (!options.apiKey?.trim() || !options.apiSecret?.trim()) {
      throw new Error("TrendyolClient requires apiKey and apiSecret.");
    }
    this.sellerId = options.sellerId.trim();
    this.authHeader = `Basic ${Buffer.from(`${options.apiKey.trim()}:${options.apiSecret.trim()}`).toString("base64")}`;
    this.storeFrontCode = options.storeFrontCode?.trim() || "TR";
    this.baseUrl = (options.baseUrl ?? DEFAULT_BASE_URL).replace(/\/$/, "");
    this.fetchImpl = options.fetchImpl ?? fetch;
  }

  private async get<T>(path: string): Promise<T> {
    const response = await this.fetchImpl(`${this.baseUrl}${path}`, {
      method: "GET",
      headers: {
        Authorization: this.authHeader,
        storeFrontCode: this.storeFrontCode,
        Accept: "application/json",
        "User-Agent": `${this.sellerId} - MarketHQ`,
      },
      cache: "no-store",
    });
    if (!response.ok) {
      const body = await response.text().catch(() => "");
      throw new Error(`Trendyol API ${response.status}: ${body.slice(0, 500)}`);
    }
    return (await response.json()) as T;
  }

  listProducts(params: { approved?: boolean; barcode?: string; page?: number; size?: number } = {}) {
    return this.get<TrendyolPage<Record<string, unknown>>>(
      `/product/sellers/${encodeURIComponent(this.sellerId)}/products${toQuery({
        approved: params.approved,
        barcode: params.barcode,
        page: params.page ?? 0,
        size: params.size ?? 20,
      })}`,
    );
  }

  getProduct(barcode: string) {
    return this.listProducts({ barcode, size: 1 });
  }

  listOrders(params: {
    page?: number;
    size?: number;
    orderByField?: string;
    orderByDirection?: "ASC" | "DESC";
    startDate?: number;
    endDate?: number;
    status?: string;
  } = {}) {
    return this.get<TrendyolPage<Record<string, unknown>>>(
      `/order/sellers/${encodeURIComponent(this.sellerId)}/v2/orders${toQuery({
        page: params.page ?? 0,
        size: params.size ?? 20,
        orderByField: params.orderByField,
        orderByDirection: params.orderByDirection,
        startDate: params.startDate,
        endDate: params.endDate,
        status: params.status,
      })}`,
    );
  }

  getBrands() {
    return this.get<unknown>("/product/brands");
  }

  getCategories() {
    return this.get<unknown>("/product/product-categories");
  }

  getAddresses() {
    return this.get<unknown>(`/order/sellers/${encodeURIComponent(this.sellerId)}/addresses`);
  }
}

export function trendyolClientFromEnv(env: NodeJS.ProcessEnv = process.env): TrendyolClient | null {
  const sellerId = env.MARKETHQ_TRENDYOL_SELLER_ID?.trim();
  const apiKey = env.MARKETHQ_TRENDYOL_API_KEY?.trim();
  const apiSecret = env.MARKETHQ_TRENDYOL_API_SECRET?.trim();
  if (!sellerId || !apiKey || !apiSecret) return null;
  return new TrendyolClient({ sellerId, apiKey, apiSecret });
}
