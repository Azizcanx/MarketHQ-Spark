import { NextResponse } from "next/server";

import { storeClient, storeNotConfigured } from "../_lib";

export const dynamic = "force-dynamic";

export async function GET(request: Request) {
  const store = storeClient();
  if (!store) return NextResponse.json(storeNotConfigured());
  const url = new URL(request.url);
  const page = Math.max(0, Number(url.searchParams.get("page") ?? 0) || 0);
  const size = Math.min(50, Math.max(1, Number(url.searchParams.get("size") ?? 20) || 20));
  const status = url.searchParams.get("status")?.trim() || undefined;
  try {
    const result = await store.client.listOrders({
      page,
      size,
      status,
      orderByField: "PackageLastModifiedDate",
      orderByDirection: "DESC",
    });
    return NextResponse.json({ success: true, configured: true, source: store.source, ...result });
  } catch (error) {
    return NextResponse.json(
      {
        success: false,
        configured: true,
        source: store.source,
        error: error instanceof Error ? error.message.slice(0, 300) : String(error).slice(0, 300),
      },
      { status: 502 },
    );
  }
}
