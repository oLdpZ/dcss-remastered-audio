# Suoni di pickup per classe oggetto — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Riprodurre un suono dedicato per ogni classe di oggetto raccolta in DCSS, al posto dell'unico suono generico attuale.

**Architecture:** L'hook Lua `ready()` in `remaster.rc` (già gira ogni turno) fa un diff dell'inventario via `items.inventory()`/`you.gold()`, legge `item:class(true)` e riproduce con `crawl.playsound()` il WAV della categoria. I WAV sono sintetizzati in `make_sfx.py` e registrati in `soundmap.json`; il Director li instrada per basename. Nessuna ricompilazione del gioco.

**Tech Stack:** Lua (config `.rc` clua sandbox), Python 3 (stdlib `wave`/`struct`/`math` per la sintesi; `pytest` per i test del router), JSON.

## Global Constraints

- WAV di output: **mono, 44100 Hz, 16-bit** (funzione `save()` esistente in `make_sfx.py`).
- Sintesi **CC0** e **deterministica**: ogni suono preceduto da `random.seed(<n>)` con seed fisso.
- Un token audio non registrato in `soundmap.json` viene **ignorato** (silenzio) dal Director → ogni nuovo WAV DEVE avere la sua entry.
- La logica Lua **non deve mai crashare l'audio**: ogni chiamata all'API di gioco va in `pcall`; su fallimento si degrada al silenzio, mai un errore.
- Nessuna ricompilazione di `crawl.exe`. Modifiche solo a config/asset/Director.
- Le stringhe esatte di `item:class(true)` sono da **confermare in-game** (Task 4): la mappa è difensiva e le classi ignote cadono sul fallback `evt__pickup`.

---

### Task 1: Sintesi dei 13 WAV di pickup (make_sfx.py)

**Files:**
- Modify: `remaster/tools/make_sfx.py` (append prima della riga finale `print(...)`)

**Interfaces:**
- Consumes: helper esistenti nello stesso file — `tone()`, `noise()`, `sweep()`, `mix()`, `pad()`, `metal()`, `wood_knock()`, `save()`, costante `FR`.
- Produces: 13 file in `remaster/audio/sfx/`: `evt__pickup_weapon.wav`, `evt__pickup_armour.wav`, `evt__pickup_missile.wav`, `evt__pickup_scroll.wav`, `evt__pickup_potion.wav`, `evt__pickup_ring.wav`, `evt__pickup_amulet.wav`, `evt__pickup_wand.wav`, `evt__pickup_book.wav`, `evt__pickup_staff.wav`, `evt__pickup_misc.wav`, `evt__pickup_talisman.wav`, `evt__pickup_gold.wav`.

- [ ] **Step 1: Aggiungere la sezione di sintesi**

In `remaster/tools/make_sfx.py`, subito **prima** della riga finale `print("SFX sintetizzati in", OUT)`, incollare:

