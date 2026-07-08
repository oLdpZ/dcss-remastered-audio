# DCSS Remastered - pipeline di packaging "estrai e gioca".
# Assembla un bundle portable (gioco + proxy DLL + Director congelato + asset + config)
# e lo zippa. Eseguire da qualunque cartella:
#   powershell -ExecutionPolicy Bypass -File remaster\tools\build_release.ps1 -Version 0.1
param(
    [string]$Version = "0.1",
    [switch]$SkipAssets,   # salta gen sfx/markers e fetch musica se gia' presenti
    [switch]$SkipDlls      # salta build DLL se gia' presenti
)
$ErrorActionPreference = "Stop"
$R    = Split-Path $PSScriptRoot            # ...\remaster
$GAME = Split-Path $R                       # ...\stone_soup-tiles-0.34
$DIST = "$R\dist"

Write-Host "== 1/6  Proxy DLL (x86) ==" -ForegroundColor Cyan
if (-not $SkipDlls) {
    & "$R\proxy\build.ps1"
    & "$R\gfx\build.ps1"
}
foreach ($d in @("$R\proxy\winmm.dll", "$R\gfx\opengl32.dll")) {
    if (-not (Test-Path $d)) { throw "manca $d - build DLL fallita (serve MSVC x86)" }
}

Write-Host "== 2/6  Asset (SFX, marker, musica) ==" -ForegroundColor Cyan
if (-not $SkipAssets) {
    python "$R\tools\make_sfx.py"
    python "$R\tools\make_markers.py"
    python "$R\tools\fetch_music.py"
}
if (-not (Test-Path "$R\audio\sfx\evt__step.wav")) { throw "SFX non generati" }

Write-Host "== 3/6  Freeze Director (PyInstaller --onedir) ==" -ForegroundColor Cyan
python -m pip install --quiet --disable-pip-version-check pyinstaller
$work = "$DIST\_pyi"
python -m PyInstaller --noconfirm --onedir --name director `
    --distpath "$DIST\_frozen" --workpath $work --specpath $work `
    "$R\director\director.py"
if (-not (Test-Path "$DIST\_frozen\director\director.exe")) { throw "freeze fallito: director.exe non prodotto" }
Write-Host "  director.exe OK"

Write-Host "== 4/6  Assembla il bundle ==" -ForegroundColor Cyan
$OUT = "$DIST\DCSS-Remastered"
if (Test-Path $OUT) { Remove-Item $OUT -Recurse -Force }
New-Item -ItemType Directory -Force $OUT | Out-Null

# 4a. Gioco (crawl.exe + dat/ + settings/ + docs/ + LICENSE), escludendo repo remaster,
#     artefatti proxy/dev, dati utente e init.txt dev (rigenerati puliti).
$skip = @("remaster", ".git", "init.txt",
          "winmm.dll", "winmm_orig.dll", "winmm_proxy.obj",
          "opengl32.dll", "opengl32_orig.dll",
          "remaster_proxy.log", "morgue", "saves",
          "Play DCSS Remastered.bat")
Get-ChildItem $GAME -Force | Where-Object { $skip -notcontains $_.Name } |
    ForEach-Object { Copy-Item $_.FullName "$OUT\$($_.Name)" -Recurse -Force }

# 4b. Proxy DLL puliti (gli _orig li crea il launcher al primo avvio dal SysWOW64 utente).
Copy-Item "$R\proxy\winmm.dll"  "$OUT\winmm.dll"  -Force
Copy-Item "$R\gfx\opengl32.dll" "$OUT\opengl32.dll" -Force

# 4c. init.txt cablato.
"include = settings/init.txt`r`ninclude = remaster/config/remaster.rc" |
    Set-Content "$OUT\init.txt" -Encoding UTF8

