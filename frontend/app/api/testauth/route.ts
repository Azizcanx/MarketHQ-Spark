import { NextResponse } from "next/server";
export const dynamic = "force-dynamic";
export async function GET() {
  return NextResponse.json({
    env: process.env.AGENTSPACE_API_TOKEN || "NOT_SET",
    node_env: process.env.NODE_ENV,
  });
}
export async function POST() {
  return NextResponse.json({ ok: true });
}
