import pytest

from zhiyin import server, store


def test_likes_made_before_connecting_go_across_once(monkeypatch):
    from zhiyin import google
    monkeypatch.setattr(google, "writes_back", lambda uid=None: False)
    with store.as_user("u9"):
        assert server._backfill_likes() == 0     # joined read-only: nothing goes across until they allow writing
    monkeypatch.setattr(google, "writes_back", lambda uid=None: True)
    con = store.db()
    for vid in ("a", "b", "c"):
        con.execute("insert into feedback (vid, action, ts, uid) values (?, ?, 1, 'u9')", (vid, "dislike" if vid == "c" else "like"))
    con.execute("insert into outbox(uid, op, vid, arg, created) values ('u9', 'rate', 'a', 'like', 1)")
    con.commit()
    with store.as_user("u9"):
        assert server._backfill_likes() == 1
        assert server._backfill_likes() == 0
    queued = [r["vid"] for r in con.execute("select vid from outbox where uid='u9' order by id")]
    assert queued == ["a", "b"]


def test_a_link_stops_opening_an_account_tied_to_google(monkeypatch):
    from starlette.requests import Request
    from zhiyin import accounts, google
    monkeypatch.setattr(google, "configured", lambda: True)
    tok = accounts.invite("Ming")
    uid = accounts.redeem(tok)
    req = Request({"type": "http", "headers": []})
    assert "set-cookie" in server.invite_link(tok, req).headers          # first visit: signed in by the link
    accounts.link_google(uid, "sub-1", "ming@example.com", "Ming")
    r = server.invite_link(tok, req)
    assert "set-cookie" not in r.headers and r.headers["location"] == "/auth/google/start?mode=login"


def test_only_a_video_id_names_a_lyrics_file():
    from fastapi.testclient import TestClient
    from zhiyin import lyrics
    c = TestClient(server.app)
    for vid in ("../../users/owner/profile", "/data/google_client", "a.b"):
        assert c.get("/api/lyrics", params={"vid": vid, "t": "x"}).status_code == 422
    with pytest.raises(ValueError):
        lyrics.get("../x", "t", [])


def test_worker_routes_check_the_token_before_reading_a_body(monkeypatch):
    from fastapi.testclient import TestClient
    monkeypatch.setattr(server, "WORKER_TOKEN", "t")
    c = TestClient(server.app)
    assert c.post("/api/worker/result", content=b"{" * 1000).status_code == 403
    r = c.post("/api/worker/llm/x", headers={"x-worker-token": "t"}, json={"data": {}, "usd": -1e9})
    assert r.status_code == 422


def test_a_sibling_site_cannot_post():
    from fastapi.testclient import TestClient
    c = TestClient(server.app)
    assert c.post("/auth/logout", headers={"sec-fetch-site": "same-site"}).status_code == 403
    assert c.post("/auth/logout", headers={"sec-fetch-site": "same-origin"}).status_code == 200


def test_your_own_second_account_needs_no_api_key(monkeypatch):
    from fastapi import HTTPException
    from zhiyin import llm
    monkeypatch.setattr(llm, "API_KEY", False)
    with store.as_user(store.OWNER):
        assert "/i/" in server.invite(server.InviteReq(mine=True))["url"]
        with pytest.raises(HTTPException) as e:
            server.invite(server.InviteReq(name="Ming"))
    assert e.value.status_code == 409


def test_a_bookmark_signs_in_as_the_named_account_in_one_click(monkeypatch):
    from urllib.parse import parse_qs, urlparse
    from zhiyin import google
    monkeypatch.setattr(google, "client", lambda: {"id": "c"})
    q = parse_qs(urlparse(google.auth_url("s", "x", False, "me@example.com", pick=False)).query)
    assert q["login_hint"] == ["me@example.com"] and "prompt" not in q
    assert parse_qs(urlparse(google.auth_url("s", "x", False)).query)["prompt"] == ["select_account"]


def test_starting_a_sign_in_leaves_the_database_writable(monkeypatch):
    import sqlite3
    from fastapi.testclient import TestClient
    from zhiyin import google
    monkeypatch.setattr(google, "configured", lambda: True)
    monkeypatch.setattr(google, "client", lambda: {"id": "c"})
    c = TestClient(server.app)
    for _ in range(2):
        assert c.get("/auth/google/start", params={"mode": "login", "as": "me@example.com"},
                     follow_redirects=False).status_code == 303
    raw = sqlite3.connect(store.DB, timeout=1)
    raw.execute("insert or replace into kv values ('probe', '1')")
    raw.commit()


