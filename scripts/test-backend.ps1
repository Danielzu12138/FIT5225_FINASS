$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
& "$ProjectRoot\.venv\Scripts\python.exe" -m pytest "$ProjectRoot\tests\unit" -q
