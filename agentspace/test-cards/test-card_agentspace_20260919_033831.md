# AgentSpace Test Card

**Run ID:** `agentspace_20260919_033831`

**Task:** sistem durumu kontrol

**Timestamp:** 2026-09-19T03:38:31.819229

**Exit Code:** `0`



## Output Summary

**Stdout lines:** 36

**Output preview:**
> Çalışan servisler:
> - Postgres (docker + local) — port 5432
> - MarketHQ API (uvicorn) — port 9999, uptime ~2 gün
> - Next.js frontend — port 3000 (yaklaşık 20 dk önce başladı)
> - CodeGraph indexer — CPU yükü yüksek ama normal (dosya tarama devam ediyor)
> - Pyright LSP
> 
> Herhangi bir hata yok, hiçbir süreç crash yok.
> ╰──────────────────────────────────────────────────────────────────────────────╯
> ⚠ Auxiliary title generation failed: HTTP 400: This request is not valid. Check the model name and other parameters. Additional info: Provider returned error
> 
> Resume this session with:
>   hermes --resume 20260919_033819_8d5bcc
>   hermes -c "[Context: Recursion guard: skip.] sistem durumu…"
> 
> Session:        20260919_033819_8d5bcc
> Title:          [Context: Recursion guard: skip.] sistem durumu…
> Duration:       10s
> Messages:       4 (1 user, 2 tool calls)
> 


## Evidence

- Evidence JSON: `/opt/markethq/agentspace/evidence/evidence_agentspace_20260919_033831.json`

- Test Card: `None`