def test_a_tab_left_open_as_another_account_cannot_write(monkeypatch):
    from fastapi.testclient import TestClient
    from zhiyin import accounts
    monkeypatch.setattr(server, "AUTH", True)
    a = accounts.redeem(accounts.invite("A"))
    b = accounts.redeem(accounts.invite("B", mine=True))
    c = TestClient(server.app)
    c.cookies.set(accounts.COOKIE, accounts.new_session(b))
    stale = c.post("/api/feedback", json={"vid": "abc", "action": "like"}, headers={"X-Zhiyin-Uid": a})
    assert stale.status_code == 409 and stale.json()["detail"] == "account-changed"
    assert store.db().execute("select count(*) from feedback where vid='abc'").fetchone()[0] == 0
    unmarked = c.post("/api/feedback", json={"vid": "abc", "action": "like"})
    assert unmarked.status_code == 409
    assert c.get("/api/jobs").status_code == 200
    ok = c.post("/api/feedback", json={"vid": "abc", "action": "like"}, headers={"X-Zhiyin-Uid": b})
    assert ok.status_code == 200
    assert store.db().execute("select uid from feedback where vid='abc'").fetchone()[0] == b


def test_a_refused_lyric_translation_is_not_shown(monkeypatch):
    import json
    import threading
    from zhiyin import llm, lyrics
    lines = [{"t": i, "x": f"歌詞の行 {i}"} for i in range(10)]
    lyrics._path("refused0001").write_text(json.dumps({"vid": "refused0001", "found": True, "lang": "ja", "lines": lines}))
    summary = "I can't translate these lyrics line by line because the song is copyrighted. Here is a summary instead."
    monkeypatch.setattr(llm, "unavailable", lambda: None)
    monkeypatch.setattr(llm, "call", lambda *a, **k: {"lines": [{"i": 0, "tr": summary}]})
    monkeypatch.setattr(threading, "Thread", lambda target, args, daemon: type("T", (), {"start": lambda s: target(*args)})())
    assert lyrics.translate_later("refused0001", "en")
    d = json.loads(lyrics._path("refused0001").read_text())
    assert d["tr_failed_en"] and not any(l.get("tr_en") for l in d["lines"])
    d["lines"][0]["tr_en"] = summary                     # what a reader already cached before this check got
    assert not any(l.get("tr") for l in lyrics.for_reader(d, "en")["lines"])


def test_lyrics_with_nothing_to_translate_are_not_sent_again(monkeypatch):
    import json
    import threading
    from zhiyin import llm, lyrics
    lines = [{"t": i, "x": f"line {i}"} for i in range(6)]
    lyrics._path("same0000001").write_text(json.dumps({"vid": "same0000001", "found": True, "lang": "ja", "lines": lines}))
    calls = []
    monkeypatch.setattr(llm, "unavailable", lambda: None)
    monkeypatch.setattr(llm, "call", lambda *a, **k: calls.append(1) or {"lines": [{"i": i, "tr": f"line {i}"} for i in range(6)]})
    monkeypatch.setattr(threading, "Thread", lambda target, args, daemon: type("T", (), {"start": lambda s: target(*args)})())
    assert lyrics.translate_later("same0000001", "en")
    assert not lyrics.translate_later("same0000001", "en") and calls == [1]


def test_someone_not_signed_in_hears_the_sample_in_their_language_and_changes_nothing(monkeypatch):
    from fastapi.testclient import TestClient
    monkeypatch.setattr(server, "AUTH", True)
    monkeypatch.setattr(server, "SAMPLE_ON", [server._install_sample()])
    c = TestClient(server.app)
    en = c.get("/api/state", headers={"accept-language": "en-US"}).json()
    assert en["me"]["sample"] and en["me"]["uid"] == store.SAMPLE and en["edition"]["lanes"]
    tw = c.get("/api/state", headers={"accept-language": "zh-TW"}).json()
    assert tw["me"]["uid"] == store.SAMPLE_ZH and tw["me"]["lang"] == "zh-Hant" and not tw["stale_lang"]
    assert c.get("/", headers={"accept-language": "zh-TW"}).status_code == 200
    assert c.post("/api/feedback", json={"vid": "hp0KiJs0S5g", "action": "like"}).status_code == 401
    assert c.post("/api/refresh", json={}).status_code == 401
    assert c.get("/api/users").status_code == 401
    assert not (store.USERS / store.SAMPLE / "edition.json").read_text() == ""
    assert server._jobs.get((store.SAMPLE, "refresh")) is None     # looking never starts a build
    assert en["owner_name"] == ""

    # what signed-out visitors make the server fetch from YouTube is capped, for all of them together
    from zhiyin import ytm
    monkeypatch.setattr(ytm, "radio", lambda vid, limit=50: {"tracks": []})
    monkeypatch.setattr(server, "SAMPLE_FETCHES", {**server.SAMPLE_FETCHES, "more": 2})
    monkeypatch.setattr(server, "_sample_fetched", {k: [] for k in server.SAMPLE_FETCHES})
    assert [c.get("/api/more?vid=hp0KiJs0S5g").status_code for _ in range(3)] == [200, 200, 429]


