# AgentSpace Test Card

**Run ID:** `agentspace_20260916_033543`

**Task:** --timeout 60 Hello test

**Timestamp:** 2026-09-16T03:36:12.759838

**Exit Code:** `0`



## Output Summary

**Stdout lines:** 24

**Output preview:**
>   ┊ 💻 preparing terminal…
>   ┊ 💻 $         --timeout 60 Hello test  0.4s [exit 2]
>   ┊ 💻 preparing terminal…
>   ┊ 💻 $         Hello test  0.3s [exit 127]
>   ┊ 💻 preparing terminal…
>   ┊ 💻 $         echo "Hello test"  0.4s
> 
> ╭─ ☤ Hermes ───────────────────────────────────────────────────────────────────╮
> Hello test — exit code 0.
> ╰──────────────────────────────────────────────────────────────────────────────╯
> 
> Resume this session with:
>   hermes --resume 20260916_033545_35ee7a
>   hermes -c "--timeout 60 Hello test"
> 
> Session:        20260916_033545_35ee7a
> Title:          --timeout 60 Hello test
> Duration:       26s
> Messages:       8 (1 user, 6 tool calls)
> 


## Diff from Previous Run

**Previous run:** `agentspace_20260916_033423`

**Previous exit code:** `0`


**Stdout differences:** `14` lines added, `6` lines removed
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
> Query: burdamısın
> Merhaba! Size nasıl yardımcı olabilirim?
>   hermes --resume 20260916_033425_3a6ec9
> Session:        20260916_033425_3a6ec9
> Duration:       8s
> Messages:       2 (1 user, 0 tool calls)


## Evidence

- Evidence JSON: `/opt/markethq/agentspace/agentspace/evidence/evidence_agentspace_20260916_033543.json`

- Test Card: `None`
