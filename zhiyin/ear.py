"""What the 「你的耳朵」 page draws: every liked song placed on a record, ring by year (centre = the first like,
edge = now) and wedge by station (wedges that sound alike sit side by side; inside a wedge, quieter songs come
first, clockwise). Plus a few facts read straight off the likes, each pointing at the songs it is about.

A new listener's record is drawn before their stations exist, from the liked videos alone: then the angle is the
time of year of the like (stage "glimpse", and "library" once the songs are matched), and the songs move into their
wedges when the stations arrive (stage "full")."""
import itertools
import time
from collections import Counter, defaultdict
from datetime import date

import numpy as np

from . import audio, i18n, settings, store
from .text import fold, song_key

TOP_GAP = 16.0          # degrees left open at 12 o'clock for the year ruler
SECTOR_GAP = 4.5       # wide enough to read as an empty spoke between tastes
MIN_ARC = 7.0
LANG = {"ko": "韩语", "en": "英语", "cmn": "国语", "yue": "粤语", "ja": "日语", "th": "泰语", "instrumental": "纯音乐"}


def _year(d: str | None) -> float | None:
    if not d:
        return None
    try:
        y, m, dd = (int(x) for x in (d + "-01-01")[:10].split("-"))
        return y + (date(y, m, dd).timetuple().tm_yday - 1) / 365.25
    except ValueError:
        return None


def _times(tracks: list[dict]) -> list[float]:
    """Like dates as fractional years. Gaps are filled from the neighbours in like order, which is also time order."""
    ts = [_year(t.get("liked_est")) for t in tracks]   # tracks are newest first
    known = [i for i, x in enumerate(ts) if x is not None]
    now = date.today().year + (date.today().timetuple().tm_yday - 1) / 365.25
    if not known:
        n = len(ts)
        return [now - i / max(1, n - 1) for i in range(n)]
    out = list(ts)
    for i, x in enumerate(ts):
        if x is not None:
            continue
        a = max((k for k in known if k < i), default=None)
        b = min((k for k in known if k > i), default=None)
        if a is not None and b is not None:
            out[i] = ts[a] + (ts[b] - ts[a]) * (i - a) / (b - a)
        else:
            out[i] = ts[a if a is not None else b]
    # a like never goes back in time as the list goes down; estimated dates sometimes do
    for i in range(1, len(out)):
        out[i] = min(out[i], out[i - 1])
    return out


def _lane_order(keys: list[str], cents: dict[str, np.ndarray]) -> list[str]:
    """Round the circle so that neighbouring wedges sound most alike."""
    have = [k for k in keys if k in cents]
    rest = [k for k in keys if k not in cents]
    if len(have) < 3:
        return have + rest
    C = audio.unit(np.stack([cents[k] for k in have]))
    S = C @ C.T
    first, others = 0, list(range(1, len(have)))
    best, best_s = None, -1e9
    for perm in itertools.permutations(others):
        tour = (first, *perm)
        s = sum(S[tour[i], tour[(i + 1) % len(tour)]] for i in range(len(tour)))
        if s > best_s:
            best, best_s = tour, s
    return [have[i] for i in best] + rest


def _glimpse_tracks() -> list[dict]:
    g = store.read_json(store.GLIMPSE) or {}
    return [{"rank": i, "vid": x["vid"], "ll": x["vid"], "title": x["title"], "artists": [{"name": x["artist"]}],
             "album": None, "dur": x["dur"], "liked_est": x["at"] or None, "source": "google", "long": False}
            for i, x in enumerate(g.get("songs", []))]


def _calendar(tracks, ts, nm, out_songs) -> None:
    """Before there are stations: the angle is the time of year of the like, January just past twelve o'clock."""
    usable = 360 - TOP_GAP
    for t in tracks:
        x = ts[t["rank"]]
        out_songs.append(_song(t, x, "none", TOP_GAP / 2 + usable * (x - int(x)), nm))


def _song(t, x, lane, ang, nm) -> list:
    return [t["vid"], t["title"], [a["name"] for a in t["artists"][:2]], (t.get("album") or {}).get("name") or "",
            t.get("dur") or 0, round(x, 3), lane, round(ang, 2), t.get("ll"), int(settings.is_not_me(t, nm))]


def label() -> str | None:
    """The short name Claude gave this listener's taste, in the reader's script; None if it was written in the
    other language."""
    d = store.read_json(store.IDENT) or {}
    if not d.get("label") or i18n.family(d.get("lang")) != i18n.family(i18n.of()):
        return None
    return i18n.convert(d["label"], d.get("lang", "zh-Hans"), i18n.of())


