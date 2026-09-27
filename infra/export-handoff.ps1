param([switch]$IncludeDataset)
$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
Set-Location $root
if (-not (Get-Command git -ErrorAction SilentlyContinue) -or -not (Get-Command tar -ErrorAction SilentlyContinue)) { throw 'git and tar are required' }
if ((git status --porcelain).Length -ne 0) { throw 'Commit or stash changes before export' }
if ($LASTEXITCODE -ne 0) { throw 'git status failed' }
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$handoff = Join-Path $root 'handoff'
New-Item -ItemType Directory -Force -Path $handoff | Out-Null
$bundle = Join-Path $handoff "bundle-$stamp"
New-Item -ItemType Directory -Path $bundle | Out-Null
$source = Join-Path $bundle 'source'
New-Item -ItemType Directory -Path $source | Out-Null
$gitTar = Join-Path $bundle 'source.tar'
git archive --format=tar -o $gitTar HEAD
if ($LASTEXITCODE -ne 0) { throw 'git archive failed' }
tar -xf $gitTar -C $source
if ($LASTEXITCODE -ne 0) { throw 'Could not unpack source archive' }
Remove-Item -LiteralPath $gitTar
if (Test-Path -LiteralPath (Join-Path $root 'runs')) { Copy-Item -LiteralPath (Join-Path $root 'runs') -Destination (Join-Path $bundle 'runs') -Recurse }
if ($IncludeDataset) {
  foreach ($item in @('dataset', 'data')) {
    $path = Join-Path $root $item
    if (Test-Path -LiteralPath $path) { Copy-Item -LiteralPath $path -Destination (Join-Path $bundle $item) -Recurse }
  }
}
$manifest = @{ git_commit = (git rev-parse HEAD).Trim(); created_at_utc = (Get-Date).ToUniversalTime().ToString('o'); includes_dataset = [bool]$IncludeDataset }
$manifest | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $bundle 'handoff.json') -Encoding utf8
$archive = Join-Path $handoff "bundle-$stamp.tar.gz"
tar -czf $archive -C $handoff "bundle-$stamp"
if ($LASTEXITCODE -ne 0) { throw 'Could not create bundle archive' }
Write-Output $archive
