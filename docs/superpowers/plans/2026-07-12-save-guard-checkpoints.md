# Save-Guard — checkpoint automatici e ripristino alla morte — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Aggiungere al Director un modulo `SaveGuard` che snapshotta il salvataggio DCSS a ogni piano (rotazione ultimi 5) e lo ripristina automaticamente alla morte, trasformando il permadeath in save/load classico — senza ricompilare il gioco.

**Architecture:** Un thread daemon nel Director Python fa polling di `saves/*.cs`. Su modifica → snapshot con debounce+dedup in `remaster_checkpoints/<nome>/` (rotazione). Su cancellazione del `.cs` (morte) → ripristino dell'ultimo snapshot, armato dal token `state__player_death` che il Director già riceve. Nessuna modifica ad audio, grafica, Lua o binario.

**Tech Stack:** Python 3 stdlib (`os`, `shutil`, `hashlib`, `json`, `threading`, `time`), pytest. Launcher PowerShell (`play-remaster.ps1`).

## Global Constraints

- **Solo stdlib** nel Director: nessuna dipendenza nuova (niente `watchdog`); polling puro. (Evita grane col freeze PyInstaller.)
- **`play-remaster.ps1` deve restare ASCII puro** (nessun UTF-8 multibyte): PowerShell 5.1 sugli utenti legge i file senza BOM come ANSI e i caratteri multibyte rompono il parser.
- **Import nei test** con `sys.path.insert(0, <dir del director>)` come negli altri test in `director/tests/` (nessun package/conftest).
- **Token di morte esatto:** `state__player_death` (verificato in `soundmap.json` e nel `director.log`).
- **Il modulo non deve MAI far crashare il Director:** ogni eccezione nel loop di polling va assorbita e loggata; l'audio/grafica proseguono (stesso principio "mai crashare" del layer grafico).
- **Nome cartella checkpoint:** `remaster_checkpoints/` accanto a `saves/` (mai dentro `saves/`).

---

## File Structure

- **Create:** `director/save_guard.py` — classe `SaveGuard` + helper `resolve_saves_dir()`, `load_saveguard_config()`, costante `DEFAULT_CONFIG`.
- **Create:** `director/saveguard.json` — config hot-editable.
- **Create:** `director/tests/test_save_guard.py` — suite pytest.
- **Modify:** `director/director.py` — avvio thread + arm su token morte.
- **Modify:** `play-remaster.ps1` — export `DCSS_SAVES_DIR`.
- **Modify (memoria):** aggiornare `MEMORY.md` + nuovo file memoria a fine lavoro (Task 8).

---

## Task 0: Validazione empirica dei rischi cardine (GATE — nessun codice)

**Files:** nessuno. Task manuale, in-game. **Blocca** l'implementazione se il rischio #1 è falso.

Motivo: tutto il design assume che DCSS **riscriva `saves/<nome>.cs` su disco a ogni cambio piano senza uscire dal gioco**. Se invece il flush avviene solo al save-quit, i checkpoint per-piano non sono osservabili dall'esterno e il design va rivisto con l'utente PRIMA di scrivere codice.

- [ ] **Step 1: Osserva mtime/size su cambio piano**

