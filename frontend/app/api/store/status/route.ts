import { NextResponse } from "next/server";

import { maskSellerId, storeClient, storeNotConfigured } from "../_lib";

export const dynamic = "force-dynamic";

export async function GET() {
  const store = storeClient();
  if (!store) return NextResponse.json(storeNotConfigured());
  const sellerId = process.env.MARKETHQ_TRENDYOL_SELLER_ID?.trim() || (store.source === "mock" ? "MOCK-SELLER-ID" : "");
  try {
    const [products, orders] = await Promise.all([
      store.client.listProducts({ approved: true, page: 0, size: 1 }),
      store.client.listOrders({ page: 0, size: 1 }),
    ]);
    return NextResponse.json({
      success: true,
      configured: true,
      reachable: true,
      source: store.source,
      sellerId: maskSellerId(sellerId),
      productTotal: products.totalElements ?? products.content.length,
      orderTotal: orders.totalElements ?? orders.content.length,
    });
  } catch (error) {
    return NextResponse.json({
      success: true,
      configured: true,
      reachable: false,
      source: store.source,
      sellerId: maskSellerId(sellerId),
      error: error instanceof Error ? error.message.slice(0, 300) : String(error).slice(0, 300),
    });
  }
}