```python
# =========================================================================
#  Suoni di pickup per classe oggetto (CC0)
# =========================================================================

# pergamena: fruscio cartaceo breve + micro-tick
random.seed(90)
save("evt__pickup_scroll.wav", mix([
    pad(noise(0.10, 0.04, vol=0.32, lp=0.35), 0.16),
    pad([0]*int(0.05*FR) + noise(0.05, 0.02, vol=0.22, lp=0.4), 0.16)]))

# pozione: clink vetroso brillante + piccolo "tappo"
random.seed(91)
save("evt__pickup_potion.wav", mix([
    pad(tone(1760, 0.10, 0.05, vol=0.35, partials=(1, 0.6, 0.3)), 0.20),
    pad([0]*int(0.03*FR) + tone(2637, 0.08, 0.04, vol=0.22), 0.20),
    pad([0]*int(0.11*FR) + tone(300, 0.05, 0.02, vol=0.18), 0.20)]))  # pop tappo

# anello: ting metallico piccolo e brillante
random.seed(92)
save("evt__pickup_ring.wav", pad(metal(1320, 0.30, 0.12), 0.34))

# amuleto: chime caldo (piu' grave, code lunghe)
random.seed(93)
save("evt__pickup_amulet.wav", mix([
    pad(tone(880, 0.5, 0.35, vol=0.3, partials=(1, 0.5, 0.25)), 0.5),
    pad([0]*int(0.06*FR) + tone(1174, 0.45, 0.3, vol=0.2, partials=(1, 0.5)), 0.5)]))

# arma: "shing" metallico corto (draw della lama)
random.seed(94)
save("evt__pickup_weapon.wav", mix([
    pad(sweep(600, 2600, 0.14, 0.06, vol=0.3), 0.26),
    pad(metal(720, 0.3, 0.1), 0.26),
    pad(noise(0.05, 0.015, vol=0.2, lp=0.85), 0.26)]))

# armatura: clangore pesante + componente cuoio + tonfo
random.seed(95)
save("evt__pickup_armour.wav", mix([
    pad(metal(300, 0.4, 0.18), 0.34),
    pad(noise(0.12, 0.05, vol=0.28, lp=0.3), 0.34),
    pad([0]*int(0.02*FR) + tone(140, 0.10, 0.04, vol=0.3), 0.34)]))

# dardi/proiettili: rattle di faretra (noise ritmico)
random.seed(96)
quiver = []
for k in range(3):
    quiver.append(pad([0]*int(0.05*k*FR) + noise(0.05, 0.02, vol=0.3, lp=0.6), 0.22))
save("evt__pickup_missile.wav", mix(quiver))

# bacchetta: blip shimmer magico (sweep ascendente + detune)
random.seed(97)
save("evt__pickup_wand.wav", mix([
    pad(sweep(500, 1500, 0.16, 0.09, vol=0.28), 0.24),
    pad(sweep(505, 1520, 0.16, 0.09, vol=0.18), 0.24)]))

# libro: tonfo sordo di copertina + sfoglio di pagine
random.seed(98)
save("evt__pickup_book.wav", mix([
    pad(tone(120, 0.12, 0.05, vol=0.4), 0.28),
    pad([0]*int(0.10*FR) + noise(0.12, 0.05, vol=0.22, lp=0.3), 0.28)]))

# bastone magico: knock legnoso + hum grave
random.seed(99)
save("evt__pickup_staff.wav", mix([
    pad(wood_knock(150, 0.4), 0.30),
    pad([0]*int(0.04*FR) + tone(90, 0.22, 0.12, vol=0.22, partials=(1, 0.5)), 0.30)]))

# misc/evocable: pickup neutro brillante (due note)
random.seed(100)
save("evt__pickup_misc.wav", mix([
    pad(tone(784, 0.12, 0.08, vol=0.35, partials=(1, 0.4)), 0.26),
    pad([0]*int(0.09*FR) + tone(1175, 0.14, 0.09, vol=0.3, partials=(1, 0.4)), 0.26)]))

# talismano: shimmer esoterico (accordo sospeso + vibrato)
random.seed(101)
save("evt__pickup_talisman.wav", mix([
    pad(tone(659, 0.4, 0.28, vol=0.26, partials=(1, 0.5, 0.3), vibrato=0.015), 0.42),
    pad(tone(988, 0.38, 0.26, vol=0.2, partials=(1, 0.5), vibrato=0.02), 0.42)]))

# oro: jingle di monete (tintinnii metallici multipli)
random.seed(102)
coins = []
for k, f in enumerate([2100, 2640, 1900, 2400, 2200]):
    coins.append(pad([0]*int(0.03*k*FR) + tone(f, 0.10, 0.05, vol=0.22, partials=(1, 0.7, 0.4)), 0.34))
save("evt__pickup_gold.wav", mix(coins))
```

- [ ] **Step 2: Eseguire il generatore**

