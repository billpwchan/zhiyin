"""Synced lyrics for whatever is playing, matched by title, artist and duration.

Sources, best first: NetEase (word timing, a Chinese translation line for Japanese/Korean/English, credits),
LRCLIB (line timing), YouTube Music's own timed lyrics (line timing, same catalogue we play from).
Lyrics are only cached locally and shown in the player; nothing is redistributed."""
import concurrent.futures as cf
import contextvars
import difflib
import json
import re
import threading
import time
import unicodedata
from pathlib import Path

import httpx
import opencc

from . import llm, store, ytm

CACHE = store.CACHE / "lyrics"
CACHE.mkdir(parents=True, exist_ok=True)
MISS_TTL = 7 * 86400
UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/141 Safari/537.36"}
NE = {**UA, "Referer": "https://music.163.com"}
LRCLIB = {"User-Agent": "zhiyin/0.1 (personal player)", "Lrclib-Client": "zhiyin/0.1"}
DUR_TOL = 4.0
MIN_SCORE = 0.6

_t2s = opencc.OpenCC("t2s")
_s2hk = opencc.OpenCC("s2hk")
_s2tw = opencc.OpenCC("s2tw")
_s2t_std = opencc.OpenCC("s2t")
_inflight: dict[str, threading.Event] = {}
_lock = threading.Lock()

CREDIT = re.compile(r"^\s*(作词|作詞|作曲|编曲|編曲|制作人|製作人|监制|監製|词|詞|曲|演唱|原唱|和声|和聲|混音|母带|录音|吉他|贝斯|鼓|钢琴|弦乐|Lyrics?|Composer|Composed by|Arranger|Arranged by|Producer|Produced by|Written by)\s*[:：]\s*(.+)$", re.I)
# a section heading some uploaders time like a line ("hook", "[Chorus]", "副歌：")
SECTION = re.compile(r"^\s*[\[(（【]?\s*(hook|verse|chorus|pre-?chorus|post-?chorus|bridge|intro|outro|refrain|interlude|rap|"
                     r"副歌|主歌|前奏|间奏|間奏|尾奏|桥段|橋段|导歌|導歌|说唱|說唱)\s*\d*\s*[\])）】]?\s*[:：]?\s*$", re.I)
LRC_TS = re.compile(r"\[(\d+):(\d+(?:\.\d+)?)\]")
YRC_LINE = re.compile(r"^\[(\d+),(\d+)\](.*)$")
YRC_WORD = re.compile(r"\((\d+),(\d+),\d+\)")
# whole words only: "Love Instantly", "Alive" and "Discover" are not versions
VERSION = re.compile(r"(?<![a-z])(?:live|remix\w*|karaoke|inst(?:rumental)?|cover|dj|demo|acoustic)(?![a-z])|伴奏|纯音乐|純音樂|翻唱|現場|现场",
                     re.I)
SHOW_ROLES = {"作词": "作词", "作詞": "作词", "词": "作词", "詞": "作词", "作曲": "作曲", "曲": "作曲",
              "编曲": "编曲", "編曲": "编曲", "制作人": "制作", "製作人": "制作", "监制": "监制", "監製": "监制"}


def norm(s: str) -> str:
    s = _t2s.convert(unicodedata.normalize("NFKC", s or "")).lower()
    s = re.sub(r"[\(\[（【「『].*?[\)\]）】」』]", "", s)
    s = re.sub(r"\b(feat|ft|prod)\.?\b.*$", "", s)
    return re.sub(r"[\s\W_]+", "", s)


def _sim(a: str, b: str) -> float:
    a, b = norm(a), norm(b)
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    if len(a) >= 2 and len(b) >= 2 and (a in b or b in a):
        return 0.9
    return difflib.SequenceMatcher(None, a, b).ratio()


def _artist_sim(names: list[str], cand: str) -> float:
    parts = [p for p in re.split(r"[,、/&;]|feat\.?|ft\.?", cand or "") if p.strip()] or [cand]
    return max((_sim(n, p) for n in names for p in parts), default=0.0)


def _score(title: str, artists: list[str], dur: float, c_title: str, c_artist: str, c_dur: float) -> float:
    if dur and c_dur and abs(dur - c_dur) > DUR_TOL:
        return 0.0
    if VERSION.search(c_title or "") and not VERSION.search(title or ""):
        return 0.0
    t = _sim(title, c_title)
    s = 0.5 * t + 0.5 * _artist_sim(artists, c_artist)
    return s - 0.35 if t < 0.3 else s


