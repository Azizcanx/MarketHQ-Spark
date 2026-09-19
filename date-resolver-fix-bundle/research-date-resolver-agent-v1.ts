import type { AgentContext } from "./agent-types";
import { agentRunner } from "./agent-runner";

type UnknownRecord = Record<string, unknown>;

const BACKEND_BASE_URL =
  process.env.MARKETHQ_BACKEND_URL?.trim() ||
  "http://127.0.0.1:8010";

const DEFAULT_INTERVAL = "1d";
const DEFAULT_LOOKBACK_BARS = 756;
const DEFAULT_TRAIN_BARS = 504;
const DEFAULT_VALIDATION_BARS = 126;
const DEFAULT_INDEPENDENT_BARS = 126;

function isRecord(value: unknown): value is UnknownRecord {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function toStringValue(value: unknown, fallback = ""): string {
  if (typeof value === "string" && value.trim()) return value.trim();
  if (typeof value === "number" && Number.isFinite(value)) return String(value);
  return fallback;
}

function toNumber(value: unknown, fallback: number): number {
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (typeof value === "string" && value.trim()) {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : fallback;
  }
  return fallback;
}

function firstRecord(...values: unknown[]): UnknownRecord {
  for (const value of values) {
    if (isRecord(value)) return value;
  }
  return {};
}

function parseIsoDate(value: unknown): string | null {
  const text = toStringValue(value);
  if (!text) return null;
  const match = text.match(/^(\d{4}-\d{2}-\d{2})/);
  return match ? match[1] : null;
}

function yesterdayUtc(): string {
  const now = new Date();
  now.setUTCDate(now.getUTCDate() - 1);
  return now.toISOString().slice(0, 10);
}

function normalizeRows(value: unknown): Array<{ timestamp: string }> {
  if (!Array.isArray(value)) return [];

  return value
    .map((row) => {
      if (!isRecord(row)) return null;
      const timestamp = parseIsoDate(row.timestamp ?? row.date);
      return timestamp ? { timestamp } : null;
    })
    .filter((row): row is { timestamp: string } => row !== null)
    .sort((a, b) => a.timestamp.localeCompare(b.timestamp));
}

async function fetchHistoricalRows(
  symbol: string,
  interval: string,
): Promise<{
  ok: boolean;
  rows: Array<{ timestamp: string }>;
  source: string;
  error?: string;
}> {
  const end = yesterdayUtc();
  const url = new URL(`${BACKEND_BASE_URL}/api/research-data`);
  url.searchParams.set("symbol", symbol);
  url.searchParams.set("start", "2000-01-01");
  url.searchParams.set("end", end);
  url.searchParams.set("interval", interval);
  url.searchParams.set("limit", "5000");

  try {
    const response = await fetch(url.toString(), {
      method: "GET",
      headers: { Accept: "application/json" },
      cache: "no-store",
    });

    const body = await response.json().catch(() => null);
    if (!response.ok || !isRecord(body) || body.success !== true) {
      const error = isRecord(body)
        ? toStringValue(body.error, `Research data HTTP ${response.status}`)
        : `Research data HTTP ${response.status}`;
      return { ok: false, rows: [], source: "research-data", error };
    }

    const data = isRecord(body.data) ? body.data : {};
    const rows = normalizeRows(data.rows);
    return {
      ok: rows.length > 0,
      rows,
      source: toStringValue(data.source, "yfinance"),
      error: rows.length > 0 ? undefined : "Historical data returned no usable rows.",
    };
  } catch (error) {
    return {
      ok: false,
      rows: [],
      source: "research-data",
      error: error instanceof Error ? error.message : "Historical data request failed.",
    };
  }
}

function extractQueueOutput(context: AgentContext): UnknownRecord {
  const output = context.previousResults?.["research-queue"]?.output;
  return isRecord(output) ? output : {};
}

function extractQueueTask(context: AgentContext): UnknownRecord {
  const queue = firstRecord(extractQueueOutput(context).queue);
  return firstRecord(queue.selectedTask);
}

function extractQueueDateScope(context: AgentContext): UnknownRecord {
  const output = extractQueueOutput(context);
  return firstRecord(
    output.dateScope,
    extractQueueTask(context).dateScope,
    extractQueueTask(context).metadata,
  );
}

function extractDecisionOutput(context: AgentContext): UnknownRecord {
  const output = context.previousResults?.["research-decision"]?.output;
  return isRecord(output) ? output : {};
}

function extractStrategyOutput(context: AgentContext): UnknownRecord {
  const output = context.previousResults?.["strategy"]?.output;
  return isRecord(output) ? output : {};
}

function extractExplicitScope(context: AgentContext): UnknownRecord {
  return firstRecord(
    context.input?.dateScope,
    extractQueueDateScope(context),
    context.input?.researchDateScope,
    context.input?.research_dates,
  );
}

function resolveSymbol(context: AgentContext): string {
  const queueTask = extractQueueTask(context);
  const metadata = firstRecord(queueTask.metadata);
  return (
    toStringValue(context.symbol) ||
    toStringValue(queueTask.symbol) ||
    toStringValue(metadata.symbol ?? metadata.ticker) ||
    ""
  ).toUpperCase();
}

function resolveTimeframe(context: AgentContext): string {
  const queueTask = extractQueueTask(context);
  const metadata = firstRecord(queueTask.metadata);
  return (
    toStringValue(context.timeframe) ||
    toStringValue(queueTask.timeframe) ||
    toStringValue(metadata.timeframe ?? metadata.interval) ||
    DEFAULT_INTERVAL
  ).toLowerCase();
}

function findExplicitPair(
  scope: UnknownRecord,
  startKeys: string[],
  endKeys: string[],
): { startDate: string | null; endDate: string | null } {
  let startDate: string | null = null;
  let endDate: string | null = null;

  for (const key of startKeys) {
    startDate = parseIsoDate(scope[key]);
    if (startDate) break;
  }

  for (const key of endKeys) {
    endDate = parseIsoDate(scope[key]);
    if (endDate) break;
  }

  return { startDate, endDate };
}

function validateScope(
  startDate: string | null,
  endDate: string | null,
  validationStartDate: string | null,
  validationEndDate: string | null,
  holdoutStartDate: string | null,
  holdoutEndDate: string | null,
  independentStartDate: string | null,
  independentEndDate: string | null,
): boolean {
  const values = [
    startDate,
    endDate,
    validationStartDate,
    validationEndDate,
    holdoutStartDate,
    holdoutEndDate,
    independentStartDate,
    independentEndDate,
  ];

  if (values.some((value) => !value)) return false;
  if (
    startDate! >= endDate! ||
    validationStartDate! >= validationEndDate! ||
    holdoutStartDate! >= holdoutEndDate! ||
    independentStartDate! >= independentEndDate!
  ) {
    return false;
  }

  return (
    startDate! <= validationStartDate! &&
    validationEndDate! <= endDate! &&
    holdoutStartDate! <= endDate! &&
    independentStartDate! <= independentEndDate!
  );
}

function buildResolvedScopeFromRows(
  rows: Array<{ timestamp: string }>,
  lookbackBars: number,
  trainBars: number,
  validationBars: number,
  independentBars: number,
) {
  if (rows.length < lookbackBars) return null;

  const slice = rows.slice(-lookbackBars);
  const train = slice.slice(0, trainBars);
  const validation = slice.slice(trainBars, trainBars + validationBars);
  const independent = slice.slice(trainBars + validationBars);

  if (
    train.length < trainBars ||
    validation.length < validationBars ||
    independent.length < independentBars
  ) {
    return null;
  }

  const startDate = train[0].timestamp;
  const endDate = slice[slice.length - 1].timestamp;
  const validationStartDate = validation[0].timestamp;
  const validationEndDate = validation[validation.length - 1].timestamp;
  const independentStartDate = independent[0].timestamp;
  const independentEndDate = independent[independent.length - 1].timestamp;

  return {
    startDate,
    endDate,
    validationStartDate,
    validationEndDate,
    holdoutStartDate: independentStartDate,
    holdoutEndDate: independentEndDate,
    independentSliceStartDate: independentStartDate,
    independentSliceEndDate: independentEndDate,
    bars: slice.length,
    trainBars: train.length,
    validationBars: validation.length,
    holdoutBars: independent.length,
    selectionStatus: "RESOLVED" as const,
    selectionSource: "research-data.availability:last_bars",
    independenceStatus: "CHRONOLOGICAL_HOLDOUT_UNVERIFIED_AGAINST_PRIOR_RUNS",
  };
}

export async function runResearchDateResolverAgent(
  context: AgentContext,
): Promise<Record<string, unknown>> {
  const strategy = extractStrategyOutput(context);
  const queueTask = extractQueueTask(context);
  const decision = extractDecisionOutput(context);
  const explicitScope = extractExplicitScope(context);

  const strategyId =
    toStringValue(context.strategyId) ||
    toStringValue(strategy.strategyId ?? strategy.strategy_id) ||
    "UNKNOWN_STRATEGY";
  const symbol = resolveSymbol(context);
  const timeframe = resolveTimeframe(context);
  const market =
    toStringValue(context.input?.market) ||
    toStringValue(queueTask.market) ||
    toStringValue(firstRecord(queueTask.metadata).market) ||
    "";

  if (!symbol) {
    return {
      agent: "research-date-resolver",
      runId: context.runId,
      status: "BLOCKED",
      reason: "Symbol could not be resolved from Research Queue or context.",
      dateScope: {
        selectionStatus: "BLOCKED",
        selectionSource: "none",
        startDate: null,
        endDate: null,
        validationStartDate: null,
        validationEndDate: null,
        holdoutStartDate: null,
        holdoutEndDate: null,
        independentSliceStartDate: null,
        independentSliceEndDate: null,
        exactDatesProvided: false,
        independentSliceProvided: false,
        independenceStatus: "BLOCKED_SYMBOL",
      },
      safety: {
        researchOnly: true,
        executionEnabled: false,
        databaseWriteEnabled: false,
        brokerExecutionEnabled: false,
      },
      mode: "READ_ONLY_RESEARCH_DATE_RESOLUTION",
    };
  }

  const explicit = findExplicitPair(
    explicitScope,
    ["startDate", "start", "historyStart", "history_start"],
    ["endDate", "end", "historyEnd", "history_end"],
  );
  const explicitValidation = findExplicitPair(
    explicitScope,
    ["validationStartDate", "validation_start"],
    ["validationEndDate", "validation_end"],
  );
  const explicitIndependent = findExplicitPair(
    explicitScope,
    ["independentSliceStartDate", "independent_start"],
    ["independentSliceEndDate", "independent_end"],
  );

  const explicitHoldout = findExplicitPair(
    explicitScope,
    ["holdoutStartDate", "holdout_start"],
    ["holdoutEndDate", "holdout_end"],
  );

  if (
    validateScope(
      explicit.startDate,
      explicit.endDate,
      explicitValidation.startDate,
      explicitValidation.endDate,
      explicitHoldout.startDate || explicitIndependent.startDate,
      explicitHoldout.endDate || explicitIndependent.endDate,
      explicitIndependent.startDate,
      explicitIndependent.endDate,
    )
  ) {
    return {
      agent: "research-date-resolver",
      runId: context.runId,
      strategyId,
      symbol,
      timeframe,
      market,
      dateScope: {
        selectionStatus: "RESOLVED",
        selectionSource: "explicit_research_scope",
        startDate: explicit.startDate,
        endDate: explicit.endDate,
        validationStartDate: explicitValidation.startDate,
        validationEndDate: explicitValidation.endDate,
        holdoutStartDate:
          explicitHoldout.startDate || explicitIndependent.startDate,
        holdoutEndDate:
          explicitHoldout.endDate || explicitIndependent.endDate,
        independentSliceStartDate: explicitIndependent.startDate,
        independentSliceEndDate: explicitIndependent.endDate,
        exactDatesProvided: true,
        independentSliceProvided: true,
        generatedByResolver: false,
        independenceStatus: "DECLARED_BY_RESEARCH_SCOPE",
        notes: [
          "Explicit date scope was supplied by the research context.",
          "Resolver did not infer or optimize dates from strategy results.",
        ],
      },
      sourceContext: {
        queueTaskId: queueTask.id ?? queueTask.queue_id ?? null,
        decision: toStringValue(decision.decision),
        action: toStringValue(decision.action),
      },
      safety: {
        researchOnly: true,
        executionEnabled: false,
        databaseWriteEnabled: false,
        brokerExecutionEnabled: false,
      },
      mode: "READ_ONLY_RESEARCH_DATE_RESOLUTION",
      calculatedAt: new Date().toISOString(),
    };
  }

  if (timeframe !== DEFAULT_INTERVAL) {
    return {
      agent: "research-date-resolver",
      runId: context.runId,
      strategyId,
      symbol,
      timeframe,
      market,
      status: "BLOCKED",
      reason: "Resolver v1 intentionally supports daily historical data only.",
      dateScope: {
        selectionStatus: "BLOCKED",
        selectionSource: "none",
        exactDatesProvided: false,
        independentSliceProvided: false,
        independenceStatus: "BLOCKED_INTERVAL",
      },
      safety: {
        researchOnly: true,
        executionEnabled: false,
        databaseWriteEnabled: false,
        brokerExecutionEnabled: false,
      },
      mode: "READ_ONLY_RESEARCH_DATE_RESOLUTION",
    };
  }

  const input = isRecord(context.input) ? context.input : {};
  const datePolicy = firstRecord(input.datePolicy);

  const lookbackBars = Math.max(
    DEFAULT_LOOKBACK_BARS,
    Math.floor(
      toNumber(datePolicy.lookbackBars, DEFAULT_LOOKBACK_BARS),
    ),
  );
  const trainBars = Math.max(
    DEFAULT_TRAIN_BARS,
    Math.floor(
      toNumber(datePolicy.trainBars, DEFAULT_TRAIN_BARS),
    ),
  );
  const validationBars = Math.max(
    DEFAULT_VALIDATION_BARS,
    Math.floor(
      toNumber(datePolicy.validationBars, DEFAULT_VALIDATION_BARS),
    ),
  );
  const independentBars = Math.max(
    DEFAULT_INDEPENDENT_BARS,
    Math.floor(
      toNumber(datePolicy.independentBars, DEFAULT_INDEPENDENT_BARS),
    ),
  );

  const resolvedHistorical = await fetchHistoricalRows(symbol, timeframe);

  if (!resolvedHistorical.ok) {
    return {
      agent: "research-date-resolver",
      runId: context.runId,
      strategyId,
      symbol,
      timeframe,
      market,
      status: "BLOCKED",
      reason:
        resolvedHistorical.error ||
        "Historical availability could not be resolved.",
      dateScope: {
        selectionStatus: "BLOCKED",
        selectionSource: resolvedHistorical.source,
        startDate: null,
        endDate: null,
        validationStartDate: null,
        validationEndDate: null,
        holdoutStartDate: null,
        holdoutEndDate: null,
        independentSliceStartDate: null,
        independentSliceEndDate: null,
        exactDatesProvided: false,
        independentSliceProvided: false,
        generatedByResolver: false,
        independenceStatus: "BLOCKED_DATA_AVAILABILITY",
      },
      dataAvailability: {
        source: resolvedHistorical.source,
        usableBars: resolvedHistorical.rows.length,
        requiredBars: lookbackBars,
      },
      safety: {
        researchOnly: true,
        executionEnabled: false,
        databaseWriteEnabled: false,
        brokerExecutionEnabled: false,
      },
      mode: "READ_ONLY_RESEARCH_DATE_RESOLUTION",
      calculatedAt: new Date().toISOString(),
    };
  }

  const scope = buildResolvedScopeFromRows(
    resolvedHistorical.rows,
    lookbackBars,
    trainBars,
    validationBars,
    independentBars,
  );

  if (!scope) {
    return {
      agent: "research-date-resolver",
      runId: context.runId,
      strategyId,
      symbol,
      timeframe,
      market,
      status: "BLOCKED",
      reason: "Historical data does not contain enough daily bars for the frozen resolver policy.",
      dateScope: {
        selectionStatus: "BLOCKED",
        selectionSource: "research-data.availability:last_bars",
        startDate: null,
        endDate: null,
        validationStartDate: null,
        validationEndDate: null,
        holdoutStartDate: null,
        holdoutEndDate: null,
        independentSliceStartDate: null,
        independentSliceEndDate: null,
        exactDatesProvided: false,
        independentSliceProvided: false,
        generatedByResolver: false,
        independenceStatus: "BLOCKED_INSUFFICIENT_HISTORY",
      },
      dataAvailability: {
        source: resolvedHistorical.source,
        usableBars: resolvedHistorical.rows.length,
        requiredBars: lookbackBars,
      },
      policy: {
        lookbackBars,
        trainBars,
        validationBars,
        independentBars,
        selectionRule:
          "Use the latest available completed daily bars; never inspect strategy performance when selecting dates.",
      },
      safety: {
        researchOnly: true,
        executionEnabled: false,
        databaseWriteEnabled: false,
        brokerExecutionEnabled: false,
      },
      mode: "READ_ONLY_RESEARCH_DATE_RESOLUTION",
      calculatedAt: new Date().toISOString(),
    };
  }

  return {
    agent: "research-date-resolver",
    runId: context.runId,
    strategyId,
    symbol,
    timeframe,
    market,
    status: "READY",
    dateScope: {
      ...scope,
      exactDatesProvided: true,
      independentSliceProvided: true,
      generatedByResolver: true,
      notes: [
        `Frozen chronological policy used ${scope.bars} completed daily bars.`,
        "Dates were selected from data availability only; strategy performance was not inspected.",
        "The independent slice is a chronological holdout and is not yet proven independent of prior historical strategy-selection activity.",
      ],
    },
    dataAvailability: {
      source: resolvedHistorical.source,
      usableBars: resolvedHistorical.rows.length,
      resolvedBars: scope.bars,
      firstAvailableDate: resolvedHistorical.rows[0]?.timestamp ?? null,
      lastAvailableDate:
        resolvedHistorical.rows[resolvedHistorical.rows.length - 1]?.timestamp ?? null,
    },
    policy: {
      lookbackBars,
      trainBars,
      validationBars,
      independentBars,
      selectionRule:
        "Use the latest available completed daily bars; never inspect strategy performance when selecting dates.",
    },
    sourceContext: {
      queueTaskId: queueTask.id ?? queueTask.queue_id ?? null,
      decision: toStringValue(decision.decision),
      action: toStringValue(decision.action),
      researchQuestion:
        toStringValue(decision.nextResearchQuestion) ||
        toStringValue(queueTask.question),
    },
    safety: {
      researchOnly: true,
      executionEnabled: false,
      databaseWriteEnabled: false,
      brokerExecutionEnabled: false,
    },
    mode: "READ_ONLY_RESEARCH_DATE_RESOLUTION",
    calculatedAt: new Date().toISOString(),
  };
}

export function registerResearchDateResolverAgent(): void {
  agentRunner.register(
    "research-date-resolver",
    runResearchDateResolverAgent,
  );
}


