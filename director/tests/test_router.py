import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from router import path_to_token, Router

SOUNDMAP = {
    "sfx":   {"evt__melee_hit": {"files": ["hit1.wav", "hit2.wav"], "volume": 0.8, "group": "combat"},
              "evt__level_up":  {"files": ["levelup.ogg"], "volume": 1.0, "group": "jingle", "duck": True}},
    "music": {"state__branch_D": {"file": "dungeon.ogg", "volume": 0.5}},
    "control": {"state__hp_low": {"op": "duck", "volume": 0.3},
                "state__player_death": {"op": "stop_music"}},
}

def test_path_to_token_strips_dir_and_ext():
    assert path_to_token(r"remaster/audio/sfx/evt__melee_hit.wav") == "evt__melee_hit"
    assert path_to_token("evt__level_up.ogg") == "evt__level_up"

def test_route_sfx_returns_one_play_action_from_variants():
    acts = Router(SOUNDMAP).route("evt__melee_hit")
    assert len(acts) == 1 and acts[0]["op"] == "sfx"
    assert acts[0]["file"] in ("hit1.wav", "hit2.wav")
    assert acts[0]["group"] == "combat" and acts[0]["volume"] == 0.8

def test_route_levelup_ducks_then_plays():
    ops = [a["op"] for a in Router(SOUNDMAP).route("evt__level_up")]
    assert ops == ["duck", "sfx"]

def test_route_music_change():
    acts = Router(SOUNDMAP).route("state__branch_D")
    assert acts == [{"op": "music", "file": "dungeon.ogg", "volume": 0.5, "group": None}]

def test_route_control_stop_music():
    assert Router(SOUNDMAP).route("state__player_death") == [{"op": "stop_music", "file": None, "volume": 1.0, "group": None}]

def test_unknown_token_returns_empty():
    assert Router(SOUNDMAP).route("evt__nonexistent") == []
