import type {
  AgentContext,
} from "./agent-types";

import {
  agentRunner,
} from "./agent-runner";

type UnknownRecord = Record<string, unknown>;

const BACKEND_BASE_URL =
  process.env.MARKETHQ_BACKEND_URL?.trim() ||
  "http://127.0.0.1:8010";

const DEFAULT_INTERVAL = "1d";
const DEFAULT_START_DATE = "2000-01-01";
const DEFAULT_LIMIT = 5000;

function isRecord(
  value: unknown,
): value is UnknownRecord {
  return (
    Boolean(value) &&
    typeof value === "object" &&
    !Array.isArray(value)
  );
}

function toStringValue(
  value: unknown,
  fallback = "",
): string {
  if (
    typeof value === "string" &&
    value.trim()
  ) {
    return value.trim();
  }

  if (
    typeof value === "number" &&
    Number.isFinite(value)
  ) {
    return String(value);
  }

  return fallback;
}

function toNumber(
  value: unknown,
  fallback = 0,
): number {
  if (
    typeof value === "number" &&
    Number.isFinite(value)
  ) {
    return value;
  }

  if (
    typeof value === "string" &&
    value.trim()
  ) {
    const parsed = Number(value);

    return Number.isFinite(parsed)
      ? parsed
      : fallback;
  }

  return fallback;
}

function yesterdayUtc(): string {
  const now = new Date();

  now.setUTCDate(
    now.getUTCDate() - 1,
  );

  return now
    .toISOString()
    .slice(0, 10);
}

function normalizeSymbol(
  symbol: unknown,
): string {
  return toStringValue(
    symbol,
  ).toUpperCase();
}

function normalizeTimeframe(
  timeframe: unknown,
): string {
  return (
    toStringValue(
      timeframe,
      DEFAULT_INTERVAL,
    ) || DEFAULT_INTERVAL
  );
}

function normalizeRows(
  value: unknown,
): UnknownRecord[] {
  if (!Array.isArray(value)) {
    return [];
  }

  return value.filter(
    isRecord,
  );
}

async function fetchResearchData(
  symbol: string,
  interval: string,
): Promise<{
  ok: boolean;
  data: UnknownRecord;
  error?: string;
}> {
  const endDate =
    yesterdayUtc();

  const url =
    new URL(
      `${BACKEND_BASE_URL}/api/research-data`,
    );

  url.searchParams.set(
    "symbol",
    symbol,
  );

  url.searchParams.set(
    "start",
    DEFAULT_START_DATE,
  );

  url.searchParams.set(
    "end",
    endDate,
  );

  url.searchParams.set(
    "interval",
    interval,
  );

  url.searchParams.set(
    "limit",
    String(DEFAULT_LIMIT),
  );

  try {
    const response =
      await fetch(
        url.toString(),
        {
          method: "GET",
          headers: {
            Accept:
              "application/json",
          },
          cache: "no-store",
        },
      );

    const body =
      await response
        .json()
        .catch(() => null);

    if (
      !response.ok ||
      !isRecord(body) ||
      body.success !== true
    ) {
      const error =
        isRecord(body)
          ? toStringValue(
              body.error,
              `Research data HTTP ${response.status}`,
            )
          : `Research data HTTP ${response.status}`;

      return {
        ok: false,
        data: {},
        error,
      };
    }

    const data =
      isRecord(body.data)
        ? body.data
        : {};

    const rows =
      normalizeRows(
        data.rows,
      );

    if (rows.length === 0) {
      return {
        ok: false,
        data,
        error:
          "Historical research data returned no usable rows.",
      };
    }

    return {
      ok: true,
      data,
    };
  } catch (error) {
    return {
      ok: false,
      data: {},
      error:
        error instanceof Error
          ? error.message
          : "Historical research data request failed.",
    };
  }
}

