$ErrorActionPreference = "Stop"

Set-Location $PSScriptRoot

if (-not (Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
    Write-Host "Created .env from .env.example. Fill OPENAI_API_KEY before requesting advice." -ForegroundColor Yellow
}

python app.py
