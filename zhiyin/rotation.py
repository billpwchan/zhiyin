"""The listener's own likes, back in the stations between the new songs.

Each like gets how much the listener seems to want it (`want`, 0-1) and when it has rested enough to come round again
(`due`). A favourite rests about a day; one heard through several times this fortnight rests longer; one skipped in its
first half minute rests two weeks, which says "not now", never "not my taste". The page decides the order (app.js,
`weave`): how many of these between new songs, the like a new song was found from just before it, a reunion now and
then."""
import time

from . import edition, library, settings, signals, store, taste, ytm

DAY = 86400
REST_MAX_D = 30
SKIP_REST_D = 14      # skipped in its first half minute
HUSH_D = 60           # "not for a while" (这阵子先不听)
DRIFT_D, DRIFT_DAYS = 60, 3   # skipped on this many separate days within DRIFT_D: wanted half as much
AGAIN_AGE_D, AGAIN_QUIET_D = 365, 180   # liked over a year ago and not heard for half a year: a reunion


def _ts(day: str | None) -> float | None:
    try:
        return time.mktime(time.strptime(day[:10] if len(day) >= 10 else day[:7] + "-15", "%Y-%m-%d"))
    except (TypeError, ValueError):
        return None


def want(t: dict, played: dict | None, heard: dict | None, saved: bool, now: float) -> float:
    """Liked (more if lately), picked and heard through here, played on YouTube Music (Takeout), kept in a playlist,
    among their 100 most played on NetEase (听歌排行, `ne_score` 0-100).
    The play evidence saturates at signals.LOVE, the point where an unliked song counts as a love."""
    liked = _ts(t.get("liked_est"))
    months = (now - liked) / (30.4 * DAY) if liked else 24
    w = 0.4 + 0.2 * 0.5 ** (max(0.0, months) / 12)
    if played:
        w += 0.4 * min(1.0, max(0.0, played["w"]) / signals.LOVE)
    if heard:
        w += 0.4 * min(1.0, max(0.0, heard["w"]) / signals.LOVE)
    if saved:
        w += 0.2
    if t.get("ne_score") is not None:
        w += 0.2 + 0.2 * t["ne_score"] / 100
    return min(1.0, w)


def rest_days(w: float, full_14d: int) -> float:
    """A favourite rests about a day, a lukewarm like about four; each listen in the last fortnight beyond the first
    doubles it, up to a month."""
    return min(REST_MAX_D, (1 + 4 * (1 - w)) * 2 ** max(0, full_14d - 1))


def songs() -> list[dict]:
    now = time.time()
    prof = store.read_json(store.PROFILE) or {}
    assign = prof.get("assign", {})
    aside = {r for s in prof.get("set_aside", []) for r in s["ranks"]}
    tags = store.read_json(store.TAGS) or {}
    nm = settings.not_me()
    hush = {v: u for v, u in settings.load().get("rest", {}).items() if u > now}
    ls = signals.listens()
    played = signals.play_scores(ls)
    hist = signals.history().get("songs", {})
    heard_scores = signals.history_scores()
    saved = {s["vid"] for s in signals.youtube().get("saved", [])}
    # (YouTube wouldn't play it in the page: it can only be skipped)
    failed = {r["vid"] for r in store.db().execute("select distinct vid from plays where uid=? and ev='error' and test=0",
                                                   (store.uid(),))}

    by = {}
    for x in ls:
        s = by.setdefault(x["vid"], {"last": 0.0, "last_end": None, "full14": 0, "full30": 0, "skip_days": set()})
        if x["ts"] >= s["last"]:
            s["last"], s["last_end"] = x["ts"], x["end"]
        age = now - x["ts"]
        if signals.full(x):
            s["full14"] += age < 14 * DAY
            s["full30"] += age < 30 * DAY
        if x["end"] == "skip" and age < DRIFT_D * DAY:
            s["skip_days"].add(signals.day_of(x["ts"]))

    out = []
    for t in library.load():
        if t["long"] or t["rank"] in aside or settings.is_not_me(t, nm) or tags.get(t["vid"], {}).get("kind") not in ("song", None):
            continue
        if t["vid"] in failed or (ytm.cached("song", t["vid"]) or {}).get("embed") is False:
            continue
        v = t["vid"]
        s = by.get(v, {})
        w = want(t, played.get(v), heard_scores.get(v), v in saved, now)
        if len(s.get("skip_days", ())) >= DRIFT_DAYS:
            w *= 0.5
        due = 0.0
        if s.get("last"):
            days = rest_days(w, s["full14"])
            if s["last_end"] == "skip":
                days = max(days, SKIP_REST_D)
            due = s["last"] + days * DAY
        due = max(due, hush.get(v, 0))
        h = hist.get(v)
        last_known = max(s.get("last", 0), (_ts(h["last"]) if h else None) or 0)
        liked = _ts(t.get("liked_est"))
        again = bool(liked and now - liked > AGAIN_AGE_D * DAY and (not last_known or now - last_known > AGAIN_QUIET_D * DAY))
        out.append({"vid": v, "title": t["title"], "artists": t["artists"][:3], "album": t.get("album"), "dur": t.get("dur"),
                    "type": t.get("type"), "thumb": (ytm.cached("track", v) or {}).get("thumb"), "at": (t.get("liked_est") or "")[:7] or None, "lanes": assign.get(v, []),
                    "real": t.get("source") in ("google", "163"),   # a date YouTube or NetEase gave; a snapshot's is an estimate
                    "want": round(w, 2), "due": round(due), "last": round(last_known) or None, "n30": s.get("full30", 0),
                    "again": again})
    return out


def view() -> dict:
    """What the page needs to weave likes into the stations. Sound vectors are packed with today's basis for the likes
    and the edition's picks alike, so the page can compare one with the other."""
    out = songs()
    prof = store.read_json(store.PROFILE) or {}
    ed = store.read_json(store.EDITION) or {}
    picks = [dict(vid=p["vid"]) for l in ed.get("lanes", []) for p in l.get("picks", []) + l.get("reserve", [])]
    try:
        tst = taste.Taste(library.load(), prof)
        edition.sound_tags(out + picks, tst)
    except Exception:   # no vectors yet (a new listener): the page then weaves without sound
        pass
    return {"songs": out, "picks": {p["vid"]: {"v": p["v"], "en": p.get("en")} for p in picks if p.get("v")},
            "ed": ed.get("id"), "now": round(time.time())}


def hush(vid: str, days: float) -> None:
    """Keep one like out of the stations for `days` (0 lets it back)."""
    s = settings.load()
    rest = {v: u for v, u in s.get("rest", {}).items() if u > time.time() and v != vid}
    if days > 0:
        rest[vid] = time.time() + days * DAY
    s["rest"] = rest
    settings.save(s)