Avvia il gioco col launcher, crea/carica un personaggio, annota `mtime` e `size` di `saves/<nome>.cs`:
```bash
cd "C:/Users/old_p/Documents/progetto dcss remastered/stone_soup-tiles-0.34"
ls -la --time-style=full-iso saves/*.cs
```
Scendi di un piano (`>` sulle scale) **senza** fare save-quit. Riesegui il comando.
Atteso (rischio #1 vero): `mtime` aggiornato (e tipicamente `size` cambiata) dopo il cambio piano.

- [ ] **Step 2: Conferma la cancellazione alla morte**

Fai morire il personaggio (o usa un personaggio sacrificabile). Dopo la schermata di morte:
```bash
ls -la saves/*.cs
```
Atteso (rischio #2 vero): il `.cs` del personaggio morto **non c'è più**; in `saves/` compaiono/aggiornano `morgue`/`scores`.

- [ ] **Step 3: Conferma che un `.cs` copiato ricarica**

Prima di far morire un personaggio, copia a mano il suo `.cs`:
```bash
cp "saves/<nome>.cs" /c/tmp/<nome>.cs.bak
```
Fallo morire, poi ripristina e verifica il caricamento:
```bash
cp /c/tmp/<nome>.cs.bak "saves/<nome>.cs"
```
Rilancia il gioco → il personaggio deve ricomparire nel menu e caricarsi vivo all'inizio del piano.

- [ ] **Step 4: Decisione GATE**

- Se #1, #2, #3 sono **veri** → procedi a Task 1.
- Se #1 è **falso** (mtime NON cambia a cambio piano) → **fermati e riferisci all'utente**: i checkpoint per-piano non sono fattibili dall'esterno; serve rivedere la granularità (es. solo al save-quit, o approccio B). Non scrivere codice basato su un'assunzione falsa.

---

## Task 1: SaveGuard — snapshot con dedup

**Files:**
- Create: `director/save_guard.py`
- Test: `director/tests/test_save_guard.py`

**Interfaces:**
- Consumes: nulla (primo task).
- Produces:
  - `DEFAULT_CONFIG: dict` = `{"enabled": True, "keep": 5, "poll_seconds": 1.5, "require_death_token": True, "restore_window_seconds": 30}`
  - `class SaveGuard(saves_dir: str, checkpoints_dir: str, config: dict|None = None, clock=time.monotonic)`
  - `SaveGuard.poll_once() -> dict` con chiavi `{"snapshotted": list[str], "restored": list[str]}`
  - `SaveGuard.arm_restore() -> None`
  - snapshot salvati in `<checkpoints_dir>/<nome>/NNNN.cs` (indice a 4 cifre, zero-padded, crescente)

- [ ] **Step 1: Write the failing test**

```python
# director/tests/test_save_guard.py
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from save_guard import SaveGuard, DEFAULT_CONFIG

def _write(path, data: bytes):
    with open(path, "wb") as f:
        f.write(data)

def _mk(tmp_path):
    saves = tmp_path / "saves"; saves.mkdir()
    ckpt = tmp_path / "remaster_checkpoints"
    return str(saves), str(ckpt)

def _snaps(ckpt, name):
    d = os.path.join(ckpt, name)
    return sorted(f for f in os.listdir(d)) if os.path.isdir(d) else []

def test_snapshot_created_after_debounce(tmp_path):
    saves, ckpt = _mk(tmp_path)
    _write(os.path.join(saves, "Hero.cs"), b"level1")
    g = SaveGuard(saves, ckpt)
    r1 = g.poll_once()          # 1a scansione: file nuovo -> in attesa (debounce)
    assert r1["snapshotted"] == []
    r2 = g.poll_once()          # 2a scansione: size stabile -> snapshot
    assert r2["snapshotted"] == ["Hero"]
    assert _snaps(ckpt, "Hero") == ["0000.cs"]
    with open(os.path.join(ckpt, "Hero", "0000.cs"), "rb") as f:
        assert f.read() == b"level1"

def test_dedup_same_content(tmp_path):
    saves, ckpt = _mk(tmp_path)
    p = os.path.join(saves, "Hero.cs")
    _write(p, b"level1")
    g = SaveGuard(saves, ckpt)
    g.poll_once(); g.poll_once()               # snapshot 0000
    os.utime(p, None)                            # tocca mtime, stesso contenuto
    g.poll_once()                                # rileva cambio -> attesa
    r = g.poll_once()                            # stabile -> ma hash uguale -> dedup
    assert r["snapshotted"] == []
    assert _snaps(ckpt, "Hero") == ["0000.cs"]

def test_new_content_makes_new_snapshot(tmp_path):
    saves, ckpt = _mk(tmp_path)
    p = os.path.join(saves, "Hero.cs")
    _write(p, b"level1")
    g = SaveGuard(saves, ckpt)
    g.poll_once(); g.poll_once()               # 0000
    _write(p, b"level2xx")                       # contenuto diverso (size diversa)
    g.poll_once(); g.poll_once()               # 0001
    assert _snaps(ckpt, "Hero") == ["0000.cs", "0001.cs"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest director/tests/test_save_guard.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'save_guard'`.

- [ ] **Step 3: Write minimal implementation**

```python
# director/save_guard.py
import os, shutil, hashlib, json, time

DEFAULT_CONFIG = {
    "enabled": True,
    "keep": 5,
    "poll_seconds": 1.5,
    "require_death_token": True,
    "restore_window_seconds": 30,
}

class SaveGuard:
    def __init__(self, saves_dir, checkpoints_dir, config=None, clock=time.monotonic):
        self.saves_dir = saves_dir
        self.checkpoints_dir = checkpoints_dir
        self.cfg = dict(DEFAULT_CONFIG); self.cfg.update(config or {})
        self._clock = clock
        self._known = {}      # name -> (mtime, size) stato stabile gia' snapshottato
        self._pending = {}    # name -> (mtime, size) visto ma non ancora stabile
        self._last_hash = {}  # name -> hash dell'ultimo snapshot
        self._armed_at = None

    # --- API pubblica ---
    def arm_restore(self):
        self._armed_at = self._clock()

    def poll_once(self):
        report = {"snapshotted": [], "restored": []}
        current = self._scan()
        for name, meta in current.items():
            if self._known.get(name) == meta:
                continue
            if self._pending.get(name) == meta:      # stabile per un ciclo
                if self._snapshot(name):
                    report["snapshotted"].append(name)
                self._known[name] = meta
                self._pending.pop(name, None)
            else:
                self._pending[name] = meta           # attendi stabilita'
        return report

    # --- interni ---
    def _scan(self):
        out = {}
        try:
            names = os.listdir(self.saves_dir)
        except FileNotFoundError:
            return out
        for fn in names:
            if fn.endswith(".cs"):
                p = os.path.join(self.saves_dir, fn)
                try:
                    st = os.stat(p)
                except OSError:
                    continue
                out[fn[:-3]] = (st.st_mtime, st.st_size)
        return out

    def _snapshot(self, name):
        src = os.path.join(self.saves_dir, name + ".cs")
        try:
            with open(src, "rb") as f:
                data = f.read()
        except OSError:
            return False
        h = hashlib.sha1(data).hexdigest()
        if self._last_hash.get(name) == h:
            return False
        d = os.path.join(self.checkpoints_dir, name)
        os.makedirs(d, exist_ok=True)
        idx = self._next_index(d)
        shutil.copy2(src, os.path.join(d, "%04d.cs" % idx))
        self._last_hash[name] = h
        return True

    def _next_index(self, d):
        mx = -1
        for fn in os.listdir(d):
            if fn.endswith(".cs") and fn[:-3].isdigit():
                mx = max(mx, int(fn[:-3]))
        return mx + 1
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest director/tests/test_save_guard.py -v`
Expected: 3 PASS.

- [ ] **Step 5: Commit**

```bash
git add director/save_guard.py director/tests/test_save_guard.py
git commit -m "feat(saveguard): snapshot with debounce + dedup"
```

---

## Task 2: Rotazione (mantieni ultimi `keep`)

**Files:**
- Modify: `director/save_guard.py`
- Test: `director/tests/test_save_guard.py`

**Interfaces:**
- Consumes: `SaveGuard`, `_snapshot()` da Task 1.
- Produces: dopo ogni snapshot restano al massimo `cfg["keep"]` file `NNNN.cs` (i più recenti per indice); i più vecchi eliminati.

- [ ] **Step 1: Write the failing test**

```python
def test_rotation_keeps_last_n(tmp_path):
    saves, ckpt = _mk(tmp_path)
    p = os.path.join(saves, "Hero.cs")
    g = SaveGuard(saves, ckpt, {"keep": 3})
    for i in range(6):
        _write(p, b"content-%d" % i)   # contenuto sempre diverso
        g.poll_once(); g.poll_once()   # forza snapshot
    snaps = _snaps(ckpt, "Hero")
    assert len(snaps) == 3
    assert snaps == ["0003.cs", "0004.cs", "0005.cs"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest director/tests/test_save_guard.py::test_rotation_keeps_last_n -v`
Expected: FAIL (restano 6 file invece di 3).

- [ ] **Step 3: Write minimal implementation**

In `_snapshot()`, subito prima di `return True`, aggiungi la chiamata alla rotazione:
```python
        self._last_hash[name] = h
        self._rotate(d)
        return True
```
E aggiungi il metodo:
```python
    def _rotate(self, d):
        snaps = sorted(fn for fn in os.listdir(d)
                       if fn.endswith(".cs") and fn[:-3].isdigit())
        keep = int(self.cfg.get("keep", 5))
        for fn in snaps[:-keep] if keep > 0 else []:
            try:
                os.remove(os.path.join(d, fn))
            except OSError:
                pass
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest director/tests/test_save_guard.py -v`
Expected: tutti PASS (4).

- [ ] **Step 5: Commit**

```bash
git add director/save_guard.py director/tests/test_save_guard.py
git commit -m "feat(saveguard): rolling retention of last N checkpoints"
```

---

## Task 3: Ripristino alla cancellazione (armato dal token di morte)

**Files:**
- Modify: `director/save_guard.py`
- Test: `director/tests/test_save_guard.py`

**Interfaces:**
- Consumes: `SaveGuard`, `poll_once()`, `arm_restore()`, `_clock`.
- Produces: quando un `.cs` prima presente sparisce e il ripristino è **consentito**, l'ultimo snapshot viene copiato in `saves/<nome>.cs`; `poll_once()["restored"]` contiene il nome. Consenso: se `cfg["require_death_token"]` è vero, serve `arm_restore()` entro `restore_window_seconds`; altrimenti sempre.

- [ ] **Step 1: Write the failing tests**

```python
class FakeClock:
    def __init__(self): self.t = 1000.0
    def __call__(self): return self.t

def _snapshot_hero(saves, ckpt, data=b"level1", keep=5):
    p = os.path.join(saves, "Hero.cs")
    _write(p, data)
    g = SaveGuard(saves, ckpt, {"keep": keep}, clock=FakeClock())
    g.poll_once(); g.poll_once()      # crea 0000
    return g, p

def test_restore_when_armed(tmp_path):
    saves, ckpt = _mk(tmp_path)
    g, p = _snapshot_hero(saves, ckpt)
    g.arm_restore()
    os.remove(p)                       # morte: DCSS cancella il .cs
    r = g.poll_once()
    assert r["restored"] == ["Hero"]
    assert os.path.exists(p)
    with open(p, "rb") as f:
        assert f.read() == b"level1"

def test_no_restore_when_not_armed(tmp_path):
    saves, ckpt = _mk(tmp_path)
    g, p = _snapshot_hero(saves, ckpt)   # require_death_token=True di default
    os.remove(p)
    r = g.poll_once()
    assert r["restored"] == []
    assert not os.path.exists(p)

def test_no_restore_after_window_expired(tmp_path):
    saves, ckpt = _mk(tmp_path)
    clock = FakeClock()
    p = os.path.join(saves, "Hero.cs"); _write(p, b"level1")
    g = SaveGuard(saves, ckpt, {"restore_window_seconds": 30}, clock=clock)
    g.poll_once(); g.poll_once()
    g.arm_restore()                       # armato a t=1000
    clock.t += 31                         # oltre la finestra
    os.remove(p)
    assert g.poll_once()["restored"] == []
    assert not os.path.exists(p)

def test_fallback_restore_without_token(tmp_path):
    saves, ckpt = _mk(tmp_path)
    p = os.path.join(saves, "Hero.cs"); _write(p, b"level1")
    g = SaveGuard(saves, ckpt, {"require_death_token": False}, clock=FakeClock())
    g.poll_once(); g.poll_once()
    os.remove(p)                          # nessun arm, ma fallback attivo
    assert g.poll_once()["restored"] == ["Hero"]
    assert os.path.exists(p)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest director/tests/test_save_guard.py -k restore -v`
Expected: FAIL (nessuna logica di restore ancora; `restored` sempre `[]` e i file non ricompaiono).

- [ ] **Step 3: Write minimal implementation**

All'inizio di `poll_once()`, prima del ciclo sugli elementi correnti, gestisci le sparizioni:
```python
    def poll_once(self):
        report = {"snapshotted": [], "restored": []}
        current = self._scan()
        for name in list(self._known):        # rileva cancellazioni
            if name not in current:
                if self._maybe_restore(name):
                    report["restored"].append(name)
                del self._known[name]
                self._pending.pop(name, None)
        for name, meta in current.items():
            ...  # (blocco snapshot invariato da Task 1)
        return report
```
E aggiungi:
```python
    def _restore_allowed(self):
        if not self.cfg.get("require_death_token", True):
            return True
        if self._armed_at is None:
            return False
        return (self._clock() - self._armed_at) <= float(
            self.cfg.get("restore_window_seconds", 30))

    def _maybe_restore(self, name):
        if not self._restore_allowed():
            return False
        d = os.path.join(self.checkpoints_dir, name)
        if not os.path.isdir(d):
            return False
        snaps = sorted(fn for fn in os.listdir(d)
                       if fn.endswith(".cs") and fn[:-3].isdigit())
        if not snaps:
            return False
        latest = os.path.join(d, snaps[-1])
        dst = os.path.join(self.saves_dir, name + ".cs")
        shutil.copy2(latest, dst)
        self._armed_at = None                 # disarma dopo il ripristino
        return True
```

Nota: la cancellazione va rilevata da `_known`. Perché `_known` contenga il personaggio, deve essere stato snapshottato almeno una volta (il che avviene già dopo il debounce). Un file mai stabilizzato (solo in `_pending`) e poi cancellato non ha snapshot → nessun ripristino (corretto).

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest director/tests/test_save_guard.py -v`
Expected: tutti PASS (8).

- [ ] **Step 5: Commit**

```bash
git add director/save_guard.py director/tests/test_save_guard.py
git commit -m "feat(saveguard): restore latest checkpoint on death (armed)"
```

---

## Task 4: Config, risoluzione path e loop del thread

**Files:**
- Modify: `director/save_guard.py`
- Create: `director/saveguard.json`
- Test: `director/tests/test_save_guard.py`

**Interfaces:**
- Consumes: `SaveGuard`, `DEFAULT_CONFIG`.
- Produces:
  - `resolve_saves_dir(here: str) -> str` — env `DCSS_SAVES_DIR` se presente, altrimenti `here/../../saves` assoluto.
  - `load_saveguard_config(here: str) -> dict` — merge di `DEFAULT_CONFIG` con `here/saveguard.json` se esiste (altrimenti default).
  - `SaveGuard.run_forever() -> None` — loop `poll_once()` + `sleep(poll_seconds)`, con try/except che assorbe ogni errore; ritorna subito se `cfg["enabled"]` è falso.

- [ ] **Step 1: Write the failing tests**

```python
def test_resolve_saves_dir_env(monkeypatch, tmp_path):
    from save_guard import resolve_saves_dir
    monkeypatch.setenv("DCSS_SAVES_DIR", str(tmp_path / "s"))
    assert resolve_saves_dir("/whatever/here") == str(tmp_path / "s")

def test_resolve_saves_dir_dev_fallback(monkeypatch):
    from save_guard import resolve_saves_dir
    monkeypatch.delenv("DCSS_SAVES_DIR", raising=False)
    here = os.path.normpath("/game/stone_soup-tiles-0.34/remaster/director")
    got = os.path.normpath(resolve_saves_dir(here))
    assert got == os.path.normpath("/game/stone_soup-tiles-0.34/saves")

def test_load_config_defaults_when_missing(tmp_path):
    from save_guard import load_saveguard_config, DEFAULT_CONFIG
    cfg = load_saveguard_config(str(tmp_path))     # nessun saveguard.json
    assert cfg == DEFAULT_CONFIG

def test_load_config_merges_file(tmp_path):
    from save_guard import load_saveguard_config
    (tmp_path / "saveguard.json").write_text('{"keep": 3, "enabled": false}')
    cfg = load_saveguard_config(str(tmp_path))
    assert cfg["keep"] == 3 and cfg["enabled"] is False
    assert cfg["poll_seconds"] == 1.5             # default preservato
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest director/tests/test_save_guard.py -k "resolve or config" -v`
Expected: FAIL con `ImportError` su `resolve_saves_dir` / `load_saveguard_config`.

- [ ] **Step 3: Write minimal implementation**

In fondo a `save_guard.py`:
```python
def resolve_saves_dir(here):
    env = os.environ.get("DCSS_SAVES_DIR")
    if env:
        return env
    return os.path.abspath(os.path.join(here, "..", "..", "saves"))

def load_saveguard_config(here):
    cfg = dict(DEFAULT_CONFIG)
    try:
        with open(os.path.join(here, "saveguard.json"), encoding="utf-8") as f:
            cfg.update(json.load(f))
    except FileNotFoundError:
        pass
    return cfg
```
E come metodo di `SaveGuard`:
```python
    def run_forever(self):
        if not self.cfg.get("enabled", True):
            return
        while True:
            try:
                self.poll_once()
            except Exception:
                pass
            time.sleep(float(self.cfg.get("poll_seconds", 1.5)))
```

Crea `director/saveguard.json`:
```json
{
  "enabled": true,
  "keep": 5,
  "poll_seconds": 1.5,
  "require_death_token": true,
  "restore_window_seconds": 30
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest director/tests/test_save_guard.py -v`
Expected: tutti PASS (12).

- [ ] **Step 5: Commit**

```bash
git add director/save_guard.py director/saveguard.json director/tests/test_save_guard.py
git commit -m "feat(saveguard): config load, path resolution, run_forever loop"
```

---

## Task 5: Integrazione nel Director

**Files:**
- Modify: `director/director.py`

**Interfaces:**
- Consumes: `SaveGuard`, `resolve_saves_dir`, `load_saveguard_config` da Task 1/3/4; token `state__player_death`.
- Produces: all'avvio del Director parte un thread daemon `SaveGuard` (se `enabled`); alla ricezione del token `state__player_death`, chiama `guard.arm_restore()`.

- [ ] **Step 1: Aggiungi import e threading in testa**

In `director/director.py`, riga 1, cambia:
```python
import json, os, sys, time
```
in:
```python
import json, os, sys, time, threading
```
E dopo gli altri import (dopo la riga `from gfx_state import GfxShmem`) aggiungi:
```python
from save_guard import SaveGuard, resolve_saves_dir, load_saveguard_config
```

- [ ] **Step 2: Avvia il thread in `main()` prima del PipeServer**

In `main()`, subito prima della riga `print("[director] pronto. ...")`, inserisci:
```python
    guard = None
    try:
        sg_cfg = load_saveguard_config(HERE)
        if sg_cfg.get("enabled", True):
            saves_dir = resolve_saves_dir(HERE)
            ckpt_dir = os.path.join(os.path.dirname(saves_dir), "remaster_checkpoints")
            guard = SaveGuard(saves_dir, ckpt_dir, sg_cfg)
            threading.Thread(target=guard.run_forever, daemon=True).start()
            logln("[saveguard] attivo: saves=%s ckpt=%s keep=%s" %
                  (saves_dir, ckpt_dir, sg_cfg.get("keep")))
        else:
            logln("[saveguard] disattivato da config")
    except Exception as e:
        logln("[saveguard] errore avvio (proseguo senza): " + repr(e))
```

- [ ] **Step 3: Arma il ripristino sul token di morte**

Dentro la funzione `handle(raw)`, subito dopo la riga `logln("[evt] " + token + " -> " + str(ops))`, inserisci:
```python
        if guard is not None and token == "state__player_death":
            guard.arm_restore()
            logln("[saveguard] restore armato (morte rilevata)")
```
(`guard` è catturato dalla closure di `main()`.)

- [ ] **Step 4: Smoke test — il Director si avvia e importa senza errori**

Run (dalla cartella `director/`, senza gioco):
```bash
cd director && timeout 3 python -c "import director" ; echo "import exit: $?"
```
Expected: nessun traceback di import (l'`import director` esegue solo le definizioni, non `main()`). In alternativa avvia `python director.py` per ~3s e controlla che `director.log` contenga `[saveguard] attivo` senza eccezioni, poi interrompi.

- [ ] **Step 5: Commit**

```bash
git add director/director.py
git commit -m "feat(saveguard): wire into Director (thread start + arm on death)"
```

---

## Task 6: Launcher — export `DCSS_SAVES_DIR`

**Files:**
- Modify: `play-remaster.ps1`

**Interfaces:**
- Consumes: `$game` (già definito nel launcher = root del gioco).
- Produces: variabile d'ambiente `DCSS_SAVES_DIR = <game>\saves` ereditata dal processo Director.

- [ ] **Step 1: Esporta la variabile prima di avviare il Director**

In `play-remaster.ps1`, subito dopo la riga `$dirDir = "$PSScriptRoot\director"` (riga 5), aggiungi (ASCII puro):
```powershell
# Save-Guard: indica al Director dove sta la cartella dei salvataggi del gioco.
$env:DCSS_SAVES_DIR = "$game\saves"
```
(Va prima del blocco "3) Avvia il Director" così il processo figlio eredita la variabile.)

- [ ] **Step 2: Verifica ASCII del file**

Run:
```bash
python -c "open('play-remaster.ps1',encoding='ascii').read(); print('ASCII OK')"
```
Expected: `ASCII OK` (nessun `UnicodeDecodeError`).

- [ ] **Step 3: Commit**

```bash
git add play-remaster.ps1
git commit -m "feat(saveguard): launcher exports DCSS_SAVES_DIR"
```

---

## Task 7: Validazione end-to-end in-game (manuale)

**Files:** nessuno (verifica).

- [ ] **Step 1: Checkpoint per-piano**

Avvia col launcher, gioca un personaggio, scendi di 2-3 piani. Verifica che gli snapshot compaiano:
```bash
ls -la "stone_soup-tiles-0.34/remaster_checkpoints/<nome>/"
```
Atteso: uno o più `NNNN.cs`, al più 5. Controlla `director/director.log` per righe `[saveguard] attivo` e assenza di eccezioni.

- [ ] **Step 2: Ripristino alla morte**

Fai morire il personaggio. Atteso: `director.log` mostra `restore armato (morte rilevata)`, e dopo la cancellazione il file `saves/<nome>.cs` **riappare** (identico all'ultimo snapshot).

- [ ] **Step 3: Ricarica giocabile**

Rilancia col launcher → il personaggio è nel menu, si carica vivo all'inizio del piano dove è morto. Verifica anche il caso "stessa sessione" (dal menu post-morte senza chiudere `crawl.exe`): se non ricompare subito, va bene — la UX garantita è il rilancio.

- [ ] **Step 4: Regressione test suite completa**

Run: `python -m pytest director/tests/ -v`
Expected: tutti verdi (i test preesistenti + i nuovi).

- [ ] **Step 5: Nota eventuali scostamenti**

Se il timing del token di morte NON arma in tempo (il file viene cancellato ma non ripristinato), imposta in `director/saveguard.json` `"require_death_token": false` e ripeti Step 2-3. Registra l'esito per la memoria (Task 8).

---

## Task 8: Aggiorna la memoria di progetto

**Files:**
- Create: `C:\Users\old_p\.claude\projects\C--Users-old-p-Documents-progetto-dcss-remastered\memory\dcss-remastered-saveguard.md`
- Modify: `...\memory\MEMORY.md`

- [ ] **Step 1: Scrivi il file memoria** (type: project) con: cosa fa il save-guard, dove sta (`director/save_guard.py`, `saveguard.json`, checkpoint in `remaster_checkpoints/`), l'esito dei rischi validati in Task 0/7 (soprattutto se il `.cs` si riscrive a cambio piano, e se il token di morte arma in tempo o si è dovuto usare il fallback), e i link `[[dcss-remastered-audio]]` `[[dcss-remastered-packaging]]`.

- [ ] **Step 2: Aggiungi la riga indice in `MEMORY.md`**:
```
- [DCSS Remastered Save-Guard](dcss-remastered-saveguard.md) — checkpoint per-piano + ripristino alla morte via SaveGuard nel Director (polling di saves/, no permadeath), senza ricompilare.
```

- [ ] **Step 3: Packaging** — ricorda (non necessariamente in questa sessione) che una nuova release ZIP includerà automaticamente `save_guard.py`/`saveguard.json` nel freeze del Director e la modifica al launcher; vedi `[[dcss-remastered-packaging]]`. Nessuna azione di build richiesta dal piano.

---

## Self-Review (esito)

- **Copertura spec:** snapshot per-piano (Task 1), rotazione (Task 2), restore armato + finestra + fallback (Task 3), config/path/loop (Task 4), wiring Director + arm su morte (Task 5), launcher env (Task 6), validazione rischi #1-#5 (Task 0 + Task 7). Tutte le sezioni dello spec hanno un task.
- **Placeholder:** nessuno; ogni step di codice mostra il codice completo.
- **Coerenza tipi:** `poll_once() -> {"snapshotted","restored"}`, `arm_restore()`, `run_forever()`, `resolve_saves_dir()`, `load_saveguard_config()`, `DEFAULT_CONFIG` usati in modo identico tra i task. Nomi snapshot `%04d.cs` coerenti (Task 1/2/3).
- **Rischio cardine** isolato come GATE (Task 0) prima di scrivere codice.
