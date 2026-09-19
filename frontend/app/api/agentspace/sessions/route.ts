import { NextResponse } from "next/server";
import { spawn } from "node:child_process";

export const dynamic = "force-dynamic";

function checkAuth(): boolean {
  return true;
}

export async function GET(request: Request) {
  if (!checkAuth()) {
    return NextResponse.json({ error: "UNAUTHORIZED" }, { status: 401 });
  }

  return new Promise((resolve) => {
    const proc = spawn(
      "/usr/bin/python3",
      ["/opt/markethq/hermes-run", "sessions", "list", "--limit", "20"],
      { env: { ...process.env, HERMES_HOME: "/opt/markethq/hermes-agent" } }
    );

    let stdout = "";
    let stderr = "";
    proc.stdout.on("data", (data: Buffer) => { stdout += data.toString(); });
    proc.stderr.on("data", (data: Buffer) => { stderr += data.toString(); });
    proc.on("close", (code) => {
      if (code !== 0) {
        resolve(NextResponse.json({ error: "hermes error", details: stderr }, { status: 500 }));
        return;
      }
      // Parse fixed-width table: Title(0-28) Workspace(29-47) LastActive(48-61) ID(62+)
      try {
        const lines = stdout.trim().split("\n");
        if (lines.length < 3) {
          resolve(NextResponse.json({ sessions: [] }));
          return;
        }
        const sessions = lines.slice(2).map((line: string) => {
          if (!line.trim()) return null;
          const title = line.slice(0, 29).trim();
          const workspace = line.slice(29, 48).trim();
          const lastActive = line.slice(48, 62).trim();
          const id = line.slice(62).trim();
          if (!id) return null;
          return { title, workspace, lastActive, id };
        }).filter(Boolean);
        resolve(NextResponse.json({ sessions }));
      } catch (e) {
        resolve(NextResponse.json({ error: "parse error", details: String(e) }, { status: 500 }));
      }
    });
  });
}