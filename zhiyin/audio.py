"""What songs sound like. Each track's 30-second preview (Deezer first, the iTunes store as fallback) is embedded
with MuQ-MuLan, which puts audio and text in one 512-d space: "sounds like the songs you love" and "quieter" are
both cosine similarities. Previews are decoded in memory and discarded; only the vector is kept.

The model needs torch and ~3 GB of memory, so embedding runs in a child process (`python -m zhiyin.audio`)
that exits when done; everything else here is numpy and safe to import in the server."""
import base64
import fcntl
import json
import os
import re
import subprocess
import sys
import threading
import time

import httpx
import numpy as np

from . import store
from .lyrics import VERSION, _artist_sim, _score, _sim, _t2s
from .text import display_title

SR = 24000
CLIP_S = 29
DIM = 512
MIN_MATCH = 0.72
RETRY_MISS_DAYS = 30
ITUNES_PER_RUN = int(os.environ.get("ZHIYIN_ITUNES_BUDGET", 80))  # Apple allows ~20 searches a minute; misses beyond this wait for the next run
# The server has no room for the model. There, ensure() only queues what it wants heard; `zhiyin worker` on the
# Mac embeds it and sends the vectors back. Vectors belong to songs, not listeners, so one Mac serves everyone.
REMOTE = os.environ.get("ZHIYIN_AUDIO") == "remote"
WORKER_FRESH_S = 900
UA = {"User-Agent": "zhiyin/0.1 (personal player)"}

# Directions in the shared space used to steer a queue. Each pair is (towards, away from).
AXES = {
    "energy": ("energetic upbeat danceable song with strong drums, 节奏强烈 带劲的歌", "quiet calm slow gentle ballad, 安静 舒缓的慢歌"),
    "vocal": ("song with prominent lead vocals, 人声为主", "instrumental music with no vocals, 纯音乐 没有人声"),
}


def _db():
    con = store.db()
    con.execute("create table if not exists audio(vid text primary key, src text, ref text, score real, emb blob, ts real)")
    con.execute("create table if not exists textemb(text text primary key, emb blob)")
    con.execute("create table if not exists audio_wanted(vid text primary key, item text, ts real)")
    con.execute("create table if not exists text_wanted(text text primary key, ts real)")
    return con


# ---------- reading vectors (server side) ----------

def vectors(vids) -> dict[str, np.ndarray]:
    vids = list(dict.fromkeys(vids))
    out = {}
    con = _db()
    for i in range(0, len(vids), 500):
        chunk = vids[i:i + 500]
        q = f"select vid, emb from audio where emb is not null and vid in ({','.join('?' * len(chunk))})"
        for r in con.execute(q, chunk):
            out[r["vid"]] = np.frombuffer(r["emb"], dtype=np.float16).astype(np.float32)
    return out


def alias(vid: str, same_as: str) -> None:
    """Another video of the same recording shares its vector."""
    con = _db()
    con.execute("insert or ignore into audio select ?, src, ref, score, emb, ts from audio where vid=?", (vid, same_as))
    con.commit()


def text_vectors() -> dict[str, np.ndarray]:
    return {r["text"]: np.frombuffer(r["emb"], dtype=np.float16).astype(np.float32)
            for r in _db().execute("select text, emb from textemb")}


def missing(tracks: list[dict]) -> list[dict]:
    """Tracks with no vector and no recent failed attempt."""
    con = _db()
    cutoff = time.time() - RETRY_MISS_DAYS * 86400
    have = {}
    vids = [t["vid"] for t in tracks]
    for i in range(0, len(vids), 500):
        chunk = vids[i:i + 500]
        for r in con.execute(f"select vid, emb is not null as ok, ts from audio where vid in ({','.join('?' * len(chunk))})", chunk):
            have[r["vid"]] = r["ok"] or r["ts"] > cutoff
    seen, out = set(), []
    for t in tracks:
        if t["vid"] not in seen and not have.get(t["vid"]):
            seen.add(t["vid"])
            out.append(t)
    return out


