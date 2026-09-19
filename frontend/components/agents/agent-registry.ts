import type {
  AgentDefinition,
  AgentId,
  AgentStatus,
} from "./agent-types";

const definitions: AgentDefinition[] = [
  {
    id: "market-data",
    name: "Market Data",
    description:
      "Araştırma için gerekli piyasa verisini ve veri bağlamını hazırlar.",
    dependencies: [],
  },

  {
    id: "trend-regime",
    name: "Trend + Market Regime",
    description:
      "Market Data çıktısından trend yönü, trend gücü, momentum, volatilite ve piyasa rejimi bağlamını üretir.",
    dependencies: [
      "market-data",
    ],
  },

  {
    id: "strategy",
    name: "Strategy",
    description:
      "Araştırılacak stratejinin kural ve parametre bağlamını hazırlar.",
    dependencies: [
      "market-data",
    ],
  },

  {
    id: "backtest",
    name: "Backtest",
    description:
      "Stratejinin historical araştırma sonuçlarını üretir.",
    dependencies: [
      "strategy",
      "market-data",
    ],
  },

  {
    id: "validation",
    name: "Validation",
    description:
      "Backtest sonuçlarını robustness ve bağımsız doğrulama açısından değerlendirir.",
    dependencies: [
      "backtest",
      "strategy",
    ],
  },

  {
    id: "evidence",
    name: "Evidence",
    description:
      "Araştırma iddiaları için bağımsız kanıt ve güvenilirlik bağlamı üretir.",
    dependencies: [
      "validation",
      "backtest",
    ],
  },

  {
    id: "brain",
    name: "Brain",
    description:
      "Mevcut research knowledge ve evidence bağlamını birleştirir.",
    dependencies: [
      "evidence",
      "validation",
    ],
  },

  {
    id: "result-ingestion",
    name: "Result Ingestion",
    description:
      "Mevcut araştırma çıktılarından standartlaştırılmış ve izlenebilir araştırma sonucu oluşturur.",
    dependencies: [
      "backtest",
      "validation",
      "evidence",
    ],
  },

  {
    id: "learning",
    name: "Learning",
    description:
      "Normalize edilmiş araştırma sonuçlarını Brain ve Evidence bağlamıyla birlikte öğrenme girdisine dönüştürür.",
    dependencies: [
      "brain",
      "evidence",
    ],
  },

  {
    id: "research-decision",
    name: "Research Decision",
    description:
      "Learning, evidence ve validation çıktılarından bir sonraki araştırma yönünü belirler.",
    dependencies: [
      "learning",
      "evidence",
      "validation",
    ],
  },

  {
    id: "research-queue",
    name: "Research Queue",
    description:
      "Research Decision ve Brain bağlamından sıradaki araştırma görevini seçer.",
    dependencies: [
      "research-decision",
      "brain",
    ],
  },

  {
    id: "research-date-resolver",
    name: "Research Date Resolver",
    description:
      "Research deneyleri için tarih kapsamını yalnızca veri erişilebilirliğine dayanarak çözer ve kronolojik bağımsız araştırma dilimlerini üretir.",
    dependencies: [
      "research-queue",
      "research-decision",
      "market-data",
    ],
  },

  {
    id: "experiment-generator",
    name: "Experiment Generator",
    description:
      "Seçilen research queue görevini standart ve izlenebilir experiment tanımına dönüştürür.",
    dependencies: [
      "research-queue",
      "research-decision",
      "strategy",
      "market-data",
      "research-date-resolver",
    ],
  },

  {
    id: "experiment-runner",
    name: "Experiment Runner",
    description:
      "Oluşturulan experiment'i araştırma kapsamında bağımsız execution adapter üzerinden çalıştırır.",
    dependencies: [
      "experiment-generator",
      "backtest",
      "validation",
      "evidence",
    ],
  },

  {
    id: "paper-trading",
    name: "Paper Trading",
    description:
      "Experiment Runner tarafından dondurulmuş araştırma deneyini yalnızca research-only historical paper simulation kapsamında çalıştırır.",
    dependencies: [
      "experiment-runner",
    ],
  },

  {
    id: "brain-update",
    name: "Brain Update",
    description:
      "Learning, validation ve result-ingestion çıktılarından türetilen araştırma bilgisini Brain graph katmanına işler; doğrulanmış kural terfisi yapmaz.",
    dependencies: [
      "learning",
      "validation",
      "result-ingestion",
    ],
  },

  {
    id: "orchestrator",
    name: "Orchestrator",
    description:
      "Research-only agent pipeline'ını sıralar ve çalıştırır.",
    dependencies: [],
  },
];

const statusMap = new Map<
  AgentId,
  AgentStatus
>();

for (const definition of definitions) {
  statusMap.set(
    definition.id,
    "IDLE"
  );
}

export function getAgent(
  agentId: AgentId
): AgentDefinition {
  const definition =
    definitions.find(
      (item) => item.id === agentId
    );

  if (!definition) {
    throw new Error(
      `Unknown agent: ${agentId}`
    );
  }

  return definition;
}

export function getAgentDependencies(
  agentId: AgentId
): AgentId[] {
  return [
    ...getAgent(agentId).dependencies,
  ];
}

export function getAllAgents(): AgentDefinition[] {
  return [
    ...definitions,
  ];
}

export function getAgentStatus(
  agentId: AgentId
): AgentStatus {
  return (
    statusMap.get(agentId) ??
    "IDLE"
  );
}

export function updateAgentStatus(
  agentId: AgentId,
  status: AgentStatus
): void {
  statusMap.set(
    agentId,
    status
  );
}

/**
 * Research cycle:
 *
 * Market Data
 *   ↓
 * Strategy
 *   ↓
 * Backtest
 *   ↓
 * Validation
 *   ↓
 * Evidence
 *   ↓
 * Brain
 *   ↓
 * Learning
 *   ↓
 * Research Decision
 *   ↓
 * Research Queue
 *   ↓
 * Research Date Resolver
 *   ↓
 * Experiment Generator
 *   ↓
 * Experiment Runner
 *   ↓
 * Paper Trading
 *   ↓
 * Result Ingestion
 *   ↓
 * Learning
 *   ↓
 * Brain Update
 *   ↓
 * Research Decision
 *
 * Learning and Research Decision intentionally appear twice.
 * Result Ingestion runs exactly once, after Experiment Runner.
 * Brain Update runs after the second-stage Learning/Validation/
 * Result Ingestion outputs and updates only the derived Brain layer.
 */
export function getAgentPipelineOrder(): AgentId[] {
  return [
    "market-data",
    "trend-regime",
    "strategy",
    "backtest",
    "validation",
    "evidence",
    "brain",
    "learning",
    "research-decision",
    "research-queue",
    "research-date-resolver",
    "experiment-generator",
    "experiment-runner",
    "paper-trading",
    "result-ingestion",
    "learning",
    "brain-update",
    "research-decision",
  ];
}
