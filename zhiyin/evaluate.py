"""Time-split check: hide the newest likes, rebuild candidates from older likes only, count how many hidden likes
(or their artists) the engine would have surfaced. Compared with a plain 'radio from your latest likes' baseline,
which is roughly what YouTube Music itself does."""
import json
import random
import time
from collections import Counter
from pathlib import Path

from . import candidates, library, settings, store, ytm
from .text import fold, song_key


def _hit(c, target):
    if c["vid"] == target["vid"]:
        return True
    names = {fold(a["name"]) for a in c["artists"]}
    return song_key(c["title"]) == song_key(target["title"]) and bool(names & {fold(a["name"]) for a in target["artists"]})


def run(holdout: int = 60, seed: int = 7):
    prof = store.read_json(store.PROFILE)
    tracks = library.load()
    tags = store.read_json(store.TAGS) or {}
    hidden = [t for t in tracks if t["rank"] < holdout and not t["long"] and t["type"] in ("ATV", "OMV")
              and (tags.get(t["vid"], {}).get("kind") in ("song", None))]
    train = [t for t in tracks if t["rank"] >= holdout]
    prof_train = {**prof, "lanes": [{**l, "seeds": [r for r in l["seeds"] if r >= holdout]} for l in prof["lanes"]]}
    known = candidates.Known(train, prof_train)
    known.heard, known.recent_shown, known.just_shown, known.disliked = set(), set(), set(), set()
    train_keys = {song_key(t["title"]) for t in train}
    for h in hidden:   # a hidden like that also sits in a playlist of theirs is still hidden
        known.vids.discard(h["vid"])
        if song_key(h["title"]) not in train_keys:
            known.songs.pop(song_key(h["title"]), None)
    rng = random.Random(seed)

    base = {}
    for t in [t for t in train if not t["long"] and t["type"] in ("ATV", "OMV")][:10]:
        for x in ytm.radio(t["vid"])["tracks"][1:]:
            if not known.reject(x):
                base.setdefault(x["vid"], x)

    pool, short = {}, {}
    for lane in prof_train["lanes"]:
        lane = settings.lane_view(lane)
        seeds = candidates.lane_seeds(lane, train, prof_train, rng, loves=known.loves)
        g = candidates.gather(lane, seeds, known, candidates.core_artists(lane, train, prof_train), explore=False)
        for v, c in g["cands"].items():
            pool.setdefault(v, c)
        for c in candidates.shortlist(lane, g["cands"]):
            short.setdefault(c["vid"], c)
            known.taken.add(c["vid"])  # same cross-lane dedupe as a real edition


    def recall(cands):
        song_hits = [h for h in hidden if any(_hit(c, h) for c in cands.values())]
        cand_artists = {fold(a["name"]) for c in cands.values() for a in c["artists"]}
        art_hits = [h for h in hidden if {fold(a["name"]) for a in h["artists"]} & cand_artists]
        return song_hits, art_hits

    hidden_new_artists = [h for h in hidden if not known.artist_familiarity(h["artists"])]
    print(f"hidden likes: {len(hidden)} (of which by artists not in older likes: {len(hidden_new_artists)})")
    for name, cands in (("zhiyin pool", pool), ("zhiyin shortlists", short), ("baseline radio", base)):
        s, a = recall(cands)
        new_art_found = [h for h in a if h in hidden_new_artists]
        print(f"{name:18s} size {len(cands):5d} | song recall {len(s)}/{len(hidden)} | artist recall {len(a)}/{len(hidden)}"
              f" | new-artist recall {len(new_art_found)}/{len(hidden_new_artists)}")
    s, _ = recall(pool)
    src = Counter(src for h in s for c in pool.values() if _hit(c, h) for src in c["sources"])
    print("sources of song hits:", dict(src))
    print("found:", "; ".join(f"{h['title']} - {h['artists'][0]['name']}" for h in s))


