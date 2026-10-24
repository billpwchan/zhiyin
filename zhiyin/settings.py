from . import store

DEFAULT = {"lanes": {}, "never": [], "picks_per_lane": 8}


def load() -> dict:
    s = store.read_json(store.SETTINGS) or {}
    return {**DEFAULT, **s}


def save(s: dict) -> None:
    store.write_json(store.SETTINGS, s)


def lane_view(lane: dict) -> dict:
    """The profile's lane with the listener's own overrides applied."""
    o = load()["lanes"].get(lane["key"], {})
    return {**lane, "enabled": o.get("enabled", True), "discovery": o.get("discovery", lane.get("discovery", 0.4))}