Run: `python "remaster/tools/make_sfx.py"`
Expected: stampa `SFX sintetizzati in <...>/remaster/audio/sfx` senza errori.

- [ ] **Step 3: Verificare i 13 file (esistenza + formato WAV corretto)**

Run:
```bash
python - <<'PY'
import wave, os
OUT = "remaster/audio/sfx"
toks = ["weapon","armour","missile","scroll","potion","ring","amulet",
        "wand","book","staff","misc","talisman","gold"]
for t in toks:
    p = os.path.join(OUT, f"evt__pickup_{t}.wav")
    w = wave.open(p); assert w.getnchannels()==1 and w.getsampwidth()==2 and w.getframerate()==44100, p
    assert w.getnframes() > 0, p
    w.close()
print("OK", len(toks), "file")
PY
```
Expected: `OK 13 file`

- [ ] **Step 4: Commit**

```bash
git add remaster/tools/make_sfx.py
git commit -m "feat(audio): synth 13 per-class pickup SFX"
```
(I `.wav` sono gitignored come gli altri asset: si committa solo il generatore.)

---

### Task 2: Registrare i 13 token in soundmap.json (+ test router)

**Files:**
- Modify: `remaster/director/soundmap.json` (blocco `"sfx"`, dopo la entry `evt__pickup`)
- Create: `remaster/director/tests/test_pickup_soundmap.py`

**Interfaces:**
- Consumes: `router.Router` esistente e il file `soundmap.json` reale.
- Produces: 13 entry sfx (`group: "item"`) che il `Router` instrada come azione singola `op == "sfx"`.

- [ ] **Step 1: Scrivere il test che fallisce**

Creare `remaster/director/tests/test_pickup_soundmap.py`:

```python
import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from router import Router

HERE = os.path.dirname(__file__)
SOUNDMAP_PATH = os.path.join(os.path.dirname(HERE), "soundmap.json")

PICKUP_TOKENS = [
    "evt__pickup_weapon", "evt__pickup_armour", "evt__pickup_missile",
    "evt__pickup_scroll", "evt__pickup_potion", "evt__pickup_ring",
    "evt__pickup_amulet", "evt__pickup_wand", "evt__pickup_book",
    "evt__pickup_staff", "evt__pickup_misc", "evt__pickup_talisman",
    "evt__pickup_gold",
]

def _load():
    with open(SOUNDMAP_PATH, encoding="utf-8") as f:
        return json.load(f)

def test_all_pickup_tokens_registered_as_item_sfx():
    r = Router(_load())
    for tok in PICKUP_TOKENS:
        acts = r.route(tok)
        assert len(acts) == 1, f"{tok} non instradato"
        assert acts[0]["op"] == "sfx", f"{tok} op={acts[0]['op']}"
        assert acts[0]["group"] == "item", f"{tok} group={acts[0]['group']}"

def test_generic_pickup_fallback_still_present():
    acts = Router(_load()).route("evt__pickup")
    assert len(acts) == 1 and acts[0]["op"] == "sfx"
```

- [ ] **Step 2: Eseguire il test per verificare che fallisca**

Run: `python -m pytest remaster/director/tests/test_pickup_soundmap.py -v`
Expected: FAIL su `test_all_pickup_tokens_registered_as_item_sfx` (i token non esistono ancora → `route()` torna `[]`, `len(acts)==0`).

- [ ] **Step 3: Aggiungere le entry a soundmap.json**

