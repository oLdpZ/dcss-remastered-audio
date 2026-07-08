import os, random

def path_to_token(path: str) -> str:
    return os.path.splitext(os.path.basename(path.strip().replace("\\", "/")))[0]

def _action(op, file=None, volume=1.0, group=None, duck=False):
    return {"op": op, "file": file, "volume": volume, "group": group, "duck": duck}

class Router:
    def __init__(self, soundmap: dict):
        self.sfx = soundmap.get("sfx", {})
        self.music = soundmap.get("music", {})
        self.control = soundmap.get("control", {})

    def route(self, token: str) -> list:
        if token in self.sfx:
            e = self.sfx[token]
            # Il flag duck viaggia dentro l'azione sfx: l'engine abbassa la musica,
            # riproduce il jingle e la ririalza da solo a fine suono (auto-unduck).
            acts = [_action("sfx", file=random.choice(e["files"]),
                            volume=e.get("volume", 1.0), group=e.get("group"),
                            duck=bool(e.get("duck")))]
            # Un evento puo' anche fermare la musica dopo il proprio sting (es. morte).
            if e.get("stop_music"):
                acts.append(_action("stop_music"))
            return acts
        if token in self.music:
            e = self.music[token]
            return [_action("music", file=e["file"], volume=e.get("volume", 1.0))]
        if token in self.control:
            e = self.control[token]
            return [_action(e["op"], volume=e.get("volume", 1.0))]
        return []
