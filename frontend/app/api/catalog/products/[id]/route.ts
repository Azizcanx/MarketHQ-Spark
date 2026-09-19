import { NextRequest, NextResponse } from "next/server";
import { deleteProduct, updateProduct, validateProductInput, type ProductInput } from "@/lib/catalog/db";
import { sessionUser } from "@/lib/catalog/session-user";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const ID_RE = /^\d{1,19}$/;

export async function PATCH(request: NextRequest, context: { params: Promise<{ id: string }> }) {
  const { id } = await context.params;
  if (!ID_RE.test(id)) return NextResponse.json({ success: false, error: "INVALID_ID" }, { status: 400 });
  const actor = await sessionUser(request);
  if (!actor) return NextResponse.json({ success: false, error: "UNAUTHENTICATED" }, { status: 401 });
  let body: Partial<ProductInput>;
  try { body = await request.json() as Partial<ProductInput>; } catch { return NextResponse.json({ success: false, error: "INVALID_BODY" }, { status: 400 }); }
  const invalid = validateProductInput(body, true);
  if (invalid) return NextResponse.json({ success: false, error: invalid }, { status: 400 });
  try {
    const updated = await updateProduct(actor, id, body);
    if (!updated) return NextResponse.json({ success: false, error: "NOT_FOUND" }, { status: 404 });
    return NextResponse.json({ success: true, product: updated });
  } catch (error) {
    const message = error instanceof Error ? error.message : "";
    if (message.includes("store_products_sku_key")) return NextResponse.json({ success: false, error: "SKU zaten mevcut" }, { status: 409 });
    if (message.includes("store_products_trendyol_barcode_key")) return NextResponse.json({ success: false, error: "Bu barkod başka bir üründe kayıtlı" }, { status: 409 });
    return NextResponse.json({ success: false, error: message.slice(0, 300) || "catalog_update_failed" }, { status: 500 });
  }
}

export async function DELETE(request: NextRequest, context: { params: Promise<{ id: string }> }) {
  const { id } = await context.params;
  if (!ID_RE.test(id)) return NextResponse.json({ success: false, error: "INVALID_ID" }, { status: 400 });
  const actor = await sessionUser(request);
  if (!actor) return NextResponse.json({ success: false, error: "UNAUTHENTICATED" }, { status: 401 });
  const removed = await deleteProduct(actor, id);
  return removed ? NextResponse.json({ success: true }) : NextResponse.json({ success: false, error: "NOT_FOUND" }, { status: 404 });
}