In `remaster/director/soundmap.json`, subito **dopo** la riga:
```json
    "evt__pickup":    {"files": ["evt__pickup.wav"], "volume": 0.6, "group": "item"},
```
inserire:
```json
    "evt__pickup_weapon":   {"files": ["evt__pickup_weapon.wav"],   "volume": 0.6,  "group": "item"},
    "evt__pickup_armour":   {"files": ["evt__pickup_armour.wav"],   "volume": 0.6,  "group": "item"},
    "evt__pickup_missile":  {"files": ["evt__pickup_missile.wav"],  "volume": 0.55, "group": "item"},
    "evt__pickup_scroll":   {"files": ["evt__pickup_scroll.wav"],   "volume": 0.55, "group": "item"},
    "evt__pickup_potion":   {"files": ["evt__pickup_potion.wav"],   "volume": 0.55, "group": "item"},
    "evt__pickup_ring":     {"files": ["evt__pickup_ring.wav"],     "volume": 0.55, "group": "item"},
    "evt__pickup_amulet":   {"files": ["evt__pickup_amulet.wav"],   "volume": 0.55, "group": "item"},
    "evt__pickup_wand":     {"files": ["evt__pickup_wand.wav"],     "volume": 0.55, "group": "item"},
    "evt__pickup_book":     {"files": ["evt__pickup_book.wav"],     "volume": 0.6,  "group": "item"},
    "evt__pickup_staff":    {"files": ["evt__pickup_staff.wav"],    "volume": 0.6,  "group": "item"},
    "evt__pickup_misc":     {"files": ["evt__pickup_misc.wav"],     "volume": 0.55, "group": "item"},
    "evt__pickup_talisman": {"files": ["evt__pickup_talisman.wav"], "volume": 0.55, "group": "item"},
    "evt__pickup_gold":     {"files": ["evt__pickup_gold.wav"],     "volume": 0.6,  "group": "item"},
```
(Verificare che la entry `evt__pickup` mantenga la virgola finale e che non ci siano virgole pendenti a fine blocco.)

- [ ] **Step 4: Eseguire il test per verificare che passi**

Run: `python -m pytest remaster/director/tests/test_pickup_soundmap.py -v`
Expected: PASS (2 test).

- [ ] **Step 5: Eseguire l'intera suite del Director (nessuna regressione)**

Run: `python -m pytest remaster/director/tests -q`
Expected: tutti i test verdi.

- [ ] **Step 6: Commit**

```bash
git add remaster/director/soundmap.json remaster/director/tests/test_pickup_soundmap.py
git commit -m "feat(audio): register 13 per-class pickup tokens in soundmap"
```

---

### Task 3: Rilevamento pickup via diff inventario (remaster.rc)

**Files:**
- Modify: `remaster/config/remaster.rc` (rimuovere la regola generica riga ~22; estendere il blocco clua `{ ... }`)

**Interfaces:**
- Consumes: API clua verificate presenti nel binario — `items.inventory()`, `item:class(true)`, `item.quantity`, `item.slot`, `item:name()`, `you.gold()`, `crawl.playsound()`. Token audio da Task 1/2.
- Produces: nessuna interfaccia per task successivi (foglia). Riproduce i token `evt__pickup_*` in reazione ai pickup.

- [ ] **Step 1: Rimuovere la regola di pickup generica**

In `remaster/config/remaster.rc`, **eliminare** la riga:
```
sound += You now have:evt__pickup.wav
```
(Lasciare intatte le righe `Orb of Zot` e `rune of Zot` che la precedono: sono jingle epici su messaggi propri e riguardano oggetti non-inventario.)

- [ ] **Step 2: Aggiungere stato e helper in cima al blocco clua**

Nel blocco `{ ... }` (quello che inizia con `local last_branch = nil`), **dopo** la riga `local msg_this_turn = false` e **prima** di `function c_message`, inserire:

