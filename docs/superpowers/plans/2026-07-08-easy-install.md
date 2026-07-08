# Pacchetto "estrai e gioca" — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** produrre un unico `DCSS-Remastered-vX.Y.zip` che un utente non tecnico scarica, estrae e avvia con un doppio clic — senza Python, senza compilazione, senza download aggiuntivi.

**Architecture:** uno script di packaging (`build_release.ps1`, lato sviluppatore) assembla un bundle portable: gioco + proxy DLL pre-compilati + Director congelato in `.exe` (PyInstaller `--onedir`) + asset (musica/SFX/marker) + config cablata + launcher + doc/legale. Il launcher, al primo avvio sulla macchina utente, crea le copie `_orig` dei DLL di sistema dal SysWOW64 locale (non ridistribuiamo DLL Microsoft) e preferisce `director.exe` a Python.

**Tech Stack:** PowerShell (packaging + launcher), PyInstaller 6.x (freeze), Python 3.14 + pygame-ce + pywin32 (Director), MSVC x86 (proxy DLL), `gh` CLI (release).

## Global Constraints

- Proxy DLL (`winmm.dll`, `opengl32.dll`) devono essere **x86** (match con `crawl.exe`). `director.exe` può essere x64 (processo separato, comunica via named pipe).
- **Mai ridistribuire DLL Microsoft**: `winmm_orig.dll`/`opengl32_orig.dll` NON vanno nel bundle; li crea il launcher al primo avvio da `%WINDIR%\SysWOW64` dell'utente.
- Il bundle contiene **solo runtime**: niente sorgenti `.py`/`.c`, toolchain, `__pycache__`, test, `.git`, `director.log`, `.spec`, `build/`.
- Freeze con **`--onedir`** (avvio istantaneo, niente estrazione temporanea, meno sospetto agli antivirus). NON usare `--onefile` (startup ~11s + più flaggato).
- `director.py` è già frozen-aware: `HERE = dirname(sys.executable)` se `sys.frozen`, altrimenti `dirname(__file__)`. Il bundle mette `director.exe` in `remaster/director/` così trova `soundmap.json` + `../audio`.
- Legale: `crawl.exe` è **GPL** → includere offerta sorgenti in `LICENSES/`. Musica **CC-BY** (Kevin MacLeod) → attribuzione in `CREDITS.txt`.
- Named pipe: `\\.\pipe\dcss_audio`.

---

## File structure

- **Modify** `remaster/play-remaster.ps1` — setup `_orig` al primo avvio, preferisce `director.exe`, attende la pipe invece di sleep fisso. Usato sia in dev sia nel bundle.
- **Create** `remaster/tools/build_release.ps1` — pipeline di packaging (unico entry point lato dev).
- **Create** `remaster/dist_templates/launcher.bat` — launcher del bundle (copiato e rinominato).
- **Create** `remaster/dist_templates/LEGGIMI.txt` — guida utente (italiano): avvio + sblocco antivirus.
- **Create** `remaster/dist_templates/SOURCE-OFFER.txt` — offerta sorgenti GPL.

Output (non committati, gitignored): `remaster/dist/DCSS-Remastered/` (bundle) e `remaster/dist/DCSS-Remastered-vX.Y.zip`.

---

## Task 1: Launcher robusto (`play-remaster.ps1`)

**Files:**
- Modify: `remaster/play-remaster.ps1` (riscrittura completa)

**Interfaces:**
- Consumes: `director.exe` in `remaster/director/` (se presente) oppure `python` + `director.py`; `crawl.exe` in `<game>`; `%WINDIR%\SysWOW64\{winmm,opengl32}.dll`.
- Produces: crea `<game>\winmm_orig.dll` e `<game>\opengl32_orig.dll` al primo avvio; avvia il Director e attende `\\.\pipe\dcss_audio`.

- [ ] **Step 1: Riscrivere `play-remaster.ps1`**

