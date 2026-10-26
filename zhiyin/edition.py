import datetime as dt
import os
import random
import statistics
import threading
import time
import traceback

import numpy as np

from . import audio, candidates, i18n, library, llm, quality, rank, settings, signals, store, taste, ytm
from .text import display_title, fold, song_key

FOCUS_MIN_S = 20 * 60
NEAR_CLAIM = 0.92   # the median nearest-neighbour similarity among the listener's own likes
RESERVE = 12


def _public(c: dict) -> dict:
    keep = ("vid", "title", "artists", "album", "year", "thumb", "dur", "type", "reason", "fit", "familiar", "knows",
            "sources", "because", "probe", "slot")
    out = {k: c.get(k) for k in keep}
    out.update({k: c[k] for k in ("v", "en", "mv") if c.get(k) is not None})
    out["title"] = display_title(c.get("title") or "", c.get("artists") or [])
    out["via"] = [v for v in c.get("via", []) if not v.startswith(("editor:", "playlist:"))][:3]
    if c.get("audio") and c["audio"]["near_sim"] >= NEAR_CLAIM:
        out["near"] = display_title(c["audio"]["near"], [])
    return out


def sound_tags(tracks: list[dict], taste) -> None:
    """Give each track the compact vector and energy the page uses to adapt the queue while you listen."""
    V = audio.vectors([t["vid"] for t in tracks])
    if not V or not len(taste.M):
        return
    b, scale = audio.basis(taste.M)
    vids = [t["vid"] for t in tracks if t["vid"] in V]
    m = np.stack([V[v] for v in vids])
    en = audio.axis_scores(m).get("energy")
    ref = audio.axis_scores(taste.M).get("energy")
    by = {v: i for i, v in enumerate(vids)}
    for t in tracks:
        i = by.get(t["vid"])
        if i is None:
            continue
        t["v"] = audio.pack(m[i], b, scale)
        if en is not None and ref is not None:
            t["en"] = round(float((en[i] - ref.mean()) / (ref.std() or 1)), 2)


def localize(picks: list[dict]) -> None:
    """Artist pages and search are read in English (see ytm.client); show each pick the way the listener's own
    YouTube Music shows it."""
    with store.Pool(4) as ex:
        locs = list(ex.map(lambda p: ytm.track(p["vid"]), picks))
    for p, loc in zip(picks, locs):
        if not loc:
            continue
        p["title"] = ytm.plain_title(loc["title"] or p["title"])
        p["artists"] = loc["artists"] or p["artists"]
        p["album"] = loc["album"] or p.get("album")
        p["thumb"] = loc["thumb"] or p.get("thumb")
        p["year"] = p.get("year") or loc.get("year")


def prefer_record(picks: list[dict], known) -> None:
    """A music video brings skits, long intros and a frame that isn't the cover. When YouTube Music has the same
    recording as an audio track, play that instead and keep the video's id in "mv"."""
    todo = [p for p in picks if p.get("type") in ("OMV", "UGC")]

    def find(p):
        return library.counterpart(display_title(p["title"], p["artists"]), [a["name"] for a in p["artists"]], p.get("dur") or 0)

    with store.Pool(4) as ex:
        found = list(ex.map(find, todo))
    for p, h in zip(todo, found):
        if not h or known.reject(h) in ("liked", "feedback"):
            continue
        audio.alias(h["vid"], p["vid"])
        p["mv"] = p["vid"]
        p.update(vid=h["vid"], type="ATV", dur=h["dur"] or p.get("dur"), thumb=h.get("thumb") or p.get("thumb"),
                 album=h.get("album") or p.get("album"), year=p.get("year") or h.get("year"))


def _label(t: dict) -> str:
    """How a like is named in a candidate's provenance (candidates.gather)."""
    return f"{t['title']} - {t['artists'][0]['name']}" if t.get("artists") else t["title"]


