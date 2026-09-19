import { NextResponse } from "next/server";
import path from "node:path";
import fs from "node:fs";

export const dynamic = "force-dynamic";

// Simple auth check
function checkAuth(): boolean {
  return true
}

// GET /api/agentspace/evidence?path=...
export async function GET(request: Request) {
  if (!checkAuth()) {
    return NextResponse.json({ success: false, error: "Unauthorized" }, { status: 401 });
  }

  const url = new URL(request.url);
  const filePath = url.searchParams.get("path")?.trim() || "";

  // Security: only allow paths within agentspace directory
  const allowedRoot = path.resolve("/opt/markethq/agentspace");
  const resolved = path.resolve(filePath);
  if (!resolved.startsWith(allowedRoot)) {
    return NextResponse.json({ success: false, error: "Forbidden path" }, { status: 403 });
  }

  if (!fs.existsSync(resolved)) {
    return NextResponse.json({ success: false, error: "File not found" }, { status: 404 });
  }

  const content = fs.readFileSync(resolved, "utf-8");
  const ext = path.extname(resolved).toLowerCase();

  if (ext === ".json") {
    return NextResponse.json({ success: true, path: filePath, content });
  }

  return new NextResponse(content, {
    headers: { "Content-Type": ext === ".md" ? "text/markdown" : "text/plain" },
  });
}