```lua
-- === Pickup per classe oggetto: stato + mappa ===
local last_inv = nil        -- slot(index) -> { qty = n, cls = string }
local last_gold = nil
local PICKUP_CAP = 2        -- max suoni di pickup per turno (anti-cacofonia)
local DEBUG_CLASS = false   -- true = emette il nome classe grezzo su director.log (tuning)

-- classe terse di item:class(true) -> token wav
local CLASS_SND = {
  ["weapon"]        = "evt__pickup_weapon",
  ["armour"]        = "evt__pickup_armour",
  ["missile"]       = "evt__pickup_missile",
  ["scroll"]        = "evt__pickup_scroll",
  ["potion"]        = "evt__pickup_potion",
  ["wand"]          = "evt__pickup_wand",
  ["book"]          = "evt__pickup_book",
  ["magical staff"] = "evt__pickup_staff",
  ["staff"]         = "evt__pickup_staff",
  ["miscellaneous"] = "evt__pickup_misc",
  ["misc"]          = "evt__pickup_misc",
  ["talisman"]      = "evt__pickup_talisman",
  ["gold"]          = "evt__pickup_gold",
  -- "jewellery" gestita a parte (ring vs amulet)
}

local function play_pickup(token)
  crawl.playsound("remaster/audio/sfx/" .. token .. ".wav")
end

-- token audio per un item (jewellery -> ring/amulet dal nome)
local function token_for(it)
  local okc, cls = pcall(function() return it:class(true) end)
  if not okc or not cls then return "evt__pickup" end
  if DEBUG_CLASS then
    crawl.playsound("remaster/dbg/cls_" .. tostring(cls) .. ".wav")
  end
  if cls == "jewellery" then
    local okn, nm = pcall(function() return it:name() end)
    if okn and nm and string.find(nm, "amulet") then
      return "evt__pickup_amulet"
    end
    return "evt__pickup_ring"
  end
  return CLASS_SND[cls] or "evt__pickup"
end
```

- [ ] **Step 3: Azzerare lo stato pickup alla nuova partita**

Nel corpo di `function ready()`, dentro il blocco che rileva una nuova partita, **aggiungere** l'azzeramento. Trovare:
```lua
    if nm ~= last_name or xl < last_xl then
      last_branch = nil      -- forza il riavvio della musica del branch
      last_hp_band = nil
      last_turns = -1        -- niente passo spurio all'inizio di una nuova partita
    end
```
e sostituirlo con:
```lua
    if nm ~= last_name or xl < last_xl then
      last_branch = nil      -- forza il riavvio della musica del branch
      last_hp_band = nil
      last_turns = -1        -- niente passo spurio all'inizio di una nuova partita
      last_inv = nil         -- non annunciare l'inventario iniziale come pickup
      last_gold = nil
    end
```

- [ ] **Step 4: Inserire il diff inventario + oro nel corpo di ready()**

In `function ready()`, **prima** della riga finale `msg_this_turn = false`, inserire:

```lua
  -- Pickup: diff inventario. Uno slot nuovo o con quantita' aumentata = raccolto.
  local oki, inv = pcall(function() return items.inventory() end)
  if oki and inv then
    local cur = {}
    for _, it in ipairs(inv) do
      local slot = it.slot
      local q = it.quantity or 1
      cur[slot] = { qty = q, it = it }
    end
    if last_inv ~= nil then           -- salta il primo turno / nuova partita
      local played, seen = 0, {}
      for slot, info in pairs(cur) do
        local prev = last_inv[slot]
        if (prev == nil) or (info.qty > prev.qty) then
          local token = token_for(info.it)
          if not seen[token] and played < PICKUP_CAP then
            play_pickup(token)
            seen[token] = true
            played = played + 1
          end
        end
      end
    end
    last_inv = {}                     -- snapshot senza riferimenti agli item
    for slot, info in pairs(cur) do last_inv[slot] = { qty = info.qty } end
  end

  -- Oro: non e' un item d'inventario, si guarda il delta.
  local okg, g = pcall(function() return you.gold() end)
  if okg and g then
    if last_gold ~= nil and g > last_gold then
      play_pickup("evt__pickup_gold")
    end
    last_gold = g
  end
```

- [ ] **Step 5: Sanity check sintattico del Lua**

