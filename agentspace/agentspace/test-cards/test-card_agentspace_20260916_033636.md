# AgentSpace Test Card

**Run ID:** `agentspace_20260916_033636`

**Task:** Hello world

**Timestamp:** 2026-09-16T03:36:44.486569

**Exit Code:** `0`



## Output Summary

**Stdout lines:** 16

**Output preview:**
> Query: Hello world
> Initializing agent...
> ────────────────────────────────────────
> 
> 
> ╭─ ☤ Hermes ───────────────────────────────────────────────────────────────────╮
> Hello!
> ╰──────────────────────────────────────────────────────────────────────────────╯
> 
> Resume this session with:
>   hermes --resume 20260916_033637_353465
> 
> Session:        20260916_033637_353465
> Duration:       6s
> Messages:       2 (1 user, 0 tool calls)
> 


## Diff from Previous Run

**Previous run:** `agentspace_20260916_033543`

**Previous exit code:** `0`


**Stdout differences:** `6` lines added, `14` lines removed
> Query: Hello world
> Hello!
>   hermes --resume 20260916_033637_353465
> Session:        20260916_033637_353465
> Duration:       6s
> Messages:       2 (1 user, 0 tool calls)
> Query: --timeout 60 Hello test
>   ┊ 💻 preparing terminal…
>   ┊ 💻 $         --timeout 60 Hello test  0.4s [exit 2]
>   ┊ 💻 preparing terminal…
>   ┊ 💻 $         Hello test  0.3s [exit 127]
>   ┊ 💻 preparing terminal…
>   ┊ 💻 $         echo "Hello test"  0.4s
> Hello test — exit code 0.
>   hermes --resume 20260916_033545_35ee7a
>   hermes -c "--timeout 60 Hello test"
> Session:        20260916_033545_35ee7a
> Title:          --timeout 60 Hello test
> Duration:       26s
> Messages:       8 (1 user, 6 tool calls)


## Evidence

- Evidence JSON: `/opt/markethq/agentspace/agentspace/evidence/evidence_agentspace_20260916_033636.json`

- Test Card: `None`
