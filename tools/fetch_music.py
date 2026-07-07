"""Scarica musica a tema (Kevin MacLeod / Incompetech, CC-BY 4.0) per tutti i branch.
Prova piu' tracce candidate per branch, con pause anti-throttling; salta i file gia' presenti.
Salva in remaster/audio/music/<branch>.mp3 e stampa un manifest (fonte+licenza)."""
import os, time, urllib.request, urllib.parse

BASE = "https://incompetech.com/music/royalty-free/mp3-royaltyfree/"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.abspath(os.path.join(HERE, "..", "audio", "music"))
os.makedirs(OUT, exist_ok=True)

# nome file (branch) -> tracce candidate (ordine di preferenza). Piu' candidati = piu' robusto ai 404.
CANDIDATES = {
    "dungeon": ["Long Note Two", "Long Note Four", "Deep Haze"],
    "temple":  ["Meditation Impromptu 01", "Meditation Impromptu 02", "Peace of Mind 3"],
    "lair":    ["Chee Zee Cave", "Chee Zee Jungle", "Rites"],
    "orc":     ["Crusade", "Volatile Reaction", "Death and Axes"],
    "crypt":   ["Ghost Processional", "Bump in the Night", "Ossuary 5 Rest"],
    "depths":  ["The Descent", "Gathering Darkness", "Lightless Dawn"],
    # --- espansione ---
    "swamp":   ["Mesmerize", "Dark Fog", "Long Note Three", "Anxiety"],
    "shoals":  ["Windswept", "Impact Andante", "Long Note Four", "Deep Haze"],
    "snake":   ["Desert City", "Ibn Al-Noor", "Rites", "Kalimba Relaxation"],
    "spider":  ["Phantom from Space", "Bump in the Night", "Mesmerize", "Crypto"],
    "slime":   ["Controlled Chaos", "Nervous", "Volatile Reaction", "Mesmerize"],
    "elf":     ["Angevin", "Minstrel Guild", "Fairytale Waltz", "Pippin the Hunchback"],
    "vaults":  ["Master of the Feast", "Five Armies", "Clash Defiant", "Killers"],
    "tomb":    ["Curse of the Scarab", "Desert City", "Ibn Al-Noor", "Mysterioso March"],
    "zot":     ["Lightless Dawn", "Echoes of Time", "Killers", "Anguish"],
    "hell":    ["Anguish", "Nightmare Machine", "Dark Fog", "Mysterioso March"],
    "coc":     ["Frost Waltz", "Frozen Star", "Long Note Two", "Deep Haze"],
    "geh":     ["Volatile Reaction", "Anguish", "Crypto", "Dark Times"],
    "tar":     ["Dark Fog", "Wounded", "Mesmerize", "Anxiety"],
    "dis":     ["Killers", "Crypto", "Heavy Interlude", "Controlled Chaos"],
    "abyss":   ["Unseen Horrors", "Phantom from Space", "Nervous", "Controlled Chaos"],
    "pan":     ["Nightmare Machine", "Anxiety", "Dark Times", "Anguish"],
}

def fetch(track):
    req = urllib.request.Request(BASE + urllib.parse.quote(track) + ".mp3", headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=40) as r:
        return r.read()

manifest = []
for branch, tracks in CANDIDATES.items():
    path = os.path.join(OUT, branch + ".mp3")
    if os.path.exists(path):
        print(f"[skip] {branch:8s} (gia' presente)")
        continue
    done = False
    for track in tracks:
        try:
            data = fetch(track)
            with open(path, "wb") as f:
                f.write(data)
            print(f"[OK]  {branch:8s} <- \"{track}\" ({round(len(data)/1048576,1)} MB)")
            manifest.append((branch, track))
            done = True
            break
        except Exception as e:
            print(f"[--]  {branch:8s} \"{track}\": {e}")
        time.sleep(1.5)
    if not done:
        print(f"[KO]  {branch:8s} nessun candidato valido")
    time.sleep(1.5)

print("\n=== MANIFEST nuovi (fonte: Kevin MacLeod / incompetech.com, CC-BY 4.0) ===")
for b, t in manifest:
    print(f"{b}.mp3\t{t}")
