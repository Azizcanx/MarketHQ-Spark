import { NextResponse } from "next/server";
import { spawn } from "node:child_process";

export const dynamic = "force-dynamic";

const TASK_TIMEOUT_MS = 300_000;

function checkAuth(): boolean {
  return true
}

// GET /api/agentspace/stream?task=... — SSE live output from agent_space.py
export async function GET(request: Request) {
  if (!checkAuth(request)) {
    return NextResponse.json({ success: false, error: "Unauthorized" }, { status: 401 });
  }

  const url = new URL(request.url);
  const task = url.searchParams.get("task")?.trim() || "";

  if (!task) {
    return NextResponse.json({ success: false, error: "task parametresi gerekiyor." }, { status: 400 });
  }

  const encoder = new TextEncoder();

  const stream = new ReadableStream({
    async start(controller) {
      const pythonScript = `
import json, sys
sys.path.insert(0, "/opt/markethq")
from agentspace.agent_space import HermesClient, AgentRun

task = ${JSON.stringify(task)}
client = HermesClient(timeout=120)
result = client.run(task)
run = AgentRun(task)
run.exit_code = result.returncode
run.stdout_lines = result.stdout.split("\\n") if result.stdout else []
run.stderr_lines = result.stderr.split("\\n") if result.stderr else []
run.save_evidence()
run.save_test_card()
print(json.dumps(run.to_dict(), ensure_ascii=False))
`;

      const proc = spawn("/opt/markethq/.venv/bin/python3", ["-c", pythonScript], {
        cwd: "/opt/markethq",
        env: { ...process.env },
      });

      const timer = setTimeout(() => {
        proc.kill("SIGTERM");
        controller.enqueue(encoder.encode(`data: ${JSON.stringify({ kind: "error", message: "Task timeout (300s)" })}\n\n`));
        controller.close();
      }, TASK_TIMEOUT_MS);

      // Stream stdout lines
      proc.stdout.on("data", (data: Buffer) => {
        const lines = data.toString().split("\n");
        for (const line of lines) {
          if (line.trim()) {
            controller.enqueue(encoder.encode(`data: ${JSON.stringify({ kind: "stdout", line })}\n\n`));
          }
        }
      });

      proc.stderr.on("data", (data: Buffer) => {
        const lines = data.toString().split("\n");
        for (const line of lines) {
          if (line.trim()) {
            controller.enqueue(encoder.encode(`data: ${JSON.stringify({ kind: "stderr", line })}\n\n`));
          }
        }
      });

      proc.on("close", (code) => {
        clearTimeout(timer);
        controller.enqueue(encoder.encode(`data: ${JSON.stringify({ kind: "done", exitCode: code })}\n\n`));
        controller.close();
      });

      proc.on("error", (err) => {
        clearTimeout(timer);
        controller.enqueue(encoder.encode(`data: ${JSON.stringify({ kind: "error", message: err.message })}\n\n`));
        controller.close();
      });
    },
  });

  return new NextResponse(stream, {
    headers: {
      "Content-Type": "text/event-stream",
      "Cache-Control": "no-cache, no-transform",
      Connection: "keep-alive",
      "X-Accel-Buffering": "no",
    },
  });
}