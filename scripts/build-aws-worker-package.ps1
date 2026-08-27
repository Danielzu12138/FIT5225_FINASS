[CmdletBinding()]
param(
    [string]$OutputPath = (Join-Path (Join-Path (Split-Path -Parent $PSScriptRoot) "build") "aws-worker.zip")
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$StagePath = Join-Path (Join-Path $ProjectRoot "build") "aws-worker-stage"
$Python = (Get-Command python -ErrorAction Stop).Source
$Certifi = & $Python -c "import certifi; print(certifi.where())"

if (Test-Path -LiteralPath $StagePath) { Remove-Item -LiteralPath $StagePath -Recurse -Force }
New-Item -ItemType Directory -Path $StagePath -Force | Out-Null
New-Item -ItemType Directory -Path (Split-Path -Parent $OutputPath) -Force | Out-Null

& $Python -m pip install --disable-pip-version-check --no-compile --only-binary=:all: --cert $Certifi `
  --platform manylinux2014_x86_64 --implementation cp --python-version 312 `
  --requirement (Join-Path (Join-Path (Join-Path $ProjectRoot "backend") "aws_api") "requirements-worker.txt") --target $StagePath
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Copy-Item -LiteralPath (Join-Path $ProjectRoot "backend") -Destination (Join-Path $StagePath "backend") -Recurse -Force
Copy-Item -LiteralPath (Join-Path $ProjectRoot "worker_adapter.py") -Destination (Join-Path $StagePath "worker_adapter.py") -Force
if (Test-Path -LiteralPath $OutputPath) { Remove-Item -LiteralPath $OutputPath -Force }
Compress-Archive -Path (Join-Path $StagePath "*") -DestinationPath $OutputPath -CompressionLevel Optimal
Write-Host "AWS worker package: $OutputPath"
