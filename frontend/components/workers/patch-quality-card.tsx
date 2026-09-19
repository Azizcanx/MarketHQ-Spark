"use client";

import type { WorkerPatchQuality } from "./patch-quality-v2";

export function PatchQualityCard({ quality }: { quality: WorkerPatchQuality | null }) {
 if(!quality) return <div className="rounded-xl border border-border p-4"><h3 className="font-semibold">Patch Quality</h3><p className="mt-2 text-xs text-muted-foreground">Bir worker seçildiğinde patch kalite değerlendirmesi burada görünür.</p></div>;
 const tone=quality.unsafeEvidence||!quality.scopeCompliant?"bg-amber-100 text-amber-800":quality.score>=80?"bg-emerald-100 text-emerald-800":"bg-muted text-muted-foreground";
 return <div className="rounded-xl border border-border p-4 space-y-3"><div className="flex items-center justify-between"><div><p className="text-xs text-muted-foreground">Patch assessment</p><h3 className="font-semibold">Patch Quality</h3></div><span className={`rounded-full px-3 py-1 text-xs font-bold ${tone}`}>{quality.grade} · {quality.score}/100</span></div><div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4 text-xs"><div><span className="text-muted-foreground">Patch</span><div className="font-medium">{quality.hasPatch?"YES":"NO"}</div></div><div><span className="text-muted-foreground">Scope</span><div className="font-medium">{quality.scopeCompliant?"COMPLIANT":"OUT OF SCOPE"}</div></div><div><span className="text-muted-foreground">Validation</span><div className="font-medium">{quality.validationPassed?"PASSED":quality.validationAttempted?"FAILED":"NOT RUN"}</div></div><div><span className="text-muted-foreground">Evidence</span><div className="font-medium">{quality.evidenceQuality}</div></div></div><div className="rounded-lg bg-muted/40 p-3 text-xs"><span className="font-semibold">Decision:</span> {quality.recommendation} · {quality.reason}</div></div>;
}