# 4d. remaster runtime: SOLO cio' che serve a runtime.
$rr = "$OUT\remaster"
New-Item -ItemType Directory -Force "$rr\director", "$rr\config", "$rr\audio" | Out-Null
Copy-Item "$DIST\_frozen\director\*" "$rr\director\" -Recurse -Force        # director.exe + _internal\
Copy-Item "$R\director\soundmap.json", "$R\director\visualmap.json" "$rr\director\" -Force
Copy-Item "$R\config\remaster.rc" "$rr\config\" -Force
Copy-Item "$R\audio\*" "$rr\audio\" -Recurse -Force
Copy-Item "$R\play-remaster.ps1" "$rr\play-remaster.ps1" -Force

# 4e. Launcher + doc/legale.
Copy-Item "$R\dist_templates\launcher.bat" "$OUT\$([char]0x25B6) Gioca a DCSS Remastered.bat" -Force
Copy-Item "$R\dist_templates\LEGGIMI.txt" "$OUT\LEGGIMI.txt" -Force
if (Test-Path "$R\CREDITS.txt") { Copy-Item "$R\CREDITS.txt" "$OUT\CREDITS.txt" -Force }
New-Item -ItemType Directory -Force "$OUT\LICENSES" | Out-Null
Copy-Item "$R\dist_templates\SOURCE-OFFER.txt" "$OUT\LICENSES\SOURCE-OFFER.txt" -Force
Get-ChildItem "$GAME\docs\license" -Filter *.txt -ErrorAction SilentlyContinue |
    ForEach-Object { Copy-Item $_.FullName "$OUT\LICENSES\$($_.Name)" -Force }
Write-Host "  bundle assemblato in $OUT"

Write-Host "== 5/6  Verifica: director.exe del bundle apre la pipe ==" -ForegroundColor Cyan
Get-Process director -ErrorAction SilentlyContinue | Stop-Process -Force
$exe = "$OUT\remaster\director\director.exe"
$p = Start-Process $exe -WorkingDirectory (Split-Path $exe) -WindowStyle Hidden -PassThru
$ok = $false
for ($i = 0; $i -lt 100; $i++) {                     # max ~10s
    try { if ([System.IO.Directory]::GetFiles('\\.\pipe\') -match 'dcss_audio') { $ok = $true; break } } catch {}
    Start-Sleep -Milliseconds 100
}
Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue
Get-Process director -ErrorAction SilentlyContinue | Stop-Process -Force
if (-not $ok) { throw "self-test FALLITO: il director.exe del bundle non ha aperto la pipe" }
Write-Host "  self-test OK (pipe aperta)"

Write-Host "== 6/6  ZIP ==" -ForegroundColor Cyan
Add-Type -AssemblyName System.IO.Compression.FileSystem
$zip = "$DIST\DCSS-Remastered-v$Version.zip"
if (Test-Path $zip) { Remove-Item $zip -Force }
# L'antivirus (Defender) scansiona in tempo reale l'albero appena scritto e blocca i
# file per qualche secondo: attendiamo che finisca, poi usiamo ZipFile.CreateFromDirectory
# (apre i sorgenti in shared-read, piu' tollerante di Compress-Archive). Retry con backoff.
$zipped = $false
for ($try = 1; $try -le 5; $try++) {
    Start-Sleep -Seconds (10 * $try)   # 10s, 20s, ... lascia sfumare le scansioni Defender
    try {
        if (Test-Path $zip) { Remove-Item $zip -Force -ErrorAction SilentlyContinue }
        [System.IO.Compression.ZipFile]::CreateFromDirectory($OUT, $zip)
        $zipped = $true; break
    } catch {
        Write-Host "  zip tentativo $try fallito ($($_.Exception.Message.Split([char]10)[0])); ritento..." -ForegroundColor Yellow
    }
}
if (-not $zipped) { throw "ZIP fallito dopo 5 tentativi (file bloccato dall'antivirus?)" }
$mb = [math]::Round((Get-Item $zip).Length / 1MB, 1)
Write-Host "FATTO -> $zip  ($mb MB)" -ForegroundColor Green
