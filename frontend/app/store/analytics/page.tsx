"use client";

import { useEffect, useState } from "react";
import {
  ArrowDownRight,
  ArrowUpRight,
  BarChart3,
  DollarSign,
  Package,
  Percent,
  RefreshCw,
  ShoppingBag,
  TrendingUp,
  Truck,
} from "lucide-react";

import {
  DemoBadge,
  ErrorCard,
  LoadingRow,
  NotConfiguredCard,
  StatCard,
  StoreNav,
  StoreShell,
  money,
  num,
  str,
  useStoreStatus,
} from "../_components";

interface AnalyticsData {
  success: boolean;
  source?: "live" | "mock";
  currency: string;
  metrics: {
    grossSales: number;
    deliveredSales: number;
    returnedSales: number;
    netProfit: number;
    profitMargin: number;
    estimatedCommission: number;
    estimatedShipping: number;
    estimatedProductCost: number;
    orderCount: number;
    totalItemsSold: number;
    returnCount: number;
    returnRate: number;
    averageOrderValue: number;
  };
  statusBreakdown: Record<string, number>;
  inventorySummary: {
    totalProducts: number;
    totalStock: number;
    lowStockCount: number;
    outOfStockCount: number;
  };
}

export default function AnalyticsPage() {
  const status = useStoreStatus();
  const [data, setData] = useState<AnalyticsData | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchData = () => {
    setLoading(true);
    fetch("/api/store/analytics", { cache: "no-store" })
      .then((r) => r.json())
      .then((res) => {
        if (res.success === false) throw new Error(res.message || "Analiz alınamadı.");
        setData(res);
      })
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    if (status?.success && status.configured && status.reachable) {
      fetchData();
    }
  }, [status]);

  const configured = status?.success && status.configured && status.reachable;

  return (
    <StoreShell
      crumb="MarketHQ / Commerce"
      title="Finans & Kârlılık Analizi"
      description="Trendyol mağazanızın brüt satışları, komisyon, kargo maliyeti, iade oranları ve net kârlılık metrikleri."
    >
      <StoreNav />

      {status?.source === "mock" && (
        <div className="mt-4">
          <DemoBadge />
        </div>
      )}

      {!status && <LoadingRow label="Durum kontrol ediliyor…" />}
      {status && !status.success && <ErrorCard message={str(status.error, "Bağlantı hatası.")} />}
      {status?.success && !status.configured && <NotConfiguredCard />}

      {configured && (
        <div className="mt-4 space-y-6">
          <div className="flex items-center justify-between">
            <span className="text-xs text-muted-foreground">
              Otomatik hesaplanan komisyon (~%18) ve kargo kesintileri baz alınmıştır.
            </span>
            <button
              onClick={fetchData}
              disabled={loading}
              className="inline-flex items-center gap-2 rounded-lg border border-border bg-card px-3 py-1.5 text-xs font-semibold text-foreground transition hover:bg-muted disabled:opacity-50"
            >
              <RefreshCw className={`h-3.5 w-3.5 ${loading ? "animate-spin" : ""}`} />
              Yenile
            </button>
          </div>

          {loading && !data && <LoadingRow label="Finansal veriler hesaplanıyor…" />}
          {error && <ErrorCard message={error} />}

          {data && (
            <>
              {/* Ana Finansal Metrikler */}
              <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
                <div className="rounded-2xl border border-emerald-900/40 bg-emerald-950/20 p-4">
                  <div className="flex items-center justify-between text-[10px] font-bold uppercase tracking-widest text-emerald-400">
                    <span>Brüt Ciro (GMV)</span>
                    <TrendingUp className="h-4 w-4" />
                  </div>
                  <div className="mt-2 text-2xl font-black text-emerald-300">
                    {money(data.metrics.grossSales)}
                  </div>
                  <div className="mt-1 text-xs text-emerald-500/80">
                    Toplam {data.metrics.orderCount} sipariş
                  </div>
                </div>

                <div className="rounded-2xl border border-blue-900/40 bg-blue-950/20 p-4">
                  <div className="flex items-center justify-between text-[10px] font-bold uppercase tracking-widest text-blue-400">
                    <span>Tahmini Net Kâr</span>
                    <DollarSign className="h-4 w-4" />
                  </div>
                  <div className="mt-2 text-2xl font-black text-blue-300">
                    {money(data.metrics.netProfit)}
                  </div>
                  <div className="mt-1 flex items-center gap-1 text-xs text-blue-400">
                    <Percent className="h-3 w-3" />
                    <span>%{data.metrics.profitMargin} Net Marj</span>
                  </div>
                </div>

                <div className="rounded-2xl border border-border bg-card p-4">
                  <div className="flex items-center justify-between text-[10px] font-bold uppercase tracking-widest text-muted-foreground">
                    <span>Ortalama Sepet (AOV)</span>
                    <ShoppingBag className="h-4 w-4 text-muted-foreground" />
                  </div>
                  <div className="mt-2 text-2xl font-black text-foreground">
                    {money(data.metrics.averageOrderValue)}
                  </div>
                  <div className="mt-1 text-xs text-muted-foreground">
                    {data.metrics.totalItemsSold} adet ürün satıldı
                  </div>
                </div>

                <div className="rounded-2xl border border-rose-900/40 bg-rose-950/20 p-4">
                  <div className="flex items-center justify-between text-[10px] font-bold uppercase tracking-widest text-rose-400">
                    <span>İade Oranı</span>
                    <ArrowDownRight className="h-4 w-4" />
                  </div>
                  <div className="mt-2 text-2xl font-black text-rose-300">
                    %{data.metrics.returnRate}
                  </div>
                  <div className="mt-1 text-xs text-rose-400/80">
                    {data.metrics.returnCount} iade ({money(data.metrics.returnedSales)})
                  </div>
                </div>
              </div>

              {/* Detaylı Gider ve Dağılım Kartları */}
              <div className="grid gap-4 lg:grid-cols-2">
                {/* Gider Dağılımı */}
                <div className="rounded-2xl border border-border bg-card p-5">
                  <div className="flex items-center gap-2 text-sm font-bold text-foreground">
                    <BarChart3 className="h-4 w-4 text-primary" />
                    Maliyet & Kesinti Dökümü
                  </div>
                  <div className="mt-4 space-y-3">
                    <div className="flex items-center justify-between border-b border-border/50 pb-2 text-sm">
                      <span className="text-muted-foreground">Ürün Maliyeti (COGS ~%45):</span>
                      <span className="font-mono font-medium text-foreground">
                        {money(data.metrics.estimatedProductCost)}
                      </span>
                    </div>
                    <div className="flex items-center justify-between border-b border-border/50 pb-2 text-sm">
                      <span className="text-muted-foreground">Pazaryeri Komisyonu (~%18):</span>
                      <span className="font-mono font-medium text-amber-400">
                        {money(data.metrics.estimatedCommission)}
                      </span>
                    </div>
                    <div className="flex items-center justify-between border-b border-border/50 pb-2 text-sm">
                      <span className="text-muted-foreground">Kargo & Operasyon:</span>
                      <span className="font-mono font-medium text-amber-400">
                        {money(data.metrics.estimatedShipping)}
                      </span>
                    </div>
                    <div className="flex items-center justify-between pt-1 text-sm font-bold">
                      <span className="text-emerald-400">Tahmini Net Kazanç:</span>
                      <span className="font-mono text-emerald-300">
                        {money(data.metrics.netProfit)}
                      </span>
                    </div>
                  </div>
                </div>

                {/* Sipariş Durumları & Envanter Özeti */}
                <div className="rounded-2xl border border-border bg-card p-5">
                  <div className="flex items-center gap-2 text-sm font-bold text-foreground">
                    <Package className="h-4 w-4 text-primary" />
                    Sipariş Durumu & Envanter Sağlığı
                  </div>
                  <div className="mt-4 grid grid-cols-2 gap-3">
                    <div className="rounded-xl border border-border/60 bg-muted/30 p-3">
                      <div className="text-[10px] uppercase tracking-wider text-muted-foreground">
                        Teslim Edilenler
                      </div>
                      <div className="mt-1 text-lg font-bold text-foreground">
                        {data.statusBreakdown["Delivered"] || 0}
                      </div>
                    </div>
                    <div className="rounded-xl border border-border/60 bg-muted/30 p-3">
                      <div className="text-[10px] uppercase tracking-wider text-muted-foreground">
                        Yoldaki / Hazırlanan
                      </div>
                      <div className="mt-1 text-lg font-bold text-foreground">
                        {(data.statusBreakdown["Shipped"] || 0) +
                          (data.statusBreakdown["InProcess"] || 0) +
                          (data.statusBreakdown["Created"] || 0) +
                          (data.statusBreakdown["Awaiting"] || 0)}
                      </div>
                    </div>
                    <div className="rounded-xl border border-amber-900/40 bg-amber-950/20 p-3">
                      <div className="text-[10px] uppercase tracking-wider text-amber-400">
                        Kritik Stok (≤ 5)
                      </div>
                      <div className="mt-1 text-lg font-bold text-amber-300">
                        {data.inventorySummary.lowStockCount} ürün
                      </div>
                    </div>
                    <div className="rounded-xl border border-rose-900/40 bg-rose-950/20 p-3">
                      <div className="text-[10px] uppercase tracking-wider text-rose-400">
                        Tükenen Stok (0)
                      </div>
                      <div className="mt-1 text-lg font-bold text-rose-300">
                        {data.inventorySummary.outOfStockCount} ürün
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </>
          )}
        </div>
      )}
    </StoreShell>
  );
}