```powershell
# DCSS Remastered — launcher one-click.
# Avvia il Director (audio+grafica), lancia il gioco, chiude il Director all'uscita.
$ErrorActionPreference = "SilentlyContinue"
$game   = Split-Path $PSScriptRoot          # ...\stone_soup-tiles-0.34
$dirDir = "$PSScriptRoot\director"

# 1) Primo avvio: crea le copie _orig dei DLL di sistema dal SysWOW64 DELL'UTENTE
#    (non ridistribuiamo DLL Microsoft). I proxy winmm/opengl32 le inoltrano.
$sys = "$env:WINDIR\SysWOW64"
if ((-not (Test-Path "$game\winmm_orig.dll"))    -and (Test-Path "$sys\winmm.dll"))    { Copy-Item "$sys\winmm.dll"    "$game\winmm_orig.dll"    -Force }
if ((-not (Test-Path "$game\opengl32_orig.dll")) -and (Test-Path "$sys\opengl32.dll")) { Copy-Item "$sys\opengl32.dll" "$game\opengl32_orig.dll" -Force }

# 2) Chiudi Director rimasti da sessioni precedenti (sia .exe sia sorgente)
Get-CimInstance Win32_Process -Filter "Name='python.exe' OR Name='director.exe'" |
    Where-Object { $_.CommandLine -like '*director*' } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force }

# 3) Avvia il Director: preferisci director.exe (congelato); fallback a python (dev).
if (Test-Path "$dirDir\director.exe") {
    $dir = Start-Process "$dirDir\director.exe" -WorkingDirectory $dirDir -WindowStyle Hidden -PassThru
} else {
    $dir = Start-Process python -ArgumentList "`"$dirDir\director.py`"" -WorkingDirectory $dirDir -WindowStyle Hidden -PassThru
}

# 4) Attendi che la named pipe sia pronta (max ~15s) invece di uno sleep fisso.
for ($i = 0; $i -lt 150; $i++) {
    if (Test-Path "\\.\pipe\dcss_audio") { break }
    Start-Sleep -Milliseconds 100
}

# 5) Lancia il gioco e attendi la chiusura.
Start-Process "$game\crawl.exe" -WorkingDirectory $game -Wait

# 6) Spegni il Director.
if ($dir -and -not $dir.HasExited) { Stop-Process -Id $dir.Id -Force }
Get-CimInstance Win32_Process -Filter "Name='python.exe' OR Name='director.exe'" |
    Where-Object { $_.CommandLine -like '*director*' } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force }
