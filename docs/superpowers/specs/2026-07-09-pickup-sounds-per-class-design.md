# Suoni di pickup per classe oggetto — Design

**Data:** 2026-07-09
**Stato:** approvato, pronto per il piano

## Contesto

Oggi raccogliere un qualsiasi oggetto produce un unico suono generico
(`evt__pickup.wav`), cablato dalla regola `sound += You now have:evt__pickup.wav`
in `remaster/config/remaster.rc`. L'utente vuole un **feedback audio dedicato per
categoria** (pergamene, anelli, pozioni, armi, armature… e, per scelta esplicita,
**tutte** le classi oggetto di DCSS).

Vincolo tecnico centrale, verificato sul binario `crawl.exe` (PE32, nessun sorgente):
il messaggio di pickup è `You now have <nome oggetto>.` — contiene il nome completo
ma **nessuna lettera di slot** e, per armi/armature, **nessuna parola di categoria**
(es. `You now have a +0 robe.`). Perciò il matching per regex sui messaggi è
impraticabile per "copri tutto": la classificazione deve leggere la **classe oggetto
reale**.

Conferme dal binario:
- `you.gold` è esposto a clua.
- Le funzioni della libreria item clua esistono come binding: `inventory`, `class`,
  `quantity`, `subtype`, `inslot`, `is_useless`, `artefact` (la stessa API usata dalle
  autopickup func, quindi disponibile nel sandbox clua del `.rc`, a differenza di
  `you.pos()` che è bloccato).
- Il Director instrada per **basename del wav** (`router.path_to_token`): un token
  assente da `soundmap.json` viene ignorato (silenzio) → i suoni nuovi vanno registrati.

## Obiettivo

Un suono distinto e "leggibile" per ogni classe oggetto raccolta, riusando
l'architettura esistente (proxy winmm → pipe → Director) senza ricompilare il gioco.

## Architettura

### 1. Rilevamento — diff dell'inventario in clua

Nell'hook `ready()` di `remaster.rc` (gira già a ogni turno per branch/HP/passo) si
aggiunge uno snapshot dell'inventario:

- Stato mantenuto: `last_inv` = tabella `slot_index → { class = <stringa>, qty = <n> }`,
  più `last_gold`.
- A ogni turno si costruisce `cur_inv` da `items.inventory()`. Per ogni item si legge
  `item:class(true)` (classe terse), `item.quantity`, e l'indice di slot.
- **Pickup rilevato** quando: uno slot è nuovo, **oppure** la quantità dello slot
  **aumenta**. Le diminuzioni (drop/uso/lancio) si ignorano.
- L'oro non è un item d'inventario: si rileva da `you.gold() > last_gold`.
- Si raccoglie l'insieme delle **classi distinte** con delta positivo e si riproduce
  un suono per classe via `crawl.playsound("remaster/audio/sfx/<token>.wav")`.

Vantaggi: robusto per armi/armature/artefatti (nessuna enumerazione di nomi base),
copre anche l'auto-pickup, riusa il pattern snapshot già presente (`last_turns`,
`last_hp_band`, `last_branch`).

### 2. Mappa classe → token audio

`item:class(true)` → token wav:

| classe clua      | token                 |
|------------------|-----------------------|
| weapon           | `evt__pickup_weapon`  |
| armour           | `evt__pickup_armour`  |
| missile          | `evt__pickup_missile` |
| scroll           | `evt__pickup_scroll`  |
| potion           | `evt__pickup_potion`  |
| jewellery → ring | `evt__pickup_ring`    |
| jewellery → amulet | `evt__pickup_amulet`|
| wand             | `evt__pickup_wand`    |
| book             | `evt__pickup_book`    |
| staff (magico)   | `evt__pickup_staff`   |
| misc / evocable  | `evt__pickup_misc`    |
| talisman         | `evt__pickup_talisman`|
| gold (Δ you.gold)| `evt__pickup_gold`    |
| *fallback ignoto*| `evt__pickup` (generico esistente) |
| rune / Orb       | *gestiti dai jingle epici esistenti (non-inventario)* |

