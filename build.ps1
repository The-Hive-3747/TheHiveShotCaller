# Release build: ruff + pytest (fail fast), PyInstaller one-folder, zip.
param([switch]$SkipChecks)  # -SkipChecks: packaging dry run only, NOT for releases
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root
$py = "$root\.venv\Scripts\python.exe"
function Step($name, [scriptblock]$b) {
    Write-Host "== $name"
    & $b
    if ($LASTEXITCODE -ne 0) { throw "$name failed (exit $LASTEXITCODE)" }
}
if (-not $SkipChecks) {
Step "ruff" { & $py -m ruff check hiveshot tests }
Step "pytest" { & $py -m pytest tests -q }
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
  This program is not code-signed. On first run Windows may show "Windows protected
  your PC". Click "More info", then "Run anyway". If your antivirus quarantines
  _internal\bin\mediamtx.exe, restore it or add an exception.
"@
$readme = ($readme -replace "`r?`n", "`r`n")
[System.IO.File]::WriteAllText("$bundle\README.txt", $readme, (New-Object System.Text.UTF8Encoding($false)))

$zip = "$root\dist\HiveShotTracker_${version}_win64.zip"
if (Test-Path $zip) { Remove-Item $zip }
Compress-Archive -Path $bundle -DestinationPath $zip
Write-Host "Built $zip ($([math]::Round((Get-Item $zip).Length/1MB,1)) MB)"