def _lang(text: str) -> str:
    if re.search(r"[぀-ヿ]", text):
        return "ja"
    if re.search(r"[가-힯]", text):
        return "ko"
    cjk = len(re.findall(r"[一-鿿]", text))
    latin = len(re.findall(r"[A-Za-z]", text))
    return "en" if latin > 3 * cjk + 20 else "zh"


# ---------- parsing ----------

def parse_lrc(text: str) -> list[dict]:
    out = []
    for raw in (text or "").splitlines():
        if raw.lstrip().startswith("{"):
            continue
        stamps = LRC_TS.findall(raw)
        if not stamps:
            continue
        body = LRC_TS.sub("", raw).strip()
        for m, s in stamps:
            out.append({"t": int(m) * 60 + float(s), "x": body})
    out.sort(key=lambda l: l["t"])
    return out


def parse_yrc(text: str) -> list[dict]:
    out = []
    for raw in (text or "").splitlines():
        m = YRC_LINE.match(raw.strip())
        if not m:
            continue
        start, dur, body = int(m.group(1)) / 1000, int(m.group(2)) / 1000, m.group(3)
        parts = YRC_WORD.split(body)
        words = []
        for i in range(1, len(parts) - 2, 3):
            ws, wd, w = int(parts[i]) / 1000, int(parts[i + 1]) / 1000, parts[i + 2]
            if w:
                words.append([round(ws, 3), round(wd, 3), w])
        x = "".join(w[2] for w in words).strip()
        if x:
            out.append({"t": start, "e": round(start + dur, 3), "x": x, "w": words})
    return out


def credits_from_json_lines(text: str) -> list[list[str]]:
    out = []
    for raw in (text or "").splitlines():
        if not raw.lstrip().startswith("{"):
            continue
        try:
            c = "".join(x.get("tx", "") for x in json.loads(raw).get("c", []))
        except (json.JSONDecodeError, AttributeError):
            continue
        m = CREDIT.match(c)
        if m:
            out.append([m.group(1), m.group(2).strip()])
    return out


def split_credits(lines: list[dict]) -> tuple[list[dict], list[list[str]]]:
    """NetEase and many LRCs open with '作词 : X' lines; they are credits, not lyrics."""
    credits, keep = [], []
    for i, l in enumerate(lines):
        m = CREDIT.match(l["x"]) if i < 14 else None
        if m:
            credits.append([m.group(1), m.group(2).strip()])
        else:
            keep.append(l)
    return keep, credits


def attach(lines: list[dict], extra: list[dict], key: str, tol: float = 1.2) -> int:
    """Pin translation/romanisation lines to the original line closest in time (indexes drift between files)."""
    n = 0
    if not extra:
        return 0
    starts = [l["t"] for l in lines]
    for e in extra:
        if not e["x"] or CREDIT.match(e["x"]):
            continue
        j = min(range(len(starts)), key=lambda k: abs(starts[k] - e["t"]), default=None)
        if j is not None and abs(starts[j] - e["t"]) <= tol and not lines[j].get(key):
            lines[j][key] = e["x"]
            n += 1
    return n


# ---------- sources ----------

def _get(url, params, headers, tries=3):
    for k in range(tries):
        try:
            r = httpx.get(url, params=params, headers=headers, timeout=10, follow_redirects=True)
            if r.status_code in (429, 503):
                time.sleep(1 + k)
                continue
            return r
        except httpx.HTTPError:
            time.sleep(0.5 + k)
    return None


