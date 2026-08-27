$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$Terraform = Get-Command terraform -ErrorAction SilentlyContinue
$Python = if (Test-Path -LiteralPath "$ProjectRoot\.venv\Scripts\python.exe") {
    "$ProjectRoot\.venv\Scripts\python.exe"
} else {
    (Get-Command python -ErrorAction Stop).Source
}

& "$ProjectRoot\scripts\build-aws-api-package.ps1"
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& "$ProjectRoot\scripts\build-aws-worker-package.ps1"
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

if ($null -eq $Terraform) {
    Write-Warning "Terraform CLI is unavailable; running HCL parse and static security checks only."
    & $Python -m pytest "$ProjectRoot\tests\contract\test_terraform_static.py" -q
    exit $LASTEXITCODE
}

& terraform fmt -check -recursive "$ProjectRoot\infra"
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

foreach ($Cloud in @("aws", "azure")) {
    $Stack = "$ProjectRoot\infra\$Cloud"
    & terraform -chdir="$Stack" init -backend=false -input=false
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    & terraform -chdir="$Stack" validate
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
