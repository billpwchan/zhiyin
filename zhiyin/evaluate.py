"""Time-split check: hide the newest likes, rebuild candidates from older likes only, count how many hidden likes
(or their artists) the engine would have surfaced. Compared with a plain 'radio from your latest likes' baseline,
which is roughly what YouTube Music itself does."""
import random
from collections import Counter

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
