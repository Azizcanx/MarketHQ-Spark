# AgentSpace Test Card

**Run ID:** `agentspace_20260919_002235`

**Task:** Copy path test

**Timestamp:** 2026-09-19T00:22:35.071292

**Exit Code:** `1`



## Output Summary

_No stdout captured_

**Stderr lines:** 15

**Errors:**
> Traceback (most recent call last):
>   File "/opt/markethq/hermes-run", line 5, in <module>
>     from hermes_cli.main import main
>   File "/opt/markethq/hermes-agent/hermes_cli/main.py", line 628, in <module>
>     load_hermes_dotenv(project_env=PROJECT_ROOT / ".env")
>   File "/opt/markethq/hermes-agent/hermes_cli/env_loader.py", line 357, in load_hermes_dotenv
>     if user_env.exists():  # normalize formatting / strip NULs before parsing
>        ^^^^^^^^^^^^^^^^^
>   File "/usr/lib/python3.12/pathlib.py", line 862, in exists
>     self.stat(follow_symlinks=follow_symlinks)
>   File "/usr/lib/python3.12/pathlib.py", line 842, in stat
>     return os.stat(self, follow_symlinks=follow_symlinks)
>            ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
> PermissionError: [Errno 13] Permission denied: '/home/markethq/.hermes/.env'
> 


## Evidence

- Evidence JSON: `/opt/markethq/agentspace/evidence/evidence_agentspace_20260919_002235.json`

- Test Card: `None`
