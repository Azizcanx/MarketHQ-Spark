import { resolveStoreClient, type ResolvedStoreClient } from "@/lib/marketplace/store-provider";

export function storeClient(): ResolvedStoreClient | null {
  return resolveStoreClient();
}

export function storeNotConfigured() {
  return {
    success: false as const,
    configured: false as const,
    error: "TRENDYOL_NOT_CONFIGURED",
    message: "Trendyol satıcı bilgileri tanımlı değil (Seller ID / API Key / API Secret).",
  };
}

export function maskSellerId(sellerId: string): string {
  if (sellerId.length <= 4) return "***";
  return `${sellerId.slice(0, 2)}***${sellerId.slice(-2)}`;
}