def ensure(tracks: list[dict], log=print, timeout: int = 1800, itunes_budget: int | None = None,
           texts: list[str] = ()) -> dict:
    """Embed whatever lacks a vector (and any new text prompts), in a child process. Returns its summary."""
    todo = missing(tracks)
    have = set(text_vectors())
    texts = [x for x in texts if x not in have]
    if not todo and not texts:
        return {"todo": 0}
    payload = [{"vid": t["vid"], "title": t.get("title") or "", "artists": [a["name"] if isinstance(a, dict) else a for a in t.get("artists") or []],
                "dur": t.get("dur") or 0, "type": t.get("type") or ""} for t in todo]
    if REMOTE:
        con = _db()
        con.executemany("insert or ignore into audio_wanted values (?, ?, ?)",
                        [(t["vid"], json.dumps(t, ensure_ascii=False), time.time()) for t in payload])
        con.executemany("insert or ignore into text_wanted values (?, ?)", [(x, time.time()) for x in texts])
        con.commit()
        log(f"{len(payload)} 首交给 Mac 试听")
        return {"todo": len(payload), "queued": True}
    log(f"试听 {len(payload)} 首新歌")
    payload = {"tracks": payload, "texts": list(texts)}
    env = {**os.environ, **({"ZHIYIN_ITUNES_BUDGET": str(itunes_budget)} if itunes_budget is not None else {})}
    p = subprocess.run([sys.executable, "-m", "zhiyin.audio"], input=json.dumps(payload), capture_output=True,
                       text=True, timeout=timeout, cwd=store.ROOT, env=env)
    if p.returncode != 0:
        raise RuntimeError(f"audio embedding failed: {p.stderr[-800:]}")
    return json.loads(p.stdout.strip().splitlines()[-1])


def worker_online() -> bool:
    return time.time() - store.kv_get("worker_seen", 0) < WORKER_FRESH_S


def wanted(limit: int = 150) -> dict:
    store.kv_set("worker_seen", time.time())
    con = _db()
    texts = [r["text"] for r in con.execute("select text from text_wanted order by ts")]
    tracks = [json.loads(r["item"]) for r in con.execute("select item from audio_wanted order by ts limit ?", (limit,))]
    return {"tracks": tracks, "texts": texts}


def accept(rows: list[dict], texts: list[dict]) -> int:
    """Vectors (or recorded misses) sent back by the worker."""
    store.kv_set("worker_seen", time.time())
    con = _db()
    dec = lambda b: base64.b64decode(b) if b else None  # noqa: E731
    con.executemany("insert or replace into audio values (?,?,?,?,?,?)",
                    [(r["vid"], r.get("src"), r.get("ref"), r.get("score"), dec(r.get("emb")), r.get("ts") or time.time()) for r in rows])
    con.executemany("insert or replace into textemb values (?,?)", [(t["text"], dec(t["emb"])) for t in texts if t.get("emb")])
    con.executemany("delete from audio_wanted where vid=?", [(r["vid"],) for r in rows])
    con.executemany("delete from text_wanted where text=?", [(t["text"],) for t in texts])
    con.commit()
    return sum(1 for r in rows if r.get("emb"))


def rows_for(vids: list[str], texts: list[str]) -> tuple[list[dict], list[dict]]:
    """What the worker sends back: one row per song it tried, misses included so the server stops asking."""
    con = _db()
    enc = lambda b: base64.b64encode(b).decode() if b else None  # noqa: E731
    out = []
    for i in range(0, len(vids), 500):
        chunk = vids[i:i + 500]
        for r in con.execute(f"select * from audio where vid in ({','.join('?' * len(chunk))})", chunk):
            out.append({"vid": r["vid"], "src": r["src"], "ref": r["ref"], "score": r["score"], "emb": enc(r["emb"]), "ts": r["ts"]})
    tv = [{"text": r["text"], "emb": enc(r["emb"])} for r in con.execute(
        f"select * from textemb where text in ({','.join('?' * len(texts))})", texts)] if texts else []
    return out, tv


