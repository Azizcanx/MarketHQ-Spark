# AgentSpace Test Card

**Run ID:** `agentspace_20260916_035037`

**Task:** Hello test --timeout 30

**Timestamp:** 2026-09-16T03:51:00.067638

**Exit Code:** `0`



## Output Summary

**Stdout lines:** 16

**Output preview:**
> Query: Hello test --timeout 30
> Initializing agent...
> ────────────────────────────────────────
> 
> 
> ╭─ ☤ Hermes ───────────────────────────────────────────────────────────────────╮
> Hello. No timeout needed for this response.
> ╰──────────────────────────────────────────────────────────────────────────────╯
> 
> Resume this session with:
>   hermes --resume 20260916_035038_e74e33
> 
> Session:        20260916_035038_e74e33
> Duration:       20s
> Messages:       2 (1 user, 0 tool calls)
> 


## Diff from Previous Run

**Previous run:** `agentspace_20260916_035030`

**Previous exit code:** `0`


**Stdout differences:** `5` lines added, `7` lines removed
> Query: Hello test --timeout 30
> Hello. No timeout needed for this response.
>   hermes --resume 20260916_035038_e74e33
> Session:        20260916_035038_e74e33
> Duration:       20s
> Query: Hello --timeout 30
> Hello! The --timeout 30 is noted. How can I help you today?
>   hermes --resume 20260916_035031_8af214
>   hermes -c "Hello --timeout 30"
> Session:        20260916_035031_8af214
> Title:          Hello --timeout 30
> Duration:       26s


## Evidence

- Evidence JSON: `/opt/markethq/agentspace/agentspace/evidence/evidence_agentspace_20260916_035037.json`

- Test Card: `None`
