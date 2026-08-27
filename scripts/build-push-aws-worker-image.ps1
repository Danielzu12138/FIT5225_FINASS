[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$RepositoryUri,
    [string]$Tag = "ml-v1",
    [string]$ModelDirectory = (Join-Path (Split-Path -Parent (Split-Path -Parent $PSScriptRoot)) "PacificBioArchive")
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$ContextPath = Join-Path (Join-Path $ProjectRoot "build") "aws-worker-image"
$DockerfileDirectory = Join-Path (Join-Path $ProjectRoot "deployment") "aws-worker"

foreach ($name in @("mdv5a.pt", "model.pt", "labels.txt")) {
    if (-not (Test-Path -LiteralPath (Join-Path $ModelDirectory $name) -PathType Leaf)) {
        throw "Missing model artifact: $(Join-Path $ModelDirectory $name)"
    }
}

if (Test-Path -LiteralPath $ContextPath) {
    Remove-Item -LiteralPath $ContextPath -Recurse -Force
}
New-Item -ItemType Directory -Path (Join-Path $ContextPath "models") -Force | Out-Null
Copy-Item -LiteralPath (Join-Path $ProjectRoot "backend") -Destination (Join-Path $ContextPath "backend") -Recurse -Force
Copy-Item -LiteralPath (Join-Path $ProjectRoot "worker_adapter.py") -Destination (Join-Path $ContextPath "worker_adapter.py") -Force
Copy-Item -LiteralPath (Join-Path $DockerfileDirectory "Dockerfile") -Destination (Join-Path $ContextPath "Dockerfile") -Force
Copy-Item -LiteralPath (Join-Path $DockerfileDirectory "requirements-worker-container.txt") -Destination (Join-Path $ContextPath "requirements-worker-container.txt") -Force
foreach ($name in @("mdv5a.pt", "model.pt", "labels.txt")) {
    Copy-Item -LiteralPath (Join-Path $ModelDirectory $name) -Destination (Join-Path (Join-Path $ContextPath "models") $name) -Force
}

$Image = "${RepositoryUri}:${Tag}"
docker buildx build --platform linux/amd64 --provenance=false --push --tag $Image $ContextPath
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

$RepositoryName = ($RepositoryUri -split "/", 2)[1]
$Digest = aws ecr describe-images --repository-name $RepositoryName --image-ids "imageTag=$Tag" --query "imageDetails[0].imageDigest" --output text
if ($LASTEXITCODE -ne 0 -or -not $Digest.StartsWith("sha256:")) {
    throw "Unable to resolve the pushed ECR image digest"
}
Write-Host "Worker image URI: ${RepositoryUri}@${Digest}"
