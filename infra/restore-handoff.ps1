param([Parameter(Mandatory=$true)][string]$BundleRoot, [switch]$Force)
$ErrorActionPreference = 'Stop'
if (-not $Force) { throw 'Pass -Force to copy saved runs into the current workspace' }
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$bundle = (Resolve-Path -LiteralPath $BundleRoot).Path
$manifest = Get-Content -LiteralPath (Join-Path $bundle 'handoff.json') -Raw | ConvertFrom-Json
Set-Location $root
$savedRuns = Join-Path $bundle 'runs'
if (Test-Path -LiteralPath $savedRuns) {
  $target = Join-Path $root 'runs'
  New-Item -ItemType Directory -Force -Path $target | Out-Null
  Copy-Item -Path (Join-Path $savedRuns '*') -Destination $target -Recurse -Force
}
docker compose up --build -d --wait --remove-orphans
if ($LASTEXITCODE -ne 0) { throw 'Online stack startup failed' }
Write-Output 'Handoff restored'
