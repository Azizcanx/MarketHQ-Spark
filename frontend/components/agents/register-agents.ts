import { registerMarketDataAgent } from "./market-data-agent";
import { registerTrendRegimeAgent } from "./trend-regime-agent";

import {
  registerResearchDateResolverAgent,
} from "./research-date-resolver-agent-v1";

import { registerStrategyAgent } from "./strategy-agent";
import { registerBacktestAgent } from "./backtest-agent";
import { registerValidationAgent } from "./validation-agent";
import { registerEvidenceAgent } from "./evidence-agent";
import { registerBrainAgent } from "./brain-agent";
import { registerBrainUpdateAgent } from "./brain-update-agent";
import { registerLearningAgent } from "./learning-agent";
import { registerResearchDecisionAgent } from "./research-decision-agent";
import { registerResearchQueueAgent } from "./research-queue-agent";
import { registerExperimentGeneratorAgent } from "./experiment-generator-agent";
import { registerExperimentRunnerAgent } from "./experiment-runner-agent";
import { registerPaperTradingAgent } from "./paper-trading-agent";
import { registerResultIngestionAgent } from "./result-ingestion-agent";

let registered = false;

export function registerDefaultAgents(): void {
  if (registered) {
    return;
  }

  registerMarketDataAgent();

  registerTrendRegimeAgent();

  registerStrategyAgent();

  registerBacktestAgent();

  registerValidationAgent();

  registerEvidenceAgent();

  registerBrainAgent();

  registerResultIngestionAgent();

  registerLearningAgent();

  registerBrainUpdateAgent();

  registerResearchDecisionAgent();

  registerResearchQueueAgent();

  registerResearchDateResolverAgent();

  registerExperimentGeneratorAgent();

  registerExperimentRunnerAgent();

  registerPaperTradingAgent();

  registered = true;
}

export const DEFAULT_AGENT_IDS = [
  "market-data",
  "trend-regime",
  "strategy",
  "backtest",
  "validation",
  "evidence",
  "brain",
  "result-ingestion",
  "learning",
  "brain-update",
  "research-decision",
  "research-queue",
  "research-date-resolver",
  "experiment-generator",
  "experiment-runner",
  "paper-trading",
] as const;



