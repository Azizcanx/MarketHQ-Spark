import type {
  AgentContext,
} from "./agent-types";

import {
  analyzeTrendAndRegime,
} from "./trend-regime-engine";

import {
  agentRunner,
} from "./agent-runner";

type UnknownRecord =
  Record<string, unknown>;

function isRecord(
  value: unknown,
): value is UnknownRecord {
  return (
    Boolean(value) &&
    typeof value === "object" &&
    !Array.isArray(value)
  );
}

function getAgentOutput(
  context: AgentContext,
  agentId: string,
): UnknownRecord {
  const result =
    context.previousResults?.[
      agentId as keyof typeof context.previousResults
    ];

  if (
    result &&
    isRecord(result.output)
  ) {
    return result.output;
  }

  return {};
}

function parseNumber(
  value: unknown,
): number | null {
  const numberValue =
    typeof value === "number"
      ? value
      : Number(value);

  return Number.isFinite(numberValue)
    ? numberValue
    : null;
}

function normalizeRows(
  value: unknown,
): UnknownRecord[] {
  if (!Array.isArray(value)) {
    return [];
  }

  const rows: UnknownRecord[] = [];

  for (const row of value) {
    if (!isRecord(row)) {
      continue;
    }

    const timestamp =
      row.timestamp ??
      row.date ??
      row.datetime;

    const open = parseNumber(row.open);
    const high = parseNumber(row.high);
    const low = parseNumber(row.low);
    const close = parseNumber(row.close);
    const volume =
      parseNumber(row.volume) ?? 0;

    if (
      timestamp === undefined ||
      open === null ||
      high === null ||
      low === null ||
      close === null
    ) {
      continue;
    }

    rows.push({
      timestamp: String(timestamp),
      open,
      high,
      low,
      close,
      volume,
    });
  }

  rows.sort(
    (a, b) =>
      String(a.timestamp).localeCompare(
        String(b.timestamp),
      ),
  );

  return rows;
}

function extractRowsFromCandidates(
  candidates: unknown[],
): UnknownRecord[] {
  for (const candidate of candidates) {
    if (Array.isArray(candidate)) {
      const rows =
        normalizeRows(candidate);

      if (rows.length > 0) {
        return rows;
      }
    }

    if (isRecord(candidate)) {
      const nestedCandidates = [
        candidate.rows,
        candidate.data,
        candidate.records,
        candidate.candles,
        candidate.history,
        candidate.prices,
      ];

      for (
        const nested of nestedCandidates
      ) {
        if (!Array.isArray(nested)) {
          continue;
        }

        const rows =
          normalizeRows(nested);

        if (rows.length > 0) {
          return rows;
        }
      }
    }
  }

  return [];
}

function resolveInlineMarketRows(
  context: AgentContext,
): UnknownRecord[] {
  const marketData =
    getAgentOutput(
      context,
      "market-data",
    );

  const input =
    isRecord(context.input)
      ? context.input
      : {};

  return extractRowsFromCandidates([
    marketData.marketData,
    marketData.marketSnapshot,
    marketData.snapshot,
    marketData.data,
    marketData.rows,
    input.marketData,
    input.marketSnapshot,
    input.snapshot,
    input.data,
    input.rows,
  ]);
}

function getBackendBaseUrl(): string {
  return (
    process.env.MARKETHQ_BACKEND_URL ??
    "http://127.0.0.1:8010"
  ).replace(/\/+$/, "");
}

function getRequestedSymbol(
  context: AgentContext,
): string {
  return (
    context.symbol ??
    (
      isRecord(context.input)
        ? String(
            context.input.symbol ?? "",
          )
        : ""
    )
  )
    .trim()
    .toUpperCase();
}

function getRequestedTimeframe(
  context: AgentContext,
): string {
  return (
    context.timeframe ??
    (
      isRecord(context.input)
        ? String(
            context.input.timeframe ?? "1d",
          )
        : "1d"
    )
  )
    .trim()
    .toLowerCase();
}

function yesterdayUtc(): string {
  const date = new Date();

  date.setUTCHours(
    0,
    0,
    0,
    0,
  );

  date.setUTCDate(
    date.getUTCDate() - 1,
  );

  return date
    .toISOString()
    .slice(0, 10);
}

