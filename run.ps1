# One-command launcher for HiveShotTracker (Windows PowerShell)
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
& "$root\.venv\Scripts\python.exe" -m hiveshot.app @args