def netease(title, artists, album, dur):
    # api/search/get answers a server outside China with unrelated songs (2026-10-30: 富士山下 found nothing);
    # cloudsearch/pc returns the real catalogue
    r = _get("https://music.163.com/api/cloudsearch/pc", {"s": f"{artists[0] if artists else ''} {title}", "type": 1, "limit": 12}, NE)
    if not r or r.status_code != 200:
        return None
    songs = (r.json().get("result") or {}).get("songs") or []
    ranked = sorted(((_score(title, artists, dur, s.get("name"), "/".join(a.get("name", "") for a in s.get("ar", [])),
                             (s.get("dt") or 0) / 1000), s) for s in songs), key=lambda x: -x[0])
    for sc, s in ranked[:3]:
        if sc < MIN_SCORE:
            break
        lr = _get("https://music.163.com/api/song/lyric/v1",
                  {"id": s["id"], "lv": 1, "tv": 1, "rv": 1, "yv": 1, "ytv": 1, "yrv": 1}, NE)
        if not lr or lr.status_code != 200:
            continue
        d = lr.json()
        if d.get("pureMusic"):
            return {"source": "网易云音乐", "instrumental": True, "score": sc}
        lrc = (d.get("lrc") or {}).get("lyric") or ""
        yrc = (d.get("yrc") or {}).get("lyric") or ""
        lines = parse_yrc(yrc) or parse_lrc(lrc)
        if not lines:
            continue
        credits = credits_from_json_lines(yrc) + credits_from_json_lines(lrc)
        lines, more = split_credits(lines)
        credits += more
        attach(lines, parse_lrc((d.get("tlyric") or {}).get("lyric")), "tr")
        attach(lines, parse_lrc((d.get("romalrc") or {}).get("lyric")), "ro")
        return {"source": "网易云音乐", "lines": lines, "credits": credits, "score": round(sc, 2),
                "words": bool(yrc and lines and lines[0].get("w"))}
    return None


def lrclib(title, artists, album, dur):
    params = {"track_name": title, "artist_name": artists[0] if artists else ""}
    hits = []
    if dur:
        r = _get("https://lrclib.net/api/get", {**params, "duration": round(dur)}, LRCLIB)
        if r is not None and r.status_code == 200:
            hits = [r.json()]
    if not hits:
        r = _get("https://lrclib.net/api/search", params, LRCLIB)
        if r is not None and r.status_code == 200:
            hits = r.json() or []
    best = None
    for h in hits:
        if not h.get("syncedLyrics") and not h.get("instrumental"):
            continue
        sc = _score(title, artists, dur, h.get("trackName"), h.get("artistName"), h.get("duration") or 0)
        if sc >= MIN_SCORE and (not best or sc > best[0]):
            best = (sc, h)
    if not best:
        return None
    sc, h = best
    if h.get("instrumental"):
        return {"source": "LRCLIB", "instrumental": True, "score": sc}
    lines, credits = split_credits(parse_lrc(h["syncedLyrics"]))
    return {"source": "LRCLIB", "lines": lines, "credits": credits, "score": round(sc, 2), "words": False}


def youtube(vid):
    try:
        yt = ytm.client()
        bid = yt.get_watch_playlist(videoId=vid, limit=1).get("lyrics")
        if not bid:
            return None
        res = yt.get_lyrics(bid, timestamps=True)
    except Exception:
        return None
    if not res or not res.get("hasTimestamps"):
        return None
    lines = [{"t": l.start_time / 1000, "e": l.end_time / 1000, "x": (l.text or "").strip()} for l in res["lyrics"]]
    lines, credits = split_credits(lines)
    src = re.sub(r"^.*?[:：]\s*", "", res.get("source") or "").strip() or "YouTube Music"
    return {"source": src, "lines": lines, "credits": credits, "score": 1.0, "words": False}


# ---------- assembly ----------

def _script_like_title(lines: list[dict], shown: str):
    """Show Chinese lyrics in the script the song is shown in (title, artist, album as YouTube Music gives them to
    this listener), down to the Hong Kong or Taiwan variant of each character. Text with no telling characters
    gets Traditional (Taiwan) forms, matching the zh_TW reading in ytm.client."""
    simplified = _s2t_std.convert(shown) != shown
    if simplified and _t2s.convert(shown) == shown:
        return None
    conv = _s2hk if _s2hk.convert(_t2s.convert(shown)) == shown and _s2tw.convert(_t2s.convert(shown)) != shown else _s2tw
    for l in lines:
        l["x"] = conv.convert(l["x"])
        for w in l.get("w") or []:
            w[2] = conv.convert(w[2])
    return conv


def _credits(raw: list[list[str]]) -> list[list[str]]:
    out, seen = [], set()
    for role, name in raw:
        r = SHOW_ROLES.get(role)
        if r and r not in seen:
            seen.add(r)
            out.append([r, name])
    return out


_pool = cf.ThreadPoolExecutor(6)