def wait_text(text: str, timeout: float = 45) -> np.ndarray | None:
    """A request in words needs the model too. Wait for the worker briefly when it is around."""
    end = time.time() + timeout
    while True:
        v = text_vectors().get(text)
        if v is not None or not REMOTE or not worker_online() or time.time() > end:
            return v
        time.sleep(3)


# ---------- taste maths (numpy only) ----------

def unit(m: np.ndarray) -> np.ndarray:
    return m / np.maximum(np.linalg.norm(m, axis=-1, keepdims=True), 1e-8)


def knn(cands: np.ndarray, ref: np.ndarray, weights: np.ndarray | None = None, k: int = 5) -> np.ndarray:
    """Mean of the k highest (weighted) similarities to a set of reference songs. One centroid would blur a lane
    that holds two sounds; the nearest few keep each of them."""
    if len(ref) == 0 or len(cands) == 0:
        return np.zeros(len(cands))
    s = unit(cands) @ unit(ref).T
    if weights is not None:
        s = s * (0.7 + 0.3 * weights[None, :])
    k = min(k, s.shape[1])
    return np.sort(s, axis=1)[:, -k:].mean(axis=1)


def axis_scores(m: np.ndarray) -> dict[str, np.ndarray]:
    tv = text_vectors()
    out = {}
    for name, (pos, neg) in AXES.items():
        if pos in tv and neg in tv:
            out[name] = unit(m) @ unit(tv[pos]) - unit(m) @ unit(tv[neg])
    return out


def pack(v: np.ndarray, basis: np.ndarray, scale: float) -> str:
    """A compact int8 projection of a vector for the page, enough for in-session similarity."""
    q = np.clip(np.round((unit(v) @ basis.T) / scale * 127), -127, 127).astype(np.int8)
    return base64.b64encode(q.tobytes()).decode()


def basis(m: np.ndarray, dims: int = 48) -> tuple[np.ndarray, float]:
    x = unit(m)
    x = x - x.mean(axis=0)
    _, _, vt = np.linalg.svd(x, full_matrices=False)
    b = vt[:dims]
    scale = float(np.abs(unit(m) @ b.T).max()) or 1.0
    return b, scale


# ---------- finding previews ----------

class Unavailable(Exception):
    """The service is rate-limiting or down: try this track again next run instead of recording a miss."""


class Pace:
    """A minimum gap between calls, shared by every process on the machine (the daily build and a manual run can
    overlap, and the services count requests per address)."""

    def __init__(self, name, gap):
        self.gap, self.lock = gap, threading.Lock()
        self.path = store.CACHE / f"{name}.pace"

    def wait(self):
        with self.lock, open(self.path, "a+") as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            f.seek(0)
            try:
                last = float(f.read() or 0)
            except ValueError:
                last = 0.0
            d = last + self.gap - time.time()
            if d > 0:
                time.sleep(d)
            f.seek(0)
            f.truncate()
            f.write(str(time.time()))


_deezer = Pace("deezer", 0.12)
_itunes = Pace("itunes", 3.1)


def _get(url, params, pace, tries=4):
    for k in range(tries):
        pace.wait()
        try:
            r = httpx.get(url, params=params, headers=UA, timeout=12)
            limited = r.status_code in (403, 429) or r.status_code >= 500 or (
                r.status_code == 200 and isinstance(r.json(), dict) and (r.json().get("error") or {}).get("code") == 4)
            if limited:
                time.sleep(4 * (k + 1))
                continue
            return r.json() if r.status_code == 200 else None
        except (httpx.HTTPError, ValueError):
            time.sleep(1 + k)
    raise Unavailable(url)


DUR_TOL = 10   # the same recording differs by a few seconds of silence between platforms; a preview needs no more


