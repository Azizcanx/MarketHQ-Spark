# AgentSpace Test Card

**Run ID:** `agentspace_20260916_034231`

**Task:** Hello test

**Timestamp:** 2026-09-16T03:42:41.024269

**Exit Code:** `0`



## Output Summary

**Stdout lines:** 16

**Output preview:**
> Query: Hello test
> Initializing agent...
> ────────────────────────────────────────
> 
> 
> ╭─ ☤ Hermes ───────────────────────────────────────────────────────────────────╮
> Hello.
> ╰──────────────────────────────────────────────────────────────────────────────╯
> 
> Resume this session with:
>   hermes --resume 20260916_034233_516b23
> 
> Session:        20260916_034233_516b23
> Duration:       6s
> Messages:       2 (1 user, 0 tool calls)
> 


## Diff from Previous Run

**Previous run:** `agentspace_20260916_034205`

**Previous exit code:** `0`


**Stdout differences:** `5` lines added, `7` lines removed
> Query: Hello test
> Hello.
>   hermes --resume 20260916_034233_516b23
> Session:        20260916_034233_516b23
> Duration:       6s
> Query: Hello world --timeout 10
> Hello! The --timeout 10 flag wasn't recognized as a command, but hello! How can I help?
>   hermes --resume 20260916_034207_1f1d19
>   hermes -c "Hello world --timeout 10"
> Session:        20260916_034207_1f1d19
> Title:          Hello world --timeout 10
> Duration:       11s


## Evidence

- Evidence JSON: `/opt/markethq/agentspace/agentspace/evidence/evidence_agentspace_20260916_034231.json`

- Test Card: `None`
