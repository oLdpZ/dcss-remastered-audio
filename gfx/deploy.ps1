$ErrorActionPreference = "Stop"
$game = Split-Path (Split-Path $PSScriptRoot)   # ...\stone_soup-tiles-0.34
Copy-Item "$PSScriptRoot\opengl32.dll" "$game\opengl32.dll" -Force
if (-not (Test-Path "$game\opengl32_orig.dll")) {
    Copy-Item "C:\Windows\SysWOW64\opengl32.dll" "$game\opengl32_orig.dll" -Force
}
Write-Output "deploy gfx ok in $game"
