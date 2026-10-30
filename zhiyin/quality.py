"""Are the recommendations any good? Measured on first listens: the first time each recommended song played.

A good first listen is one heard through (or 80% of the way) and not refused. An early skip is one left within ten
seconds. Counted overall and split the ways that say what to change: by station, by the editor's confidence (does
"fit" mean anything?), by whether the artist was new to them, by place in the station, and for the probe songs the
editor would not have sent out (is its judgement worth what it costs?). The listener's own likes played between the
new songs are counted apart, every listen of them: a favourite skipped often means it comes round too soon."""
import os
import time
from collections import defaultdict

from . import signals, store

PROBE_ENOUGH = 60   # probe songs heard per listener before probing stops: enough to see a 20-point difference
FIT_BINS = ((0.9, "0.9+"), (0.8, "0.8-0.9"), (0.7, "0.7-0.8"), (0.01, "<0.7"), (0.0, "unvetted"))


def probing() -> bool:
    if os.environ.get("ZHIYIN_PROBES") == "0":
        return False
    n = store.db().execute("select count(distinct vid) from plays where uid=? and probe is not null and test=0",
                           (store.uid(),)).fetchone()[0]
    return n < PROBE_ENOUGH


def outcome(x: dict, nope: bool) -> str:
    if x["end"] == "error":
        return "error"
    if x["end"] in (None, "stop"):   # never said, or left for something else: no verdict on the song
        return "unknown"
    if signals.early(x):
        return "early"
    return "good" if signals.full(x) and not nope else "partial"


def first_listens(since: float, uid: str | None = None) -> list[dict]:
    """The first listen of each recommended song, if it fell after `since`, with "out", "like" and "nope"."""
    uid = uid or store.uid()
    con = store.db()
    shown = {r["vid"] for r in con.execute("select distinct vid from shown where uid=?", (uid,))}
    fb = {r["vid"]: r["action"] for r in con.execute("select vid, action from feedback where uid=?", (uid,))}
    first = {}
    for x in signals.listens(uid):
        # (a listen cut short for another station or a comparison says nothing: the next one is its first)
        if x["vid"] in first or x["src"] == "compare" or (x["lane"] or "") == "ear" or x["end"] == "stop":
            continue
        first[x["vid"]] = x
    out = []
    for v, x in first.items():
        if x["ts"] < since or not (x["slot"] is not None or v in shown):
            continue
        out.append({**x, "out": outcome(x, fb.get(v) == "dislike"), "like": fb.get(v) == "like", "nope": fb.get(v) == "dislike"})
    return out


def by_lane(uid: str | None = None) -> dict:
    """Per station, the verdicts its next editor will read (rank.outcomes): loved, heard through, skipped within
    seconds, turned down. Shown on the station so the listener sees their reactions are being used."""
    uid = uid or store.uid()
    out = defaultdict(lambda: {"like": 0, "good": 0, "early": 0, "nope": 0})
    counted = set()
    for x in first_listens(0, uid):
        if not x["lane"]:
            continue
        k = "like" if x["like"] else "nope" if x["nope"] else x["out"] if x["out"] in ("good", "early") else None
        if k:
            out[x["lane"]][k] += 1
            counted.add(x["vid"])
    for r in store.db().execute("select vid, action, lane from feedback where uid=? and action in ('like', 'dislike') "
                                "and lane is not null", (uid,)):
        if r["vid"] not in counted:
            out[r["lane"]]["like" if r["action"] == "like" else "nope"] += 1
            counted.add(r["vid"])
    return dict(out)


def _fit_bin(x: dict) -> str:
    f = x["fit"] or 0
    return next(name for lo, name in FIT_BINS if f >= lo)


def _slot_bin(x: dict) -> str | None:
    s = x["slot"]
    return None if s is None else "reserve" if s < 0 else "1-3" if s < 3 else "4+"


def report(days: int = 14, uid: str | None = None) -> dict:
    since = time.time() - days * 86400
    ls = first_listens(since, uid)
    groups = defaultdict(lambda: defaultdict(lambda: {"n": 0, "good": 0, "early": 0, "partial": 0, "unknown": 0,
                                                      "error": 0, "like": 0, "nope": 0}))

    def add(dim, key, x):
        if key is None:
            return
        g = groups[dim][key]
        g["n"] += 1
        g[x["out"]] += 1
        g["like"] += x["like"]
        g["nope"] += x["nope"]
    for x in ls:
        add("all", "all", x)
        add("lane", x["lane"], x)
        if x["fit"] is not None or x["slot"] is not None:
            add("fit", "probe" if x["probe"] else _fit_bin(x), x)
        add("artist", {0: "new", 1: "liked", 2: "known"}.get(x["fam"]), x)
        add("slot", _slot_bin(x), x)
        add("arm", "probe:" + x["probe"] if x["probe"] else "editor" if x["slot"] is not None and x["slot"] >= 0 else None, x)
        add("start", "chosen" if x["src"] in signals.CHOSEN else "played on" if x["src"] else None, x)
    for x in signals.listens(uid, since):
        if x["kind"] and x["src"] != "compare":
            add("mine", x["kind"], {**x, "out": outcome(x, False), "like": False, "nope": False})
    return {"days": days, "since": since, "groups": {d: dict(v) for d, v in groups.items()}}


def rate(g: dict, k: str = "good") -> float | None:
    """Of the listens whose end is known."""
    n = g["n"] - g["unknown"] - g["error"]
    return g[k] / n if n > 0 else None


def print_report(r: dict, names: dict[str, str] | None = None) -> None:
    names = names or {}
    print(f"first listens of recommended songs, last {r['days']} days")
    for dim, rows in r["groups"].items():
        print(f"\n{dim}")
        for k, g in sorted(rows.items(), key=lambda kv: -kv[1]["n"]):
            good, early = rate(g), rate(g, "early")
            print(f"  {names.get(k, k)[:28]:28s} n={g['n']:4d}  good {_pct(good):>4}  early skip {_pct(early):>4}  "
                  f"liked {g['like']:3d}  refused {g['nope']:3d}  end unknown {g['unknown']:3d}")


def _pct(x):
    return "-" if x is None else f"{100 * x:.0f}%"
