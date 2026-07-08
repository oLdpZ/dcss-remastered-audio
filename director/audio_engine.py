import os, threading, pygame

class AudioEngine:
    def __init__(self, audio_root: str, sfx_channels: int = 12):
        self.root = audio_root
        pygame.mixer.init(frequency=44100, size=-16, channels=2, buffer=512)
        pygame.mixer.set_num_channels(sfx_channels + 2)
        pygame.mixer.set_reserved(2)  # canali 0,1 riservati alla musica: Sound.play() non li usa
        self._music_ch = pygame.mixer.Channel(0)       # canale musica A
        self._music_next = pygame.mixer.Channel(1)     # canale musica B (crossfade)
        self._cache = {}
        self._music_vol = 0.5
        self._duck_vol = 0.3
        self._ducked = False        # musica attualmente abbassata (per qualunque motivo)
        self._persist_duck = False  # duck "persistente" da stato HP basso (controllo)
        self._duck_gen = 0          # generazione per invalidare timer di auto-unduck sorpassati

    def _load(self, subdir, file):
        key = (subdir, file)
        if key not in self._cache:
            self._cache[key] = pygame.mixer.Sound(os.path.join(self.root, subdir, file))
        return self._cache[key]

    def _apply_music_vol(self):
        v = self._duck_vol if self._ducked else self._music_vol
        self._music_ch.set_volume(v)
        self._music_next.set_volume(v)

    def play_sfx(self, file, volume=1.0, group=None, duck=False):
        try:
            s = self._load("sfx", file); s.set_volume(volume); s.play()
            if duck:
                # Duck transiente per un jingle: abbassa ora, ririalza a fine suono.
                self._ducked = True
                self._apply_music_vol()
                self._duck_gen += 1
                gen = self._duck_gen
                length = s.get_length() or 0.0
                t = threading.Timer(length + 0.25, self._auto_unduck, args=(gen,))
                t.daemon = True
                t.start()
        except Exception as e:
            print("[sfx err]", file, e)

    def _auto_unduck(self, gen):
        # Solo l'ultimo jingle ririalza (gen coincide) e mai se un duck persistente
        # da HP basso e' ancora attivo: in quel caso la musica resta bassa apposta.
        if gen == self._duck_gen and not self._persist_duck:
            self._ducked = False
            self._apply_music_vol()

    def play_music(self, file, volume=0.5):
        try:
            s = self._load("music", file)
            self._music_vol = volume
            cur = self._music_ch
            cur.fadeout(600)
            s.set_volume(self._duck_vol if self._ducked else volume)
            self._music_next.play(s, loops=-1, fade_ms=600)
            self._music_ch, self._music_next = self._music_next, self._music_ch
        except Exception as e:
            print("[music err]", file, e)

    def duck(self, volume=0.3):
        # Duck persistente (stato HP basso): resta finche' non arriva unduck.
        self._duck_vol = volume
        self._persist_duck = True
        self._ducked = True
        self._apply_music_vol()

    def unduck(self):
        self._persist_duck = False
        self._ducked = False
        self._apply_music_vol()

    def stop_music(self):
        self._music_ch.fadeout(800); self._music_next.fadeout(800)

    def prewarm(self, subdir, files):
        for f in files:
            try:
                self._load(subdir, f)
            except Exception as e:
                print("[prewarm err]", f, e)