def audio_check(holdout: int = 80):
    """Does sound alone predict what the listener goes on to like? Hide the newest likes, score them and the
    engine's own unliked candidates against the older likes, and report the AUC (0.5 = no signal)."""
    import numpy as np

    from . import audio, taste
    prof = store.read_json(store.PROFILE)
    tracks = library.load()
    assign = prof.get("assign", {})
    liked = {t["vid"] for t in tracks}
    V = audio.vectors([t["vid"] for t in tracks if not t["long"]])
    train = [t for t in tracks if t["rank"] >= holdout and t["vid"] in V]
    hidden = [t for t in tracks if t["rank"] < holdout and t["vid"] in V]
    con = audio._db()
    neg_vids = [r["vid"] for r in con.execute("select vid from audio where emb is not null") if r["vid"] not in liked]
    N = audio.vectors(neg_vids)
    if len(N) < 50 or len(hidden) < 20:
        print(f"not enough vectors yet: {len(hidden)} hidden likes, {len(N)} candidates")
        return
    M = audio.unit(np.stack([V[t["vid"]] for t in train]))
    w = np.array([0.5 ** (candidates._years_ago(t.get("liked_est")) / taste.HALF_LIFE_YEARS) for t in train])
    lanes = np.array([(assign.get(t["vid"]) or ["none"])[0] for t in train])
    H = audio.unit(np.stack([V[t["vid"]] for t in hidden]))
    X = audio.unit(np.stack(list(N.values())))

    def auc(pos, neg):
        allv = np.concatenate([pos, neg])
        ranks = allv.argsort().argsort() + 1
        return (ranks[:len(pos)].sum() - len(pos) * (len(pos) + 1) / 2) / (len(pos) * len(neg))

    for k in (1, 5, 15):
        print(f"knn k={k:2d}  AUC {auc(audio.knn(H, M, w, k), audio.knn(X, M, w, k)):.3f}")
    centroid = audio.unit(M.mean(axis=0))
    print(f"centroid    AUC {auc(H @ centroid, X @ centroid):.3f}")
    keys = [l["key"] for l in prof["lanes"]]
    best = np.stack([audio.knn(H, M[lanes == k], w[lanes == k]) for k in keys]).argmax(axis=0)
    truth = [(assign.get(t["vid"]) or ["none"])[0] for t in hidden]
    ok = sum(1 for i, t in enumerate(truth) if t == keys[best[i]])
    print(f"lane recovered from sound for {ok}/{sum(1 for t in truth if t in keys)} hidden likes "
          f"(chance ~{1 / len(keys):.0%})")
    print(f"vectors: {len(train)} train likes, {len(hidden)} hidden likes, {len(N)} unliked candidates")


# ---------- v2: which of the songs they went on to like does each way of narrowing a lane's pool keep? ----------
# Rolling windows of likes, newest first: each window's pools are rebuilt from the likes older than it, the way the
# owner's edition builds them. The window's own likes are what it is scored on (no song counts in two windows, so the
# intervals hold); any later like a pool holds is reported beside them. Each arm
# narrows the same pools to rank.SCREEN_K; all model calls go out as one Message Batch (half price) and are kept by
# request, so a second run only pays for what is new. Everything stays under data/eval/screen on this machine.
ARMS = {"opus": ("opus", "high"), "sonnet": ("sonnet", "high"), "opus-medium": ("opus", "medium"),
        "sonnet-medium": ("sonnet", "medium")}
OUT_PER_READ = {"high": 3500, "medium": 1500}   # output tokens a screen read spends, mostly thinking (measured on editions)


def _dir() -> Path:
    d = store.DATA / "eval" / "screen"
    d.mkdir(parents=True, exist_ok=True)
    return d


def owner_accounts() -> list[str]:
    """The owner, the only listener these checks may read."""
    return [r["id"] for r in store.db().execute("select id from users where id=? and status='ready'", (store.OWNER,))]


def screen_build(windows: int = 4, size: int = 60, min_train: int = 200, log=print) -> None:
    from . import edition, rank
    ytm.MIN_GAP = max(ytm.MIN_GAP, 1.0)   # a second process beside the live server: gentler on YouTube
    prof = store.read_json(store.PROFILE)
    tracks = library.load()
    tags = store.read_json(store.TAGS) or {}
    out = _dir() / store.uid()
    out.mkdir(exist_ok=True)
    for k in range(windows):
        cut = (k + 1) * size
        train = [t for t in tracks if t["rank"] >= cut]
        if len(train) < min_train:
            break
        later = [t for t in tracks if t["rank"] < cut and not t["long"] and t["type"] in ("ATV", "OMV")
                 and tags.get(t["vid"], {}).get("kind") in ("song", None)]
        prof_k = {**prof, "lanes": [{**l, "seeds": [r for r in l["seeds"] if r >= cut]} for l in prof["lanes"]]}
        known = candidates.Known(train, prof_k)
        # nothing they did after the window may steer it: no plays, no shows, no thumbs-downs
        known.heard, known.recent_shown, known.just_shown, known.disliked = set(), set(), set(), set()
        train_keys = {song_key(t["title"]) for t in train}
        for h in later:
            known.vids.discard(h["vid"])
            if song_key(h["title"]) not in train_keys:
                known.songs.pop(song_key(h["title"]), None)
        rng = random.Random(f"{store.uid()}|{k}")
        lanes = []
        for lane in [settings.lane_view(l) for l in prof_k["lanes"]]:
            if not lane["enabled"]:
                continue
            seeds = candidates.lane_seeds(lane, train, prof_k, rng, loves=())
            g = candidates.gather(lane, seeds, known, candidates.core_artists(lane, train, prof_k))
            known.taken.update(c["vid"] for c in candidates.shortlist(lane, g["cands"], k=edition.PRE_K))
            pool = rank.screen_pool(lane, g["cands"])
            if len(pool) <= rank.SCREEN_K:
                continue
            story = rank.lane_story(lane, train, prof_k, (), rank.STORY_N, here=False)
            lanes.append({"key": lane["key"], "head": rank.screen_head(lane, story, []),
                          "pool": [{f: c.get(f) for f in ("vid", "title", "artists", "album", "year", "familiar", "knows", "via")}
                                   for c in pool],
                          "hits": {c["vid"]: h["vid"] for c in pool for h in later if _hit(c, h)}})
            log(f"w{k} {lane['key']}: pool {len(pool)}, went on to like {len(lanes[-1]['hits'])}")
        own = [t["vid"] for t in later if t["rank"] >= cut - size]
        store.write_json(out / f"w{k}.json", {"uid": store.uid(), "window": k, "size": size, "train": len(train),
                                               "later": len(later), "own": own, "lanes": lanes})
        found = {h for l in lanes for h in l["hits"].values()}
        log(f"w{k}: {len(train)} older likes, {len(later)} later; {len(found)} of them in a pool, "
            f"{len(found & set(own))} of the window's own {len(own)}")


