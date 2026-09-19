import { NextResponse } from "next/server";
import { getAutonomousCycleState, listAutonomousCycleStates } from "@/components/workers/autonomous-cycle-state";

export async function GET(request: Request): Promise<NextResponse> {
  const url = new URL(request.url);
  const cycleId = url.searchParams.get("cycleId");
  const data = cycleId ? getAutonomousCycleState(cycleId) : listAutonomousCycleStates();
  return NextResponse.json({ success: true, mode: "RESEARCH_ONLY", data, safety: { researchOnly: true, executionEnabled: false, databaseWriteEnabled: false, brokerExecutionEnabled: false, mainRepoMutation: false, automaticPr: false, automaticMerge: false } });
}