def _join(c, monkeypatch, who, mode="join", scope=None):
    from urllib.parse import parse_qs, urlparse
    from zhiyin import google
    scope = scope or f"openid {google.YT_READ}"
    monkeypatch.setattr(google, "exchange", lambda code, v: {"id_token": who, "scope": scope,
                                                              "access_token": "a", "refresh_token": "r"})
    monkeypatch.setattr(google, "claims", lambda tok: {"sub": tok, "email": f"{tok}@example.com", "name": tok.title()})
    c.cookies.clear()                     # a stranger's browser
    r = c.get(f"/auth/google/start?mode={mode}", follow_redirects=False)
    loc = r.headers["location"]
    if mode == "join":
        assert "youtube.readonly" in loc and "%2Fyoutube+" not in loc and "%2Fyoutube&" not in loc   # read only
    state = parse_qs(urlparse(r.headers["location"]).query)["state"][0]
    c.cookies.clear()
    c.cookies.set("zy_o", state)
    return c.get(f"/auth/google/callback?state={state}&code=x", follow_redirects=False)


def test_strangers_join_with_google_until_the_seats_run_out_then_wait(monkeypatch):
    from fastapi.testclient import TestClient
    from zhiyin import accounts, google, llm
    monkeypatch.setattr(server, "AUTH", True)
    monkeypatch.setattr(llm, "HOSTED", True)
    monkeypatch.setattr(llm, "API_KEY", True)
    monkeypatch.setattr(google, "client", lambda: {"id": "x", "secret": "y"})
    started = []
    monkeypatch.setattr(server, "_start", lambda kind, fn: started.append(kind))
    monkeypatch.setattr(server, "SEATS", accounts.joined() + 1)
    c = TestClient(server.app)

    r = _join(c, monkeypatch, "ann")
    assert r.status_code == 303 and r.headers["location"] == "/" and accounts.COOKIE in r.cookies
    uid = accounts.by_google("ann")
    assert accounts.prefs(uid)["joined"] and started == ["setup"]
    with store.as_user(uid):
        assert not google.writes_back() and server._queue_rate("hp0KiJs0S5g", "LIKE") == "read-only"
        assert server._me()["sync_likes"] is False

    n = accounts.joined()                   # unticking YouTube on Google's page makes no account and takes no seat
    assert [_join(c, monkeypatch, "eve", scope="openid email").headers["location"] for _ in range(2)] == ["/login?e=noscope"] * 2
    assert accounts.by_google("eve") is None and accounts.joined() == n

    r = _join(c, monkeypatch, "bo")          # the last seat is taken: Bo goes on the waitlist, no account
    assert r.headers["location"] == "/login?e=full" and accounts.by_google("bo") is None
    assert store.db().execute("select count(*) from waitlist where sub='bo'").fetchone()[0] == 1

    con = store.db()
    con.execute("update waitlist set admitted=1 where sub='bo'")
    con.commit()
    assert _join(c, monkeypatch, "bo", mode="login").headers["location"] == "/auth/google/start?mode=join"   # signing in joins
    assert _join(c, monkeypatch, "bo").headers["location"] == "/" and accounts.by_google("bo")
    assert store.db().execute("select count(*) from waitlist where sub='bo'").fetchone()[0] == 0

    n = len(accounts.users())
    assert _join(c, monkeypatch, "ann").headers["location"] == "/" and len(accounts.users()) == n   # back in, not twice


def test_no_one_can_join_a_server_without_an_api_key(monkeypatch):
    from fastapi.testclient import TestClient
    from zhiyin import google, llm
    monkeypatch.setattr(server, "AUTH", True)
    monkeypatch.setattr(llm, "HOSTED", True)
    monkeypatch.setattr(llm, "API_KEY", False)
    monkeypatch.setattr(google, "client", lambda: {"id": "x", "secret": "y"})
    monkeypatch.setattr(server, "SEATS", 50)
    assert server._join_state() == "invite"
    r = TestClient(server.app).get("/auth/google/start?mode=join", follow_redirects=False)
    assert "youtube" not in r.headers["location"]      # quietly a plain sign-in


