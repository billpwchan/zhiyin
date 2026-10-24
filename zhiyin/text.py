import re
import unicodedata

# Covers, live cuts, remixes and lyric uploads of a song the user already likes are the same song to them.
_BRACKETS = re.compile(r"[\(\[（【「『<《].*?[\)\]）】」』>》]")
_TAIL = re.compile(r"\s+[-–|｜/].*$")
_FEAT = re.compile(r"\b(feat\.?|ft\.?|with|prod\.?)\b.*$", re.I)
_VERSION = re.compile(r"\b(live|remix|cover|acoustic|ver\.?|version|instrumental|inst\.?|demo|edit|mix|remaster(ed)?|sped up|slowed)\b", re.I)


def fold(s: str) -> str:
    s = unicodedata.normalize("NFKC", s or "").lower()
    return re.sub(r"[\s\W_]+", "", s)


def song_key(title: str) -> str:
    t = unicodedata.normalize("NFKC", title or "")
    t = _BRACKETS.sub(" ", t)
    t = _FEAT.sub(" ", t)
    base = _TAIL.sub("", t).strip() or t
    return fold(base)


def is_version(title: str) -> bool:
    return bool(_VERSION.search(unicodedata.normalize("NFKC", title or "")))


def dur_s(s: str | None) -> int:
    if not s:
        return 0
    v = 0
    for part in str(s).split(":"):
        if part.isdigit():
            v = v * 60 + int(part)
    return v


_GLOSS = re.compile(r"^(?P<main>.*[\u3040-\u30ff\u3400-\u9fff\uac00-\ud7af].*?)\s+-\s+[A-Za-z0-9][A-Za-z0-9 '’!?.,&:()-]*$")
_PROMO = re.compile(r"\s*[\(\[（【]\s*(official|官方|music video|mv|m/v|lyric|lyrics|visuali[sz]er|audio|動態歌詞|歌詞)[^\)\]）】]*[\)\]）】]\s*", re.I)


def display_title(title: str, artists: list[dict]) -> str:
    """'moon tang - 渡我 (official video)' -> '渡我' for uploads whose title repeats the artist and a promo tag."""
    t = _PROMO.sub(" ", title or "").strip()
    t = re.sub(r"\s+(official\s+)?(mv|m/v|music video)$", "", t, flags=re.I)
    for a in artists or []:
        name = (a.get("name") or "").strip()
        for sep in (" - ", " – ", "-", "「"):
            if name and t.lower().startswith((name + sep).lower()):
                t = t[len(name + sep):].strip(" 」")
        left, dash, right = t.partition(" - ")
        if name and dash and right and fold(name) in fold(left):
            t = right.strip()
    m = _GLOSS.match(t)
    if m:
        t = m.group("main").strip()
    return t or title
