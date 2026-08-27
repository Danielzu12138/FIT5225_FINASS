$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot

if (-not (Test-Path -LiteralPath "$ProjectRoot\.venv\Scripts\python.exe")) {
    if (Get-Command py -ErrorAction SilentlyContinue) {
        py -3.12 -m venv "$ProjectRoot\.venv"
    }
    elseif (Get-Command python -ErrorAction SilentlyContinue) {
        python -m venv "$ProjectRoot\.venv"
    }
    elseif (Get-Command python3 -ErrorAction SilentlyContinue) {
        python3 -m venv "$ProjectRoot\.venv"
    }
    else {
        throw "Python 3.12 is required but no py, python, or python3 command was found."
    }
}

& "$ProjectRoot\.venv\Scripts\python.exe" -m pip install -e "${ProjectRoot}[dev]"
Push-Location "$ProjectRoot\frontend"
try {
    npm.cmd ci
}
finally {
    Pop-Location
}