def resolve(vid: str, title: str, artists: list[str], album: str, dur: float) -> dict:
    # All sources start at once; take the first in priority order that has lyrics, without waiting for the rest.
    futures = [_pool.submit(netease, title, artists, album, dur), _pool.submit(lrclib, title, artists, album, dur),
               _pool.submit(youtube, vid)]
    found = None
    for f in futures:
        try:
            found = f.result(timeout=25)
        except Exception:
            found = None
        if found:
            break
    if not found:
        return {"vid": vid, "found": False, "ts": time.time()}
    if found.get("instrumental"):
        return {"vid": vid, "found": False, "instrumental": True, "source": found["source"], "ts": time.time()}
    lines = [l for l in found["lines"] if l["t"] <= (dur or 1e9) + 5]
    body = " ".join(l["x"] for l in lines)
    lang = _lang(body)
    conv = _script_like_title(lines, " ".join([title, *artists, album or ""])) if lang == "zh" else None
    credits = _credits(found.get("credits", []))
    if conv:
        credits = [[role, conv.convert(name)] for role, name in credits]
    # Lines that are empty mark instrumental breaks; collapse repeats so the player shows one break, not several.
    clean = []
    for l in lines:
        if not l["x"] and clean and not clean[-1]["x"]:
            continue
        clean.append(l)
    while clean and not clean[-1]["x"]:
        clean.pop()
    return {"vid": vid, "found": bool(clean), "source": found["source"], "lang": lang, "words": found.get("words", False),
            "translated": any(l.get("tr") for l in clean), "credits": credits,
            "lines": [{k: (round(v, 3) if isinstance(v, float) else v) for k, v in l.items()} for l in clean],
            "ts": time.time()}


def _path(vid: str) -> Path:
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", vid):
        raise ValueError(f"not a video id: {vid!r}")
    return CACHE / f"{vid}.json"


def _fresh(d: dict) -> bool:
    return bool(d.get("found")) or time.time() - d.get("ts", 0) < MISS_TTL


def cached(vid: str) -> bool:
    """get() would answer from disk without asking anyone."""
    path = _path(vid)
    return path.exists() and _fresh(json.loads(path.read_text()))


RECHECK_BEFORE = 1793348400   # 2026-10-30 08:20 UTC: until then NetEase was searched where it mostly misses (eaf358f)
_rechecking: set[str] = set()


def _recheck_later(vid: str, title: str, artists: list[str], album: str, dur: float) -> None:
    """Lyrics found back when NetEase was searched badly usually lack its word timing. Asked for again, they are
    shown as they are and looked up once more behind the scenes; a word-timed find replaces them for next time."""
    if vid in _rechecking:
        return
    _rechecking.add(vid)

    def run():
        try:
            new = resolve(vid, title, artists, album, dur)
            cur = json.loads(_path(vid).read_text())
            out = new if new.get("found") and new.get("words") else {**cur, "rechecked": time.time()}
            store.write_json(_path(vid), out)
        except Exception:
            pass
        finally:
            _rechecking.discard(vid)
    threading.Thread(target=run, daemon=True).start()


def get(vid: str, title: str, artists: list[str], album: str = "", dur: float = 0) -> dict:
    path = _path(vid)
    if path.exists():
        d = json.loads(path.read_text())
        if _fresh(d):
            if d.get("found") and not d.get("words") and not d.get("rechecked") and d.get("ts", 0) < RECHECK_BEFORE:
                _recheck_later(vid, title, artists, album, dur)
            return d
    with _lock:
        ev = _inflight.get(vid)
        mine = ev is None
        if mine:
            ev = _inflight[vid] = threading.Event()
    if not mine:
        ev.wait(30)
        return json.loads(path.read_text()) if path.exists() else {"vid": vid, "found": False}
    try:
        d = resolve(vid, title, artists, album, dur)
        store.write_json(path, d)
        return d
    finally:
        ev.set()
        with _lock:
            _inflight.pop(vid, None)


# ---------- translation for songs no source translates ----------

TR_SCHEMA = {"type": "object", "properties": {"lines": {"type": "array", "items": {"type": "object", "properties": {
    "i": {"type": "integer"}, "tr": {"type": "string"}}, "required": ["i", "tr"]}}}, "required": ["lines"]}
TR_SYSTEM = ("Translate song lyrics into natural {lang} for a listener reading along while the song plays. "
             "One translation per input line, same index. Keep it singable-plain, faithful, short; no notes, no romanisation. "
             "Lines that are only vocalisations (oh, yeah, la la) keep as-is.")
