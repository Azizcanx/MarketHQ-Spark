import { NextResponse } from "next/server";

import { registerDefaultAgents } from "@/components/agents/register-agents";
import { agentRunner } from "@/components/agents/agent-runner";
import type { AgentContext } from "@/components/agents/agent-types";

const DEFAULT_STRATEGY_ID = "STR-43839FA9C6";
const DEFAULT_TIMEFRAME = "1d";

export async function GET(request: Request) {
  const requestedAt =
    new Date().toISOString();

  try {
    // =========================================================
    // 1. DEFAULT AGENTS
    // =========================================================

    registerDefaultAgents();

    // =========================================================
    // 2. QUERY PARAMETERS
    // =========================================================

    const url =
      new URL(request.url);

    const strategyId =
      url.searchParams.get(
        "strategyId"
      ) ?? DEFAULT_STRATEGY_ID;

    const symbol =
      url.searchParams.get(
        "symbol"
      ) ?? undefined;

    const timeframe =
      url.searchParams.get(
        "timeframe"
      ) ?? DEFAULT_TIMEFRAME;

    const runId =
      `learning-${Date.now()}`;

    // =========================================================
    // 3. AGENT CONTEXT
    // =========================================================

    const context: AgentContext = {
      runId,
      strategyId,
      symbol,
      timeframe,

      metadata: {
        source: "next-api",
        endpoint: "/api/agents/learning",
        requestedAt,
        researchOnly: true,
      },
    };

    console.log(
      "[MarketHQ] Learning agent started:",
      {
        runId,
        strategyId,
        symbol,
        timeframe,
      }
    );

    // =========================================================
    // 4. RUN LEARNING AGENT
    // =========================================================

    const result =
      await agentRunner.run(
        "learning",
        context
      );

    console.log(
      "[MarketHQ] Learning agent completed:",
      {
        runId,
        success: result.success,
        status: result.status,
        durationMs:
          result.durationMs,
      }
    );

    // =========================================================
    // 5. RESPONSE
    // =========================================================

    return NextResponse.json(
      {
        success: result.success,

        result: {
          ...result,

          strategyId:
            result.output?.strategyId ??
            strategyId,

          symbol,

          timeframe,

          researchOnly: true,

          executionEnabled: false,
        },
      },
      {
        status:
          result.success
            ? 200
            : 500,

        headers: {
          "Content-Type":
            "application/json",

          "Cache-Control":
            "no-store",
        },
      }
    );
  } catch (error) {
    const message =
      error instanceof Error
        ? error.message
        : String(error);

    console.error(
      "[MarketHQ] Learning agent fatal error:",
      {
        error: message,
        requestedAt,
      }
    );

    return NextResponse.json(
      {
        success: false,

        error: message,

        researchOnly: true,

        executionEnabled: false,

        endpoint:
          "/api/agents/learning",

        requestedAt,
      },
      {
        status: 500,

        headers: {
          "Content-Type":
            "application/json",

          "Cache-Control":
            "no-store",
        },
      }
    );
  }
}