def because(p: dict, theirs: list[dict], index: tuple[dict, dict] | None = None) -> dict | None:
    """The one song of the listener's own that a pick is shown next to: the one the editor found closest ("near"),
    else the like whose radio turned it up ("from"). Always a real like, so the listener can play it and judge.
    `index` (from `_index`) saves rebuilding the lookups for every pick."""
    by_vid, by_label = index or _index([t for t in theirs if not t.get("implicit")])
    t, how = by_vid.get(p.get("like_vid")), "near"
    if not t:
        t, how = next((by_label[v] for v in p.get("via", []) if v in by_label), None), "from"
    if not t:
        return None
    return {"vid": t["vid"], "title": t["title"], "artist": t["artists"][0]["name"] if t.get("artists") else "",
            "at": (t.get("liked_est") or "")[:7] or None, "how": how}


def _index(theirs: list[dict]) -> tuple[dict, dict]:
    return {t["vid"]: t for t in theirs}, {_label(t): t for t in theirs}


def ground(picks: list[dict]) -> None:
    """Picks made before they carried `because`: find it from their provenance against the library, and take out
    of their reasons the sentences that talk about the listener's own songs, as new picks have."""
    todo = [p for p in picks if "because" not in p]
    if not todo:
        return
    theirs = [t for t in library.load() if not t["long"]]
    index, keys = _index(theirs), {song_key(t["title"]) for t in theirs}
    for p in todo:
        p["because"] = because(p, theirs, index)
        if p.get("reason"):
            p["reason"] = rank.clean_reason(p["reason"], p, keys)


def one_each(lanes: list[list[dict]]) -> None:
    """A song goes out once per edition. Its video and its audio track are different ids, and the same song can come
    up in two lanes, so compare songs, not ids. Earlier lists win."""
    seen = set()
    for items in lanes:
        keep = []
        for p in items:
            ids = {p["vid"], p.get("mv")} - {None}
            song = (song_key(display_title(p["title"], p["artists"])), fold(p["artists"][0]["name"]) if p["artists"] else "")
            dup = bool(ids & seen) or song in seen
            seen |= ids | {song}   # a dropped duplicate's ids are that song too
            if not dup:
                keep.append(p)
        items[:] = keep


def negatives() -> list[str]:
    rows = store.db().execute(
        "select title, artist, reason from feedback where uid=? and action='dislike' order by ts desc limit 20",
        (store.uid(),)).fetchall()
    out = [f"{r['title']} — {r['artist']}" + (f" ({r['reason']})" if r["reason"] else "") for r in rows]
    return out + [f"{d['title']} — {d['artist']} (thumbs-down on YouTube)" for d in signals.youtube().get("disliked", [])[:8]]


PRE_K = 64   # candidates per lane that get listened to before the final shortlist
EDITOR_K = {False: 32, True: 40}   # songs the editor reads per lane: with the whole pool screened first, more of them are worth it


def build_lane(lane, tracks, prof, known, rng, n, log, loves=()):
    seeds = candidates.lane_seeds(lane, tracks, prof, rng, loves=loves)
    g = candidates.gather(lane, seeds, known, candidates.core_artists(lane, tracks, prof))
    for c in g["cands"].values():
        c["shown_before"] = c["vid"] in known.recent_shown
    pre = candidates.shortlist(lane, g["cands"], k=PRE_K)
    log(i18n.tr("{lane}: {c} 首候选，{p} 首进入试听", lane=lane["name"], c=len(g["cands"]), p=len(pre)))
    return lane, seeds, g, pre