def build() -> dict:
    prof = store.read_json(store.PROFILE) or {}
    tags = store.read_json(store.TAGS) or {}
    lib = store.read_json(store.LIBRARY) or {}
    tracks = sorted((t for t in lib.get("tracks", []) if not t["long"]), key=lambda t: t["rank"])
    stage = "full" if tracks and prof.get("lanes") else "library" if tracks else "glimpse"
    if not tracks:
        tracks = _glimpse_tracks()
    if not tracks:   # the liked videos aren't read yet: an empty record of the same shape
        return {"songs": [], "sectors": [], "span": [0, 0], "eras": [], "facts": [], "real_dates": False, "stage": stage,
                "center": None, "label": None, "built": time.time()}
    nm = settings.not_me()
    real = any(t.get("source") in ("google", "163") for t in tracks)
    rl = i18n.of()
    if stage != "full":
        ts = dict(zip((t["rank"] for t in tracks), _times(tracks)))
        songs = []
        _calendar(tracks, ts, nm, songs)
        mine = [t for t in tracks if not settings.is_not_me(t, nm)] or tracks
        return {"songs": songs, "sectors": [], "span": [round(min(ts.values()), 3), round(max(ts.values()), 3)], "eras": [],
                "facts": facts(mine, ts, {t["vid"]: "none" for t in tracks}, {}, tags, real, rl,
                               names=stage == "library"),
                "real_dates": real, "stage": stage, "center": center(mine, tags), "label": label(), "built": time.time()}
    assign = prof.get("assign", {})
    pl = prof.get("lang", "zh-Hans")
    lanes = {ln["key"]: i18n.convert(ln["name"], pl, rl) for ln in prof.get("lanes", [])}
    lane_of = {t["vid"]: (assign.get(t["vid"]) or ["none"])[0] for t in tracks}
    lane_of = {v: (k if k in lanes else "none") for v, k in lane_of.items()}
    ts = dict(zip((t["rank"] for t in tracks), _times(tracks)))   # by rank: a song liked twice sits on two rings

    V = audio.vectors([t["vid"] for t in tracks])
    vids = [t["vid"] for t in tracks if t["vid"] in V]
    energy = {}
    if vids:
        M = audio.unit(np.stack([V[v] for v in vids]))
        e = audio.axis_scores(M).get("energy")
        if e is not None:
            z = (e - e.mean()) / (e.std() or 1)
            energy = dict(zip(vids, z.tolist()))
    for t in tracks:
        if t["vid"] not in energy:
            energy[t["vid"]] = ((tags.get(t["vid"]) or {}).get("energy", 3) - 3) * 0.8

    by_lane = defaultdict(list)
    for t in tracks:
        by_lane[lane_of[t["vid"]]].append(t)
    cents = {k: np.mean([V[t["vid"]] for t in ts_ if t["vid"] in V], axis=0)
             for k, ts_ in by_lane.items() if k != "none" and sum(t["vid"] in V for t in ts_) >= 3}
    order = _lane_order([k for k in lanes if by_lane.get(k)], cents) + (["none"] if by_lane.get("none") else [])

    usable = 360 - TOP_GAP - SECTOR_GAP * (len(order) - 1)
    raw = {k: len(by_lane[k]) for k in order}
    total = sum(raw.values())
    arcs = {k: max(MIN_ARC, usable * n / total) for k, n in raw.items()}
    scale = usable / sum(arcs.values())
    sectors, songs, a = [], [], TOP_GAP / 2
    for k in order:
        span = arcs[k] * scale
        members = sorted(by_lane[k], key=lambda t: energy[t["vid"]])
        n = len(members)
        sectors.append({"key": k, "name": lanes.get(k) or i18n.tr("其他", rl), "a0": round(a, 2), "a1": round(a + span, 2), "n": n,
                        "covers": [t["vid"] for t in sorted(members, key=lambda t: t["rank"])[:4]]})
        for j, t in enumerate(members):
            songs.append(_song(t, ts[t["rank"]], k, a + span * (j + 0.5) / n, nm))
        a += span + SECTOR_GAP

    t_all = list(ts.values())
    t0, t1 = min(t_all), max(t_all)
    eras = []
    rank_t = ts
    for er in (prof.get("portrait") or {}).get("eras", []):
        inside = [x for r, x in rank_t.items() if er["to_rank"] >= r >= er["from_rank"]]
        if inside:
            eras.append({"years": er["years"], "label": i18n.convert(er["label"], pl, rl), "text": i18n.convert(er["text"], pl, rl),
                         "t0": round(min(inside), 3), "t1": round(max(inside), 3)})
    eras.sort(key=lambda e: e["t0"])   # the portrait lists them newest first; the page reads them oldest first
    mine = [t for t in tracks if not settings.is_not_me(t, nm)] or tracks
    return {"songs": songs, "sectors": sectors, "span": [round(t0, 3), round(t1, 3)], "eras": eras,
            "facts": facts(mine, ts, lane_of, lanes, tags, real, rl), "real_dates": real, "stage": stage,
            "center": center(mine, tags), "label": label(), "built": time.time()}


