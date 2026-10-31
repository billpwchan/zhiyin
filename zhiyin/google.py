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

from . import accounts, i18n, store

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
REVOKE_URL = "https://oauth2.googleapis.com/revoke"
API = "https://www.googleapis.com/youtube/v3"
YT_SCOPE = "https://www.googleapis.com/auth/youtube"
YT_FORCE_SSL = "https://www.googleapis.com/auth/youtube.force-ssl"
# Keep existing deployments on their submitted scopes. Try force-ssl in an isolated review deployment first;
# switch production only after its exact scope set is verified. Both support ratings and private playlists.
WRITE_SCOPE = os.environ.get("ZHIYIN_YOUTUBE_WRITE_SCOPE", YT_SCOPE)
if WRITE_SCOPE not in (YT_SCOPE, YT_FORCE_SSL):
    raise ValueError("ZHIYIN_YOUTUBE_WRITE_SCOPE must be the full youtube or youtube.force-ssl scope URL")
# Joining asks only to read; writing likes back is asked for when the listener turns it on, so the first consent
# screen says "view your YouTube account" instead of "see, edit, and permanently delete".
YT_READ = "https://www.googleapis.com/auth/youtube.readonly"
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


class NoChannel(Exception):
    """A Google account that never made a YouTube channel: the API can't list its likes until it has one."""


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


HL = {"zh-Hans": "zh-CN", "zh-Hant": "zh-TW", "en": "en"}   # Google's page in the language the app is shown in


def requested_scopes(connect: bool = False, write: bool = False) -> list[str]:
    return BASE_SCOPES.split() + ([WRITE_SCOPE if write else YT_READ] if connect else [])


def scope_manifest() -> dict:
    """The scopes this deployment actually requests; safe to copy into verification materials."""
    flows = {"sign_in": requested_scopes(), "connect": requested_scopes(True),
             "optional_write": requested_scopes(True, True)}
    return {"flows": flows, "all_requested_scopes": sorted({s for scopes in flows.values() for s in scopes}),
            "note": "Google may also return previously granted scopes through include_granted_scopes. "
                    "Record with a fresh review account; compare against Cloud Console Data Access."}


def auth_url(state: str, challenge: str, connect: bool, hint: str | None = None, write: bool = False,
             lang: str | None = None) -> str:
    c = client()
    q = {"client_id": c["id"], "redirect_uri": redirect_uri(), "response_type": "code", "state": state,
         "code_challenge": challenge, "code_challenge_method": "S256", "include_granted_scopes": "true",
         "scope": " ".join(requested_scopes(connect, write))}
    if connect:
        # prompt=consent guarantees a refresh token even if the listener granted access before.
        q |= {"access_type": "offline", "prompt": "consent"}
    else:
        q["prompt"] = "select_account"
    if hint:
        q["login_hint"] = hint
    if lang in HL:
        q["hl"] = HL[lang]
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
    return bool({YT_SCOPE, YT_FORCE_SSL, YT_READ} & set((tok.get("scope") or "").split()))


def writes_back(uid: str | None = None) -> bool:
    """Allowed to put likes into the listener's YouTube Music, not only to read them."""
    t = _load(uid or store.uid())
    return bool(t and {YT_SCOPE, YT_FORCE_SSL} & set((t.get("scope") or "").split()))


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
        try:
            d = _call(uid, "GET", "playlistItems", 1, params=params).json()
        except httpx.HTTPStatusError as e:
            if not page and e.response.status_code in (401, 404) and (
                    "youtubeSignupRequired" in e.response.text or "playlistNotFound" in e.response.text):
                raise NoChannel() from e
            raise
        for it in d.get("items", []):
            sn, cd = it["snippet"], it["contentDetails"]
            if sn.get("title") in ("Deleted video", "Private video"):
                continue
            out.append({"vid": cd["videoId"], "at": sn.get("publishedAt"), "title": sn.get("title") or "",
                        "channel": sn.get("videoOwnerChannelTitle") or ""})
        if log:
            log(i18n.tr("已读 {n} / {total} 个喜欢的视频", n=len(out), total=d.get("pageInfo", {}).get("totalResults", "?")))
        page = d.get("nextPageToken")
        if not page:
            break
    return out