async function fetchHistoricalRows(
  context: AgentContext,
): Promise<{
  rows: UnknownRecord[];
  source: string;
}> {
  const symbol =
    getRequestedSymbol(context);

  const timeframe =
    getRequestedTimeframe(context);

  if (!symbol) {
    throw new Error(
      "Trend + Market Regime requires a symbol.",
    );
  }

  const url =
    new URL(
      `${getBackendBaseUrl()}/api/research-data`,
    );

  url.searchParams.set(
    "symbol",
    symbol,
  );
  url.searchParams.set(
    "start",
    "2000-01-01",
  );
  url.searchParams.set(
    "end",
    yesterdayUtc(),
  );
  url.searchParams.set(
    "interval",
    timeframe,
  );
  url.searchParams.set(
    "limit",
    "5000",
  );

  let response: Response;

  try {
    response = await fetch(
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
  } catch (error) {
    throw new Error(
      `Trend + Market Regime backend request failed: ${
        error instanceof Error
          ? error.message
          : String(error)
      }`,
    );
  }

  const body =
    await response
      .json()
      .catch(() => null);

  if (
    !response.ok ||
    !isRecord(body) ||
    body.success !== true
  ) {
    const backendError =
      isRecord(body)
        ? String(
            body.error ??
              `HTTP ${response.status}`,
          )
        : `HTTP ${response.status}`;

    throw new Error(
      `Trend + Market Regime historical data unavailable for ${symbol} ${timeframe}: ${backendError}`,
    );
  }

  const data =
    isRecord(body.data)
      ? body.data
      : {};

  const rows =
    normalizeRows(data.rows);

  if (rows.length === 0) {
    throw new Error(
      `Trend + Market Regime received no usable OHLCV rows for ${symbol} ${timeframe}.`,
    );
  }

  return {
    rows,
    source:
      typeof data.source === "string"
        ? data.source
        : "research-data",
  };
}

async function resolveMarketRows(
  context: AgentContext,
): Promise<{
  rows: UnknownRecord[];
  source: string;
}> {
  const inlineRows =
    resolveInlineMarketRows(context);

  if (inlineRows.length > 0) {
    return {
      rows: inlineRows,
      source: "market-data",
    };
  }

  return fetchHistoricalRows(
    context,
  );
}

export async function runTrendRegimeAgent(
  context: AgentContext,
): Promise<Record<string, unknown>> {
  const startedAt =
    new Date().toISOString();

  const marketRows =
    await resolveMarketRows(
      context,
    );

  const result =
    analyzeTrendAndRegime(
      marketRows.rows,
      {
        symbol:
          context.symbol ??
          null,
        timeframe:
          context.timeframe ??
          null,
      },
    );

  return {
    agent:
      "trend-regime",
    runId:
      context.runId,
    status:
      result.status,
    startedAt,
    completedAt:
      new Date().toISOString(),

    symbol:
      result.symbol,
    timeframe:
      result.timeframe,

    trend:
      result.snapshot.trendDirection,

    trendDirection:
      result.snapshot.trendDirection,

    trendStrength:
      result.snapshot.trendStrength,

    momentum:
      result.snapshot.momentum,

    momentumScore:
      result.snapshot.momentumScore,

    volatility:
      result.snapshot.volatility,

    volatilityScore:
      result.snapshot.volatilityScore,

    marketRegime:
      result.snapshot.marketRegime,

    evidenceScore:
      result.snapshot.evidenceScore,

    confidence:
      result.snapshot.confidence,

    indicators:
      result.snapshot.indicators,

    evidence:
      result.snapshot.evidence,

    warnings:
      result.snapshot.warnings,

    barsUsed:
      result.barsUsed,

    minimumBarsRequired:
      result.minimumBarsRequired,

    snapshot:
      result.snapshot,

    engine:
      result.engine,

    safety: {
      researchOnly: true,
      executionEnabled: false,
      databaseWriteEnabled: false,
      brokerExecutionEnabled: false,
      liveTradingAllowed: false,
      liveExecutionAllowed: false,
    },

    researchOnly: true,
    lookAheadSafe:
      result.lookAheadSafe,

    source:
      marketRows.source,
  };
}

export function registerTrendRegimeAgent(): void {
  agentRunner.register(
    "trend-regime",
    runTrendRegimeAgent,
  );
}

