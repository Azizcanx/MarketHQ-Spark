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

function findStringRecursive(
  value: unknown,
  keys: string[]
): string | null {
  if (isRecord(value)) {
    for (const key of keys) {
      const directValue =
        getString(value[key]);

      if (directValue) {
        return directValue;
      }
    }

    for (const child of Object.values(value)) {
      const found =
        findStringRecursive(
          child,
          keys
        );

      if (found) {
        return found;
      }
    }
  }

  if (Array.isArray(value)) {
    for (const item of value) {
      const found =
        findStringRecursive(
          item,
          keys
        );

      if (found) {
        return found;
      }
    }
  }

  return null;
}

export async function runBacktestAgent(
  context: AgentContext
): Promise<Record<string, unknown>> {
  const pipeline =
    await marketHQApi.pipeline();

  if (!pipeline.success) {
    throw new Error(
      "MarketHQ pipeline data could not be loaded."
    );
  }

  const trades =
    await marketHQApi.trades();

  if (!trades.success) {
    throw new Error(
      "MarketHQ backtest trade data could not be loaded."
    );
  }

  const pipelineData =
    pipeline.data ?? null;

  const backtestEvidence =
    trades.data ?? null;

  const previousStrategy =
    context.previousResults?.[
      "strategy"
    ];

  const previousMarketData =
    context.previousResults?.[
      "market-data"
    ];

  const strategyOutput =
    previousStrategy?.output ?? null;

  const marketDataOutput =
    previousMarketData?.output ?? null;

  const explicitStrategyInput =
    context.input?.["strategy"] ?? null;

  const explicitMarketDataInput =
    context.input?.["market-data"] ?? null;

  const strategyInput =
    explicitStrategyInput ??
    strategyOutput;

  const marketDataInput =
    explicitMarketDataInput ??
    marketDataOutput;

  const strategyId =
    findStringRecursive(
      strategyOutput,
      [
        "strategyId",
        "strategy_id",
      ]
    ) ??
    findStringRecursive(
      pipelineData,
      [
        "strategyId",
        "strategy_id",
      ]
    ) ??
    context.strategyId ??
    null;

  const strategyName =
    findStringRecursive(
      strategyOutput,
      [
        "strategyName",
        "strategy_name",
      ]
    ) ??
    findStringRecursive(
      pipelineData,
      [
        "strategyName",
        "strategy_name",
      ]
    ) ??
    null;

  return {
    agent: "backtest",
    runId: context.runId,

    strategyId,

    strategyName,

    pipelineData,

    backtestEvidence,

    strategyInput,

    marketDataInput,

    previousAgentState: {
      strategyAvailable:
        Boolean(strategyOutput),

      marketDataAvailable:
        Boolean(marketDataOutput),

      strategyRunId:
        previousStrategy?.runId ?? null,

      marketDataRunId:
        previousMarketData?.runId ?? null,

      strategySuccess:
        previousStrategy?.success ?? false,

      marketDataSuccess:
        previousMarketData?.success ?? false,
    },

    mode:
      "READ_ONLY_BACKTEST_EVIDENCE",

    researchContext: {
      symbol:
        context.symbol ?? null,

      timeframe:
        context.timeframe ?? null,

      backendPipelineLoaded:
        pipeline.success,

      backendTradesLoaded:
        trades.success,
    },

    note:
      "Bu ajan mevcut Backtest Engine çıktılarının araştırma amaçlı okunması ve analiz edilmesi için çalışır. Yeni backtest çalıştırmaz ve veri yazmaz.",

    collectedAt:
      new Date().toISOString(),
  };
}

export function registerBacktestAgent(): void {
  agentRunner.register(
    "backtest",
    runBacktestAgent
  );
}