def test_a_like_can_stop_speaking_for_your_taste_and_come_back(monkeypatch):
    from fastapi.testclient import TestClient
    from zhiyin import accounts, settings
    from zhiyin.text import fold
    monkeypatch.setattr(server, "AUTH", True)
    uid = accounts.redeem(accounts.invite("N"))
    with store.as_user(uid):
        store.write_json(store.LIBRARY, {"source": "google", "synced": 1, "tracks": [
            {"rank": 0, "vid": "notme000001", "title": "Baby Shark", "artists": [{"name": "Pinkfong"}], "long": False, "source": "google"},
            {"rank": 1, "vid": "notme000002", "title": "Real Love", "artists": [{"name": "Someone"}], "long": False, "source": "google"}]})
    c = TestClient(server.app)
    c.cookies.set(accounts.COOKIE, accounts.new_session(uid))
    h = {"X-Zhiyin-Uid": uid}
    v = c.post("/api/notme", json={"vid": "notme000001", "on": True}, headers=h).json()["not_me"]
    assert v["songs"] == [{"vid": "notme000001", "title": "Baby Shark", "artist": "Pinkfong"}]
    v = c.post("/api/notme", json={"artist": "Pinkfong", "on": True}, headers=h).json()["not_me"]
    assert v["artists"] == [{"key": fold("Pinkfong"), "name": "Pinkfong"}]
    assert c.get("/api/state", headers=h).json()["not_me"] == v
    c.post("/api/notme", json={"key": fold("Pinkfong"), "on": False}, headers=h)
    c.post("/api/notme", json={"vid": "notme000001", "on": False}, headers=h)
    with store.as_user(uid):
        assert settings.not_me() == (set(), set())


def test_a_taste_gets_a_new_name_a_few_times_a_day(monkeypatch):
    from fastapi.testclient import TestClient
    from zhiyin import accounts, llm
    monkeypatch.setattr(server, "AUTH", True)
    monkeypatch.setattr(llm, "unavailable", lambda *a: None)
    started = []
    monkeypatch.setattr(server, "_start", lambda kind, fn: started.append(kind))
    uid = accounts.redeem(accounts.invite("R"))
    c = TestClient(server.app)
    c.cookies.set(accounts.COOKIE, accounts.new_session(uid))
    codes = [c.post("/api/ear/label", json={}, headers={"X-Zhiyin-Uid": uid}).status_code for _ in range(server.LABEL_ROLLS + 1)]
    assert codes == [200] * server.LABEL_ROLLS + [429] and started == ["label"] * server.LABEL_ROLLS


def test_one_listeners_choices_never_reach_another(monkeypatch):
    from fastapi.testclient import TestClient
    from zhiyin import accounts, settings
    monkeypatch.setattr(server, "AUTH", True)
    a1, a2, b = (accounts.redeem(accounts.invite(n)) for n in ("A1", "A2", "B1"))
    c = TestClient(server.app)
    # each the very first thing a listener does, so there is no settings file yet
    c.cookies.set(accounts.COOKIE, accounts.new_session(a1))
    assert c.post("/api/settings/lane", json={"key": "k", "enabled": False}, headers={"X-Zhiyin-Uid": a1}).status_code == 200
    c.cookies.set(accounts.COOKIE, accounts.new_session(a2))
    assert c.post("/api/notme", json={"artist": "Pinkfong", "on": True}, headers={"X-Zhiyin-Uid": a2}).status_code == 200
    assert settings.DEFAULT == {"lanes": {}, "never": [], "picks_per_lane": 8, "not_me": {"songs": [], "artists": []}}
    with store.as_user(b):
        assert settings.not_me() == (set(), set()) and settings.load()["lanes"] == {}


def test_a_new_listeners_record_has_its_full_shape_before_any_like_is_read(monkeypatch):
    from fastapi.testclient import TestClient
    from zhiyin import accounts
    monkeypatch.setattr(server, "AUTH", True)
    monkeypatch.setattr(server, "_want_label", lambda: None)
    uid = accounts.redeem(accounts.invite("E1"))
    c = TestClient(server.app)
    c.cookies.set(accounts.COOKIE, accounts.new_session(uid))
    d = c.get("/api/ear", headers={"X-Zhiyin-Uid": uid}).json()
    assert d["songs"] == [] and d["facts"] == [] and d["eras"] == [] and d["sectors"] == [] and d["stage"] == "glimpse"


def test_a_rename_already_under_way_is_not_counted(monkeypatch):
    from fastapi import HTTPException
    from fastapi.testclient import TestClient
    from zhiyin import accounts, llm
    monkeypatch.setattr(server, "AUTH", True)
    monkeypatch.setattr(llm, "unavailable", lambda *a: None)

    def busy(kind, fn):
        raise HTTPException(409, "running")
    monkeypatch.setattr(server, "_start", busy)
    uid = accounts.redeem(accounts.invite("R2"))
    c = TestClient(server.app)
    c.cookies.set(accounts.COOKIE, accounts.new_session(uid))
    assert c.post("/api/ear/label", json={}, headers={"X-Zhiyin-Uid": uid}).status_code == 409
    assert not accounts.prefs(uid).get("label_rolls")
    with store.as_user(uid), pytest.raises(RuntimeError):
        server._label(print)   # no likes yet: no name, and the job counts as failed rather than done