# Chinese readers share one translation (sources give Simplified; Traditional readers get it converted); English
# readers get their own, kept beside it.
TR_FIELD = {"zh": "tr", "en": "tr_en"}


def _fits(tr: str | None, x: str) -> bool:
    """A line's translation, not a paragraph about the song (what a refusal puts in the first slot)."""
    return bool(tr) and len(tr) <= 3 * len(x) + 40
_tr_running: set[str] = set()


def translate_later(vid: str, to: str = "zh") -> bool:
    """Start a background translation of a lyric into Chinese (to="zh") or English (to="en") when no source gave one.
    Returns True if started."""
    path = _path(vid)
    key = f"{vid}:{to}"
    if not path.exists() or key in _tr_running:
        return False
    d = json.loads(path.read_text())
    field, done = TR_FIELD[to], "translated" if to == "zh" else "translated_en"
    if not d.get("found") or d.get(done) or d.get("lang") == to or d.get(f"tr_failed_{to}", d.get("tr_failed") if to == "zh" else None):
        return False
    if d.get(f"tr_retry_{to}", d.get("tr_retry", 0) if to == "zh" else 0) > time.time() or llm.unavailable():
        return False
    _tr_running.add(key)

    def run():
        try:
            idx = [i for i, l in enumerate(d["lines"]) if l["x"]]
            prompt = "\n".join(f"{i}\t{d['lines'][i]['x']}" for i in idx)
            system = TR_SYSTEM.format(lang="Simplified Chinese" if to == "zh" else "English")
            res = llm.call(prompt, system, TR_SCHEMA, model="sonnet", timeout=180, retries=1)
            got = {x["i"]: x["tr"].strip() for x in res["lines"] if 0 <= x["i"] < len(d["lines"]) and x["tr"].strip()}
            # a reply covering a few lines is a refusal or a summary, not a translation; don't show it as one
            if len(got) < len(idx) / 2:
                raise ValueError(f"translated {len(got)} of {len(idx)} lines")
            for i, tr in got.items():
                if tr != d["lines"][i]["x"] and _fits(tr, d["lines"][i]["x"]):
                    d["lines"][i][field] = tr
            d[done] = any(l.get(field) for l in d["lines"])
            if not d[done]:
                d[f"tr_failed_{to}"] = True   # every line came back as it was: nothing to translate, don't ask again
            d["tr_by" if to == "zh" else "tr_en_by"] = "AI"
            d.pop(f"tr_retry_{to}", None)
        except llm.LLMError:
            d[f"tr_retry_{to}"] = time.time() + 3600   # Claude failed, not the lyric: try again later, not every play
        except Exception:
            d[f"tr_failed_{to}"] = True
        finally:
            store.write_json(path, d)
            _tr_running.discard(key)
    # the listener who pressed play is the one whose Claude translates
    threading.Thread(target=contextvars.copy_context().run, args=(run,), daemon=True).start()
    return True


def _words(w: list, lang: str) -> list:
    """A line's timed words in the reader's script, converted as one phrase (头发 is 頭髮, 发现 is 發現) and cut back
    into the same pieces; piece by piece only if the phrase changed length."""
    from . import i18n
    whole = "".join(x[2] for x in w)
    out = i18n.script(whole, lang)
    if len(out) != len(whole):
        return [[*x[:2], i18n.script(x[2], lang), *x[3:]] for x in w]
    at, res = 0, []
    for x in w:
        res.append([*x[:2], out[at:at + len(x[2])], *x[3:]])
        at += len(x[2])
    return res


def for_reader(d: dict, lang: str) -> dict:
    """The cached lyric as a reader of `lang` sees it: their translation in `tr`, credits in their script."""
    from . import i18n
    if not d.get("found"):
        return d
    d = {**d, "lines": [l for l in d["lines"] if not SECTION.match(l["x"])]}
    if lang == "en":
        lines = [{**{k: v for k, v in l.items() if k not in ("tr", "tr_en")}, **({"tr": l["tr_en"]} if _fits(l.get("tr_en"), l["x"]) else {})}
                 for l in d["lines"]]
        return {**d, "lines": lines, "translated": any(l.get("tr") for l in lines), "tr_by": d.get("tr_en_by", "AI")}
    lines = [{k: v for k, v in l.items() if k != "tr_en" and (k != "tr" or _fits(v, l["x"]))} for l in d["lines"]]
    # Chinese lyrics in the script the page shows the title in (i18n.for_reader); a Japanese song keeps its own
    if not any(i18n.japanese(l["x"]) for l in lines):
        lines = [{**l, "x": i18n.script(l["x"], lang), **({"w": _words(l["w"], lang)} if l.get("w") else {})} for l in lines]
    if lang == "zh-Hant":
        lines = [{**l, "tr": i18n.convert(l["tr"], "zh-Hans", "zh-Hant")} if l.get("tr") else l for l in lines]
    return {**d, "lines": lines}


