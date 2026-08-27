$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot

$env:APP_ENV = "local"
if ([string]::IsNullOrWhiteSpace($env:LOCAL_AUTH_SECRET)) {
    $RandomBytes = New-Object byte[] 32
    [Security.Cryptography.RandomNumberGenerator]::Fill($RandomBytes)
    $env:LOCAL_AUTH_SECRET = [Convert]::ToBase64String($RandomBytes)
}

$BackendJob = Start-Job -ScriptBlock {
    param($Root, $RuntimeSecret)
    $env:APP_ENV = "local"
    $env:LOCAL_AUTH_SECRET = $RuntimeSecret
    Set-Location $Root
    & "$Root\.venv\Scripts\python.exe" -m uvicorn backend.aws_api.app:app --reload --port 8000
} -ArgumentList $ProjectRoot, $env:LOCAL_AUTH_SECRET

try {
    Push-Location "$ProjectRoot\frontend"
    npm.cmd run dev
}
finally {
    Pop-Location
    Stop-Job -Job $BackendJob -ErrorAction SilentlyContinue
    Remove-Job -Job $BackendJob -Force -ErrorAction SilentlyContinue
}