def listen(built, taste_args, log, itunes_budget=None, text=None, orders=None):
    """Embed every pre-shortlisted track, then re-rank each lane by how it sounds against the listener's likes
    (and, for a request in words, against the words themselves)."""
    pool = [c for b in built for c in b[3]]
    try:
        stats = audio.ensure(pool, log=log, itunes_budget=itunes_budget, texts=[text] if text else [])
        log(i18n.tr("试听完成 {stats}", stats=stats))
    except Exception as e:  # a missing preview service must never cost the listener their edition
        log(i18n.tr("试听失败，按图谱排序 ({e})", e=e))
    t = taste.Taste(*taste_args)
    out = []
    tv = audio.wait_text(text) if text else None
    for lane, seeds, g, pre in built:
        t.measure(pre, lane.get("audio_lane") or lane["key"])
        if tv is None:
            # Sound barely predicts what they will like (AUC 0.55-0.61 on held-out likes), and choosing by it pulled
            # mellow Mandopop into the jazz lane. For the daily edition it only vetoes near-copies of refused sounds.
            keep = {c["vid"]: c for c in pre if not (c.get("audio") and c["audio"]["neg"] > taste.NEG_FLOOR)}
            order = (orders or {}).get(lane["key"])
            out.append((lane, seeds, g, candidates.shortlist(lane, keep, k=EDITOR_K[order is not None], order=order)))
        else:
            out.append((lane, seeds, g, taste.select(lane, taste.rank(lane, pre, text_vec=tv))))
    return out, t


def build_focus(prof, known, rng, log, n=4):
    focus = prof.get("focus")
    if not focus:
        return None
    queries = list(focus["queries"])
    rng.shuffle(queries)
    found = {}
    for q in queries[:6]:
        for pos, t in enumerate(ytm.search(q, "videos", 20)):
            if (t.get("dur") or 0) < FOCUS_MIN_S or known.reject(t) in ("liked", "feedback", "shown"):
                continue
            c = found.setdefault(t["vid"], {**t, "support": 0.0, "via": [q], "familiar": 0, "sources": ["search"]})
            c["support"] += 1 / (1 + pos)
    pool = sorted(found.values(), key=lambda c: -c["support"])
    picks, per_channel = [], {}
    for c in pool:
        ch = fold(c["artists"][0]["name"]) if c["artists"] else ""
        if per_channel.get(ch):
            continue
        per_channel[ch] = 1
        picks.append(c)
        if len(picks) >= n:
            break
    log(i18n.tr("专注: {n} 个长歌单候选", n=len(found)))
    return {"blurb": focus["blurb"], "when": focus["when"], "picks": [_public(c) for c in picks]}


# Gathering candidates leans on YouTube Music from one address, so only a few listeners gather at once. The editor
# step runs outside it: on the shared key a scheduled edition waits there on a batch for up to hours.
GATHER = threading.BoundedSemaphore(int(os.environ.get("ZHIYIN_GATHER", 2)))


def played_since(ed: dict | None) -> set[str]:
    """Stations the listener actually played from since this edition came out."""
    if not ed:
        return set()
    rows = store.db().execute("select distinct lane from plays where uid=? and ts>? and lane is not null and test=0",
                              (store.uid(), ed["created"])).fetchall()
    return {r["lane"] for r in rows}