def _windows() -> list[dict]:
    return [store.read_json(f) for f in sorted(_dir().glob("*/w*.json"))]


def _results() -> dict:
    p = _dir() / "results.jsonl"
    return {r["id"]: r for r in map(json.loads, p.read_text().splitlines())} if p.exists() else {}


def _request_id(w: dict, lane: str, arm: str, seed: int) -> str:
    return f"{w['uid']}|{w['window']}|{lane}|{arm}|{seed}"


def screen_submit(arms=("opus", "sonnet"), passes: int = 3, go: bool = False, log=print) -> None:
    """Every read not yet answered, as one batch. Without `go` only says what it would cost."""
    from . import llm, rank
    done, todo = _results(), []
    for w in _windows():
        for l in w["lanes"]:
            for arm in arms:
                for seed in range(passes):
                    rid = _request_id(w, l["key"], arm, seed)
                    if rid not in done:
                        todo.append((rid, arm, rank.screen_prompt(l["head"], l["pool"], l["key"], seed)))
    if not todo:
        log("nothing to ask: every read has an answer")
        return
    api = llm._api()
    system = rank.screen_system()
    per_char = {}
    for model in {ARMS[a][0] for a in arms}:
        sample = next(p for _, a, p in todo if ARMS[a][0] == model)
        n = api.messages.count_tokens(model=llm.MODELS[model], system=system, messages=[{"role": "user", "content": sample}])
        per_char[model] = n.input_tokens / (len(system) + len(sample))
    usd = 0.0
    for _, arm, prompt in todo:
        model, effort = ARMS[arm]
        i, o, _, _ = llm.PRICES[model]
        usd += (per_char[model] * (len(system) + len(prompt)) * i + OUT_PER_READ[effort] * o) / 1e6 / 2
    log(f"{len(todo)} reads over {len(_windows())} windows, arms {', '.join(arms)}: about ${usd:.0f} at batch prices")
    if not go:
        return
    ids = {f"r{n}": rid for n, (rid, _, _) in enumerate(todo)}
    b = api.messages.batches.create(requests=[{"custom_id": f"r{n}", "params": {
        "model": llm.MODELS[ARMS[arm][0]], "max_tokens": 32000,
        "system": [{"type": "text", "text": system}],
        "messages": [{"role": "user", "content": prompt}],
        "output_config": {"effort": ARMS[arm][1], "format": {"type": "json_schema", "schema": llm.strict(rank.IDS_SCHEMA)}}}}
        for n, (rid, arm, prompt) in enumerate(todo)])
    batches = store.read_json(_dir() / "batches.json") or []
    store.write_json(_dir() / "batches.json", batches + [{"id": b.id, "at": time.time(), "ids": ids, "estimate": usd}])
    log(f"submitted {b.id}")


