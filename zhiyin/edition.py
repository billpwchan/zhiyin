import datetime as dt
import random
import time

import numpy as np

from . import audio, candidates, library, llm, rank, settings, store, taste, ytm
from .text import display_title, fold, song_key

FOCUS_MIN_S = 20 * 60
NEAR_CLAIM = 0.92   # the median nearest-neighbour similarity among the listener's own likes
RESERVE = 12


def _public(c: dict) -> dict:
    keep = ("vid", "title", "artists", "album", "year", "thumb", "dur", "type", "reason", "fit", "familiar", "sources")
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
    return [f"{r['title']} — {r['artist']}" + (f" ({r['reason']})" if r["reason"] else "") for r in rows]


PRE_K = 64   # graph-ranked candidates per lane that get listened to before the final shortlist


def build_lane(lane, tracks, prof, known, rng, n, log):
    seeds = candidates.lane_seeds(lane, tracks, prof, rng)
    g = candidates.gather(lane, seeds, known, candidates.core_artists(lane, tracks, prof))
    for c in g["cands"].values():
        c["shown_before"] = c["vid"] in known.recent_shown
    pre = candidates.shortlist(lane, g["cands"], k=PRE_K)
    log(f"{lane['name']}: {len(g['cands'])} 首候选，{len(pre)} 首进入试听")
    return lane, seeds, g, pre


def listen(built, taste_args, log, itunes_budget=None, text=None):
    """Embed every pre-shortlisted track, then re-rank each lane by how it sounds against the listener's likes
    (and, for a request in words, against the words themselves)."""
    pool = [c for b in built for c in b[3]]
    try:
        stats = audio.ensure(pool, log=log, itunes_budget=itunes_budget, texts=[text] if text else [])
        log(f"试听完成 {stats}")
    except Exception as e:  # a missing preview service must never cost the listener their edition
        log(f"试听失败，按图谱排序 ({e})")
    t = taste.Taste(*taste_args)
    out = []
    tv = audio.wait_text(text) if text else None
    for lane, seeds, g, pre in built:
        t.measure(pre, lane.get("audio_lane") or lane["key"])
        if tv is None:
            # Sound barely predicts what they will like (AUC 0.55-0.61 on held-out likes), and choosing by it pulled
            # mellow Mandopop into the jazz lane. For the daily edition it only vetoes near-copies of refused sounds.
            keep = {c["vid"]: c for c in pre if not (c.get("audio") and c["audio"]["neg"] > taste.NEG_FLOOR)}
            out.append((lane, seeds, g, candidates.shortlist(lane, keep)))
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
    log(f"专注: {len(found)} 个长歌单候选")
    return {"blurb": focus["blurb"], "when": focus["when"], "picks": [_public(c) for c in picks]}


def build(log=print, model: str = "opus") -> dict:
    t0 = time.time()
    prof = store.read_json(store.PROFILE)
    if not prof:
        raise RuntimeError("no taste profile yet: run `zhiyin profile` first")
    s = settings.load()
    n = s.get("picks_per_lane", 8)
    tracks = library.load()
    known = candidates.Known(tracks, prof)
    edition_id = dt.datetime.now().strftime("%Y-%m-%d %H:%M")
    rng = random.Random(edition_id)
    lanes = [settings.lane_view(l) for l in prof["lanes"]]
    active = [l for l in lanes if l["enabled"]]

    built = []
    for lane in active:
        built.append(build_lane(lane, tracks, prof, known, rng, n, log))
        # A track surfaced in one lane shouldn't reappear in the next.
        for c in built[-1][3]:
            known.taken.add(c["vid"])
    focus = build_focus(prof, known, rng, log)
    built, tst = listen(built, (tracks, prof), log)

    negs = negatives()
    log(f"编辑精选中（{len(built)} 条线并行）")

    def choose(b):
        lane, seeds, g, sl = b
        try:
            picks = rank.pick(lane, sl, seeds, negs, model=model)
        except llm.LLMError as e:
            log(f"{lane['name']}: 编辑失败，按分数兜底 ({e})")
            picks = [{**c, "fit": 0.5, "reason": ""} for c in sl]
        # fewer, surer picks: what the editor isn't confident about doesn't go out (but always a few to play)
        sure = [p for p in picks if p["fit"] >= rank.MIN_FIT] or picks[:3]
        chosen = rank.enforce_quota(sure, n, lane["discovery"])
        ids = {p["vid"] for p in chosen}
        reserve = [p for p in picks if p["vid"] not in ids]
        ids |= {p["vid"] for p in reserve}
        reserve += [{**c, "fit": 0, "reason": ""} for c in sl if c["vid"] not in ids]
        return lane, seeds, g, chosen, reserve[:RESERVE]

    with store.Pool(4) as ex:
        chosen = list(ex.map(choose, built))

    log("整理歌曲信息")
    every = [p for _, _, _, picks, reserve in chosen for p in picks + reserve]
    prefer_record(every, known)
    one_each([picks for _, _, _, picks, _ in chosen] + [reserve for *_, reserve in chosen])
    localize(every)
    sound_tags(every, tst)
    ytm.warm_covers(every + (focus["picks"] if focus else []))
    out_lanes = []
    con = store.db()
    for lane, seeds, g, picks, reserve in chosen:
        out_lanes.append({
            "key": lane["key"], "name": lane["name"], "english": lane["english"], "blurb": lane["blurb"],
            "when": lane["when"], "discovery": lane["discovery"],
            "seeds": [{"vid": x["vid"], "title": x["title"], "artists": x["artists"],
                       "thumb": (ytm.track(x["vid"]) or {}).get("thumb")} for x in seeds[:6]],
            "picks": [_public(p) for p in picks],
            "reserve": [_public(p) for p in reserve],
            "stats": {"candidates": len(g["cands"]), "rejected": g["rejected"], "playlists": g.get("playlists", 0),
                      "heard": sum(1 for p in picks if p.get("audio"))},
        })
        con.executemany("insert into shown (vid, edition, lane, ts, uid) values (?,?,?,?,?)",
                        [(v, edition_id, lane["key"], store.now(), store.uid()) for p in picks for v in (p["vid"], p.get("mv")) if v])
    if focus:
        con.executemany("insert into shown (vid, edition, lane, ts, uid) values (?,?,?,?,?)",
                        [(p["vid"], edition_id, "focus", store.now(), store.uid()) for p in focus["picks"]])
    con.commit()
    ed = {"id": edition_id, "created": store.now(), "took": round(time.time() - t0), "lanes": out_lanes, "focus": focus,
          "audio_coverage": round(tst.coverage, 2)}
    store.write_json(store.EDITION, ed)
    log(f"完成，用时 {ed['took']} 秒")
    return ed


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
