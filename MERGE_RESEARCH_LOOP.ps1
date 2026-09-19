$ErrorActionPreference = "Stop"

# MarketHQ – research loop consolidation
# 1) Backup current canonical agents
Copy-Item .\agents\brain_research_agent_v4.py .\agents\brain_research_agent_v4_pre_merge_backup.py -Force
Copy-Item .\agents\brain_research_evidence_update_v1.py .\agents\brain_research_evidence_update_v1_pre_merge_backup.py -Force

# 2) Copy the two final files you downloaded into the canonical filenames.
Copy-Item .\agents\brain_research_agent_v4_2_paper_gap.py .\agents\brain_research_agent_v4.py -Force
Copy-Item .\agents\brain_research_evidence_update_v2_fixed2.py .\agents\brain_research_evidence_update_v2.py -Force

Write-Host ""
Write-Host "MERGE OK"
Write-Host "Canonical Research Agent : agents\brain_research_agent_v4.py"
Write-Host "Canonical Evidence Update: agents\brain_research_evidence_update_v2.py"
Write-Host ""
Write-Host "1) Run Evidence Update V2:"
Write-Host "   .\.venv\Scripts\python.exe .\agents\brain_research_evidence_update_v2.py"
Write-Host ""
Write-Host "2) Then run Research Agent V4:"
Write-Host "   .\.venv\Scripts\python.exe .\agents\brain_research_agent_v4.py"