def _titles(t):
    """The title as shown, plus a Latin gloss YouTube Music appends to some CJK titles (きらり - Kirari)."""
    shown = display_title(t["title"], [{"name": a} for a in t["artists"]])
    out = [shown]
    m = re.search(r"\s[-–]\s*([A-Za-z][\w' .!?&]+)$", t["title"])
    if m and m.group(1).strip().lower() != shown.lower():
        out.append(m.group(1).strip())
    return out


def _best(t, items):
    titles = _titles(t)
    best = (0.0, None)
    for pos, it in enumerate(items):
        diff = abs(t["dur"] - it["dur"]) if t.get("dur") and it.get("dur") else None
        if diff is not None and diff > DUR_TOL and t.get("type") != "OMV":   # music videos run longer than the record
            continue
        sc = max(_score(x, t["artists"], 0, it["title"], it["artist"], 0) for x in titles)
        if diff is not None and t.get("type") != "OMV":
            sc -= 0.03 * max(0.0, diff - 3)
        same_len = diff is not None and diff <= 1.5
        clean = not VERSION.search(it["title"] or "")
        # Stores often file Cantonese and Mandarin songs under an English title. Same artist, same length to the
        # second and near the top of a search that named the song is the same recording.
        if sc < MIN_MATCH and pos < 3 and same_len and clean and _artist_sim(t["artists"], it["artist"]) >= 0.95:
            sc = 0.75
        # The reverse: stores list the artist under another name (陳奕迅 / Eason Chan, Nancy Kwai / 歸綽嶢).
        if (sc < MIN_MATCH and pos < 3 and same_len and clean and t.get("type") != "UGC"
                and max(_sim(x, it["title"] or "") for x in titles) >= 0.9):
            sc = 0.74
        if sc > best[0]:
            best = (sc, it)
    return best


def _queries(t):
    artist = t["artists"][0] if t["artists"] else ""
    out = []
    for title in _titles(t):
        title = re.sub(r"[\(\[（【].*?[\)\]）】]|\b(feat|ft)\..*$", "", title, flags=re.I).strip() or title
        out += [f"{artist} {title}".strip(), _t2s.convert(f"{artist} {title}".strip())]
    return list(dict.fromkeys(out))


def find_deezer(t):
    best = (0.0, None)
    for q in _queries(t):
        d = _get("https://api.deezer.com/search", {"q": q, "limit": 10}, _deezer) or {}
        items = [{"title": x.get("title"), "artist": (x.get("artist") or {}).get("name", ""), "dur": x.get("duration") or 0,
                  "preview": x.get("preview"), "ref": f"deezer:{x.get('id')}"} for x in d.get("data") or [] if x.get("preview")]
        sc, it = _best(t, items)
        if sc > best[0]:
            best = (sc, it)
        if best[0] >= 0.9:
            break
    return best


def find_itunes(t):
    term = _queries(t)[0]
    text = t["title"] + " ".join(t["artists"])
    if re.search(r"[\u3040-\u30ff]", text):
        stores = ("JP", "HK")
    elif re.search(r"[\uac00-\ud7af]", text) or not re.search(r"[\u4e00-\u9fff]", text):
        stores = ("US", "HK")
    else:
        stores = ("HK", "TW")
    for store_ in stores:
        d = _get("https://itunes.apple.com/search", {"term": term, "country": store_, "media": "music", "entity": "song", "limit": 8}, _itunes) or {}
        items = [{"title": x.get("trackName"), "artist": x.get("artistName", ""), "dur": (x.get("trackTimeMillis") or 0) / 1000,
                  "preview": x.get("previewUrl"), "ref": f"itunes:{x.get('trackId')}"} for x in d.get("results") or [] if x.get("previewUrl")]
        sc, it = _best(t, items)
        if sc >= MIN_MATCH:
            return sc, it
    return 0.0, None


