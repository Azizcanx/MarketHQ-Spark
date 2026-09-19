import type { AgentContext } from "@/components/agents/agent-types";
import type { WorkerFeedback } from "./worker-types";
import { loadLatestWorkerFeedbackForContext } from "./worker-feedback-context";

export type WorkerResearchHandoff = {
  available: boolean;
  workerFeedback: WorkerFeedback | null;
  implementationStatus: "VERIFIED" | "NO_PATCH" | "BLOCKED" | "REVIEW" | "UNKNOWN";
  researchImpact: "NONE" | "IMPLEMENTATION_ONLY";
  researchHypothesisChanged: false;
  researchDecisionOverride: false;
  nextImplementationAction: "CONTINUE" | "RETRY_IMPLEMENTATION" | "REVIEW_IMPLEMENTATION" | "NO_PATCH_ACTION";
};

function statusOf(feedback: WorkerFeedback | null): WorkerResearchHandoff["implementationStatus"] {
  if (!feedback) return "UNKNOWN";
  switch (feedback.kind) {
    case "IMPLEMENTATION_VERIFIED": return "VERIFIED";
    case "IMPLEMENTATION_NO_PATCH": return "NO_PATCH";
    case "IMPLEMENTATION_BLOCKED": return "BLOCKED";
    case "IMPLEMENTATION_REVIEW": return "REVIEW";
  }
}
function actionOf(status: WorkerResearchHandoff["implementationStatus"]): WorkerResearchHandoff["nextImplementationAction"] {
  switch (status) {
    case "VERIFIED": return "CONTINUE";
    case "NO_PATCH": return "NO_PATCH_ACTION";
    case "BLOCKED": return "RETRY_IMPLEMENTATION";
    case "REVIEW": return "REVIEW_IMPLEMENTATION";
    default: return "CONTINUE";
  }
}

export function buildWorkerResearchHandoff(context: AgentContext, options: { repoRoot: string; queueDbPath?: string }): WorkerResearchHandoff {
  const feedback = loadLatestWorkerFeedbackForContext(context, options);
  const implementationStatus = statusOf(feedback);
  return { available: feedback !== null, workerFeedback: feedback, implementationStatus, researchImpact: feedback ? feedback.researchImpact : "NONE", researchHypothesisChanged: false, researchDecisionOverride: false, nextImplementationAction: actionOf(implementationStatus) };
}
