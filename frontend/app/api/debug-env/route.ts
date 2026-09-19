import { NextResponse } from "next/server";
export const dynamic = "force-dynamic";
export async function GET() {
  return NextResponse.json({ token: process.env.AGENTSPACE_API_TOKEN || "NOT_SET" });
}
