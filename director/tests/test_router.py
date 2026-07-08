import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from router import path_to_token, Router

SOUNDMAP = {
    "sfx":   {"evt__melee_hit": {"files": ["hit1.wav", "hit2.wav"], "volume": 0.8, "group": "combat"},
              "evt__hurt":      {"files": ["hurt1.wav", "hurt2.wav", "hurt3.wav"], "volume": 0.75, "group": "combat"},
              "evt__level_up":  {"files": ["levelup.ogg"], "volume": 1.0, "group": "jingle", "duck": True},
              "evt__orb":       {"files": ["orb.ogg"], "volume": 1.0, "group": "jingle", "duck": True},
              "state__player_death": {"files": ["death.wav"], "volume": 1.0, "group": "jingle", "stop_music": True}},
    "music": {"state__branch_D": {"file": "dungeon.ogg", "volume": 0.5}},
    "control": {"state__hp_low": {"op": "duck", "volume": 0.3},
                "state__hp_ok":  {"op": "unduck"}},
}

def test_path_to_token_strips_dir_and_ext():
    assert path_to_token(r"remaster/audio/sfx/evt__melee_hit.wav") == "evt__melee_hit"
    assert path_to_token("evt__level_up.ogg") == "evt__level_up"

def test_route_sfx_returns_one_play_action_from_variants():
    acts = Router(SOUNDMAP).route("evt__melee_hit")
    assert len(acts) == 1 and acts[0]["op"] == "sfx"
    assert acts[0]["file"] in ("hit1.wav", "hit2.wav")
    assert acts[0]["group"] == "combat" and acts[0]["volume"] == 0.8
    assert acts[0]["duck"] is False

def test_route_hurt_picks_one_of_three_variants():
    acts = Router(SOUNDMAP).route("evt__hurt")
    assert len(acts) == 1 and acts[0]["op"] == "sfx"
    assert acts[0]["file"] in ("hurt1.wav", "hurt2.wav", "hurt3.wav")

def test_route_jingle_folds_duck_into_sfx_action():
    # Un jingle con duck:true non emette piu' una "duck" persistente separata:
    # l'azione sfx porta il flag duck e l'engine gestisce l'auto-unduck a tempo.
    acts = Router(SOUNDMAP).route("evt__level_up")
    assert len(acts) == 1 and acts[0]["op"] == "sfx"
    assert acts[0]["duck"] is True

def test_route_orb_is_ducking_jingle():
    acts = Router(SOUNDMAP).route("evt__orb")
    assert [a["op"] for a in acts] == ["sfx"]
    assert acts[0]["duck"] is True and acts[0]["group"] == "jingle"

def test_route_death_plays_sting_then_stops_music():
    acts = Router(SOUNDMAP).route("state__player_death")
    assert [a["op"] for a in acts] == ["sfx", "stop_music"]
    assert acts[0]["file"] == "death.wav"

def test_route_music_change():
    acts = Router(SOUNDMAP).route("state__branch_D")
    assert acts == [{"op": "music", "file": "dungeon.ogg", "volume": 0.5, "group": None, "duck": False}]

def test_route_control_hp_duck():
    assert Router(SOUNDMAP).route("state__hp_low") == [{"op": "duck", "file": None, "volume": 0.3, "group": None, "duck": False}]

def test_unknown_token_returns_empty():
    assert Router(SOUNDMAP).route("evt__nonexistent") == []