def build(log=print, model: str = "opus", only: set[str] | None = None) -> dict:
    """A new edition. With `only`, just those stations get new songs; the rest keep the ones not yet heard."""
    llm.require()   # before an hour of gathering that the editor then couldn't use
    t0 = time.time()
    prof = store.read_json(store.PROFILE)
    if not prof:
        raise RuntimeError("no taste profile yet: run `zhiyin profile` first")
    s = settings.load()
    n = s.get("picks_per_lane", 8)
    tracks = library.load()
    try:
        loves = signals.refresh(prof, log)
    except Exception:   # what their plays say can wait a day; the edition can't
        traceback.print_exc()
        loves = signals.loves()
    known = candidates.Known(tracks, prof)
    edition_id = dt.datetime.now().strftime("%Y-%m-%d %H:%M")
    rng = random.Random(edition_id)
    lanes = [settings.lane_view(l) for l in prof["lanes"]]
    active = [l for l in lanes if l["enabled"]]
    prev = store.read_json(store.EDITION) if only is not None else None
    kept = {l["key"]: l for l in (prev or {}).get("lanes", []) if l["key"] not in only} if prev else {}
    for l in kept.values():
        known.taken.update(p["vid"] for p in l["picks"] + l.get("reserve", []))

    if not GATHER.acquire(blocking=False):
        log(i18n.tr("排队中：另一位听众的电台正在准备"))
        GATHER.acquire()
    try:
        built = []
        for lane in [l for l in active if l["key"] not in kept]:
            built.append(build_lane(lane, tracks, prof, known, rng, n, log, loves))
            # A track surfaced in one lane shouldn't reappear in the next.
            for c in built[-1][3]:
                known.taken.add(c["vid"])
        focus = prev["focus"] if prev and prev.get("focus") and "focus" not in only else build_focus(prof, known, rng, log)
    finally:
        GATHER.release()

    # What the screen and the editor read about each lane: all its songs, and how earlier picks for it went. The
    # owner's own accounts get the whole pool read by Claude before listening (rank.screen); others the graph's top.
    mine = store.is_owners(store.uid())
    stories = {b[0]["key"]: rank.lane_story(b[0], tracks, prof, loves, rank.STORY_N if mine else 60) for b in built}
    went = {b[0]["key"]: rank.outcomes(b[0]["key"]) for b in built}
    orders = {}
    if mine and built:
        log(i18n.tr("Claude 通读每条线的全部候选（{n} 条线）", n=len(built)))
        with store.Pool(4) as ex:
            for b, order in zip(built, ex.map(lambda b: rank.screen(b[0], b[2]["cands"], stories[b[0]["key"]],
                                                                    went[b[0]["key"]], model=model), built)):
                if order:
                    orders[b[0]["key"]] = order
        built = [(lane, seeds, g, candidates.shortlist(lane, g["cands"], k=PRE_K, order=orders[lane["key"]])
                  if lane["key"] in orders else pre) for lane, seeds, g, pre in built]
    built, tst = listen(built, (tracks, prof), log, orders=orders)

    negs = negatives()
    log(i18n.tr("编辑精选中（{n} 条线并行）", n=len(built)))
    probing = quality.probing()

    def choose(b):
        lane, seeds, g, sl = b
        # No editor, no edition: graph-ranked songs nobody vetted are what cost the listener's trust before, so a
        # failure keeps the previous edition up and the scheduler tries again.
        picks = rank.pick(lane, sl, seeds, negs, model=model, story=stories.get(lane["key"], ()), went=went.get(lane["key"], ()))
        # fewer, surer picks: what the editor isn't confident about doesn't go out (but always a few to play)
        sure = [p for p in picks if p["fit"] >= rank.MIN_FIT] or picks[:3]
        chosen = rank.enforce_quota(sure, n, lane["discovery"])
        ids = {p["vid"] for p in chosen}
        reserve = [p for p in picks if p["vid"] not in ids]
        ids |= {p["vid"] for p in reserve}
        reserve += [{**c, "fit": 0, "reason": ""} for c in sl if c["vid"] not in ids]
        if probing:
            probe(lane, chosen, reserve, picks, random.Random(f"{edition_id}|{lane['key']}"))
        for p in chosen + reserve:
            p["because"] = because(p, seeds)
        return lane, seeds, g, chosen, reserve[:RESERVE]

    with store.Pool(4) as ex:
        chosen = list(ex.map(choose, built))

    log(i18n.tr("整理歌曲信息"))
    every = [p for _, _, _, picks, reserve in chosen for p in picks + reserve]
    prefer_record(every, known)
    one_each([picks for _, _, _, picks, _ in chosen] + [reserve for *_, reserve in chosen])
    localize(every)
    sound_tags(every, tst)
    ytm.warm_covers(every + (focus["picks"] if focus else []))
    out_lanes = []
    con = store.db()
    for lane, seeds, g, picks, reserve in chosen:
        for i, p in enumerate(picks):
            p["slot"] = i
        for p in reserve:
            p["slot"] = -1
        out_lanes.append({
            "key": lane["key"], "name": lane["name"], "english": lane["english"], "blurb": lane["blurb"],
            "when": lane["when"], "discovery": lane["discovery"],
            "seeds": [{"vid": x["vid"], "title": x["title"], "artists": x["artists"],
                       "thumb": (ytm.track(x["vid"]) or {}).get("thumb")} for x in seeds[:6]],
            "picks": [_public(p) for p in picks],
            "reserve": [_public(p) for p in reserve],
            "stats": {"candidates": len(g["cands"]), "rejected": g["rejected"], "playlists": g.get("playlists", 0),
                      "heard": sum(1 for p in picks if p.get("audio")),
                      # does the editor lean towards hits? median views of what it sent out vs what it was offered
                      "views": [_median_views(p for p in picks if not p.get("probe")), _median_views(g["cands"].values())]},
        })
        con.executemany("insert into shown (vid, edition, lane, ts, uid, fit, pos, fam, probe) values (?,?,?,?,?,?,?,?,?)",
                        [(v, edition_id, lane["key"], store.now(), store.uid(), p.get("fit"), i, fam_code(p), p.get("probe"))
                         for i, p in enumerate(picks) for v in (p["vid"], p.get("mv")) if v])
    fresh = {l["key"] for l in out_lanes}
    order = [l["key"] for l in active]
    out_lanes = sorted([*out_lanes, *({**l, "fresh": False} for k, l in kept.items() if k in order)],
                       key=lambda l: order.index(l["key"]))
    for l in out_lanes:
        if l["key"] in fresh:
            l["fresh"] = edition_id
    if focus and not (prev and focus is prev.get("focus")):
        con.executemany("insert into shown (vid, edition, lane, ts, uid) values (?,?,?,?,?)",
                        [(p["vid"], edition_id, "focus", store.now(), store.uid()) for p in focus["picks"]])
    con.commit()
    ed = {"id": edition_id, "created": store.now(), "took": round(time.time() - t0), "lanes": out_lanes, "focus": focus,
          "audio_coverage": round(tst.coverage, 2), "lang": i18n.of()}
    store.write_json(store.EDITION, ed)
    log(i18n.tr("完成，用时 {s} 秒", s=ed["took"]))
    return ed