def from_tracks(tracks: list[dict], lang: str, released: bool = False) -> dict:
    """The record of likes kept somewhere else (library.app_likes), drawn as a new listener's is before their stations
    exist: ring by year, angle by the time of year of the like. `released`: QQ Music shows nobody when a song was
    liked, and a playlist's order says nothing of it either, so each song sits where it came out (undated ones are
    left off)."""
    out = sorted((t for t in tracks if t.get("released")), key=lambda t: t["released"], reverse=True) if released else []
    released = bool(out)
    if released:
        tracks = [{**t, "rank": i, "liked_est": t["released"]} for i, t in enumerate(out)]
    ts = dict(zip((t["rank"] for t in tracks), _times(tracks)))
    songs = []
    _calendar(tracks, ts, (set(), set()), songs)
    tags = {t["vid"]: {"year": t["year"]} for t in tracks if t.get("year")}
    real = any(t.get("source") == "163" for t in tracks)
    return {"songs": songs, "sectors": [], "span": [round(min(ts.values()), 3), round(max(ts.values()), 3)], "eras": [],
            "facts": facts(tracks, ts, {t["vid"]: "none" for t in tracks}, {}, tags, real, lang, released=released),
            "real_dates": real, "dates": "released" if released else "liked", "stage": "library",
            "center": center(tracks, tags), "label": None, "built": time.time()}


