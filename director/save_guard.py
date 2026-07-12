import os, shutil, hashlib, json, time

DEFAULT_CONFIG = {
    "enabled": True,
    "keep": 5,
    "poll_seconds": 1.5,
    "require_death_token": True,
    "restore_window_seconds": 30,
}

class SaveGuard:
    def __init__(self, saves_dir, checkpoints_dir, config=None, clock=time.monotonic, log=None):
        self.saves_dir = saves_dir
        self.checkpoints_dir = checkpoints_dir
        self.cfg = dict(DEFAULT_CONFIG); self.cfg.update(config or {})
        self._clock = clock
        self._log = log or (lambda msg: None)
        self._known = {}      # name -> (mtime, size) stato stabile gia' snapshottato
        self._pending = {}    # name -> (mtime, size) visto ma non ancora stabile
        self._last_hash = {}  # name -> hash dell'ultimo snapshot
        self._vanished = {}   # name -> clock time in cui il .cs e' sparito (morte)
        self._armed_at = None

    # --- API pubblica ---
    def arm_restore(self):
        self._armed_at = self._clock()

    def poll_once(self):
        report = {"snapshotted": [], "restored": []}
        current = self._scan()

        # 1. Sparizioni: un file noto non c'e' piu' -> candidato al ripristino (morte).
        for name in list(self._known):
            if name not in current:
                self._vanished[name] = self._clock()
                del self._known[name]
                self._pending.pop(name, None)

        # 2. Serve i personaggi spariti: riprova il ripristino a ogni poll finche' il
        #    flag e' valido, e tiene d'occhio una eventuale ri-cancellazione dal gioco.
        window = float(self.cfg.get("restore_window_seconds", 30))
        for name in list(self._vanished):
            if name in current:
                # Il file e' tornato (il nostro restore ha tenuto, o e' una nuova
                # partita con lo stesso nome): stabile -> smetti di seguirlo e disarma.
                del self._vanished[name]
                self._armed_at = None
                continue
            if self._maybe_restore(name):
                report["restored"].append(name)
                self._log("[saveguard] ripristinato checkpoint per " + name)
                # resta in _vanished: al prossimo poll confermiamo che non sia
                # stato ri-cancellato dal gioco mentre finalizzava la morte.
            elif (self._clock() - self._vanished[name]) > window:
                # Finestra scaduta senza ripristino riuscito -> smetti di seguirlo.
                del self._vanished[name]

        # 3. Snapshot dei file nuovi/cambiati (debounce + dedup invariati).
        for name, meta in current.items():
            if self._known.get(name) == meta:
                continue
            self._log("[saveguard][diag] cambio visto %s known=%r pending=%r new=%r"
                      % (name, self._known.get(name), self._pending.get(name), meta))
            if self._pending.get(name) == meta:
                ok = self._snapshot(name)
                self._log("[saveguard][diag] snapshot %s -> %s" % (name, ok))
                if ok:
                    report["snapshotted"].append(name)
                    self._log("[saveguard] checkpoint " + name)
                self._known[name] = meta
                self._pending.pop(name, None)
            else:
                self._pending[name] = meta
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
        except OSError as e:
            self._log("[saveguard][diag] read FAIL %s: %r" % (name, e))
            return False
        h = hashlib.sha1(data).hexdigest()
        if self._last_hash.get(name) == h:
            return False
        d = os.path.join(self.checkpoints_dir, name)
        os.makedirs(d, exist_ok=True)
        idx = self._next_index(d)
        with open(os.path.join(d, "%04d.cs" % idx), "wb") as f:
            f.write(data)
        self._last_hash[name] = h
        self._rotate(d)
        return True

    def _next_index(self, d):
        mx = -1
        for fn in os.listdir(d):
            if fn.endswith(".cs") and fn[:-3].isdigit():
                mx = max(mx, int(fn[:-3]))
        return mx + 1

    def _rotate(self, d):
        snaps = sorted((fn for fn in os.listdir(d)
                        if fn.endswith(".cs") and fn[:-3].isdigit()),
                       key=lambda fn: int(fn[:-3]))
        # keep <= 0 disabilita la rotazione (ritenzione illimitata).
        keep = int(self.cfg.get("keep", 5))
        for fn in snaps[:-keep] if keep > 0 else []:
            try:
                os.remove(os.path.join(d, fn))
            except OSError:
                pass

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
        snaps = sorted((fn for fn in os.listdir(d)
                        if fn.endswith(".cs") and fn[:-3].isdigit()),
                       key=lambda fn: int(fn[:-3]))
        if not snaps:
            return False
        latest = os.path.join(d, snaps[-1])
        dst = os.path.join(self.saves_dir, name + ".cs")
        try:
            shutil.copy2(latest, dst)
        except OSError:
            return False
        return True

    def run_forever(self):
        if not self.cfg.get("enabled", True):
            return
        while True:
            try:
                self.poll_once()
            except Exception as e:
                self._log("[saveguard] errore poll: " + repr(e))
            time.sleep(float(self.cfg.get("poll_seconds", 1.5)))


def resolve_saves_dir(here):
    env = os.environ.get("DCSS_SAVES_DIR")
    if env:
        return os.path.abspath(env)
    return os.path.abspath(os.path.join(here, "..", "..", "saves"))


def load_saveguard_config(here):
    cfg = dict(DEFAULT_CONFIG)
    try:
        with open(os.path.join(here, "saveguard.json"), encoding="utf-8") as f:
            cfg.update(json.load(f))
    except FileNotFoundError:
        pass
    return cfg
