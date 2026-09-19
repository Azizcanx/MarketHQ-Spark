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
      `brain-${Date.now()}`;

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
        endpoint: "/api/agents/brain",
        requestedAt,
        researchOnly: true,
      },
    };

    console.log(
      "[MarketHQ] Brain agent started:",
      {
        runId,
        strategyId,
        symbol,
        timeframe,
      }
    );

    // =========================================================
    // 4. RUN BRAIN AGENT
    // =========================================================

    const result =
      await agentRunner.run(
        "brain",
        context
      );

    console.log(
      "[MarketHQ] Brain agent completed:",
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
      "[MarketHQ] Brain agent fatal error:",
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
          "/api/agents/brain",

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

export async function POST(request: Request) {
  const requestedAt =
    new Date().toISOString();

  try {
    let body: Record<
      string,
      unknown
    > = {};

    try {
      const parsed =
        await request.json();

      if (
        typeof parsed === "object" &&
        parsed !== null
      ) {
        body =
          parsed as Record<
            string,
            unknown
          >;
      }
    } catch {
      body = {};
    }

    const strategyId =
      typeof body.strategyId ===
      "string"
        ? body.strategyId
        : DEFAULT_STRATEGY_ID;

    const symbol =
      typeof body.symbol ===
      "string"
        ? body.symbol
        : undefined;

    const timeframe =
      typeof body.timeframe ===
      "string"
        ? body.timeframe
        : DEFAULT_TIMEFRAME;

    const runId =
      `brain-${Date.now()}`;

    const context: AgentContext = {
      runId,
      strategyId,
      symbol,
      timeframe,

      input: {
        ...body,
      },

      metadata: {
        source: "next-api",
        endpoint: "/api/agents/brain",
        method: "POST",
        requestedAt,
        researchOnly: true,
      },
    };

    console.log(
      "[MarketHQ] Brain POST started:",
      {
        runId,
        strategyId,
        symbol,
        timeframe,
      }
    );

    const result =
      await agentRunner.run(
        "brain",
        context
      );

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
      "[MarketHQ] Brain POST fatal error:",
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
          "/api/agents/brain",

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
