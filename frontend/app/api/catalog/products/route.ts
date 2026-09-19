import { NextRequest, NextResponse } from "next/server";
import { createProduct, listProducts, validateProductInput, type ProductInput } from "@/lib/catalog/db";
import { sessionUser } from "@/lib/catalog/session-user";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET(request: NextRequest) {
  const url = new URL(request.url);
  const page = Math.max(0, Number(url.searchParams.get("page") ?? 0) || 0);
  const size = Math.min(100, Math.max(1, Number(url.searchParams.get("size") ?? 25) || 25));
  const search = url.searchParams.get("search")?.trim() || undefined;
  try {
    const result = await listProducts({ search, page, size });
    return NextResponse.json({ success: true, ...result });
  } catch (error) {
    return NextResponse.json(
      { success: false, error: error instanceof Error ? error.message.slice(0, 300) : "catalog_error" },
      { status: 503 },
    );
  }
}

export async function POST(request: NextRequest) {
  const actor = await sessionUser(request);
  if (!actor) return NextResponse.json({ success: false, error: "UNAUTHENTICATED" }, { status: 401 });
  let body: Partial<ProductInput>;
  try { body = await request.json() as Partial<ProductInput>; } catch { return NextResponse.json({ success: false, error: "INVALID_BODY" }, { status: 400 }); }
  const invalid = validateProductInput(body, false);
  if (invalid) return NextResponse.json({ success: false, error: invalid }, { status: 400 });
  try {
    const created = await createProduct(actor, body as ProductInput);
    return NextResponse.json({ success: true, product: created }, { status: 201 });
  } catch (error) {
    const message = error instanceof Error ? error.message : "";
    if (message.includes("store_products_sku_key")) return NextResponse.json({ success: false, error: "SKU zaten mevcut" }, { status: 409 });
    if (message.includes("store_products_trendyol_barcode_key")) return NextResponse.json({ success: false, error: "Bu barkod başka bir üründe kayıtlı" }, { status: 409 });
    return NextResponse.json({ success: false, error: message.slice(0, 300) || "catalog_create_failed" }, { status: 500 });
  }
}
