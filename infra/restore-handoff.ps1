param([Parameter(Mandatory=$true)][string]$BundleRoot, [switch]$Force)
$ErrorActionPreference = 'Stop'
if (-not $Force) { throw 'Pass -Force to replace the local transport database and runs selection' }
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$bundle = (Resolve-Path -LiteralPath $BundleRoot).Path
$manifest = Get-Content -LiteralPath (Join-Path $bundle 'handoff.json') -Raw | ConvertFrom-Json
$dump = Join-Path $bundle 'transport.dump'
if ((Get-FileHash -Algorithm SHA256 -LiteralPath $dump).Hash.ToLowerInvariant() -ne $manifest.transport_dump_sha256) { throw 'Dump checksum mismatch' }
Set-Location $root
docker compose up -d --wait postgres
if ($LASTEXITCODE -ne 0) { throw 'PostgreSQL startup failed' }
docker compose stop backend grafana
if ($LASTEXITCODE -ne 0) { throw 'Could not stop database clients' }
$container = (docker compose ps -q postgres).Trim()
if ($LASTEXITCODE -ne 0 -or -not $container) { throw 'PostgreSQL container not found' }
docker cp $dump "${container}:/tmp/transport-handoff.dump"
if ($LASTEXITCODE -ne 0) { throw 'Could not copy dump' }
docker exec $container sh -c 'export PGPASSWORD="$POSTGRES_PASSWORD"; pg_restore -U transport -d transport --clean --if-exists --no-owner --exit-on-error /tmp/transport-handoff.dump'
if ($LASTEXITCODE -ne 0) { throw 'pg_restore failed' }
docker exec $container rm -f /tmp/transport-handoff.dump | Out-Null
$savedRuns = Join-Path $bundle 'runs'
if (Test-Path -LiteralPath $savedRuns) {
  $target = Join-Path $root 'runs'
  New-Item -ItemType Directory -Force -Path $target | Out-Null
  Copy-Item -Path (Join-Path $savedRuns '*') -Destination $target -Recurse -Force
}
docker compose up --build -d --wait --remove-orphans
if ($LASTEXITCODE -ne 0) { throw 'Online stack startup failed' }
Write-Output 'Handoff restored'
