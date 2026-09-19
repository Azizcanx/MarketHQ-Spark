# AgentSpace Test Card

**Run ID:** `agentspace_20260916_035030`

**Task:** Hello --timeout 30

**Timestamp:** 2026-09-16T03:50:59.385188

**Exit Code:** `0`



## Output Summary

**Stdout lines:** 18

**Output preview:**
> Query: Hello --timeout 30
> Initializing agent...
> ────────────────────────────────────────
> 
> 
> ╭─ ☤ Hermes ───────────────────────────────────────────────────────────────────╮
> Hello! The --timeout 30 is noted. How can I help you today?
> ╰──────────────────────────────────────────────────────────────────────────────╯
> 
> Resume this session with:
>   hermes --resume 20260916_035031_8af214
>   hermes -c "Hello --timeout 30"
> 
> Session:        20260916_035031_8af214
> Title:          Hello --timeout 30
> Duration:       26s
> Messages:       2 (1 user, 0 tool calls)
> 


## Diff from Previous Run

**Previous run:** `agentspace_20260916_034925`

**Previous exit code:** `0`


**Stdout differences:** `7` lines added, `5` lines removed
> Query: Hello --timeout 30
> Hello! The --timeout 30 is noted. How can I help you today?
>   hermes --resume 20260916_035031_8af214
>   hermes -c "Hello --timeout 30"
> Session:        20260916_035031_8af214
> Title:          Hello --timeout 30
> Duration:       26s
> Query: Hello test --timeout 30
> Hello.
>   hermes --resume 20260916_034928_5f1a5b
> Session:        20260916_034928_5f1a5b
> Duration:       8s


## Evidence

- Evidence JSON: `/opt/markethq/agentspace/agentspace/evidence/evidence_agentspace_20260916_035030.json`

- Test Card: `None`