def center(tracks, tags) -> int | None:
    """The year by which half of the liked songs had come out (the lower median of release years)."""
    years = sorted(y for t in tracks if (y := (tags.get(t["vid"]) or {}).get("year") or 0) > 1950)
    return years[(len(years) - 1) // 2] if len(years) >= 30 else None


def facts(tracks, ts, lane_of, lanes, tags, real, lang="zh-Hans", names=True, released=False) -> list[dict]:
    """`names` False: the artists are still YouTube channel names (a label's channel would pass for the artist), so
    nothing is said about who. `released`: the songs sit where they came out, so nothing is said about when liked."""
    def tr(text, **kw):
        return i18n.tr(text, lang, **kw)
    out = []
    first = min(tracks, key=lambda t: (ts[t["rank"]], -t["rank"]))
    who = i18n.script(first["artists"][0]["name"], lang) if first["artists"] else ""
    if released:
        text = tr("最老的一首是《{title}》，{who}。", title=first["title"], who=who) if names and who else tr("最老的一首是《{title}》。", title=first["title"])
    else:
        text = tr("最早的一首是《{title}》，{who}。", title=first["title"], who=who) if names and who else tr("最早的一首是《{title}》。", title=first["title"])
    out.append({"key": "first", "lead": f"{int(ts[first['rank']])}", "text": text, "vids": [first["vid"]]})

    span = defaultdict(list)
    for t in tracks:
        if t["artists"] and names:
            span[t["artists"][0]["name"]].append(t)
    long_ = [(max(ts[t["rank"]] for t in v) - min(ts[t["rank"]] for t in v), len(v), k, v) for k, v in span.items() if len(v) >= 3]
    if long_ and not released:
        yrs, n, name, songs = max(long_)
        a, b = int(min(ts[t["rank"]] for t in songs)), int(max(ts[t["rank"]] for t in songs))
        if yrs >= 2:   # a year together says little about who stayed
            out.append({"key": "longest", "lead": tr("{n} 年", n=b - a), "text": tr("陪你最久的是{name}：从 {a} 到 {b}，一共 {n} 首。", name=i18n.script(name, lang), a=a, b=b, n=n),
                        "vids": [t["vid"] for t in songs]})

    lang_of = {t["vid"]: (tags.get(t["vid"]) or {}).get("lang") for t in tracks}
    langs = [(k, n) for k, n in Counter(lang_of.values()).most_common() if k in LANG and k != "instrumental"]
    if len(langs) >= 2:
        tot = sum(n for _, n in langs)
        shown = langs if len(langs) <= 5 else langs[:4]   # the rest share one "other" so every language counted is listed
        groups = [{"label": tr(LANG[k]), "n": n, "pct": round(100 * n / tot), "vids": [v for v, x in lang_of.items() if x == k]}
                  for k, n in shown]
        if len(shown) < len(langs):
            rest = {k for k, _ in langs[4:]}
            n = sum(n for k, n in langs[4:])
            groups.append({"label": tr("其他"), "n": n, "pct": round(100 * n / tot), "vids": [v for v, x in lang_of.items() if x in rest]})
        out.append({"key": "langs", "lead": tr("{n} 种语言", n=len(langs)), "text": "", "groups": groups,
                    "vids": groups[0]["vids"]})

    y = center(tracks, tags)
    if y:
        out.append({"key": "center", "lead": f"{y}", "text": tr("你喜欢的歌，有一半发行在 {y} 年或更早。", y=y),
                    "vids": [t["vid"] for t in tracks if 1950 < ((tags.get(t["vid"]) or {}).get("year") or 0) <= y]})

    now = max(ts.values())
    recent = [t for t in tracks if ts[t["rank"]] > now - 1]
    older = [t for t in tracks if ts[t["rank"]] <= now - 1]
    if lanes and len(recent) >= 15 and len(older) >= 30:
        def share(group, k):
            return sum(lane_of[t["vid"]] == k for t in group) / len(group)
        grow = max(lanes, key=lambda k: share(recent, k) - share(older, k))
        p1, p0 = round(100 * share(recent, grow)), round(100 * share(older, grow))
        if p1 - p0 >= 4 and p1 >= 1.6 * max(p0, 1):
            out.append({"key": "rising", "lead": f"{p1}%", "text": tr("最近一年的新喜欢里，「{lane}」占了 {p1}%，之前只有 {p0}%。", lane=lanes[grow], p1=p1, p0=p0),
                        "vids": [t["vid"] for t in recent if lane_of[t["vid"]] == grow], "lane": grow})

    first_year = {}
    for t in tracks:
        k = lane_of[t["vid"]]
        if k in lanes:
            first_year[k] = min(first_year.get(k, 9999), ts[t["rank"]])
    if first_year:
        k = max(first_year, key=first_year.get)
        if first_year[k] - min(ts.values()) >= 2:
            members = [t["vid"] for t in tracks if lane_of[t["vid"]] == k]
            out.append({"key": "newest", "lead": f"{int(first_year[k])}", "text": tr("「{lane}」是最晚出现的一种口味，那年才有第一首，现在已经 {n} 首。", lane=lanes[k], n=len(members)),
                        "vids": members, "lane": k})

    again = defaultdict(list)
    for t in tracks:
        again[(song_key(t["title"]), fold(t["artists"][0]["name"]) if t["artists"] else "")].append(t)
    back = [v for v in again.values() if len(v) >= 2 and max(ts[t["rank"]] for t in v) - min(ts[t["rank"]] for t in v) >= 0.5]
    if len(back) >= 2:
        ex = max(back, key=lambda v: max(ts[t["rank"]] for t in v) - min(ts[t["rank"]] for t in v))
        gap = max(ts[t["rank"]] for t in ex) - min(ts[t["rank"]] for t in ex)
        out.append({"key": "again", "lead": tr("{n} 首", n=len(back)), "text": tr("隔了一阵又点了一次喜欢，像《{title}》，前后隔了 {gap} 年。", title=ex[0]["title"], gap=f"{gap:.0f}") if gap >= 1.5 else tr("隔了一阵又点了一次喜欢，像《{title}》。", title=ex[0]["title"]),
                    "vids": [t["vid"] for v in back for t in v]})

    if real:
        months = Counter(_month(ts[t["rank"]]) for t in tracks)
        (m, n), = months.most_common(1)
        if n >= 12:
            y, mo = m.split("-")
            out.append({"key": "month", "lead": tr("{n} 首", n=n), "text": tr("点得最密的一个月是 {y} 年 {m} 月。", y=y, m=int(mo), month=date(int(y), int(mo), 1).strftime("%B %Y")),
                        "vids": [t["vid"] for t in tracks if _month(ts[t["rank"]]) == m]})
        lag = [ts[t["rank"]] - (tags.get(t["vid"]) or {}).get("year", 0) for t in tracks
               if (tags.get(t["vid"]) or {}).get("year", 0) > 1950]
        if len(lag) >= 30:
            fresh = [t["vid"] for t in tracks if 0 <= ts[t["rank"]] - ((tags.get(t["vid"]) or {}).get("year") or -99) < 1]
            p = round(100 * len(fresh) / len(lag))
            out.append({"key": "fresh", "lead": f"{p}%", "text": tr("{p}% 的歌，你在它发行的当年就点了喜欢。", p=p),
                        "vids": fresh})
    return out[:6]


def _month(x: float) -> str:
    y = int(x)
    m = min(12, int((x - y) * 12) + 1)
    return f"{y}-{m:02d}"
