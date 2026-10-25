import time

from . import candidates, edition, i18n, library, llm, rank, store, ytm


PLAN_SCHEMA = {
    "type": "object",
    "properties": {
        "intent": {"type": "string"},
        "lane": {"type": "string"},
        "seeds": {"type": "array", "items": {"type": "integer"}},
        "artists": {"type": "array", "items": {"type": "string"}},
        "queries": {"type": "array", "items": {"type": "string"}},
        "langs": {"type": "array", "items": {"type": "string"}},
        "energy": {"type": "array", "items": {"type": "integer"}},
        "avoid": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["intent", "lane", "seeds", "artists", "queries", "langs", "energy", "avoid"],
}

PLAN_SYSTEM = """You turn one listener's music request into a retrieval plan for a recommender built on YouTube Music.
You see their listening lanes and, per lane, the songs they like most right now (rank|title|artists).
- intent: restate the request in @INTENT@, as a title.
- lane: the closest lane key, or "none".
- seeds: up to 6 ranks from THEIR songs that best match the request (these start YouTube radios).
- artists: up to 6 real artists (new to them preferred) whose catalogue fits; only names you are sure exist.
- queries: up to 6 YouTube Music song searches ("artist song" or a precise descriptive phrase) that would surface fitting songs.
- langs: sung languages allowed, from yue, cmn, ko, ja, en, th, instrumental. Empty means any.
- energy: [min,max] on 1-5.
- avoid: what would be wrong for this request."""


def _lane_digest(prof, tracks, per_lane=14):
    assign = prof.get("assign", {})
    by_lane = {}
    for t in tracks:
        if t["long"]:
            continue
        for k in assign.get(t["vid"], [])[:1]:
            by_lane.setdefault(k, []).append(t)
    parts = []
    for l in prof["lanes"]:
        songs = by_lane.get(l["key"], [])[:per_lane]
        lines = "\n".join(f"{t['rank']}|{t['title']}|{', '.join(a['name'] for a in t['artists'])}" for t in songs)
        parts.append(f"## {l['key']} — {l['english']}: {l['sound']}\n{lines}")
    return "\n\n".join(parts)


def run(question: str, log=print) -> dict:
    t0 = time.time()
    prof = store.read_json(store.PROFILE)
    tracks = library.load()
    by_rank = {t["rank"]: t for t in tracks}
    log(i18n.tr("理解需求"))
    plan = llm.call(f"REQUEST: {question}\n\nLANES:\n{_lane_digest(prof, tracks)}", PLAN_SYSTEM.replace("@INTENT@", i18n.write("intent")), PLAN_SCHEMA,
                    model="sonnet", timeout=300)
    known = candidates.Known(tracks, prof)
    known.recent_shown, known.just_shown = set(), set()
    lane_base = next((l for l in prof["lanes"] if l["key"] == plan["lane"]), None)
    langs = plan["langs"] or ["yue", "cmn", "ko", "ja", "en", "th", "instrumental"]
    lane = {
        "key": "ask", "name": plan["intent"], "english": "request", "sound": question,
        "when": "", "langs": langs, "energy": plan["energy"] or [1, 5], "avoid": plan["avoid"],
        "discovery": lane_base.get("discovery", 0.5) if lane_base else 0.5,
        "core_artists": [], "explore_artists": [{"name": a, "why": "fits the request", "song": ""} for a in plan["artists"]],
    }
    seeds = [{**by_rank[r], "w": 1.0} for r in plan["seeds"] if r in by_rank and not by_rank[r]["long"]][:6]
    log(i18n.tr("从 {s} 首你的歌和 {a} 位歌手出发找歌", s=len(seeds), a=len(plan["artists"])))
    g = candidates.gather(lane, seeds, known, [])
    cands = g["cands"]

    def q(query):
        return query, ytm.search(query, "songs", 8)
    with store.Pool(4) as ex:
        for query, hits in ex.map(q, plan["queries"]):
            for pos, t in enumerate(hits):
                if known.reject(t) or not candidates._lang_ok(t, langs):
                    continue
                c = cands.setdefault(t["vid"], {**t, "support": 0.0, "via": [], "sources": [],
                                                "familiar": known.artist_familiarity(t["artists"])})
                c["support"] += 0.8 / (1 + pos)
                c["sources"] = sorted(set(c["sources"]) | {"search"})
    pre = candidates.shortlist(lane, cands, k=40)
    lane["audio_lane"] = plan["lane"] if lane_base else None
    # Previews from Deezer only: the iTunes fallback is rate-limited and a request should come back within a minute.
    built, tst = edition.listen([(lane, seeds, g, pre)], (tracks, prof), log, itunes_budget=0, text=question)
    sl = built[0][3][:26]
    log(i18n.tr("{n} 首候选，编辑挑选中", n=len(cands)))
    picks = rank.pick(lane, sl, seeds, edition.negatives(), model="opus")[:10]
    edition.prefer_record(picks, known)
    edition.localize(picks)
    edition.sound_tags(picks, tst)
    ytm.warm_covers(picks)
    result = {"q": question, "lang": i18n.of(), "intent": plan["intent"], "lane": plan["lane"], "created": store.now(),
              "took": round(time.time() - t0), "picks": [edition._public(p) for p in picks]}
    hist = store.read_json(store.ASKS) or []
    store.write_json(store.ASKS, [result] + hist[:19])
    log(i18n.tr("完成，用时 {s} 秒", s=result["took"]))
    return result