def fam_code(p: dict) -> int:
    """0 an artist new to them, 1 one with liked songs, 2 one they follow or play without a like."""
    return 1 if p.get("familiar") else 2 if p.get("knows") else 0


def _median_views(cands) -> float | None:
    v = [candidates.views_n(c) for c in cands]
    v = [x for x in v if x]
    return round(statistics.median(v)) if v else None


def probe(lane: dict, chosen: list[dict], reserve: list[dict], picks: list[dict], rng: random.Random) -> None:
    """One song per station the editor would not have sent out, placed among its picks and marked, so the listens
    show whether its judgement is worth what it costs: "low" is one it returned below the bar (rank.MIN_FIT),
    "graph" the best song by the YouTube graph alone that it passed over. Stops by itself once quality.PROBE_ENOUGH
    of them have been heard."""
    if len(chosen) < 5:
        return
    returned = {p["vid"] for p in picks}
    artists = {fold(p["artists"][0]["name"]) for p in chosen if p.get("artists")}
    other = [p for p in reserve if p.get("artists") and fold(p["artists"][0]["name"]) not in artists]
    # (a pick the editor rated above the bar but lost to the station's size or quota is no test of its judgement)
    low = [p for p in other if p["vid"] in returned and 0.5 <= (p.get("fit") or 0) < rank.MIN_FIT]
    graph = [p for p in other if p["vid"] not in returned]
    kinds = [k for k, xs in (("low", low), ("graph", graph)) if xs]
    if not kinds:
        return
    kind = rng.choice(kinds)
    p = (low if kind == "low" else graph)[0]
    reserve.remove(p)
    p["probe"] = kind
    chosen.insert(rng.randint(2, len(chosen)), p)


def redecorate() -> bool:
    """Sound arrived after the edition was built (the Mac was asleep): give its picks their vectors now."""
    ed, prof = store.read_json(store.EDITION), store.read_json(store.PROFILE)
    if not ed or not prof:
        return False
    every = [p for l in ed["lanes"] for p in l["picks"] + l.get("reserve", [])]
    lacking = [p["vid"] for p in every if "v" not in p]
    if not lacking or not audio.vectors(lacking):
        return False
    t = taste.Taste(library.load(), prof)
    sound_tags(every, t)
    ed["audio_coverage"] = round(t.coverage, 2)
    store.write_json(store.EDITION, ed)
    return True