def screen_collect(log=print) -> bool:
    """Fetch the answers of every finished batch; True once none is still running."""
    from . import llm, rank
    api = llm._api()
    batches = store.read_json(_dir() / "batches.json") or []
    pools = {(w["uid"], w["window"], l["key"]): l["pool"] for w in _windows() for l in w["lanes"]}
    running = False
    for b in batches:
        if b.get("collected"):
            continue
        st = api.messages.batches.retrieve(b["id"])
        if st.processing_status != "ended":
            running = True
            log(f"{b['id']}: {st.request_counts}")
            continue
        usd, bad = 0.0, 0
        with (_dir() / "results.jsonl").open("a") as f:
            for r in api.messages.batches.results(b["id"]):
                rid = b["ids"][r.custom_id]
                uid, k, lane, arm, seed = rid.split("|")
                if r.result.type != "succeeded":
                    bad += 1
                    continue
                msg = r.result.message
                cost = llm.cost(ARMS[arm][0], msg.usage) / 2
                usd += cost
                llm._record("eval", "key:eval", cost, llm._tokens(msg.usage))   # not any listener's, nor the owner's cap
                try:
                    vids = rank.screen_ids(json.loads(next(x.text for x in msg.content if x.type == "text")),
                                           pools[(uid, int(k), lane)])
                except (StopIteration, ValueError):
                    bad += 1
                    continue
                f.write(json.dumps({"id": rid, "vids": vids, "usd": cost, "tok": llm._tokens(msg.usage),
                                    "stop": msg.stop_reason}) + "\n")
        b["collected"], b["usd"] = time.time(), usd
        log(f"{b['id']}: collected, ${usd:.2f}" + (f", {bad} failed (asked again on the next submit)" if bad else ""))
    store.write_json(_dir() / "batches.json", batches)
    return not running


def screen_report(arms=("opus", "sonnet"), passes: int = 3, log=print) -> dict:
    """Per arm: of the songs they went on to like that were in a pool, how many it kept, with a paired bootstrap
    interval against the others; and what a read and an edition cost. "+ graph" is what the edition does
    (rank.screen): rank.SCREEN_PASSES reads taken in turn with the graph's order."""
    from . import rank
    res = _results()

    def liked(l, vids):
        return {l["hits"][v] for v in vids[:rank.SCREEN_K] if v in l["hits"]}

    units = []   # one per song of a window's own that sat in its pools: which arms kept it
    cost = {a: [] for a in arms}
    for w in _windows():
        kept = {"graph": set()} | {f"{a} {x}": set() for a in arms for x in ("x1", f"x{passes}", "+ graph")}
        found, complete = set(), True
        for l in w["lanes"]:
            found |= set(l["hits"].values())
            graph = [c["vid"] for c in l["pool"]]
            kept["graph"] |= liked(l, graph)
            for a in arms:
                reads = [res.get(_request_id(w, l["key"], a, s)) for s in range(passes)]
                if not all(reads):
                    complete = False
                    continue
                cost[a] += [r["usd"] for r in reads]
                kept[f"{a} x1"] |= liked(l, reads[0]["vids"])
                kept[f"{a} x{passes}"] |= liked(l, rank.merge_reads([r["vids"] for r in reads]))
                one = rank.merge_reads([r["vids"] for r in reads[:rank.SCREEN_PASSES]])
                kept[f"{a} + graph"] |= liked(l, rank.with_graph(graph, one))
        if not complete:
            log(f"{w['uid'][:6]} w{w['window']}: some reads have no answer yet")
        own = set(w["own"]) if "own" in w else found
        units += [{"w": f"{w['uid'][:6]}.{w['window']}", "own": v in own, **{name: v in s for name, s in kept.items()}}
                  for v in found]
    later, units = units, [u for u in units if u["own"]]
    if not units:
        log("no song they went on to like sat in a pool: build the windows first")
        return {"units": 0}
    names = ["graph"] + [f"{a} {x}" for a in arms for x in ("x1", f"x{passes}", "+ graph")]
    rng = random.Random(7)
    boot = [[rng.randrange(len(units)) for _ in units] for _ in range(2000)]

    def interval(a, b):
        d = sorted(sum(units[i][a] - units[i][b] for i in idx) for idx in boot)
        return d[50], d[1949]

    out = {"units": len(units), "kept": {n: sum(u[n] for u in units) for n in names},
           "later": len(later), "kept_later": {n: sum(u[n] for u in later) for n in names},
           "per_read_usd": {a: (sum(c) / len(c) if c else None) for a, c in cost.items()}}
    log(f"each window's own likes that sat in its pools: {len(units)} (over {len({u['w'] for u in units})} windows); "
        f"with any later like, {len(later)}")
    for n in names:
        log(f"  {n:16s} kept {out['kept'][n]:3d} of {len(units)}   (any later like: {out['kept_later'][n]} of {len(later)})")
    pairs = [(f"{x} {y}", "graph") for x in arms for y in (f"x{passes}", "+ graph")] \
        + [(f"{x} + graph", f"{x} x{passes}") for x in arms] + [(f"{arms[0]} + graph", f"{x} + graph") for x in arms[1:]]
    for a, b in pairs:
        lo, hi = interval(a, b)
        log(f"  {a} minus {b}: {out['kept'][a] - out['kept'][b]:+d} (95% {lo:+d} to {hi:+d})")
    for a, c in out["per_read_usd"].items():
        if c:
            log(f"  {a}: ${c:.3f} a read at batch prices; an 8-station edition's screen ${c * rank.SCREEN_PASSES * 8:.2f}"
                f" (x{passes}: ${c * passes * 8:.2f})")
    return out
