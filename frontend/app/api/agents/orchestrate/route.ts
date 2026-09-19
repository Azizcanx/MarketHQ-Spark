import { NextRequest } from "next/server";

import {
  GET as runOrchestratorGet,
  POST as runOrchestratorPost,
} from "@/app/api/agents/orchestrator/route";

export { runOrchestratorGet as GET };

export async function POST(request: NextRequest) {
  const body = await request.text();

  if (body.trim()) {
    const normalizedRequest = new NextRequest(request.url, {
      method: "POST",
      headers: request.headers,
      body,
    });
    return runOrchestratorPost(normalizedRequest);
  }

  const headers = new Headers(request.headers);
  headers.set("content-type", "application/json");

  const normalizedRequest = new NextRequest(request.url, {
    method: "POST",
    headers,
    body: "{}",
  });

  return runOrchestratorPost(normalizedRequest);
}
