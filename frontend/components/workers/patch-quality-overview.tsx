"use client";

import { useEffect, useState } from "react";
import type { WorkerPatchQuality } from "./patch-quality-v2";

type Row={taskId:string;title:string;status:string;quality:WorkerPatchQuality};
export function PatchQualityOverview(){
 const [rows,setRows]=useState<Row[]>([]);
 async function load(){try{const r=await fetch("/api/workers?limit=25",{cache:"no-store"});const p=await r.json();if(r.ok&&p.success)setRows((p.records??[]).map((x:{taskId:string;status:string;task?:{title?:string};patchQuality:WorkerPatchQuality})=>({taskId:x.taskId,title:x.task?.title??x.taskId,status:x.status,quality:x.patchQuality})).filter((x:Row)=>Boolean(x.quality)));}catch{setRows([]);}}
 useEffect(()=>{void load();const t=window.setInterval(()=>void load(),5000);return()=>window.clearInterval(t);},[]);
 return <section className="rounded-2xl border border-border bg-card p-6 shadow-sm"><div className="mb-4"><p className="text-xs text-muted-foreground">Validation + evidence decision layer</p><h2 className="text-xl font-bold">Patch Quality Overview</h2><p className="mt-1 text-xs text-muted-foreground">Scope, validation, evidence and safety are condensed into a deterministic acceptance signal.</p></div>{rows.length===0?<p className="text-sm text-muted-foreground">Henüz değerlendirilecek patch yok.</p>:<div className="space-y-2">{rows.map(row=><div key={row.taskId} className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-border p-3"><div className="min-w-0"><div className="truncate text-sm font-medium">{row.title}</div><div className="text-[11px] text-muted-foreground">{row.status} · {row.quality.changedFileCount} changed · validation {row.quality.validationPassed?"passed":row.quality.validationAttempted?"failed":"not run"}</div></div><div className="flex items-center gap-2"><span className="rounded-full bg-muted px-2 py-1 text-[11px] font-semibold">{row.quality.recommendation}</span><span className="rounded-full bg-muted px-2 py-1 text-[11px] font-bold">{row.quality.grade} · {row.quality.score}</span></div></div>)}</div>}</section>;
}
