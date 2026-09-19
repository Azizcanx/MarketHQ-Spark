# -*- coding: utf-8 -*-
"""MarketHQ Agent Runtime V1.

Thin OpenAI Agents SDK adapter over the existing MarketHQ research stack.
The existing Brain/Research engines remain the source of truth.
"""

from __future__ import annotations

import json
import os
from typing import Any

from agents import Agent, Runner, function_tool

from agents.research_execution_adapter_v1 import run_research_execution


AGENT_MODEL = os.getenv("MARKETHQ_AGENT_MODEL", "gpt-5.6-luna")


@function_tool
def market_hq_system_status() -> str:
    """Return a read-only status of the MarketHQ agent layer."""
    return (
        "MarketHQ Agent Runtime V1 aktif. "
        "mode=research_only; live_order_execution=disabled; "
        f"model={AGENT_MODEL}."
    )


@function_tool
def market_hq_brain_pipeline_info() -> str:
    """Return the existing Brain research pipeline without executing it."""
    stages = [
        "QUEUE_HYGIENE_V2",
        "QUEUE_ENRICHMENT_V2",
        "RESEARCH_AGENT_V4",
        "KNOWLEDGE_INGEST_V3",
        "KNOWLEDGE_REPAIR_V2",
        "OBSERVATION_BRIDGE_V2",
        "EVIDENCE_REVIEW_V4",
        "EVIDENCE_FLAG_REPAIR_V1",
        "EVIDENCE_UPDATE_V1",
        "BRAIN_HEALTH_CHECK_V1",
    ]
    return "Existing Brain pipeline: " + " -> ".join(stages)


@function_tool
def market_hq_research_execution(payload_json: str) -> str:
    """Execute one existing MarketHQ research experiment through its adapter.

    The tool intentionally delegates to the existing research execution
    adapter instead of duplicating backtest logic. The adapter enforces the
    research-only execution contract and can route supported experiments to
    the existing MarketHQ engine or the isolated VectorBT engine.
    """
    try:
        payload = json.loads(payload_json)
    except json.JSONDecodeError as exc:
        return json.dumps(
            {
                "status": "BLOCKED",
                "reason": "INVALID_JSON_PAYLOAD",
                "error": str(exc),
            },
            ensure_ascii=False,
        )

    if not isinstance(payload, dict):
        return json.dumps(
            {
                "status": "BLOCKED",
                "reason": "JSON_OBJECT_REQUIRED",
            },
            ensure_ascii=False,
        )

    try:
        result = run_research_execution(payload)
    except Exception as exc:
        return json.dumps(
            {
                "status": "FAILED",
                "reason": "RESEARCH_EXECUTION_ERROR",
                "error": str(exc),
            },
            ensure_ascii=False,
        )

    return json.dumps(result, ensure_ascii=False, default=str)


market_hq_research_agent = Agent(
    name="MarketHQ Research Agent",
    model=AGENT_MODEL,
    instructions=(
        "You are the research-facing agent of MarketHQ. "
        "Use the status and Brain information tools when relevant. "
        "When the user provides a complete research experiment payload, "
        "you may use market_hq_research_execution to run the existing "
        "MarketHQ research adapter. Never claim that a pipeline, backtest, "
        "or analysis was executed unless the tool actually returned a "
        "result. Do not place orders or perform live trading. "
        "Treat tool output as verified execution output and clearly "
        "separate it from inference."
    ),
    tools=[
        market_hq_system_status,
        market_hq_brain_pipeline_info,
        market_hq_research_execution,
    ],
)


async def run_research_agent(user_input: str) -> Any:
    """Run one research request through the MarketHQ agent layer."""
    return await Runner.run(market_hq_research_agent, user_input)


if __name__ == "__main__":
    import asyncio

    async def main() -> None:
        result = await run_research_agent(
            "MarketHQ agent runtime durumunu ve mevcut Brain pipeline'ını özetle."
        )
        print(result.final_output)

    asyncio.run(main())
