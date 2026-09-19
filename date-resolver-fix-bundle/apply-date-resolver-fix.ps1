$ErrorActionPreference = "Stop"

$root = (Get-Location).Path
$agentsDir = Join-Path $root "frontend\components\agents"

if (-not (Test-Path $agentsDir)) {
  throw "frontend\components\agents bulunamadi. Bu scripti MarketHQ proje kokunde calistir."
}

$typesFile = Join-Path $agentsDir "agent-types.ts"
$registryFile = Join-Path $agentsDir "agent-registry.ts"
$registerFile = Join-Path $agentsDir "register-agents.ts"
$resolverTarget = Join-Path $agentsDir "research-date-resolver-agent-v1.ts"
$generatorTarget = Join-Path $agentsDir "experiment-generator-agent-v4-date-resolver.ts"

foreach ($f in @($typesFile, $registryFile, $registerFile)) {
  if (-not (Test-Path $f)) { throw "Dosya bulunamadi: $f" }
}

$bundleDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$resolverSource = Join-Path $bundleDir "research-date-resolver-agent-v1.ts"
$generatorSource = Join-Path $bundleDir "experiment-generator-agent-v4-date-resolver.ts"

foreach ($f in @($resolverSource, $generatorSource)) {
  if (-not (Test-Path $f)) { throw "Bundle dosyasi bulunamadi: $f" }
}

# Backup once per run
$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$backupDir = Join-Path $agentsDir "_date_resolver_backup_$stamp"
New-Item -ItemType Directory -Path $backupDir | Out-Null
Copy-Item $typesFile $backupDir
Copy-Item $registryFile $backupDir
Copy-Item $registerFile $backupDir
if (Test-Path $resolverTarget) { Copy-Item $resolverTarget $backupDir }
if (Test-Path $generatorTarget) { Copy-Item $generatorTarget $backupDir }

Copy-Item $resolverSource $resolverTarget -Force
Copy-Item $generatorSource $generatorTarget -Force

# 1) AgentId union
$types = Get-Content $typesFile -Raw
if ($types -notmatch '"research-date-resolver"') {
  $m = [regex]::Match($types, '(?s)(type\s+AgentId\s*=)(.*?)(;)')
  if (-not $m.Success) { throw "agent-types.ts icinde AgentId union bulunamadi." }

  $body = $m.Groups[2].Value
  $newBody = $body.TrimEnd() + "`r`n  | \"research-date-resolver\"`r`n"
  $types = $types.Substring(0, $m.Groups[2].Index) + $newBody + $types.Substring($m.Groups[3].Index)
  Set-Content $typesFile $types -Encoding UTF8
}

# 2) Registry
$registry = Get-Content $registryFile -Raw

if ($registry -notmatch '"research-date-resolver"\s*:') {
  $resolverBlock = @'
  "research-date-resolver": [
    "research-queue",
    "research-decision",
    "market-data",
  ],
'@

  $q = [regex]::Match($registry, '(?s)("research-queue"\s*:\s*\[.*?\],\s*\r?\n)')
  if ($q.Success) {
    $registry = $registry.Substring(0, $q.Index + $q.Length) + $resolverBlock + $registry.Substring($q.Index + $q.Length)
  } else {
    throw "agent-registry.ts icinde research-queue kaydi bulunamadi."
  }
}

if ($registry -notmatch '(?s)"experiment-generator"\s*:\s*\[.*?"research-date-resolver"') {
  $g = [regex]::Match($registry, '(?s)("experiment-generator"\s*:\s*\[)(.*?)(\])')
  if (-not $g.Success) { throw "agent-registry.ts icinde experiment-generator dependency array bulunamadi." }

  $body = $g.Groups[2].Value
  if ($body -match '"research-decision"') {
    $body = [regex]::Replace($body, '("research-decision"\s*,?)', '$1`r`n    "research-date-resolver",', 1)
  } else {
    $body = "`r`n    \"research-date-resolver\",$body"
  }

  $registry = $registry.Substring(0, $g.Groups[2].Index) + $body + $registry.Substring($g.Groups[3].Index)
}

Set-Content $registryFile $registry -Encoding UTF8

# 3) register-agents
$register = Get-Content $registerFile -Raw

if ($register -notmatch 'research-date-resolver-agent-v1') {
  $imports = 'import { registerResearchDateResolverAgent } from "./research-date-resolver-agent-v1";' + "`r`n"
  $register = $imports + $register
}

if ($register -notmatch 'registerResearchDateResolverAgent\(\)') {
  $m = [regex]::Match($register, '(function\s+registerDefaultAgents\s*\(\)\s*\{)')
  if (-not $m.Success) { throw "register-agents.ts icinde registerDefaultAgents() bulunamadi." }
  $register = $register.Substring(0, $m.Index + $m.Length) + "`r`n  registerResearchDateResolverAgent();" + $register.Substring($m.Index + $m.Length)
}

Set-Content $registerFile $register -Encoding UTF8

Write-Host ""
Write-Host "DATE RESOLVER FIX UYGULANDI." -ForegroundColor Green
Write-Host "Backup: $backupDir" -ForegroundColor DarkGray
Write-Host ""
Write-Host "Simdi:" -ForegroundColor Cyan
Write-Host "  cd frontend"
Write-Host "  npm run build"
Write-Host ""
