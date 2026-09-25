param([switch]$IncludeDataset)
$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
Set-Location $root
if (-not (Get-Command git -ErrorAction SilentlyContinue) -or -not (Get-Command docker -ErrorAction SilentlyContinue) -or -not (Get-Command tar -ErrorAction SilentlyContinue)) { throw 'git, docker and tar are required' }
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
$container = (docker compose ps -q postgres).Trim()
if ($LASTEXITCODE -ne 0 -or -not $container) { throw 'Start PostgreSQL with docker compose up -d --wait postgres db-init' }
$dump = Join-Path $bundle 'transport.dump'
docker exec $container sh -c 'export PGPASSWORD="$POSTGRES_PASSWORD"; pg_dump -U transport -d transport -Fc -f /tmp/transport-handoff.dump'
if ($LASTEXITCODE -ne 0) { throw 'pg_dump failed' }
docker cp "${container}:/tmp/transport-handoff.dump" $dump
if ($LASTEXITCODE -ne 0) { throw 'docker cp failed' }
docker exec $container rm -f /tmp/transport-handoff.dump | Out-Null
$manifest = @{ git_commit = (git rev-parse HEAD).Trim(); transport_dump_sha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $dump).Hash.ToLowerInvariant(); created_at_utc = (Get-Date).ToUniversalTime().ToString('o'); includes_dataset = [bool]$IncludeDataset }
$manifest | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $bundle 'handoff.json') -Encoding utf8
$archive = Join-Path $handoff "bundle-$stamp.tar.gz"
tar -czf $archive -C $handoff "bundle-$stamp"
if ($LASTEXITCODE -ne 0) { throw 'Could not create bundle archive' }
Write-Output $archive
