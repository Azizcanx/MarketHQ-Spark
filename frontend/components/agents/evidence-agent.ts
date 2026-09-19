import type {
  AgentContext,
} from "./agent-types";

import {
  agentRunner,
} from "./agent-runner";

import marketHQApi from "../../lib/markethq-api";

function isRecord(
  value: unknown
): value is Record<string, unknown> {
  return (
    typeof value === "object" &&
    value !== null &&
    !Array.isArray(value)
  );
}

function getString(
  value: unknown
): string | null {
  return typeof value === "string" &&
    value.trim().length > 0
    ? value
    : null;
}

function findValueRecursive(
  value: unknown,
  keys: string[]
): unknown {
  if (isRecord(value)) {
    for (const key of keys) {
      if (key in value) {
        return value[key];
      }
    }

    for (const child of Object.values(value)) {
      const found =
        findValueRecursive(
          child,
          keys
        );

      if (found !== undefined) {
        return found;
      }
    }
  }

  if (Array.isArray(value)) {
    for (const item of value) {
      const found =
        findValueRecursive(
          item,
          keys
        );

      if (found !== undefined) {
        return found;
      }
    }
  }

  return undefined;
}

export async function runEvidenceAgent(
  context: AgentContext
): Promise<Record<string, unknown>> {
  const evidence =
    await marketHQApi.evidence();

  if (!evidence.success) {
    throw new Error(
      "MarketHQ evidence data could not be loaded."
    );
  }

  const data = evidence.data;

  if (!isRecord(data)) {
    throw new Error(
      "MarketHQ evidence response contains no valid data."
    );
  }

  const previousValidation =
    context.previousResults?.[
      "validation"
    ];

  const previousBacktest =
    context.previousResults?.[
      "backtest"
    ];

  const previousStrategy =
    context.previousResults?.[
      "strategy"
    ];

  const previousMarketData =
    context.previousResults?.[
      "market-data"
    ];

  const validationOutput =
    previousValidation?.output ?? null;

  const backtestOutput =
    previousBacktest?.output ?? null;

  const strategyOutput =
    previousStrategy?.output ?? null;

  const marketDataOutput =
    previousMarketData?.output ?? null;

  const explicitValidationInput =
    context.input?.["validation"] ?? null;

  const explicitBacktestInput =
    context.input?.["backtest"] ?? null;

  const explicitStrategyInput =
    context.input?.["strategy"] ?? null;

  const explicitMarketDataInput =
    context.input?.["market-data"] ?? null;

  const validationInput =
    explicitValidationInput ??
    validationOutput;

  const backtestInput =
    explicitBacktestInput ??
    backtestOutput;

  const strategyInput =
    explicitStrategyInput ??
    strategyOutput;

  const marketDataInput =
    explicitMarketDataInput ??
    marketDataOutput;

  const strategyId =
    getString(
      context.strategyId
    ) ??
    getString(
      findValueRecursive(
        validationOutput,
        [
          "strategyId",
          "strategy_id",
        ]
      )
    ) ??
    getString(
      findValueRecursive(
        backtestOutput,
        [
          "strategyId",
          "strategy_id",
        ]
      )
    ) ??
    getString(
      findValueRecursive(
        strategyOutput,
        [
          "strategyId",
          "strategy_id",
        ]
      )
    ) ??
    getString(
      findValueRecursive(
        data,
        [
          "strategyId",
          "strategy_id",
        ]
      )
    ) ??
    null;

  const strategyName =
    getString(
      findValueRecursive(
        validationOutput,
        [
          "strategyName",
          "strategy_name",
        ]
      )
    ) ??
    getString(
      findValueRecursive(
        backtestOutput,
        [
          "strategyName",
          "strategy_name",
        ]
      )
    ) ??
    getString(
      findValueRecursive(
        strategyOutput,
        [
          "strategyName",
          "strategy_name",
        ]
      )
    ) ??
    getString(
      findValueRecursive(
        data,
        [
          "strategyName",
          "strategy_name",
        ]
      )
    ) ??
    null;

  return {
    agent: "evidence",
    runId: context.runId,

    strategyId,

    strategyName,

    evidenceData: data,

    validationInput,

    backtestInput,

    strategyInput,

    marketDataInput,

    previousAgentState: {
      validationAvailable:
        Boolean(validationOutput),

      backtestAvailable:
        Boolean(backtestOutput),

      strategyAvailable:
        Boolean(strategyOutput),

      marketDataAvailable:
        Boolean(marketDataOutput),

      validationRunId:
        previousValidation?.runId ?? null,

      backtestRunId:
        previousBacktest?.runId ?? null,

      strategyRunId:
        previousStrategy?.runId ?? null,

      marketDataRunId:
        previousMarketData?.runId ?? null,

      validationSuccess:
        previousValidation?.success ?? false,

      backtestSuccess:
        previousBacktest?.success ?? false,

      strategySuccess:
        previousStrategy?.success ?? false,

      marketDataSuccess:
        previousMarketData?.success ?? false,
    },

    researchContext: {
      symbol:
        context.symbol ?? null,

      timeframe:
        context.timeframe ?? null,

      backendEvidenceLoaded:
        evidence.success,

      evidenceDataAvailable:
        Boolean(data),
    },

    mode:
      "READ_ONLY_EVIDENCE",

    note:
      "Bu ajan mevcut MarketHQ araştırma kanıtlarını okur ve sonraki Brain katmanına aktarılabilecek hale getirir. Veritabanına yazmaz ve broker işlemi gerçekleştirmez.",

    collectedAt:
      new Date().toISOString(),
  };
}

export function registerEvidenceAgent(): void {
  agentRunner.register(
    "evidence",
    runEvidenceAgent
  );
}