export async function runMarketDataAgent(
  context: AgentContext,
): Promise<Record<string, unknown>> {
  const requestedSymbol =
    normalizeSymbol(
      context.symbol,
    );

  const requestedTimeframe =
    normalizeTimeframe(
      context.timeframe,
    );

  if (!requestedSymbol) {
    throw new Error(
      "Market Data requires a symbol.",
    );
  }

  if (
    requestedTimeframe !==
    DEFAULT_INTERVAL
  ) {
    throw new Error(
      `Research Market Data currently supports only ${DEFAULT_INTERVAL} timeframe.`,
    );
  }

  /*
   * Health is used only for service/safety
   * visibility.
   *
   * IMPORTANT:
   * database_available is NOT a blocking
   * condition for the research pipeline.
   *
   * Historical research data comes from
   * the read-only /api/research-data
   * endpoint.
   */
  let health:
    | UnknownRecord
    | null = null;

  try {
    const response =
      await fetch(
        `${BACKEND_BASE_URL}/api/health`,
        {
          method: "GET",
          headers: {
            Accept:
              "application/json",
          },
          cache: "no-store",
        },
      );

    const body =
      await response
        .json()
        .catch(() => null);

    if (
      isRecord(body)
    ) {
      health = body;
    }
  } catch {
    /*
     * Health is informational here.
     * Research data request below remains
     * the authoritative data check.
     */
    health = null;
  }

  const researchData =
    await fetchResearchData(
      requestedSymbol,
      requestedTimeframe,
    );

  if (!researchData.ok) {
    throw new Error(
      researchData.error ??
        "MarketHQ research historical data could not be loaded.",
    );
  }

  const data =
    researchData.data;

  const rows =
    normalizeRows(
      data.rows,
    );

  const bars =
    toNumber(
      data.bars,
      rows.length,
    );

  const resolvedSymbol =
    toStringValue(
      data.resolved_symbol,
      requestedSymbol,
    );

  const source =
    toStringValue(
      data.source,
      "yfinance",
    );

  const available =
    data.available === true;

  const readOnly =
    data.read_only !== false;

  const researchOnly =
    data.research_only !== false;

  const healthSafety =
    health &&
    isRecord(
      health.safety,
    )
      ? health.safety
      : {};

  const executionEnabled =
    health
      ? healthSafety.execution_enabled === true
      : false;

  const databaseWriteEnabled =
    health
      ? healthSafety.database_write_enabled === true
      : false;

  const brokerExecutionEnabled =
    health
      ? healthSafety.broker_execution_enabled === true
      : false;

  /*
   * Hard research-only safety boundary.
   *
   * Market Data must never turn into an
   * execution-capable agent.
   */
  if (
    executionEnabled ||
    databaseWriteEnabled ||
    brokerExecutionEnabled
  ) {
    throw new Error(
      "Market Data safety violation: execution or write capability is enabled.",
    );
  }

  if (!readOnly) {
    throw new Error(
      "Market Data safety violation: research data source is not read-only.",
    );
  }

  if (!researchOnly) {
    throw new Error(
      "Market Data safety violation: research-only flag is not satisfied.",
    );
  }

  if (
    !available ||
    rows.length === 0 ||
    bars <= 0
  ) {
    throw new Error(
      "Market Data returned no usable historical research bars.",
    );
  }

  return {
    agent: "market-data",

    runId:
      context.runId,

    requestedSymbol,

    resolvedSymbol,

    requestedTimeframe,

    mode:
      "READ_ONLY_RESEARCH_MARKET_DATA",

    backend: {
      baseUrl:
        BACKEND_BASE_URL,

      status:
        health
          ? toStringValue(
              health.status,
              "UNKNOWN",
            )
          : "UNKNOWN",

      apiVersion:
        health
          ? toStringValue(
              health.api_version,
              "UNKNOWN",
            )
          : "UNKNOWN",

      generatedAt:
        health
          ? toStringValue(
              health.generated_at,
            )
          : null,

      /*
       * DB availability is reported for
       * observability only.
       *
       * It does NOT block research data.
       */
      databaseAvailable:
        health
          ? health.database_available === true
          : null,
    },

    safety: {
      researchOnly:
        true,

      executionEnabled:
        false,

      databaseWriteEnabled:
        false,

      brokerExecutionEnabled:
        false,

      readOnly:
        true,

      sourceResearchOnly:
        researchOnly,
    },

    historicalData: {
      available: true,

      source,

      requestedSymbol,

      resolvedSymbol,

      interval:
        requestedTimeframe,

      requestedStart:
        toStringValue(
          data.requested_start,
          DEFAULT_START_DATE,
        ),

      requestedEnd:
        toStringValue(
          data.requested_end,
          yesterdayUtc(),
        ),

      start:
        toStringValue(
          data.start,
        ),

      end:
        toStringValue(
          data.end,
        ),

      bars,

      rows,
    },

    dataQuality: {
      bars,

      hasHistoricalData:
        rows.length > 0,

      exactSourceSymbol:
        Boolean(
          resolvedSymbol,
        ),

      source,

      readOnly:
        true,

      researchOnly:
        true,
    },

    /*
     * Keep the raw data available to
     * downstream research agents.
     */
    marketData: {
      symbol:
        resolvedSymbol,

      timeframe:
        requestedTimeframe,

      bars,

      rows,

      source,

      start:
        toStringValue(
          data.start,
        ),

      end:
        toStringValue(
          data.end,
        ),
    },

    /*
     * These fields preserve compatibility
     * with the older Market Data contract.
     */
    symbolData: {
      requestedSymbol,

      resolvedSymbol,

      source,

      bars,

      available: true,
    },

    marketSnapshot: {
      source,
      symbol:
        resolvedSymbol,

      timeframe:
        requestedTimeframe,

      bars,

      start:
        toStringValue(
          data.start,
        ),

      end:
        toStringValue(
          data.end,
        ),
    },

    collectedAt:
      new Date().toISOString(),
  };
}

export function registerMarketDataAgent(): void {
  agentRunner.register(
    "market-data",
    runMarketDataAgent,
  );
}