Run (verifica solo che il file sia Lua ben formato; DCSS lo caricherà davvero in Task 4):
```bash
luac -p "remaster/config/remaster.rc" 2>/dev/null && echo "LUA OK" || echo "luac non disponibile: verifica manuale in Task 4"
```
Expected: `LUA OK` se `luac` è installato; altrimenti la verifica reale avviene all'avvio del gioco (Task 4). Il file `.rc` contiene direttive `sound +=` in testa che non sono Lua, quindi `luac` sull'intero file può segnalare errore sulle prime righe: in tal caso ci si affida alla verifica in-game.

- [ ] **Step 6: Commit**

```bash
git add remaster/config/remaster.rc
git commit -m "feat(audio): per-class pickup detection via inventory diff"
```

---

### Task 4: Verifica end-to-end in-game + tuning della mappa classi

**Files:**
- Modify (solo se necessario): `remaster/config/remaster.rc` (`CLASS_SND`)

**Interfaces:**
- Consumes: build funzionante (Task 1–3 applicati), `director.log` scritto dal Director.

- [ ] **Step 1: Avviare il gioco con audio**

Avviare `Play DCSS Remastered.bat` nella cartella del gioco (o `python remaster/director/director.py` in dev + gioco). Confermare che parte senza errori e che la musica del branch suona.

- [ ] **Step 2: Raccogliere un oggetto per categoria**

In una partita (o in wizard mode `&` se abilitato, per generare oggetti), raccogliere: un'arma, un'armatura, dei dardi, una pergamena, una pozione, un anello, un amuleto, una bacchetta, un libro, un bastone magico, un oggetto misc, oro. Ascoltare che ogni categoria produca il suono atteso e distinto.

- [ ] **Step 3: Confrontare con director.log**

Aprire `remaster/director.log` (il Director gira a finestra nascosta e logga i token instradati). Verificare che ogni pickup abbia instradato il token `evt__pickup_<classe>` corretto e **non** il fallback `evt__pickup`.

- [ ] **Step 4: Correggere la mappa se una classe cade sul fallback**

Se una categoria suona come fallback generico: impostare `DEBUG_CLASS = true` in `remaster.rc` (Step 2 di Task 3), riavviare il Director, raccogliere di nuovo quell'oggetto e leggere in `director.log` il token `cls_<stringa>` con la stringa **reale** restituita da `item:class(true)`. Aggiungere quella stringa come chiave in `CLASS_SND` mappandola al token giusto. Rimettere `DEBUG_CLASS = false`.

- [ ] **Step 5: Commit dell'eventuale correzione**

```bash
git add remaster/config/remaster.rc
git commit -m "fix(audio): map real item:class strings to pickup tokens"
```
(Se nessuna correzione è servita, saltare questo commit.)

---

## Self-Review

**Spec coverage:**
- Rilevamento diff inventario → Task 3. ✓
- Mappa classe→token (incl. ring/amulet split, gold via you.gold) → Task 3 (`CLASS_SND`, `token_for`). ✓
- Pickup multiplo cap 2 → Task 3 Step 4 (`PICKUP_CAP`, `seen`, `played`). ✓
- Sintesi 13 WAV → Task 1. ✓
- Registrazione soundmap → Task 2. ✓
- Rimozione regola generica, Orb/rune intatti, fallback evt__pickup → Task 2 (fallback resta) + Task 3 Step 1. ✓
- Casi limite (nuova partita, equip, drop, stack merge) → Task 3 Step 3/4 + logica qty. ✓
- Verifica end-to-end + tuning → Task 4. ✓

**Placeholder scan:** nessun TBD/TODO; tutto il codice è completo e incollabile.

**Type consistency:** `CLASS_SND`, `token_for`, `play_pickup`, `PICKUP_CAP`, `last_inv`, `last_gold`, `DEBUG_CLASS` usati coerentemente tra gli step di Task 3. I 13 token in Task 1 (file), Task 2 (soundmap) e Task 3 (`CLASS_SND`/`token_for`) coincidono esattamente.
