"""Google sign-in and the YouTube Data API, the official way to read a listener's likes and to write likes back.
YouTube Music has no public API. Its liked songs sit in the account's liked-videos playlist (LL), in the same
order, with two quirks: many songs appear as their music video or another upload of the recording instead of the
audio track, and the playlist also holds every non-music video the person liked (on one account measured in
October 2026, 2,776 entries against 908 liked songs)."""
import base64
import datetime as dt
import hashlib
import json
import os
import re
import secrets
import threading
import time
import urllib.parse
from zoneinfo import ZoneInfo

import httpx
from cryptography.fernet import Fernet

from . import accounts, store

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
REVOKE_URL = "https://oauth2.googleapis.com/revoke"
API = "https://www.googleapis.com/youtube/v3"
YT_SCOPE = "https://www.googleapis.com/auth/youtube"
BASE_SCOPES = "openid email profile"
# One project shares 10,000 units a day (reset at midnight Pacific). Reading likes costs 1 per 50; a like or a
# playlist entry costs 50. Writes stop before the last 1,000 so reading new likes always works.
DAILY_QUOTA = 10_000
WRITE_FLOOR = 1_000
MUSIC_CATEGORY = "10"


class NotConnected(Exception):
    pass


class Revoked(Exception):
    """The refresh token stopped working (access removed in the Google account, or expired): reconnect."""


class QuotaExceeded(Exception):
    pass


def client() -> dict | None:
    """The OAuth client the owner created in Google Cloud ("Web application"), as downloaded."""
    path = store.DATA / "google_client.json"
    if not path.exists():
        return None
    c = json.loads(path.read_text())
    c = c.get("web") or c
    return {"id": c["client_id"], "secret": c["client_secret"]}


def configured() -> bool:
    return client() is not None


def public_url() -> str:
    return os.environ.get("ZHIYIN_PUBLIC_URL", "http://localhost:8817").rstrip("/")


def redirect_uri() -> str:
    return public_url() + "/auth/google/callback"


def _fernet() -> Fernet:
    path = store.DATA / "secret.key"
    if not path.exists():
        path.write_bytes(Fernet.generate_key())
        path.chmod(0o600)
    return Fernet(path.read_bytes())


def pkce() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(48)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    return verifier, challenge


def auth_url(state: str, challenge: str, connect: bool, hint: str | None = None) -> str:
    c = client()
    q = {"client_id": c["id"], "redirect_uri": redirect_uri(), "response_type": "code", "state": state,
         "code_challenge": challenge, "code_challenge_method": "S256", "include_granted_scopes": "true"}
    if connect:
        # prompt=consent guarantees a refresh token even if the listener granted access before.
        q |= {"scope": f"{BASE_SCOPES} {YT_SCOPE}", "access_type": "offline", "prompt": "consent"}
    else:
        q |= {"scope": BASE_SCOPES, "prompt": "select_account"}
    if hint:
        q["login_hint"] = hint
    return AUTH_URL + "?" + urllib.parse.urlencode(q)


def exchange(code: str, verifier: str) -> dict:
    c = client()
    r = httpx.post(TOKEN_URL, data={"code": code, "client_id": c["id"], "client_secret": c["secret"],
                                    "redirect_uri": redirect_uri(), "grant_type": "authorization_code",
                                    "code_verifier": verifier}, timeout=20)
    r.raise_for_status()
    tok = r.json()
    tok["expires_at"] = time.time() + tok.get("expires_in", 3600)
    return tok


def claims(id_token: str) -> dict:
    """The id_token came straight from Google's token endpoint over TLS, so its payload can be read as is."""
    body = id_token.split(".")[1]
    return json.loads(base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)))


def has_youtube(tok: dict) -> bool:
    # Google's consent screen lets people untick individual permissions.
    return YT_SCOPE in (tok.get("scope") or "").split()


def save_tokens(uid: str, tok: dict) -> None:
    keep = {k: tok[k] for k in ("access_token", "refresh_token", "expires_at", "scope") if k in tok}
    old = _load(uid) or {}
    keep.setdefault("refresh_token", old.get("refresh_token"))
    con = store.db()
    con.execute("update users set tokens=? where id=?", (_fernet().encrypt(json.dumps(keep).encode()), uid))
    con.commit()


def _load(uid: str) -> dict | None:
    r = store.db().execute("select tokens from users where id=?", (uid,)).fetchone()
    if not r or not r["tokens"]:
        return None
    return json.loads(_fernet().decrypt(r["tokens"]))


def connected(uid: str | None = None) -> bool:
    t = _load(uid or store.uid())
    return bool(t and t.get("refresh_token") and has_youtube(t))


_locks: dict[str, threading.Lock] = {}


def access_token(uid: str, force: bool = False) -> str:
    with _locks.setdefault(uid, threading.Lock()):
        tok = _load(uid)
        if not tok or not tok.get("refresh_token"):
            raise NotConnected()
        if not force and tok.get("expires_at", 0) - 60 > time.time():
            return tok["access_token"]
        c = client()
        r = httpx.post(TOKEN_URL, data={"client_id": c["id"], "client_secret": c["secret"],
                                        "refresh_token": tok["refresh_token"], "grant_type": "refresh_token"}, timeout=20)
        if r.status_code in (400, 401) and r.json().get("error") in ("invalid_grant", "unauthorized_client"):
            accounts.set_prefs(uid, google_error="revoked")
            raise Revoked()
        r.raise_for_status()
        new = r.json()
        tok.update(access_token=new["access_token"], expires_at=time.time() + new.get("expires_in", 3600))
        save_tokens(uid, tok)
        if accounts.prefs(uid).get("google_error"):
            accounts.set_prefs(uid, google_error=None)
        return tok["access_token"]


