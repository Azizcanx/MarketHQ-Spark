import { NextRequest, NextResponse } from "next/server";
import { timingSafeEqual, scryptSync } from "node:crypto";
import { SESSION_COOKIE, signSession } from "@/lib/auth/session-token";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

// naive in-memory throttle: 8 attempts / 60s / IP
const hits = new Map<string, { n: number; reset: number }>();
function throttled(ip: string): boolean {
  const now = Date.now();
  const e = hits.get(ip);
  if (!e || e.reset < now) { hits.set(ip, { n: 1, reset: now + 60000 }); return false; }
  e.n += 1;
  return e.n > 8;
}

function parseHash(stored: string): { N: number; r: number; p: number; salt: string; hash: string } | null {
  const parts = stored.split(".");
  if (parts.length !== 6 || parts[0] !== "scrypt") return null;
  return { N: Number(parts[1]), r: Number(parts[2]), p: Number(parts[3]), salt: parts[4], hash: parts[5] };
}

async function checkPassword(password: string, stored: string): Promise<boolean> {
  const spec = parseHash(stored);
  if (!spec || !Number.isFinite(spec.N)) return false;
  try {
    const derived = scryptSync(password, spec.salt, 64, { N: spec.N, r: spec.r, p: spec.p });
    const expected = Buffer.from(spec.hash, "hex");
    return expected.length === derived.length && timingSafeEqual(expected, derived);
  } catch { return false; }
}

export async function POST(request: NextRequest) {
  const user = process.env.MARKETHQ_ADMIN_USER?.trim() ?? "";
  const storedHash = process.env.MARKETHQ_ADMIN_PASSWORD_HASH?.trim() ?? "";
  const secret = process.env.MARKETHQ_AUTH_SECRET?.trim() ?? "";
  if (!user || !storedHash || !secret) {
    return NextResponse.json({ success: false, error: "AUTH_NOT_CONFIGURED" }, { status: 503 });
  }
  const ip = request.headers.get("x-forwarded-for")?.split(",")[0]?.trim() || "local";
  if (throttled(ip)) {
    return NextResponse.json({ success: false, error: "TOO_MANY_ATTEMPTS" }, { status: 429 });
  }
  let body: Record<string, unknown>;
  try { body = await request.json() as Record<string, unknown>; } catch { body = {}; }
  const sentUser = typeof body.user === "string" ? body.user.trim() : "";
  const sentPass = typeof body.password === "string" ? body.password : "";
  const ok = sentUser.toLowerCase() === user.toLowerCase() && sentPass.length > 0 && await checkPassword(sentPass, storedHash);
  if (!ok) {
    return NextResponse.json({ success: false, error: "INVALID_CREDENTIALS" }, { status: 401 });
  }
  const token = await signSession(secret, sentUser);
  const response = NextResponse.json({ success: true, user: sentUser });
  response.cookies.set(SESSION_COOKIE, token, {
    httpOnly: true,
    sameSite: "lax",
    path: "/",
    maxAge: 60 * 60 * 8,
  });
  return response;
}

export async function GET() {
  const configured = Boolean(process.env.MARKETHQ_ADMIN_USER && process.env.MARKETHQ_ADMIN_PASSWORD_HASH && process.env.MARKETHQ_AUTH_SECRET);
  return NextResponse.json({ success: true, configured });
}