# ---------- staging: where a song opens up, and the line it turns on ----------
# Immersive opens the room for the chorus and holds still on one line. Code reads the sections from the lyric itself:
# headings when the source wrote them, otherwise runs of lines sung again later, and long silences between lines.
# Claude then corrects the chorus, finds a bridge and picks the line, once per song, kept with the lyric for everyone.
# Everything is in the lyric's own seconds, so a listener's timing nudge moves it with the words.

STAGE_V = 1
MARKED = {"chorus": "chorus", "refrain": "chorus", "hook": "chorus", "postchorus": "chorus", "副歌": "chorus",
          "bridge": "bridge", "桥段": "bridge", "橋段": "bridge"}
BREAK_S = 6   # a silence this long between sung lines is a break


def _sung(lines: list[dict]) -> list[dict]:
    return [l for l in lines if l["x"] and not SECTION.match(l["x"])]


def _end(sung: list[dict], i: int) -> float:
    l = sung[i]
    nxt = sung[i + 1]["t"] if i + 1 < len(sung) else l["t"] + 8
    return round(min(l.get("e") or l["t"] + 5, nxt), 3)


def _span(sung: list[dict], a: int, b: int, kind: str) -> list:
    return [round(sung[a]["t"], 3), _end(sung, b), kind]


def _runs(flags: list[bool], least: int = 2, mend: bool = True) -> list[tuple[int, int]]:
    """Runs of flagged lines at least `least` long. With `mend`, one unflagged line after two flagged ones doesn't
    break a run (a chorus whose third line changes the second time)."""
    out, a = [], None
    for i, f in enumerate(flags + [False, False]):
        if f and a is None:
            a = i
        elif not f and a is not None and not (mend and i + 1 < len(flags) and flags[i + 1] and i - a >= 2):
            if i - a >= least:
                out.append((a, i - 1))
            a = None
    return out


def _same(a: str, b: str) -> bool:
    if not a or not b or a == b:
        return bool(a) and a == b
    if min(len(a), len(b)) < 4 or min(len(a), len(b)) < 0.85 * max(len(a), len(b)):
        return False
    m = difflib.SequenceMatcher(None, a, b, autojunk=False)
    return m.quick_ratio() >= 0.85 and m.ratio() >= 0.85


def structure(lines: list[dict]) -> dict:
    """A song's chorus and breaks from its lyric alone: [[from s, to s, kind], ...] with kind chorus, bridge or break."""
    sung = _sung(lines)
    out = {"v": STAGE_V, "sec": [], "heart": [], "by": "code"}
    if len(sung) < 4:
        return out
    kinds, kind = [], None
    for l in lines:
        m = SECTION.match(l["x"]) if l["x"] else None
        if m:
            kind = MARKED.get(re.sub(r"[\s-]", "", m.group(1).lower()), "verse")
        elif l["x"]:
            kinds.append(kind)
    if "chorus" in kinds:
        for k in ("chorus", "bridge"):
            out["sec"] += [_span(sung, a, b, k) for a, b in _runs([x == k for x in kinds], 1, False)]
    else:
        keys = [norm(l["x"]) for l in sung]
        n = len(keys)
        count = [sum(_same(keys[i], keys[j]) for j in range(n) if j != i) for i in range(n)]
        flags = [c > 0 for c in count]
        # a song that repeats most of itself: only what comes back most often is the chorus
        if sum(flags) > 0.6 * n:
            flags = [c >= 2 for c in count]
        out["sec"] += [_span(sung, a, b, "chorus") for a, b in _runs(flags)]
    for i in range(len(sung) - 1):
        quiet = sung[i].get("e") or sung[i]["t"] + 5
        if sung[i + 1]["t"] - quiet >= BREAK_S:
            out["sec"].append([round(quiet, 3), round(sung[i + 1]["t"], 3), "break"])
    out["sec"].sort()
    return out


