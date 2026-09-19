"use client";

import Link from "next/link";

import {
  DemoBadge,
  ErrorCard,
  LoadingRow,
  NotConfiguredCard,
  StatCard,
  StoreNav,
  StoreShell,
  str,
  useStoreStatus,
} from "./_components";

export default function StoreOverviewPage() {
  const status = useStoreStatus();

  return (
    <StoreShell
      crumb="MarketHQ / Commerce"
      title="Store Overview"
      description="Trendyol mağazanın salt-okunur görünümü. Ürün, stok ve siparişler — yazma işlemi yok."
    >
      <StoreNav />
      {status?.source === "mock" && <div className="mt-4"><DemoBadge /></div>}
      {!status && <LoadingRow label="Mağaza durumu yükleniyor…" />}
      {status && !status.success && <ErrorCard message={str(status.error, "Durum alınamadı.")} />}
      {status?.success && !status.configured && <NotConfiguredCard />}
      {status?.success && status.configured && !status.reachable && (
        <ErrorCard
          message={`Trendyol'a erişilemedi: ${str(status.error, "bağlantı hatası")}. Bilgileri kontrol et.`}
        />
      )}
      {status?.success && status.configured && status.reachable && (
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          <StatCard label="Satıcı" value={str(status.sellerId, "—")} sub="maskeli" />
          <StatCard label="Onaylı ürün" value={str(status.productTotal, "—")} sub="Trendyol kataloğu" />
          <StatCard label="Sipariş" value={str(status.orderTotal, "—")} sub="son durum" />
          <StatCard label="Mod" value="Salt-okunur" sub="yazma kapalı" />
        </div>
      )}
      <div className="grid gap-3 sm:grid-cols-2 md:grid-cols-3">
        {[
          { href: "/store/products", title: "Products", desc: "Onaylı ürünleri listele, barkodla ara." },
          { href: "/store/inventory", title: "Inventory", desc: "Stok seviyeleri, kritik stoklar önde." },
          { href: "/store/orders", title: "Orders", desc: "Sipariş paketleri, duruma göre filtrele." },
          { href: "/store/catalog", title: "Catalog", desc: "Veritabanı SKU ve Trendyol barkod eşleme." },
          { href: "/store/analytics", title: "Finans & Analiz", desc: "Ciro, net kârlılık, komisyon ve kargo giderleri." },
          { href: "/store/agentspace", title: "Agent AI Terminal", desc: "Hermes Agent ile stok tahmini ve araştırma çalıştırma." },
        ].map((card) => (
          <Link
            key={card.href}
            href={card.href}
            className="rounded-2xl border border-border bg-card p-5 transition hover:border-primary/50 hover:shadow-sm"
          >
            <div className="text-sm font-bold text-foreground">{card.title}</div>
            <p className="mt-1 text-xs text-muted-foreground">{card.desc}</p>
          </Link>
        ))}
      </div>
    </StoreShell>
  );
}
