"""Scarica un set iniziale di musica a tema (Kevin MacLeod / Incompetech, CC-BY 4.0)
per i branch attivi. Prova piu' tracce candidate per branch, con pause anti-throttling.
Salva in remaster/audio/music/<branch>.mp3 e stampa un manifest (fonte+licenza)."""
import os, time, urllib.request

BASE = "https://incompetech.com/music/royalty-free/mp3-royaltyfree/"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.abspath(os.path.join(HERE, "..", "audio", "music"))
os.makedirs(OUT, exist_ok=True)

# branch_key (nome file) -> lista di tracce candidate (in ordine di preferenza)
CANDIDATES = {
    "dungeon": ["Long Note Two", "Long Note Four", "Deep Haze", "Dark Times"],
    "temple":  ["Meditation Impromptu 01", "Meditation Impromptu 02", "Peace of Mind 3", "Angelic"],
    "lair":    ["Chee Zee Cave", "Chee Zee Jungle", "Rites", "Tribal"],
    "orc":     ["Crusade", "Volatile Reaction", "Death and Axes", "Heavy Interlude"],
    "crypt":   ["Ghost Processional", "Bump in the Night", "Ossuary 5 Rest", "Ossuary 6 Air"],
    "depths":  ["The Descent", "Gathering Darkness", "Lightless Dawn", "Anguish"],
}

def url_for(track):
    return BASE + urllib.parse.quote(track) + ".mp3"

def fetch(track):
    req = urllib.request.Request(url_for(track), headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=40) as r:
        return r.read()

manifest = []
for branch, tracks in CANDIDATES.items():
    done = False
    for track in tracks:
        try:
            data = fetch(track)
            path = os.path.join(OUT, branch + ".mp3")
            with open(path, "wb") as f:
                f.write(data)
            mb = round(len(data) / 1048576, 1)
            print(f"[OK]  {branch:8s} <- \"{track}\" ({mb} MB)")
            manifest.append((branch, track, "Kevin MacLeod / incompetech.com", "CC-BY 4.0"))
            done = True
            break
        except Exception as e:
            print(f"[--]  {branch:8s} \"{track}\": {e}")
        time.sleep(1.5)  # anti-throttling
    if not done:
        print(f"[KO]  {branch:8s} nessun candidato valido")
    time.sleep(1.5)

print("\n=== MANIFEST (fonte + licenza) ===")
for b, t, src, lic in manifest:
    print(f"{b}.mp3\t{t}\t{src}\t{lic}")