STAGE_SCHEMA = {"type": "object", "properties": {
    "chorus": {"type": "array", "items": {"type": "array", "items": {"type": "integer"}}},
    "bridge": {"type": "array", "items": {"type": "array", "items": {"type": "integer"}}},
    "heart": {"type": "integer"}}, "required": ["chorus", "bridge", "heart"]}
STAGE_SYSTEM = """You stage a song's lyrics for a full-screen player. The room opens up while the chorus is sung, and once
in the song everything else falls away and a single line is held: the line the song turns on, the one a listener would
quote back to a friend, at the moment it lands hardest.

You get the sung lines (index, second it starts, text, and a translation when there is one) and the chorus runs code
guessed from repeated lines. Return:
- chorus: each run sung as the chorus or the hook the song keeps coming back to, as [first index, last index]. Keep
  code's runs when they are right and fix them when they are not: a verse whose words repeat is not a chorus, and a
  chorus whose words change still is.
- bridge: the run of a bridge, sung once and usually between the last two choruses, or [] when there is none.
- heart: the index of the one line to hold, at the occurrence where it lands hardest (often its last time, or the end
  of the bridge). Never a vocalisation (oh, yeah, la la), never a line that only says the title unless the whole song
  turns on it.
Indices only, from the list given."""
_stage_running: set[str] = set()


def _staged(d: dict) -> dict:
    s = d.get("stage")
    return s if s and s.get("v") == STAGE_V else structure(d["lines"])


def stage(d: dict) -> dict | None:
    """What the player stages a found lyric by: Claude's reading once there is one, code's until then."""
    return _staged(d) if d.get("found") else None


def stage_later(vid: str) -> bool:
    """Start Claude's reading of a lyric's sections and heart line in the background. Returns True if started."""
    path = _path(vid)
    if not path.exists() or vid in _stage_running:
        return False
    d = json.loads(path.read_text())
    s = d.get("stage") or {}
    if not d.get("found") or (s.get("v") == STAGE_V and s.get("by") == "AI") or len(_sung(d["lines"])) < 6:
        return False
    if d.get("stage_retry", 0) > time.time() or d.get("stage_failed") == STAGE_V or llm.unavailable():
        return False
    _stage_running.add(vid)

    def run():
        try:
            sung = _sung(d["lines"])
            code = structure(d["lines"])
            at = {round(l["t"], 3): i for i, l in enumerate(sung)}
            guess = [[at.get(a), next((i for i, l in enumerate(sung) if _end(sung, i) == b), None)] for a, b, k in code["sec"] if k == "chorus"]
            rows = [f"{i}\t{l['t']:.1f}\t{l['x']}" + (f"\t{l['tr']}" if l.get("tr") else "") for i, l in enumerate(sung)]
            prompt = "LINES\n" + "\n".join(rows) + "\n\nCODE'S CHORUS RUNS\n" + json.dumps([g for g in guess if None not in g])
            res = llm.call(prompt, STAGE_SYSTEM, STAGE_SCHEMA, model="sonnet", timeout=180, retries=1)
            sec = [_span(sung, r[0], r[1], k) for k in ("chorus", "bridge") for r in res[k]
                   if isinstance(r, list) and len(r) == 2 and 0 <= r[0] <= r[1] < len(sung)]
            h = res["heart"]
            heart = [round(sung[h]["t"], 3)] if 0 <= h < len(sung) and len(norm(sung[h]["x"])) >= 2 else []
            if not sec and not heart:
                raise ValueError("nothing staged")
            d["stage"] = {"v": STAGE_V, "sec": sorted(sec + [s for s in code["sec"] if s[2] == "break"]), "heart": heart, "by": "AI"}
            d.pop("stage_retry", None)
        except llm.LLMError:
            d["stage_retry"] = time.time() + 3600
        except Exception:
            d["stage_failed"] = STAGE_V
        finally:
            # the lyric may have been replaced meanwhile (a word-timed find): stage only the one read
            cur = json.loads(path.read_text()) if path.exists() else {}
            if cur.get("lines") == d["lines"]:
                store.write_json(path, {**cur, **{k: d[k] for k in ("stage", "stage_retry", "stage_failed") if k in d}})
            _stage_running.discard(vid)
    threading.Thread(target=contextvars.copy_context().run, args=(run,), daemon=True).start()
    return True
