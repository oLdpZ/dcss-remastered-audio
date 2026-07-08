$ErrorActionPreference = "Stop"
$vc = "C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvarsall.bat"
$here = $PSScriptRoot
Remove-Item "$here\gl_harness.exe","$here\*.obj" -ErrorAction SilentlyContinue
cmd /c "`"$vc`" x86 && cl /nologo /O2 `"$here\gl_harness.c`" `"$here\..\postprocess.c`" /Fe:`"$here\gl_harness.exe`" /link /MACHINE:X86 opengl32.lib gdi32.lib user32.lib"
if ($LASTEXITCODE -ne 0) { throw "compilazione harness fallita (exit $LASTEXITCODE)" }
if (Test-Path "$here\gl_harness.exe") { Write-Output "BUILD OK -> $here\gl_harness.exe" } else { throw "gl_harness.exe non prodotta" }
