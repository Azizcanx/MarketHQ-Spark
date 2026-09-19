import { NextResponse } from "next/server";
import { resolveStoreClient } from "@/lib/marketplace/store-provider";
import { storeNotConfigured } from "../_lib";

export const dynamic = "force-dynamic";

export async function GET() {
  const resolved = resolveStoreClient();
  if (!resolved) {
    return NextResponse.json(storeNotConfigured(), { status: 503 });
  }

  try {
    const ordersRes = await resolved.client.listOrders({ page: 0, size: 50 });
    const productsRes = await resolved.client.listProducts({ page: 0, size: 50 });

    const orders = Array.isArray(ordersRes?.content) ? ordersRes.content : [];
    const products = Array.isArray(productsRes?.content) ? productsRes.content : [];

    // Financial Metrics Calculation
    let grossSales = 0;
    let deliveredSales = 0;
    let returnedSales = 0;
    let totalItemsSold = 0;
    const statusCounts: Record<string, number> = {};

    for (const order of orders) {
      const status = String(order.status ?? "Unknown");
      statusCounts[status] = (statusCounts[status] || 0) + 1;

      const totalPrice = Number(order.totalPrice ?? order.grossAmount ?? 0);
      grossSales += totalPrice;

      if (status === "Delivered") {
        deliveredSales += totalPrice;
      } else if (status === "Returned" || status === "Cancelled") {
        returnedSales += totalPrice;
      }

      if (Array.isArray(order.lines)) {
        totalItemsSold += order.lines.reduce(
          (sum: number, line: Record<string, unknown>) => sum + Number(line.quantity ?? 1),
          0
        );
      } else {
        totalItemsSold += 1;
      }
    }

    const orderCount = orders.length;
    const returnCount = statusCounts["Returned"] || 0;
    const returnRate = orderCount > 0 ? (returnCount / orderCount) * 100 : 0;

    // Estimated costs (standard Trendyol commission ~18%, shipping ~42 TRY per active order)
    const estimatedCommission = grossSales * 0.18;
    const estimatedShipping = orderCount * 42.0;
    const estimatedProductCost = grossSales * 0.45; // ~45% COGS average
    const netProfit = grossSales - estimatedCommission - estimatedShipping - estimatedProductCost - (returnedSales * 0.3);
    const profitMargin = grossSales > 0 ? (netProfit / grossSales) * 100 : 0;

    // Inventory health
    const lowStockThreshold = 5;
    let totalStock = 0;
    let lowStockCount = 0;
    let outOfStockCount = 0;

    for (const p of products) {
      const qty = Number(p.quantity ?? 0);
      totalStock += qty;
      if (qty === 0) outOfStockCount++;
      else if (qty <= lowStockThreshold) lowStockCount++;
    }

    return NextResponse.json({
      success: true,
      source: resolved.source,
      currency: "TRY",
      metrics: {
        grossSales: Math.round(grossSales * 100) / 100,
        deliveredSales: Math.round(deliveredSales * 100) / 100,
        returnedSales: Math.round(returnedSales * 100) / 100,
        netProfit: Math.round(netProfit * 100) / 100,
        profitMargin: Math.round(profitMargin * 10) / 10,
        estimatedCommission: Math.round(estimatedCommission * 100) / 100,
        estimatedShipping: Math.round(estimatedShipping * 100) / 100,
        estimatedProductCost: Math.round(estimatedProductCost * 100) / 100,
        orderCount,
        totalItemsSold,
        returnCount,
        returnRate: Math.round(returnRate * 10) / 10,
        averageOrderValue: orderCount > 0 ? Math.round((grossSales / orderCount) * 100) / 100 : 0,
      },
      statusBreakdown: statusCounts,
      inventorySummary: {
        totalProducts: products.length,
        totalStock,
        lowStockCount,
        outOfStockCount,
      },
      generatedAt: new Date().toISOString(),
    });
  } catch (error: unknown) {
    return NextResponse.json(
      {
        success: false,
        error: "ANALYTICS_FETCH_FAILED",
        message: error instanceof Error ? error.message : "Finansal veriler hesaplanamadı.",
      },
      { status: 500 }
    );
  }
}
