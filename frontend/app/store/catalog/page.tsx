"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";
import { Loader2, Pencil, Plus, Search, Trash2 } from "lucide-react";

import { DemoBadge, ErrorCard, LoadingRow, StoreNav, StoreShell, money, str, useStoreStatus } from "../_components";

type Row = {
  id: string; sku: string; title: string; brand: string | null;
  trendyol_barcode: string | null; local_category: string | null;
  cost_price: string | null; sale_price: string | null;
  stock_on_hand: number; stock_buffer: number; visible_stock: number;
  channel_enabled: boolean; notes?: string | null;
};

type Form = {
  sku: string; title: string; brand: string; trendyol_barcode: string; local_category: string;
  cost_price: string; sale_price: string; stock_on_hand: string; stock_buffer: string; channel_enabled: boolean; notes: string;
};

const emptyForm: Form = { sku: "", title: "", brand: "", trendyol_barcode: "", local_category: "", cost_price: "", sale_price: "", stock_on_hand: "0", stock_buffer: "5", channel_enabled: true, notes: "" };

function toNumber(value: string): number | null {
  const n = Number(value);
  return value.trim() && Number.isFinite(n) ? n : null;
}

export default function CatalogPage() {
  const status = useStoreStatus();
  const [rows, setRows] = useState<Row[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(0);
  const [search, setSearch] = useState("");
  const [applied, setApplied] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [form, setForm] = useState<Form | null>(null);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  const load = useCallback(async (nextPage: number, needle: string) => {
    setLoading(true); setError(null);
    try {
      const params = new URLSearchParams({ page: String(nextPage), size: "20" });
      if (needle.trim()) params.set("search", needle.trim());
      const response = await fetch(`/api/catalog/products?${params.toString()}`, { cache: "no-store" });
      const data = await response.json();
      if (!response.ok || data.success === false) throw new Error(str(data.error, "Katalog yüklenemedi."));
      setRows(Array.isArray(data.content) ? data.content : []);
      setTotal(Number(data.total) || 0);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Katalog yüklenemedi.");
    } finally { setLoading(false); }
  }, []);

  useEffect(() => { void load(0, ""); }, [load]);

  function openCreate() { setEditingId(null); setForm({ ...emptyForm }); setFormError(null); }
  function openEdit(row: Row) {
    setEditingId(row.id);
    setForm({
      sku: row.sku, title: row.title, brand: row.brand ?? "", trendyol_barcode: row.trendyol_barcode ?? "",
      local_category: row.local_category ?? "", cost_price: row.cost_price ?? "", sale_price: row.sale_price ?? "",
      stock_on_hand: String(row.stock_on_hand), stock_buffer: String(row.stock_buffer),
      channel_enabled: row.channel_enabled, notes: row.notes ?? "",
    });
    setFormError(null);
  }

  async function save(event: FormEvent) {
    event.preventDefault();
    if (!form) return;
    setSaving(true); setFormError(null);
    const payload = {
      sku: form.sku.trim(), title: form.title.trim(), brand: form.brand.trim() || null,
      trendyol_barcode: form.trendyol_barcode.trim() || null, local_category: form.local_category.trim() || null,
      cost_price: toNumber(form.cost_price), sale_price: toNumber(form.sale_price),
      stock_on_hand: toNumber(form.stock_on_hand) ?? 0, stock_buffer: toNumber(form.stock_buffer) ?? 0,
      channel_enabled: form.channel_enabled, notes: form.notes.trim() || null,
    };
    try {
      const response = await fetch(editingId ? `/api/catalog/products/${editingId}` : "/api/catalog/products", {
        method: editingId ? "PATCH" : "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok || data.success === false) throw new Error(str(data.error, "Kayıt başarısız."));
      setForm(null);
      void load(page, applied);
    } catch (reason) {
      setFormError(reason instanceof Error ? reason.message : "Kayıt başarısız.");
    } finally { setSaving(false); }
  }

  async function remove(row: Row) {
    if (!window.confirm(`"${row.sku}" silinsin mi? Bu işlem geri alınamaz.`)) return;
    await fetch(`/api/catalog/products/${row.id}`, { method: "DELETE" });
    void load(page, applied);
  }

  const field = "w-full rounded-xl border border-input bg-background px-3 py-2 text-sm focus:border-ring focus:outline-none";

  return (
    <StoreShell crumb="MarketHQ / Commerce / Catalog" title="Katalog" description="Yerel ürün listen — SKU, Trendyol barkod eşlemesi, maliyet ve stok tamponu. Kanala görünen stok = eldeki − tampon.">
      <StoreNav />
      {status?.source === "mock" && <div className="mt-4"><DemoBadge /></div>}
      <div className="mt-4 flex flex-wrap items-center justify-between gap-3">
        <form className="flex flex-1 min-w-[240px] max-w-md gap-2" onSubmit={(e) => { e.preventDefault(); setPage(0); setApplied(search); void load(0, search); }}>
          <div className="relative flex-1">
            <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
            <input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="SKU, isim, marka veya barkod ara…" className={field + " pl-9"} />
          </div>
          <button type="submit" className="rounded-xl border border-border px-4 py-2 text-sm font-bold">Ara</button>
        </form>
        <button type="button" onClick={openCreate} className="flex items-center gap-2 rounded-xl bg-primary px-4 py-2.5 text-sm font-bold text-primary-foreground"><Plus className="h-4 w-4" /> Yeni ürün</button>
      </div>
      {error && <div className="mt-3"><ErrorCard message={error} /></div>}
      {loading && rows.length === 0 ? <div className="mt-4"><LoadingRow label="Katalog yükleniyor…" /></div> : (
        <div className="mt-4 overflow-x-auto rounded-2xl border border-border bg-card">
          <table className="w-full min-w-[860px] text-left text-sm">
            <thead><tr className="border-b border-border text-[10px] uppercase tracking-widest text-muted-foreground">
              <th className="py-2.5 pl-4 pr-3">SKU</th><th className="py-2.5 pr-3">Ürün</th><th className="py-2.5 pr-3">Barkod eşleşmesi</th>
              <th className="py-2.5 pr-3 text-right">Eldeki</th><th className="py-2.5 pr-3 text-right">Kanala görünen</th>
              <th className="py-2.5 pr-3 text-right">Satış</th><th className="py-2.5 pr-3">Kanal</th><th className="py-2.5 pr-3 text-right">İşlem</th>
            </tr></thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.id} className="border-b border-border/50">
                  <td className="py-2.5 pl-4 pr-3 font-mono text-xs font-bold">{row.sku}</td>
                  <td className="max-w-[280px] truncate py-2.5 pr-3">{str(row.title)}{row.brand && <span className="ml-2 text-xs text-muted-foreground">{row.brand}</span>}</td>
                  <td className="py-2.5 pr-3 font-mono text-xs text-muted-foreground">{row.trendyol_barcode ?? <span className="text-amber-400/80">eşlenmemiş</span>}</td>
                  <td className="py-2.5 pr-3 text-right font-bold">{row.stock_on_hand}</td>
                  <td className="py-2.5 pr-3 text-right">{row.visible_stock}<span className="ml-1 text-[10px] text-muted-foreground">(-{row.stock_buffer})</span></td>
                  <td className="py-2.5 pr-3 text-right">{money(row.sale_price)}</td>
                  <td className="py-2.5 pr-3">{row.channel_enabled ? <span className="rounded-full bg-emerald-950/60 px-2 py-0.5 text-[10px] font-bold text-emerald-300">AÇIK</span> : <span className="rounded-full bg-muted px-2 py-0.5 text-[10px] font-bold text-muted-foreground">KAPALI</span>}</td>
                  <td className="py-2.5 pr-4 text-right">
                    <button type="button" onClick={() => openEdit(row)} aria-label="Düzenle" className="rounded-lg border border-border p-1.5 hover:bg-muted"><Pencil className="h-3.5 w-3.5" /></button>
                    <button type="button" onClick={() => remove(row)} aria-label="Sil" className="ml-1 rounded-lg border border-red-900/40 p-1.5 text-red-400 hover:bg-red-950/40"><Trash2 className="h-3.5 w-3.5" /></button>
                  </td>
                </tr>
              ))}
              {!loading && rows.length === 0 && <tr><td colSpan={8} className="py-8 text-center text-muted-foreground">Katalog boş — “Yeni ürün” ile ilk SKU&#39;nu ekleyin.</td></tr>}
            </tbody>
          </table>
        </div>
      )}
      <div className="mt-3 flex items-center justify-between text-xs text-muted-foreground">
        <span>Sayfa {page + 1} · toplam {total}</span>
        <div className="flex gap-2">
          <button type="button" disabled={page === 0 || loading} onClick={() => { setPage(page - 1); void load(page - 1, applied); }} className="rounded-lg border border-border px-3 py-1.5 font-bold disabled:opacity-40">← Önceki</button>
          <button type="button" disabled={loading || rows.length < 20} onClick={() => { setPage(page + 1); void load(page + 1, applied); }} className="rounded-lg border border-border px-3 py-1.5 font-bold disabled:opacity-40">Sonraki →</button>
        </div>
      </div>
      {form && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4" onClick={() => setForm(null)}>
          <form onClick={(e) => e.stopPropagation()} onSubmit={save} className="w-full max-w-lg space-y-3 rounded-2xl border border-border bg-card p-5 shadow-xl">
            <h2 className="text-base font-black">{editingId ? "Ürünü düzenle" : "Yeni ürün"}</h2>
            <div className="grid grid-cols-2 gap-3">
              <input required value={form.sku} onChange={(e) => setForm({ ...form, sku: e.target.value })} placeholder="SKU *" className={field} />
              <input required value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} placeholder="Ürün adı *" className={field} />
              <input value={form.brand} onChange={(e) => setForm({ ...form, brand: e.target.value })} placeholder="Marka" className={field} />
              <input value={form.local_category} onChange={(e) => setForm({ ...form, local_category: e.target.value })} placeholder="Yerel kategori" className={field} />
              <input value={form.trendyol_barcode} onChange={(e) => setForm({ ...form, trendyol_barcode: e.target.value })} placeholder="Trendyol barkodu (6-20 hane)" className={field} />
              <input value={form.notes} onChange={(e) => setForm({ ...form, notes: e.target.value })} placeholder="Not" className={field} />
              <input value={form.cost_price} onChange={(e) => setForm({ ...form, cost_price: e.target.value })} placeholder="Maliyet ₺" inputMode="decimal" className={field} />
              <input value={form.sale_price} onChange={(e) => setForm({ ...form, sale_price: e.target.value })} placeholder="Satış ₺" inputMode="decimal" className={field} />
              <input value={form.stock_on_hand} onChange={(e) => setForm({ ...form, stock_on_hand: e.target.value })} placeholder="Eldeki stok" inputMode="numeric" className={field} />
              <input value={form.stock_buffer} onChange={(e) => setForm({ ...form, stock_buffer: e.target.value })} placeholder="Tampon (oversell koruması)" inputMode="numeric" className={field} />
            </div>
            <label className="flex items-center gap-2 text-sm">
              <input type="checkbox" checked={form.channel_enabled} onChange={(e) => setForm({ ...form, channel_enabled: e.target.checked })} className="h-4 w-4 rounded border-input" />
              Trendyol kanalında görünsün
            </label>
            {formError && <div className="rounded-xl border border-red-900/50 bg-red-950/30 px-3 py-2 text-xs text-red-300">{formError}</div>}
            <div className="flex justify-end gap-2 pt-1">
              <button type="button" onClick={() => setForm(null)} className="rounded-xl border border-border px-4 py-2 text-sm font-bold">Vazgeç</button>
              <button type="submit" disabled={saving} className="flex items-center gap-2 rounded-xl bg-primary px-4 py-2 text-sm font-bold text-primary-foreground disabled:opacity-50">{saving && <Loader2 className="h-4 w-4 animate-spin" />}Kaydet</button>
            </div>
          </form>
        </div>
      )}
    </StoreShell>
  );
}