def _pages(uid: str, path: str, cap: int, **params) -> list[dict]:
    out, page = [], None
    for _ in range(cap):
        d = _call(uid, "GET", path, 1, params={**params, "maxResults": 50, **({"pageToken": page} if page else {})}).json()
        out += d.get("items", [])
        page = d.get("nextPageToken")
        if not page:
            break
    return out


def disliked(uid: str, pages: int = 10) -> list[dict]:
    """Videos the listener gave a thumbs-down on YouTube: {"vid", "title", "channel", "cat"}."""
    return [{"vid": it["id"], "title": it["snippet"].get("title") or "", "channel": it["snippet"].get("channelTitle") or "",
             "cat": it["snippet"].get("categoryId")}
            for it in _pages(uid, "videos", pages, part="snippet", myRating="dislike")]


def subscriptions(uid: str, pages: int = 20) -> list[dict]:
    """Channels the listener follows, with YouTube's topic labels for each: {"id", "title", "topics"}."""
    subs = [{"id": it["snippet"]["resourceId"]["channelId"], "title": it["snippet"].get("title") or ""}
            for it in _pages(uid, "subscriptions", pages, part="snippet", mine="true")]
    topics = {}
    for i in range(0, len(subs), 50):
        d = _call(uid, "GET", "channels", 1, params={"part": "topicDetails", "id": ",".join(s["id"] for s in subs[i:i + 50]),
                                                    "maxResults": 50}).json()
        for it in d.get("items", []):
            topics[it["id"]] = [u.rsplit("/", 1)[-1] for u in it.get("topicDetails", {}).get("topicCategories", [])]
    return [{**s, "topics": topics.get(s["id"], [])} for s in subs]


def own_playlists(uid: str, cap: int = 500, lists: int = 25) -> list[dict]:
    """Entries of the playlists the listener made, other than ones saved from Zhiyin's stations (those are its picks,
    not the listener's): {"vid", "at", "title", "channel"}. A playlist that can't be read is left out."""
    out = []
    mine = [pl for pl in _pages(uid, "playlists", 2, part="snippet", mine="true")
            if not (pl["snippet"].get("title") or "").startswith(("知音 · ", "Zhiyin · "))]
    for pl in mine[:lists]:
        try:
            items = _pages(uid, "playlistItems", 4, part="snippet,contentDetails", playlistId=pl["id"])
        except (Revoked, NotConnected, QuotaExceeded):
            raise
        except Exception:   # noqa: BLE001 - one playlist gone or broken: read the others
            continue
        for it in items:
            sn = it["snippet"]
            if sn.get("title") in ("Deleted video", "Private video") or not it["contentDetails"].get("videoId"):
                continue
            out.append({"vid": it["contentDetails"]["videoId"], "at": sn.get("publishedAt"), "title": sn.get("title") or "",
                        "channel": sn.get("videoOwnerChannelTitle") or ""})
            if len(out) >= cap:
                return out
    return out


def _iso_dur(s: str) -> int:
    m = re.fullmatch(r"P(?:(\d+)D)?T?(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", s or "")
    if not m:
        return 0
    d, h, mi, se = (int(x or 0) for x in m.groups())
    return ((d * 24 + h) * 60 + mi) * 60 + se


def videos(uid: str, vids: list[str]) -> dict[str, dict]:
    """Category, length and channel per video. Kept for everyone: these are public facts about the video, fetched
    again after 30 days as YouTube's rules ask of anything kept from its API."""
    cache = store.CACHE / "ytv"
    cache.mkdir(parents=True, exist_ok=True)
    out, todo = {}, []
    for v in dict.fromkeys(vids):
        f = cache / f"{v}.json"
        if f.exists() and time.time() - f.stat().st_mtime < 30 * 86400:
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
        for v in chunk:
            if v not in out:
                (cache / f"{v}.json").unlink(missing_ok=True)   # gone from YouTube
    return out


def sweep_videos() -> None:
    """Video facts nobody asked for again in 30 days are deleted rather than kept stale."""
    for f in (store.CACHE / "ytv").glob("*.json"):
        if time.time() - f.stat().st_mtime > 30 * 86400:
            f.unlink(missing_ok=True)


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
