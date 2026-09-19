import type {
  AgentContext,
} from "./agent-types";

import {
  agentRunner,
} from "./agent-runner";


import { resolveImportedStrategy } from "./strategy-importer-v1";
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

export async function runStrategyAgent(
  context: AgentContext
): Promise<Record<string, unknown>> {
    const importedStrategy = resolveImportedStrategy(context);

const strategy = await marketHQApi.strategy();

  if (!strategy.success) {
    throw new Error(
      "MarketHQ strategy data could not be loaded."
    );
  }

  const data = strategy.data;

  if (!isRecord(data)) {
    throw new Error(
      "MarketHQ strategy response contains no valid data."
    );
  }

  const strategyData = data;

  const pipeline = isRecord(
    strategyData.pipeline
  )
    ? strategyData.pipeline
    : null;

  const pipelineStrategy = pipeline &&
    isRecord(pipeline.strategy)
    ? pipeline.strategy
    : null;

  const nestedStrategy = pipelineStrategy &&
    isRecord(pipelineStrategy.strategy)
    ? pipelineStrategy.strategy
    : null;

  const consolidation =
    strategyData.consolidation ?? null;

  const learning =
    strategyData.learning ?? null;

  const finalDecision =
    strategyData.final_decision ?? null;

  const strategyId =
    getString(
      strategyData.strategy_id
    ) ??
    getString(
      pipelineStrategy?.strategy_id
    ) ??
    getString(
      nestedStrategy?.strategy_id
    ) ??
    context.strategyId ??
    null;

  const strategyName =
    getString(
      strategyData.strategy_name
    ) ??
    getString(
      pipelineStrategy?.strategy_name
    ) ??
    getString(
      nestedStrategy?.strategy_name
    ) ??
    null;

  const previousMarketData =
    context.previousResults?.[
      "market-data"
    ];

  const previousMarketDataOutput =
    previousMarketData?.output ?? null;

  const explicitMarketDataInput =
    context.input?.["market-data"] ?? null;

  const marketDataInput =
    explicitMarketDataInput ??
    previousMarketDataOutput;

  return {
    agent: "strategy",
    importedStrategy,
    runId: context.runId,

    strategyId,

    strategyName,

    strategy: {
      strategyId,
      strategyName,
      pipeline,
      pipelineStrategy,
      consolidation,
      learning,
      finalDecision,
    },

    marketDataInput,

    researchContext: {
      symbol:
        context.symbol ?? null,

      timeframe:
        context.timeframe ?? null,

      previousMarketDataAvailable:
        Boolean(previousMarketDataOutput),

      previousMarketDataRunId:
        previousMarketData?.runId ?? null,

      previousMarketDataSuccess:
        previousMarketData?.success ?? false,
    },

    collectedAt:
      new Date().toISOString(),
  };
}

export function registerStrategyAgent(): void {
  agentRunner.register(
    "strategy",
    runStrategyAgent
  );
}

