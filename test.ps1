# Run static checks and the unit/integration suite; writes evidence/<timestamp>/
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$ev = "$root\evidence\run_$stamp"
New-Item -ItemType Directory -Force $ev | Out-Null
& "$root\.venv\Scripts\python.exe" -m ruff check hiveshot tests 2>&1 | Tee-Object "$ev\ruff.txt"
& "$root\.venv\Scripts\python.exe" -m pytest tests -q 2>&1 | Tee-Object "$ev\pytest.txt"
"exit=$LASTEXITCODE" | Out-File "$ev\status.txt"
