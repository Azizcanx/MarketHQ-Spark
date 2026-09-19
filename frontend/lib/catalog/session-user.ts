import { NextRequest } from "next/server";
import { SESSION_COOKIE, verifySession } from "@/lib/auth/session-token";

export async function sessionUser(request: NextRequest): Promise<string | null> {
  const secret = process.env.MARKETHQ_AUTH_SECRET?.trim() ?? "";
  const session = await verifySession(secret, request.cookies.get(SESSION_COOKIE)?.value);
  return session?.user ?? null;
}
