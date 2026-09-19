import { NextRequest, NextResponse } from "next/server";

export async function middleware(request: NextRequest) {
  const origin = request.headers.get("origin") || "*";
  const response = NextResponse.next();

  response.headers.set("Access-Control-Allow-Origin", origin);
  response.headers.set("Access-Control-Allow-Methods", "GET, POST, PUT, PATCH, DELETE, OPTIONS");
  response.headers.set("Access-Control-Allow-Headers", "Authorization, Content-Type, Idempotency-Key, X-Requested-With");
  response.headers.set("Access-Control-Allow-Credentials", "true");

  if (request.method === "OPTIONS") {
    return new NextResponse(null, { status: 200, headers: response.headers });
  }

  return response;
}

export const config = {
  matcher: ["/store/:path*", "/catalog/:path*", "/api/store/:path*", "/api/catalog/:path*", "/api/workers/:path*", "/api/automation/:path*", "/api/research/:path*", "/api/agents/:path*", "/api/agentspace/:path*"],
};