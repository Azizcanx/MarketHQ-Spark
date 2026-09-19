export interface MarketHQHealth {
  success: boolean;
  status: string;
  api_version: string;
  generated_at: string;
  database_available: boolean;
  missing_core_tables: string[];
  safety: {
    research_only: boolean;
    execution_enabled: boolean;
    database_write_enabled: boolean;
    broker_execution_enabled: boolean;
  };
}

export interface MarketHQResponse<T = unknown> {
  success?: boolean;
  data?: T;
  error?: string;
  message?: string;
  [key: string]: unknown;
}

export interface MarketHQRequestOptions {
  signal?: AbortSignal;
  cache?: RequestCache;
}

class MarketHQApiClient {
  private readonly browserBaseUrl = "/api";
  private readonly serverBaseUrl =
    "http://127.0.0.1:8010/api";

  private getBaseUrl(): string {
    if (typeof window === "undefined") {
      return this.serverBaseUrl;
    }

    return this.browserBaseUrl;
  }

  private async request<T>(
    endpoint: string,
    options: RequestInit = {}
  ): Promise<T> {
    const response = await fetch(
      `${this.getBaseUrl()}${endpoint}`,
      {
        ...options,
        headers: {
          Accept: "application/json",
          ...(options.headers ?? {}),
        },
      }
    );

    const contentType =
      response.headers.get("content-type") ?? "";

    let body: unknown;

    if (contentType.includes("application/json")) {
      body = await response.json();
    } else {
      body = await response.text();
    }

    if (!response.ok) {
      const message =
        typeof body === "object" &&
        body !== null &&
        "error" in body &&
        typeof body.error === "string"
          ? body.error
          : `MarketHQ API error: ${response.status}`;

      throw new Error(message);
    }

    return body as T;
  }

  async health(
    options: MarketHQRequestOptions = {}
  ): Promise<MarketHQHealth> {
    return this.request<MarketHQHealth>(
      "/health",
      {
        method: "GET",
        signal: options.signal,
        cache: options.cache ?? "no-store",
      }
    );
  }

  async snapshot(
    options: MarketHQRequestOptions = {}
  ): Promise<MarketHQResponse> {
    return this.request<MarketHQResponse>(
      "/snapshot",
      {
        method: "GET",
        signal: options.signal,
        cache: options.cache ?? "no-store",
      }
    );
  }

  async knowledge(
    options: MarketHQRequestOptions = {}
  ): Promise<MarketHQResponse> {
    return this.request<MarketHQResponse>(
      "/knowledge",
      {
        method: "GET",
        signal: options.signal,
        cache: options.cache ?? "no-store",
      }
    );
  }

  async brain(
    options: MarketHQRequestOptions = {}
  ): Promise<MarketHQResponse> {
    return this.request<MarketHQResponse>(
      "/brain",
      {
        method: "GET",
        signal: options.signal,
        cache: options.cache ?? "no-store",
      }
    );
  }

  async learning(
    options: MarketHQRequestOptions = {}
  ): Promise<MarketHQResponse> {
    return this.request<MarketHQResponse>(
      "/learning",
      {
        method: "GET",
        signal: options.signal,
        cache: options.cache ?? "no-store",
      }
    );
  }

  async strategy(
    options: MarketHQRequestOptions = {}
  ): Promise<MarketHQResponse> {
    return this.request<MarketHQResponse>(
      "/strategy",
      {
        method: "GET",
        signal: options.signal,
        cache: options.cache ?? "no-store",
      }
    );
  }

  async pipeline(
    options: MarketHQRequestOptions = {}
  ): Promise<MarketHQResponse> {
    return this.request<MarketHQResponse>(
      "/pipeline",
      {
        method: "GET",
        signal: options.signal,
        cache: options.cache ?? "no-store",
      }
    );
  }

  async trades(
    options: MarketHQRequestOptions = {}
  ): Promise<MarketHQResponse> {
    return this.request<MarketHQResponse>(
      "/trades",
      {
        method: "GET",
        signal: options.signal,
        cache: options.cache ?? "no-store",
      }
    );
  }

  async trade(
    symbol: string,
    entryTime?: string,
    exitTime?: string,
    options: MarketHQRequestOptions = {}
  ): Promise<MarketHQResponse> {
    const params = new URLSearchParams();

    params.set("symbol", symbol);

    if (entryTime) {
      params.set("entry_time", entryTime);
    }

    if (exitTime) {
      params.set("exit_time", exitTime);
    }

    return this.request<MarketHQResponse>(
      `/trade?${params.toString()}`,
      {
        method: "GET",
        signal: options.signal,
        cache: options.cache ?? "no-store",
      }
    );
  }

  async tradeChart(
    symbol: string,
    entryTime?: string,
    exitTime?: string,
    options: MarketHQRequestOptions = {}
  ): Promise<MarketHQResponse> {
    const params = new URLSearchParams();

    params.set("symbol", symbol);

    if (entryTime) {
      params.set("entry_time", entryTime);
    }

    if (exitTime) {
      params.set("exit_time", exitTime);
    }

    return this.request<MarketHQResponse>(
      `/trade-chart?${params.toString()}`,
      {
        method: "GET",
        signal: options.signal,
        cache: options.cache ?? "no-store",
      }
    );
  }

  async symbols(
    options: MarketHQRequestOptions = {}
  ): Promise<MarketHQResponse> {
    return this.request<MarketHQResponse>(
      "/symbols",
      {
        method: "GET",
        signal: options.signal,
        cache: options.cache ?? "no-store",
      }
    );
  }

  async evidence(
    options: MarketHQRequestOptions = {}
  ): Promise<MarketHQResponse> {
    return this.request<MarketHQResponse>(
      "/evidence",
      {
        method: "GET",
        signal: options.signal,
        cache: options.cache ?? "no-store",
      }
    );
  }

  async sourceDebug(
    options: MarketHQRequestOptions = {}
  ): Promise<MarketHQResponse> {
    return this.request<MarketHQResponse>(
      "/source-debug",
      {
        method: "GET",
        signal: options.signal,
        cache: options.cache ?? "no-store",
      }
    );
  }
}

export const marketHQApi =
  new MarketHQApiClient();

export default marketHQApi;