- Ring vs amulet: distinti dal nome/subtype dell'item (`jewellery` è un'unica OBJ class).
- La stringa esatta restituita da `class(true)` verrà **confermata in-game** dal
  `director.log`; la mappa è difensiva e le classi ignote cadono sul fallback generico
  (mai silenzio, mai crash).

### 3. Comportamento pickup multiplo

Raccogliere una pila mista (comando `,`) fa entrare più classi nello stesso turno.
**Decisione:** una riproduzione per **classe distinta**, con **cap = 2** per turno
(anti-cacofonia). Le classi oltre il cap in quel turno vengono saltate.

### 4. Sintesi audio (`tools/make_sfx.py`)

~13 nuovi WAV corti (~0.15–0.3 s), mono 44100 16-bit, generati coi primitivi esistenti
(`tone`, `noise`, `sweep`, `metal`, `mix`, `pad`), deterministici (seed fissi), CC0.
Timbri distinti e riconoscibili:

- pergamena → fruscio cartaceo (breve, filtrato)
- pozione → clink vetroso + piccolo "tappo"
- anello → ting metallico brillante, piccolo
- amuleto → chime caldo
- arma → *shing* metallico corto (draw)
- armatura → clangore pesante + componente cuoio
- dardi → rattle di faretra (rumore filtrato ritmico)
- bacchetta → blip shimmer magico (sweep breve)
- libro → tonfo + sfoglio di pagine
- bastone → knock legnoso + hum basso
- misc → pickup neutro brillante
- oro → jingle di monete
- talismano → shimmer esoterico

### 5. Registrazione audio (`director/soundmap.json`)

13 nuove entry nel blocco `sfx`, `group: "item"`, volume ~0.55–0.6 (oro leggermente
più squillante). Struttura identica alle entry esistenti
(`{"files": ["<token>.wav"], "volume": …, "group": "item"}`).

### 6. Config di gioco (`config/remaster.rc`)

- **Rimuovere** la riga generica `sound += You now have:evt__pickup.wav`: ora è la Lua
  a guidare l'audio del pickup; tenerla causerebbe suono doppio.
- Le regole `Orb of Zot` / `rune of Zot` **restano** (messaggi propri, oggetti non in
  inventario → nessun conflitto con il diff).
- `evt__pickup.wav` resta come **fallback** usato dalla Lua per classi non mappate.

## Casi limite

- **Primo turno / nuova partita:** si inizializza `last_inv`/`last_gold` senza
  riprodurre alcun suono (riuso del reset new-game esistente basato su `you.name()`/xl),
  per non classificare come "pickup" l'inventario iniziale.
- **Equipaggiare/indossare:** non cambia quantità né slot → nessun falso positivo.
- **Drop / uso / lancio:** quantità in calo → ignorata.
- **Ricarica bacchette / stack merge:** aumento di quantità in slot esistente →
  correttamente rilevato come pickup.

## Componenti toccati

- `remaster/config/remaster.rc` — diff inventario nell'hook `ready()`; rimozione regola generica.
- `remaster/tools/make_sfx.py` — sintesi dei ~13 nuovi WAV.
- `remaster/director/soundmap.json` — registrazione dei 13 token.
- `remaster/audio/sfx/*.wav` — output generato (gitignored come gli altri asset).

## Verifica end-to-end

1. `python remaster/tools/make_sfx.py` → i 13 WAV esistono in `remaster/audio/sfx/`.
2. `pytest remaster/director/tests` → verde (router/soundmap invariati per contratto).
3. Avvio del gioco reale (`Play DCSS Remastered.bat`), raccolta di un oggetto per
   categoria; conferma dal `director.log` che il token corretto viene instradato.
4. Se `class(true)` restituisce stringhe diverse dal previsto, correggere la mappa in
   `remaster.rc` (nessuna ricompilazione: solo riavvio del Director).
