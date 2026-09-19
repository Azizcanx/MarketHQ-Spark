# AgentSpace Test Card

**Run ID:** `agentspace_20260916_033728`

**Task:** burdamısın --timeout 10

**Timestamp:** 2026-09-16T03:37:39.960111

**Exit Code:** `0`



## Output Summary

**Stdout lines:** 18

**Output preview:**
> Query: burdamısın --timeout 10
> Initializing agent...
> ────────────────────────────────────────
> 
> 
> ╭─ ☤ Hermes ───────────────────────────────────────────────────────────────────╮
> Anladım. --timeout 10 parametresi not alınmıştır. Hermes Agent'da timeout ayarları nasıl yapılır?
> ╰──────────────────────────────────────────────────────────────────────────────╯
> 
> Resume this session with:
>   hermes --resume 20260916_033731_97c211
>   hermes -c "burdamısın --timeout 10"
> 
> Session:        20260916_033731_97c211
> Title:          burdamısın --timeout 10
> Duration:       8s
> Messages:       2 (1 user, 0 tool calls)
> 


## Diff from Previous Run

**Previous run:** `agentspace_20260916_033708`

**Previous exit code:** `0`


**Stdout differences:** `7` lines added, `7` lines removed
> Query: burdamısın --timeout 10
> Anladım. --timeout 10 parametresi not alınmıştır. Hermes Agent'da timeout ayarları nasıl yapılır?
>   hermes --resume 20260916_033731_97c211
>   hermes -c "burdamısın --timeout 10"
> Session:        20260916_033731_97c211
> Title:          burdamısın --timeout 10
> Duration:       8s
> Query: Hello test --timeout 30
> Test received. How can I help?
>   hermes --resume 20260916_033709_3c039b
>   hermes -c "Hello test --timeout 30"
> Session:        20260916_033709_3c039b
> Title:          Hello test --timeout 30
> Duration:       11s


## Evidence

- Evidence JSON: `/opt/markethq/agentspace/agentspace/evidence/evidence_agentspace_20260916_033728.json`

- Test Card: `None`
