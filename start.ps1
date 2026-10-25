Set-Location -LiteralPath $PSScriptRoot
if (Test-Path .venv/Scripts/python.exe) { & ./.venv/Scripts/python.exe run_web.py } else { python run_web.py }
