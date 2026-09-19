import { NextRequest, NextResponse } from "next/server";
import { getAutonomousModeState, setAutonomousMode } from "@/components/workers/autonomous-mode-store";

export const dynamic = "force-dynamic";

const safety = { researchOnly: true, executionEnabled: false, brokerExecutionEnabled: false, automaticPr: false, automaticMerge: false };

function safeEnabled(value: unknown): boolean | null {
  if (typeof value === "boolean") return value;
  if (typeof value === "string") {
    const normalized = value.trim().toLowerCase();
    if (["true", "1", "on", "enabled"].includes(normalized)) return true;
    if (["false", "0", "off", "disabled"].includes(normalized)) return false;
  }
  return null;
}

function controlSecretConfigured(): boolean {
  return Boolean(process.env.MARKETHQ_AUTOMATION_SECRET?.trim());
}

function controlSecretAuthorized(request: NextRequest): boolean {
  const expected = process.env.MARKETHQ_AUTOMATION_SECRET?.trim();
  if (!expected) return true;
  const provided = request.headers.get("x-markethq-automation-secret")?.trim();
  return Boolean(provided && provided === expected);
}

export async function GET(): Promise<NextResponse> {
  return NextResponse.json({ success: true, mode: getAutonomousModeState(), configuration: { controlSecretConfigured: controlSecretConfigured() }, safety });
}

export async function POST(request: NextRequest): Promise<NextResponse> {
  try {
    const body = await request.json().catch(() => ({}));
    const enabled = safeEnabled(body?.enabled);
    if (enabled === null) return NextResponse.json({ success: false, error: "enabled must be boolean", safety }, { status: 400 });

    // If a deployment secret is configured, enabling autonomous mode requires it.
    // Disabling remains available without the secret as an emergency off switch.
    if (enabled && !controlSecretAuthorized(request)) {
      return NextResponse.json({ success: false, error: "AUTOMATION_CONTROL_UNAUTHORIZED", safety }, { status: 401 });
    }

    const state = setAutonomousMode(enabled, typeof body?.updatedBy === "string" && body.updatedBy.trim() ? body.updatedBy.trim().slice(0, 80) : "PANEL");
    return NextResponse.json({ success: true, mode: state, safety });
  } catch (error) {
    return NextResponse.json({ success: false, error: error instanceof Error ? error.message : String(error), safety }, { status: 500 });
  }
}
