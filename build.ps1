# Release build: ruff + pytest (fail fast), PyInstaller one-folder, zip.
param([switch]$SkipChecks)  # -SkipChecks: packaging dry run only, NOT for releases
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root
$py = "$root\.venv\Scripts\python.exe"
# Logs for this run: evidence\m5_build\<timestamp>\ (never overwritten by a later build).
$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$evid = "$root\evidence\m5_build\$stamp"
New-Item -ItemType Directory -Path $evid -Force | Out-Null
Write-Host "Evidence: $evid"
function Step($name, [scriptblock]$b, [string]$log) {
    Write-Host "== $name"
    $prev = $ErrorActionPreference
    $ErrorActionPreference = "Continue"   # native stderr must not abort before we read the exit code
    try {
        if ($log) { & $b 2>&1 | ForEach-Object { $line = "$_"; Add-Content -LiteralPath $log -Value $line -Encoding UTF8; $line } } else { & $b }
        $code = $LASTEXITCODE
    } finally { $ErrorActionPreference = $prev }
    if ($code -ne 0) { throw "$name failed (exit $code)" + $(if ($log) { "; log: $log" } else { "" }) }
}
if (-not $SkipChecks) {
# Pre-build gate: lint + every test except the packaged-build smoke tests, which need the NEW dist.
Step "ruff" { & $py -m ruff check hiveshot tests } "$evid\ruff.txt"
Step "pytest (not build, not timing)" { & $py -m pytest tests -q -m "not build and not timing" } "$evid\pytest_prebuild.txt"
# Wall-clock-sensitive tests: run alone, with nothing else running on the machine.
Step "pytest (timing)" { & $py -m pytest tests -q -m timing } "$evid\pytest_timing.txt"
}
$version = (& $py -c "import hiveshot; print(hiveshot.__version__)").Trim()
Step "pyinstaller" { & $py -m PyInstaller hiveshot.spec --noconfirm --clean --distpath dist --workpath build/work }
$bundle = "$root\dist\HiveShotTracker"

# Ship the operator docs (guides, placement map, bracket files) next to the exe.
$docsOut = "$bundle\docs"
if (Test-Path $docsOut) { Remove-Item $docsOut -Recurse -Force }
New-Item -ItemType Directory -Path $docsOut | Out-Null
Copy-Item "$root\docs\*" $docsOut -Recurse -Force
if (-not (Test-Path "$docsOut\operator_guide.md")) { throw "docs copy failed: operator_guide.md missing" }

# README.txt at the top of the unzipped folder (plain text, CRLF).
$readme = @"
HiveShotTracker $version (Windows 64-bit)

HOW TO RUN
  1. Unzip this whole folder to a normal location, for example C:\HiveShotTracker.
     Keep the files together; do not move HiveShotTracker.exe out of the folder.
  2. Double-click HiveShotTracker.exe. A console window opens and stays open while
     the app runs. If Windows Firewall asks, choose "Private networks" (needed only
     for GoPro RTMP streaming).
  3. Open a web browser to http://127.0.0.1:8765
  4. To stop the app, close the console window (or press Ctrl+C in it).
  No Python, Node, or other runtime needs to be installed, and no internet is needed.

WHERE YOUR DATA GOES
  Default folder: %LOCALAPPDATA%\HiveShotTracker\data
  (usually C:\Users\<you>\AppData\Local\HiveShotTracker\data)
  It holds hiveshot.db (sessions and shots), config.json, calibration.json and
  clips\ (shot video). To use another folder:
      HiveShotTracker.exe --data-dir D:\hiveshot_data
  Back up by closing the app and copying that whole folder.

DOCUMENTATION
  See the docs folder next to the exe:
    docs\operator_guide.md      start here
    docs\camera_placement.md    where to put and aim the cameras (map: camera_placement.png)
    docs\calibration.md         camera calibration
    docs\troubleshooting.md     common problems
    docs\camera_bracket.md      printable camera bracket (camera_bracket.stl)
    docs\clean_machine_test.md  checklist for verifying a new PC
  The .md files open in any text editor (Notepad works).

WINDOWS SMARTSCREEN
  This program is not code-signed, so Windows SmartScreen may react on first run:
  it may show "Windows protected your PC". Click "More info", then "Run anyway". If your antivirus quarantines
  _internal\bin\mediamtx.exe, restore it or add an exception.
"@
$readme = ($readme -replace "`r?`n", "`r`n")
[System.IO.File]::WriteAllText("$bundle\README.txt", $readme, (New-Object System.Text.UTF8Encoding($false)))

$zip = "$root\dist\HiveShotTracker_${version}_win64.zip"
if (Test-Path $zip) { Remove-Item $zip }
Compress-Archive -Path $bundle -DestinationPath $zip

# Post-build gate: smoke-test the freshly built dist (DLLs, docs, fixtures, exe run, demo mode).
if (-not (Test-Path "$bundle\HiveShotTracker.exe")) { throw "build produced no HiveShotTracker.exe" }
try {
    Step "pytest (build smoke)" { & $py -m pytest tests/test_build_smoke.py -m build -q -rs } "$evid\pytest_smoke.txt"
} catch {
    Remove-Item $zip -ErrorAction SilentlyContinue   # never leave a zip that failed its smoke gate
    throw
}
Write-Host "Built $zip ($([math]::Round((Get-Item $zip).Length/1MB,1)) MB)"
