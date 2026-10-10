# Downloads the large third-party files that are not committed to git.
# Run from the project root: powershell -ExecutionPolicy Bypass -File tools\fetch_deps.ps1
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
New-Item -ItemType Directory -Force "$root\bin" | Out-Null
$mtx = "$root\bin\mediamtx.exe"
if (-not (Test-Path $mtx)) {
  $zip = "$env:TEMP\mediamtx.zip"
  Invoke-WebRequest -UseBasicParsing -Uri "https://github.com/bluenviron/mediamtx/releases/download/v1.21.2/mediamtx_v1.21.2_windows_amd64.zip" -OutFile $zip
  Expand-Archive -Force $zip "$env:TEMP\mediamtx_x"
  Copy-Item "$env:TEMP\mediamtx_x\mediamtx.exe" $mtx
  Copy-Item "$env:TEMP\mediamtx_x\LICENSE" "$root\bin\MEDIAMTX_LICENSE" -ErrorAction SilentlyContinue
  "mediamtx v1.21.2 -> bin\mediamtx.exe"
} else { "mediamtx already present" }
New-Item -ItemType Directory -Force "$root\docs\official" | Out-Null
$docs = @{
  "competition_manual_section9_TU04.pdf" = "https://ftc-resources.firstinspires.org/ftc/game/manual-09";
  "initial_field_element_assembly_guide_v1.pdf" = "https://ftc-resources.firstinspires.org/ftc/field/initialfieldguide";
  "event_field_setup_guide.pdf" = "https://ftc-resources.firstinspires.org/ftc/field/eventfieldguide";
  "apriltag_production_art.pdf" = "https://ftc-resources.firstinspires.org/ftc/field/apriltag-art";
}
foreach ($k in $docs.Keys) {
  $p = "$root\docs\official\$k"
  if (-not (Test-Path $p)) { Invoke-WebRequest -UseBasicParsing -Uri $docs[$k] -OutFile $p; "fetched $k" }
}
"done"
