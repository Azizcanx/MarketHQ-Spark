import type { AgentContext } from "./agent-types";

type UnknownRecord = Record<string, unknown>;

export interface ImportedStrategyV1 {
  schemaVersion: "MARKETHQ_STRATEGY_V1";
  strategyId: string;
  name: string;
  ruleDefinition: unknown;
  parameters: UnknownRecord;
  signalConfig: UnknownRecord;
  riskConfig: UnknownRecord;
  supportedMarkets: string[];
  supportedTimeframes: string[];
  source: UnknownRecord;
  provenance: UnknownRecord;
}

function isRecord(value: unknown): value is UnknownRecord {
  return Boolean(
    value &&
      typeof value === "object" &&
      !Array.isArray(value),
  );
}

function asString(value: unknown, fallback = ""): string {
  return typeof value === "string" && value.trim()
    ? value.trim()
    : fallback;
}

function asRecord(value: unknown): UnknownRecord {
  return isRecord(value) ? value : {};
}

function asStringArray(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  return value
    .map((item) => asString(item))
    .filter(Boolean);
}

/**
 * Research-only importer.
 * Imported strategies are treated as DATA, never executed as code.
 */
export function resolveImportedStrategy(
  context: AgentContext,
): ImportedStrategyV1 | null {
  const input = isRecord(context.input) ? context.input : {};

  const candidate =
    input.strategyDefinition ??
    input.importedStrategy ??
    input.strategyImport;

  if (!isRecord(candidate)) return null;

  const schemaVersion = asString(
    candidate.schemaVersion ?? candidate.schema_version,
  );

  if (
    schemaVersion &&
    schemaVersion !== "MARKETHQ_STRATEGY_V1"
  ) {
    return null;
  }

  const strategyId = asString(
    candidate.strategyId ?? candidate.strategy_id,
    context.strategyId ?? "",
  );

  const name = asString(
    candidate.name ??
      candidate.strategyName ??
      candidate.strategy_name,
  );

  const ruleDefinition =
    candidate.ruleDefinition ??
    candidate.rule_definition;

  if (!strategyId || !name || ruleDefinition === undefined) {
    return null;
  }

  return {
    schemaVersion: "MARKETHQ_STRATEGY_V1",
    strategyId,
    name,
    ruleDefinition,
    parameters: asRecord(candidate.parameters),
    signalConfig: asRecord(
      candidate.signalConfig ?? candidate.signal_config,
    ),
    riskConfig: asRecord(
      candidate.riskConfig ?? candidate.risk_config,
    ),
    supportedMarkets: asStringArray(
      candidate.supportedMarkets ??
        candidate.supported_markets,
    ),
    supportedTimeframes: asStringArray(
      candidate.supportedTimeframes ??
        candidate.supported_timeframes,
    ),
    source: asRecord(candidate.source),
    provenance: asRecord(candidate.provenance),
  };
}
