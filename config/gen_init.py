from pathlib import Path
game = Path(__file__).resolve().parents[2]   # <GAME>
init = game / "init.txt"
init.write_text("include = settings/init.txt\ninclude = remaster/config/remaster.rc\n", encoding="utf-8")
print("wrote", init)
