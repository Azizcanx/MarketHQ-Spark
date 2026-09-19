"use client";

import type { ReactNode } from "react";

type WhyProps = {
  setup: {
    direction: string;
    regime: string;
    timeframe: string;
    entry_price: number;
    entry_zone: [number, number];
    invalidation: number | null;
    target: number | null;
    supporting: string[];
    opposing: string[];
    agreement: {
      long: number;
      short: number;
      neutral: number;
      consensus: string;
      conflict: boolean;
      share?: number;
      weighted?: { lean: string; long_w: number; short_w: number; regime: string; demoted?: string[] };
    };
    invalidation_rule: string;
    target_rule: string;
  } | null;
  oosWindows?: string[];
  scoreboardNote?: string | null;
  spreadNote?: string | null;
  evolutionObservations?: string[] | null;
  evolutionQuestions?: string[] | null;
};

function Row({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex items-baseline justify-between gap-3 py-1 text-[12px] leading-5">
      <span className="shrink-0 font-mono text-[10px] uppercase tracking-[0.14em] text-[#8a8f98]">{label}</span>
      <span className="min-w-0 text-right text-[#d0d6e0]">{children}</span>
    </div>
  );
}

// Research-only aciklama paneli: gercek setup kanitini gosterir, oneri vermez.
export function WhyPanel({ setup, oosWindows, scoreboardNote, spreadNote, evolutionObservations, evolutionQuestions }: WhyProps) {
  if (!setup) return null;
  const agreeShare = setup.agreement.share !== undefined ? ` (${(setup.agreement.share * 100).toFixed(0)}%)` : "";
  return (
    <div className="rounded-xl border border-[rgba(255,255,255,0.08)] bg-[rgba(255,255,255,0.02)] p-4 text-sm text-[#d0d6e0]">
      <div className="mb-1 font-mono text-[10px] font-bold uppercase tracking-[0.22em] text-[#8a8f98]">WHY — araştırma kanıtı</div>
      <div className="divide-y divide-[rgba(255,255,255,0.06)]">
        <Row label="Yön / Rejim / TF">
          <span className="font-mono">{setup.direction} · {setup.regime} · {setup.timeframe}</span>
        </Row>
        <Row label="Entry / Zon">
          <span className="font-mono">{setup.entry_price} · [{setup.entry_zone[0].toFixed(2)}, {setup.entry_zone[1].toFixed(2)}]</span>
        </Row>
        <Row label="İptal"><span className="text-[12px]">{setup.invalidation_rule}</span></Row>
        <Row label="Hedef"><span className="text-[12px]">{setup.target_rule}</span></Row>
        <Row label="Destekleyen">
          <span className="font-mono text-[11px]">{setup.supporting.join(", ") || "—"}</span>
        </Row>
        <Row label="Karşıt">
          <span className="font-mono text-[11px]">{setup.opposing.join(", ") || "—"}</span>
        </Row>
        <Row label="Agreement">
          <span className="font-mono text-[11px]">
            L{setup.agreement.long}/S{setup.agreement.short}/N{setup.agreement.neutral}
            {agreeShare}
            {setup.agreement.conflict ? " · conflict" : ""}
          </span>
        </Row>
        {setup.agreement.weighted && (
          <Row label="Rejim-oy">
            <span className="font-mono text-[11px]">
              {setup.agreement.weighted.lean} (L{setup.agreement.weighted.long_w}/S{setup.agreement.weighted.short_w})
              {setup.agreement.weighted.demoted && setup.agreement.weighted.demoted.length > 0 &&
                ` · düşük ağırlık: ${setup.agreement.weighted.demoted.join(", ")}`}
            </span>
          </Row>
        )}
        {spreadNote && (
          <Row label="Spread"><span className="font-mono text-[11px]">{spreadNote}</span></Row>
        )}
        {evolutionObservations && evolutionObservations.length > 0 && (
          <div className="py-1">
            <div className="font-mono text-[10px] uppercase tracking-[0.14em] text-[#8a8f98]">Evolution</div>
            <ul className="mt-1 space-y-0.5 text-[12px] leading-5 text-[#d0d6e0]">
              {evolutionObservations.slice(0, 3).map((o, i) => (
                <li key={i} className="truncate" title={o}>· {o}</li>
              ))}
            </ul>
            {evolutionQuestions && evolutionQuestions.length > 0 && (
              <div className="mt-0.5 truncate text-[11px] text-[#8a8f98]" title={evolutionQuestions[0]}>
                ? {evolutionQuestions[0]}
              </div>
            )}
          </div>
        )}
        {oosWindows && oosWindows.length > 0 && (
          <Row label="OOS">
            <span className="font-mono text-[11px]">[{oosWindows.join(" | ")}]</span>
          </Row>
        )}
        {scoreboardNote && (
          <Row label="Skor tablosu"><span className="text-[11px]">{scoreboardNote}</span></Row>
        )}
      </div>
    </div>
  );
}