Write-Output "Sessione DCSS Remastered terminata."
```

- [ ] **Step 2: Verificare che `Test-Path` funzioni sulla named pipe**

Run (con un Director in ascolto — da `remaster/director/`: `python director.py`):
```
powershell -NoProfile -Command "Test-Path '\\.\pipe\dcss_audio'"
```
Expected: `True`. Se stampa `False` con Director attivo, sostituire il check con:
```powershell
if ([System.IO.Directory]::GetFiles('\\.\pipe\') -match 'dcss_audio') { break }
```

- [ ] **Step 3: Test end-to-end in modalità dev (fallback Python)**

Assicurarsi che NON esista `remaster/director/director.exe`, poi eseguire il launcher:
```
powershell -ExecutionPolicy Bypass -File "remaster/play-remaster.ps1"
```
Expected: il gioco parte; `remaster/director/director.log` mostra `=== director avviato, in ascolto ===`; esistono `winmm_orig.dll`/`opengl32_orig.dll` nella cartella del gioco.

- [ ] **Step 4: Commit**

```bash
git add remaster/play-remaster.ps1
git commit -m "feat(dist): launcher creates _orig DLLs on first run, prefers director.exe, waits for pipe"
```

---

## Task 2: `build_release.ps1` — DLL, asset, freeze

**Files:**
- Create: `remaster/tools/build_release.ps1`

**Interfaces:**
- Consumes: `proxy/build.ps1`, `gfx/build.ps1`, `tools/make_sfx.py`, `tools/make_markers.py`, `tools/fetch_music.py`, `director/director.py`.
- Produces: `remaster/proxy/winmm.dll`, `remaster/gfx/opengl32.dll`, asset in `remaster/audio/`, e `remaster/dist/_frozen/director/director.exe` (+ `_internal/`).

- [ ] **Step 1: Creare `build_release.ps1` (prime 3 fasi: DLL, asset, freeze)**

```powershell
param(
  [string]$Version = "0.1",
  [switch]$SkipAssets,   # salta gen sfx/markers e fetch musica se gia' presenti
  [switch]$SkipDlls      # salta build DLL se gia' presenti
)
$ErrorActionPreference = "Stop"
$R    = Split-Path $PSScriptRoot            # ...\remaster
$GAME = Split-Path $R                       # ...\stone_soup-tiles-0.34
$DIST = "$R\dist"

Write-Host "== 1/6  Proxy DLL (x86) =="
if (-not $SkipDlls) {
    & "$R\proxy\build.ps1"
    & "$R\gfx\build.ps1"
}
foreach ($d in @("$R\proxy\winmm.dll", "$R\gfx\opengl32.dll")) {
    if (-not (Test-Path $d)) { throw "manca $d — build DLL fallita (serve MSVC x86)" }
}

Write-Host "== 2/6  Asset (SFX, marker, musica) =="
if (-not $SkipAssets) {
    python "$R\tools\make_sfx.py"
    python "$R\tools\make_markers.py"
    python "$R\tools\fetch_music.py"
}
if (-not (Test-Path "$R\audio\sfx\evt__step.wav")) { throw "SFX non generati" }

Write-Host "== 3/6  Freeze Director (PyInstaller --onedir) =="
python -m pip install --quiet --disable-pip-version-check pyinstaller
$work = "$DIST\_pyi"
python -m PyInstaller --noconfirm --onedir --name director `
    --distpath "$DIST\_frozen" --workpath $work --specpath $work `
    "$R\director\director.py"
if (-not (Test-Path "$DIST\_frozen\director\director.exe")) { throw "freeze fallito: director.exe non prodotto" }
Write-Host "  director.exe OK"
```

- [ ] **Step 2: Eseguire (asset/DLL già presenti dallo spike) e verificare**

Run:
```
powershell -ExecutionPolicy Bypass -File "remaster/tools/build_release.ps1" -SkipAssets
```
(Se i DLL non ci sono e MSVC non è disponibile, aggiungere `-SkipDlls` e copiarli a mano da un build precedente.)
Expected: termina la fase 3/6; esiste `remaster/dist/_frozen/director/director.exe` e la cartella `_internal/`.

- [ ] **Step 3: Commit**

```bash
git add remaster/tools/build_release.ps1
git commit -m "feat(dist): build_release.ps1 — build DLLs, generate assets, freeze Director"
```

---

## Task 3: `build_release.ps1` — assemblaggio bundle + doc/legale

**Files:**
- Modify: `remaster/tools/build_release.ps1` (aggiunge fase 4/6)
- Create: `remaster/dist_templates/launcher.bat`
- Create: `remaster/dist_templates/LEGGIMI.txt`
- Create: `remaster/dist_templates/SOURCE-OFFER.txt`

**Interfaces:**
- Consumes: output di Task 2 (`dist/_frozen/director/`), `proxy/winmm.dll`, `gfx/opengl32.dll`, `config/remaster.rc`, `director/*.json`, `audio/`, `play-remaster.ps1`, `CREDITS.txt`.
- Produces: `remaster/dist/DCSS-Remastered/` (bundle completo, non zippato).

- [ ] **Step 1: Creare `dist_templates/launcher.bat`**

```bat
@echo off
REM DCSS Remastered — doppio clic per giocare.
start "" /min powershell -ExecutionPolicy Bypass -WindowStyle Hidden -File "%~dp0remaster\play-remaster.ps1"
```

- [ ] **Step 2: Creare `dist_templates/LEGGIMI.txt`**

```
DCSS Remastered — Come giocare
==============================

1) Se hai scaricato uno ZIP: PRIMA di estrarre, tasto destro sullo ZIP ->
   Proprieta' -> in basso spunta "Annulla blocco" (Unblock) -> OK.
   (Windows blocca i file scaricati; questo passo evita errori.)

2) Estrai la cartella dove vuoi (es. Desktop). NON serve installare nulla.

3) Doppio clic su "  Gioca a DCSS Remastered.bat".

Al primo avvio Windows potrebbe mostrare "Windows ha protetto il tuo PC"
(SmartScreen). E' normale per i programmi senza firma:
   -> clic su "Ulteriori info" -> "Esegui comunque".

Se l'antivirus (Windows Defender) segnala i file winmm.dll / opengl32.dll:
sono i componenti che aggiungono audio e grafica al gioco (falso positivo
comune). Puoi aggiungere la cartella alle esclusioni di Defender:
Sicurezza di Windows -> Protezione da virus -> Gestisci impostazioni ->
Esclusioni -> Aggiungi cartella.

Non serve Python ne' altro: e' tutto incluso.

Crediti musica e licenze: vedi CREDITS.txt e la cartella LICENSES.
Buon divertimento!
```

- [ ] **Step 3: Creare `dist_templates/SOURCE-OFFER.txt`**

```
DCSS Remastered — nota licenze
==============================

Questo pacchetto include Dungeon Crawl Stone Soup (Tiles 0.34), rilasciato
sotto GNU General Public License (GPL). Il codice sorgente del gioco e'
disponibile su: https://github.com/crawl/crawl  (tag 0.34.x).

Il layer "Remastered" (proxy audio/grafica + Director) e' un add-on
indipendente: https://github.com/oLdpZ/dcss-remastered

Musica: Kevin MacLeod (incompetech.com), licenza Creative Commons BY.
Attribuzione completa in CREDITS.txt. Effetti sonori: sintetizzati (CC0).

winmm.dll e opengl32.dll in questa cartella sono i PROXY del progetto, non
componenti Microsoft. Le versioni di sistema (winmm_orig.dll / opengl32_orig.dll)
vengono create dal launcher copiandole dal tuo Windows al primo avvio.
```

- [ ] **Step 4: Aggiungere la fase 4/6 (assemblaggio) a `build_release.ps1`** — dopo la fase 3/6:

```powershell
Write-Host "== 4/6  Assembla il bundle =="
$OUT = "$DIST\DCSS-Remastered"
if (Test-Path $OUT) { Remove-Item $OUT -Recurse -Force }
New-Item -ItemType Directory -Force $OUT | Out-Null

# 4a. Gioco (crawl.exe + dat/ + settings/ + docs/...), escludendo repo remaster,
#     artefatti proxy gia' deployati in dev e init.txt dev (li rigeneriamo puliti).
$skip = @("remaster", ".git", "winmm.dll", "winmm_orig.dll",
          "opengl32.dll", "opengl32_orig.dll", "init.txt")
Get-ChildItem $GAME -Force | Where-Object { $skip -notcontains $_.Name } |
    ForEach-Object { Copy-Item $_.FullName "$OUT\$($_.Name)" -Recurse -Force }

# 4b. Proxy DLL puliti (gli _orig li crea il launcher al primo avvio).
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
```

- [ ] **Step 5: Eseguire e verificare il contenuto del bundle**

Run:
```
powershell -ExecutionPolicy Bypass -File "remaster/tools/build_release.ps1" -SkipAssets -SkipDlls
```
Expected (verificare a mano):
- `dist/DCSS-Remastered/crawl.exe`, `winmm.dll`, `opengl32.dll`, `init.txt`, `LEGGIMI.txt` esistono.
- `dist/DCSS-Remastered/remaster/director/director.exe` + `_internal/` + `soundmap.json` esistono.
- `dist/DCSS-Remastered/remaster/audio/music/` contiene gli `.mp3`.
- NON esistono: `winmm_orig.dll`, `opengl32_orig.dll`, alcun file `.py` sotto `remaster/director/`, `director.log`.

- [ ] **Step 6: Commit**

```bash
git add remaster/tools/build_release.ps1 remaster/dist_templates/
git commit -m "feat(dist): assemble portable bundle (game + proxies + frozen Director + assets + docs)"
```

---

## Task 4: Verifica standalone del bundle + ZIP

**Files:**
- Modify: `remaster/tools/build_release.ps1` (aggiunge fasi 5/6 verifica e 6/6 zip)

**Interfaces:**
- Consumes: `dist/DCSS-Remastered/remaster/director/director.exe`.
- Produces: `remaster/dist/DCSS-Remastered-v$Version.zip`.

- [ ] **Step 1: Aggiungere la fase 5/6 (self-test del Director congelato nel bundle)**

```powershell
Write-Host "== 5/6  Verifica: director.exe del bundle apre la pipe =="
$exe = "$OUT\remaster\director\director.exe"
Get-Process director -ErrorAction SilentlyContinue | Stop-Process -Force
$p = Start-Process $exe -WorkingDirectory (Split-Path $exe) -WindowStyle Hidden -PassThru
$ok = $false
for ($i = 0; $i -lt 100; $i++) {                     # max ~10s
    if (Test-Path "\\.\pipe\dcss_audio") { $ok = $true; break }
    Start-Sleep -Milliseconds 100
}
Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue
Get-Process director -ErrorAction SilentlyContinue | Stop-Process -Force
if (-not $ok) { throw "self-test FALLITO: il director.exe del bundle non ha aperto la pipe" }
Write-Host "  self-test OK (pipe aperta)"
```

- [ ] **Step 2: Aggiungere la fase 6/6 (ZIP)**

```powershell
Write-Host "== 6/6  ZIP =="
$zip = "$DIST\DCSS-Remastered-v$Version.zip"
if (Test-Path $zip) { Remove-Item $zip -Force }
Compress-Archive -Path "$OUT\*" -DestinationPath $zip -Force
$mb = [math]::Round((Get-Item $zip).Length / 1MB, 1)
Write-Host "FATTO -> $zip  ($mb MB)"
```

- [ ] **Step 3: Eseguire la pipeline completa e verificare lo ZIP**

Run:
```
powershell -ExecutionPolicy Bypass -File "remaster/tools/build_release.ps1" -SkipAssets -SkipDlls -Version 0.1
```
Expected: stampa `self-test OK` e `FATTO -> ...DCSS-Remastered-v0.1.zip (~300 MB)`.

- [ ] **Step 4: Prova utente reale (accettazione)**

Estrarre lo ZIP in una cartella NUOVA (es. `C:\tmp\dcss-test\`), poi doppio clic sul `.bat` (o eseguire `remaster/play-remaster.ps1`). Expected: il gioco parte, si sente musica/SFX, e in gioco camminando si sentono i passi. Confermare che `winmm_orig.dll`/`opengl32_orig.dll` sono stati creati nella cartella estratta.

- [ ] **Step 5: Commit**

```bash
git add remaster/tools/build_release.ps1
git commit -m "feat(dist): bundle self-test + zip packaging"
```

- [ ] **Step 6: Pubblicare la Release (manuale)**

```bash
gh release create v0.1 "remaster/dist/DCSS-Remastered-v0.1.zip" \
  --title "DCSS Remastered v0.1" \
  --notes "Estrai e gioca — niente Python, niente setup. Vedi LEGGIMI.txt per lo sblocco antivirus."
```

---

## Note di rischio / follow-up (fuori scope immediato)

- **SmartScreen reputazione**: al primo rilascio molti utenti vedranno "Esegui comunque". Migliora col tempo/download. Firma Authenticode fuori scope (costo).
- **Dimensione ZIP ~300 MB**: se troppo, valutare musica `.ogg` a bitrate minore in `fetch_music.py` (task separato).
- **Antivirus aggressivi**: alcuni potrebbero mettere in quarantena `winmm.dll`. Documentato in LEGGIMI; niente fix a costo zero oltre le esclusioni.
- **Icona `.lnk`**: un collegamento con icona più bello del `.bat` — miglioria successiva.
