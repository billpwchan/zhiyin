"""The listener's taste as something a new song can be measured against: how close it sounds to the songs they
love in this lane, and how close it sounds to what they recently skipped or refused."""
from collections import Counter

import numpy as np

from . import audio, settings, signals, store
from .candidates import _years_ago, is_new, score as graph_score
from .text import fold

HALF_LIFE_YEARS = 2.0   # sound preferences move slower than which artists are in rotation
# `zhiyin eval --audio`, 2026-10-25: closeness in sound to older likes separates held-out likes from the engine's own
# candidates only weakly (AUC 0.55-0.61 on random holdouts, 0.52 on the newest likes, where taste is moving). The
# candidates already sound like the listener, so sound is a tie-breaker here; its real jobs are avoidance, variety,
# requests in words and steering.
W_GRAPH, W_AUDIO, W_NEG = 1.0, 0.4, 4.0
W_TEXT = 1.0
NEG_FLOOR = 0.86        # only near-copies of a refused sound are pushed down
MISSING_AUDIO = -0.6    # unknown sound ranks a little below average, never out


class Taste:
    def __init__(self, tracks: list[dict], prof: dict):
        assign = prof.get("assign", {})
        aside = {r for s in prof.get("set_aside", []) for r in s["ranks"]}
        con = store.db()
        nm = settings.not_me()
        likes = [t for t in tracks if not t["long"] and t["rank"] not in aside and not settings.is_not_me(t, nm)]
        u = store.uid()
        app_likes = [dict(r) for r in con.execute("select vid, lane, title from feedback where uid=? and action='like'", (u,))]
        # Refused: "not for me", a thumbs-down on YouTube, a song left within seconds on its own. A skip later on, or
        # one in a run of skips, is about the moment, not the sound (signals.refused).
        negs = signals.refused()
        loves = [r for r in signals.loves() if not settings.is_not_me(r, nm)]
        V = audio.vectors([t["vid"] for t in likes] + [r["vid"] for r in app_likes] + [r["vid"] for r in loves] + list(negs))
        rows, w, lanes, titles = [], [], [], []
        for t in likes:
            if t["vid"] in V:
                rows.append(V[t["vid"]])
                w.append(0.5 ** (_years_ago(t.get("liked_est")) / HALF_LIFE_YEARS))
                lanes.append((assign.get(t["vid"]) or ["none"])[0])
                titles.append(t["title"])
        for r in app_likes:
            if r["vid"] in V:
                rows.append(V[r["vid"]])
                w.append(1.0)
                lanes.append(r["lane"] or "none")
                titles.append(r["title"] or "")
        for r in loves:   # played often without a like
            if r["vid"] in V:
                rows.append(V[r["vid"]])
                w.append(signals.weight(r))
                lanes.append((r.get("lane") or ["none"])[0])
                titles.append(r["title"])
        self.M = audio.unit(np.stack(rows)) if rows else np.zeros((0, audio.DIM))
        self.w = np.array(w)
        self.lane = np.array(lanes)
        self.titles = titles
        self.N = audio.unit(np.stack([V[v] for v in negs if v in V])) if any(v in V for v in negs) else np.zeros((0, audio.DIM))
        self.coverage = len(rows) / max(1, len(likes) + len(app_likes) + len(loves))

    def measure(self, cands: list[dict], lane_key: str) -> None:
        """Adds c["audio"] = {lane, all, neg, near, near_sim} to every candidate that has a vector."""
        V = audio.vectors([c["vid"] for c in cands])
        have = [c for c in cands if c["vid"] in V]
        for c in cands:
            c.pop("audio", None)
        if not have or not len(self.M):
            return
        X = audio.unit(np.stack([V[c["vid"]] for c in have]))
        mask = self.lane == lane_key
        ref, rw = (self.M[mask], self.w[mask]) if mask.sum() >= 5 else (self.M, self.w)
        a_lane = audio.knn(X, ref, rw)
        a_all = audio.knn(X, self.M, self.w)
        sims = X @ ref.T * (0.7 + 0.3 * rw[None, :])
        near = sims.argmax(axis=1)
        ref_titles = [t for t, m in zip(self.titles, mask) if m] if mask.sum() >= 5 else self.titles
        neg = (X @ self.N.T).max(axis=1) if len(self.N) else np.zeros(len(have))
        for i, c in enumerate(have):
            c["audio"] = {"lane": float(a_lane[i]), "all": float(a_all[i]), "neg": float(neg[i]),
                          "near": ref_titles[near[i]], "near_sim": float((X[i] @ ref[near[i]]))}
            c["_v"] = X[i]


def _z(x: np.ndarray) -> np.ndarray:
    sd = x.std()
    return (x - x.mean()) / sd if sd > 1e-9 else np.zeros_like(x)


def rank(lane: dict, cands: list[dict], text_vec: np.ndarray | None = None) -> list[dict]:
    """Blend the YouTube graph's evidence with how the song actually sounds. Sets c["s"] and returns best first.
    With text_vec (a request in words), closeness of the sound to the words counts as much as closeness to likes."""
    if not cands:
        return []
    g = _z(np.array([graph_score(c, lane) for c in cands]))
    has = np.array([bool(c.get("audio")) for c in cands])
    a = np.full(len(cands), MISSING_AUDIO)
    if has.sum() >= 5:
        a[has] = _z(np.array([c["audio"]["lane"] for c in cands if c.get("audio")]))
    pen = np.array([max(0.0, c["audio"]["neg"] - NEG_FLOOR) if c.get("audio") else 0.0 for c in cands])
    s = W_GRAPH * g + W_AUDIO * a - W_NEG * pen
    if text_vec is not None and has.sum() >= 5:
        tv = audio.unit(text_vec)
        ts = np.array([float(c["_v"] @ tv) for c in cands if c.get("audio")])
        tz = np.full(len(cands), MISSING_AUDIO)
        tz[has] = _z(ts)
        s = s + W_TEXT * tz
    for c, v, pa in zip(cands, s, np.where(has, a, np.nan)):
        c["s"] = float(v)
        if c.get("audio"):
            c["audio"]["z"] = float(pa)
    return sorted(cands, key=lambda c: -c["s"])


def select(lane: dict, ranked: list[dict], k: int = 32, lam: float = 0.78) -> list[dict]:
    """Greedy MMR on sound, under the lane's familiar/new quota and two songs per artist: a shortlist that covers
    the lane instead of ten near-identical tracks."""
    n_new = max(1, round(k * lane.get("discovery", 0.4)))
    quota = {True: n_new, False: k - n_new}
    taken = {True: 0, False: 0}
    per_artist = Counter()
    out, chosen_v = [], []
    pool = list(ranked)
    while pool and len(out) < k:
        best, best_val = None, -1e9
        for c in pool:
            new = is_new(c)
            if taken[new] >= quota[new] or per_artist[fold(c["artists"][0]["name"])] >= 2:
                continue
            red = 0.0
            if chosen_v and c.get("_v") is not None:
                red = max(float(c["_v"] @ v) for v in chosen_v)
            val = lam * c["s"] - (1 - lam) * 4.0 * max(0.0, red - 0.75)
            if val > best_val:
                best, best_val = c, val
        if best is None:
            break
        pool.remove(best)
        out.append(best)
        taken[is_new(best)] += 1
        per_artist[fold(best["artists"][0]["name"])] += 1
        if best.get("_v") is not None:
            chosen_v.append(best["_v"])
    for c in pool:  # quotas could not be met: fill by score
        if len(out) >= k:
            break
        out.append(c)
    return out
