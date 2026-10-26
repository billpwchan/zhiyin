import copy

from . import store
from .text import fold

DEFAULT = {"lanes": {}, "never": [], "picks_per_lane": 8, "not_me": {"songs": [], "artists": []}}


def load() -> dict:
    s = store.read_json(store.SETTINGS) or {}
    return {**copy.deepcopy(DEFAULT), **s}   # a copy: callers change it in place, and DEFAULT is every listener's


def save(s: dict) -> None:
    store.write_json(store.SETTINGS, s)


def lane_view(lane: dict) -> dict:
    """The profile's lane with the listener's own overrides applied."""
    o = load()["lanes"].get(lane["key"], {})
    return {**lane, "enabled": o.get("enabled", True), "discovery": o.get("discovery", lane.get("discovery", 0.4)),
            "note": o.get("note", "")}


def not_me() -> tuple[set[str], set[str]]:
    """Likes the listener said aren't their taste (someone else's songs, a phase, a joke): song ids, and artists by
    folded name. They stay liked; they just stop speaking for the listener."""
    n = load()["not_me"]
    return set(n.get("songs", [])), set(n.get("artists", []))


def is_not_me(t: dict, nm: tuple[set[str], set[str]]) -> bool:
    songs, artists = nm
    # a like marked while it was still a liked video keeps that id in `ll` once it is matched to its song
    return t["vid"] in songs or t.get("ll") in songs or bool(t.get("artists") and fold(t["artists"][0]["name"]) in artists)


def set_not_me(vid: str | None = None, artist: str | None = None, on: bool = True) -> None:
    """`artist` is a folded name."""
    s = load()
    n = s["not_me"]
    songs, artists = n.get("songs", []), n.get("artists", [])
    if vid:
        songs = [x for x in songs if x != vid] + ([vid] if on else [])
    if artist:
        artists = [x for x in artists if x != artist] + ([artist] if on else [])
    s["not_me"] = {**n, "songs": songs, "artists": artists}
    save(s)