def decode(url: str) -> np.ndarray | None:
    try:
        r = httpx.get(url, headers=UA, timeout=20, follow_redirects=True)
        r.raise_for_status()
    except httpx.HTTPError:
        return None
    p = subprocess.run(["ffmpeg", "-v", "error", "-i", "pipe:0", "-ac", "1", "-ar", str(SR), "-f", "f32le", "pipe:1"],
                       input=r.content, capture_output=True)
    if p.returncode != 0:
        return None
    x = np.frombuffer(p.stdout, dtype=np.float32)
    return x if len(x) > SR * 10 else None


# ---------- embedding (child process) ----------

def _load_model():
    import torch
    from muq import MuQMuLan
    m = MuQMuLan.from_pretrained("OpenMuQ/MuQ-MuLan-large").eval()
    dev = "mps" if torch.backends.mps.is_available() else "cpu"
    m = m.to(dev)
    # weight-norm convolutions keep plain tensor attributes that .to() does not move
    for mod in m.modules():
        for k, v in list(vars(mod).items()):
            if isinstance(v, torch.Tensor) and v.device.type != dev:
                setattr(mod, k, v.to(dev))
    return m, dev


def _main():
    import concurrent.futures as cf

    import torch
    req = json.loads(sys.stdin.read())
    tracks, extra_texts = (req, []) if isinstance(req, list) else (req["tracks"], req.get("texts", []))
    con = _db()
    model, dev = _load_model()
    stats = {"todo": len(tracks), "deezer": 0, "itunes": 0, "miss": 0, "later": 0}

    def via_deezer(t):
        try:
            sc, it = find_deezer(t)
        except Unavailable:
            return t, None, None, 0.0, None
        if sc < MIN_MATCH or not it:
            return t, None, None, sc, None
        return t, "deezer", it["ref"], sc, decode(it["preview"])

    def via_itunes(t):
        try:
            sc, it = find_itunes(t)
        except Unavailable:
            return t, "later", None, 0.0, None
        if sc < MIN_MATCH or not it:
            return t, "itunes", None, sc, None
        return t, "itunes", it["ref"], sc, decode(it["preview"])

    def flush(batch):
        n = CLIP_S * SR
        x = np.stack([np.pad(w[:n], (0, max(0, n - len(w[:n])))) for _, _, _, _, w in batch])
        with torch.no_grad():
            e = model(wavs=torch.tensor(x).to(dev)).float().cpu().numpy()
        e = unit(e).astype(np.float16)
        con.executemany("insert or replace into audio values (?,?,?,?,?,?)",
                        [(t["vid"], src, ref, sc, e[i].tobytes(), time.time()) for i, (t, src, ref, sc, _) in enumerate(batch)])
        con.commit()

    def drain(results, retry):
        batch = []
        for t, src, ref, sc, wav in results:
            if wav is None:
                if retry is not None:
                    retry.append(t)
                elif src == "later":
                    stats["later"] += 1
                else:
                    stats["miss"] += 1
                    con.execute("insert or replace into audio values (?,?,?,?,?,?)", (t["vid"], src, ref, sc, None, time.time()))
                    con.commit()
                continue
            stats[src] += 1
            batch.append((t, src, ref, sc, wav))
            if len(batch) == 8:
                flush(batch)
                batch = []
        if batch:
            flush(batch)
        con.commit()

    # Deezer first for everything (fast), then the rate-limited iTunes store for what Deezer lacks, one at a time.
    second = []
    with cf.ThreadPoolExecutor(6) as ex:
        drain(ex.map(via_deezer, tracks), second)
    budget = ITUNES_PER_RUN
    stats["later"] = max(0, len(second) - budget)
    drain(map(via_itunes, second[:budget]), None)

    have = {r["text"] for r in con.execute("select text from textemb")}
    texts = [x for x in [x for pair in AXES.values() for x in pair] + list(extra_texts) if x not in have]
    if texts:
        with torch.no_grad():
            e = unit(model(texts=texts).float().cpu().numpy()).astype(np.float16)
        con.executemany("insert or replace into textemb values (?,?)", [(x, e[i].tobytes()) for i, x in enumerate(texts)])
        con.commit()
    print(json.dumps(stats))


if __name__ == "__main__":
    _main()