def _quota_key() -> str:
    return "quota:" + dt.datetime.now(ZoneInfo("America/Los_Angeles")).strftime("%Y-%m-%d")


def quota_used() -> int:
    return store.kv_get(_quota_key(), 0)


def _spend(units: int) -> None:
    store.kv_set(_quota_key(), quota_used() + units)


def can_write(units: int = 50) -> bool:
    return quota_used() + units <= DAILY_QUOTA - WRITE_FLOOR


def _call(uid: str, method: str, path: str, cost: int, **kw) -> httpx.Response:
    for attempt in (0, 1):
        _spend(cost)
        r = httpx.request(method, f"{API}/{path}", headers={"Authorization": f"Bearer {access_token(uid, force=attempt > 0)}"},
                          timeout=30, **kw)
        if r.status_code == 401 and attempt == 0:
            continue
        if r.status_code == 403 and "quota" in r.text.lower():
            store.kv_set(_quota_key(), DAILY_QUOTA)
            raise QuotaExceeded()
        r.raise_for_status()
        return r
    raise NotConnected()


def likes(uid: str, log=None, pages: int | None = None) -> list[dict]:
    """Entries of the liked-videos playlist, newest first: {"vid", "at" (when it was liked), "title", "channel"}."""
    out, page, n = [], None, 0
    while pages is None or n < pages:
        n += 1
        params = {"part": "snippet,contentDetails", "playlistId": "LL", "maxResults": 50}
        if page:
            params["pageToken"] = page
        d = _call(uid, "GET", "playlistItems", 1, params=params).json()
        for it in d.get("items", []):
            sn, cd = it["snippet"], it["contentDetails"]
            if sn.get("title") in ("Deleted video", "Private video"):
                continue
            out.append({"vid": cd["videoId"], "at": sn.get("publishedAt"), "title": sn.get("title") or "",
                        "channel": sn.get("videoOwnerChannelTitle") or ""})
        if log:
            log(f"已读 {len(out)} / {d.get('pageInfo', {}).get('totalResults', '?')} 个喜欢的视频")
        page = d.get("nextPageToken")
        if not page:
            break
    return out


def _iso_dur(s: str) -> int:
    m = re.fullmatch(r"P(?:(\d+)D)?T?(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", s or "")
    if not m:
        return 0
    d, h, mi, se = (int(x or 0) for x in m.groups())
    return ((d * 24 + h) * 60 + mi) * 60 + se


def videos(uid: str, vids: list[str]) -> dict[str, dict]:
    """Category, length and channel per video. Kept for everyone: these are public facts about the video."""
    cache = store.CACHE / "ytv"
    cache.mkdir(parents=True, exist_ok=True)
    out, todo = {}, []
    for v in dict.fromkeys(vids):
        f = cache / f"{v}.json"
        if f.exists():
            out[v] = json.loads(f.read_text())
        else:
            todo.append(v)
    for i in range(0, len(todo), 50):
        chunk = todo[i:i + 50]
        d = _call(uid, "GET", "videos", 1, params={"part": "snippet,contentDetails", "id": ",".join(chunk), "maxResults": 50}).json()
        for it in d.get("items", []):
            sn = it["snippet"]
            info = {"cat": sn.get("categoryId"), "dur": _iso_dur(it["contentDetails"].get("duration")),
                    "title": sn.get("title") or "", "channel": sn.get("channelTitle") or "",
                    "live": sn.get("liveBroadcastContent") not in (None, "none")}
            out[it["id"]] = info
            (cache / f"{it['id']}.json").write_text(json.dumps(info, ensure_ascii=False))
    return out


def rate(uid: str, vid: str, rating: str) -> None:
    """rating: like | none. A like on the audio track shows up in YouTube Music's liked songs."""
    _call(uid, "POST", "videos/rate", 50, params={"id": vid, "rating": rating})


def create_playlist(uid: str, title: str, description: str, vids: list[str]) -> str:
    units = 50 * (1 + len(vids))
    if not can_write(units):
        raise QuotaExceeded()
    pid = _call(uid, "POST", "playlists", 50, params={"part": "snippet,status"},
                json={"snippet": {"title": title, "description": description},
                      "status": {"privacyStatus": "private"}}).json()["id"]
    for v in vids:
        _call(uid, "POST", "playlistItems", 50, params={"part": "snippet"},
              json={"snippet": {"playlistId": pid, "resourceId": {"kind": "youtube#video", "videoId": v}}})
    return pid


def disconnect(uid: str) -> None:
    tok = _load(uid)
    if tok and tok.get("refresh_token"):
        try:
            httpx.post(REVOKE_URL, data={"token": tok["refresh_token"]}, timeout=15)
        except httpx.HTTPError:
            pass
    con = store.db()
    con.execute("update users set tokens=null where id=?", (uid,))
    con.commit()
