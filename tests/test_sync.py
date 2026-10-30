import time
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
    assert parse_qs(urlparse(google.auth_url("s", "x", True, lang="zh-Hant")).query)["hl"] == ["zh-TW"]
    assert "hl" not in parse_qs(urlparse(google.auth_url("s", "x", True)).query)


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


def test_section_headings_are_not_shown_as_lyrics():
    from zhiyin import lyrics
    xs = ["hook", "[Chorus]", "Pre-Chorus 2:", "副歌：", "So can you just trust me", "Intro to you", ""]
    d = {"found": True, "lines": [{"t": i, "x": x} for i, x in enumerate(xs)]}
    assert [l["x"] for l in lyrics.for_reader(d, "zh-Hans")["lines"]] == ["So can you just trust me", "Intro to you", ""]


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


def _join(c, monkeypatch, who, mode="join", scope=None, start=None):
    from urllib.parse import parse_qs, urlparse
    from zhiyin import google
    scope = scope or f"openid {google.YT_READ}"
    monkeypatch.setattr(google, "exchange", lambda code, v: {"id_token": who, "scope": scope,
                                                              "access_token": "a", "refresh_token": "r"})
    monkeypatch.setattr(google, "claims", lambda tok: {"sub": tok, "email": f"{tok}@example.com", "name": tok.title()})
    c.cookies.clear()                     # a stranger's browser
    r = c.get(start or f"/auth/google/start?mode={mode}", follow_redirects=False)
    loc = r.headers["location"]
    if mode == "join" and server._join_state() == "open":
        assert "youtube.readonly" in loc and "%2Fyoutube+" not in loc and "%2Fyoutube&" not in loc   # read only
    if mode == "join" and server._join_state() == "full" and not start:
        assert "youtube" not in loc   # getting on the waitlist asks only who they are
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

    n = accounts.joined()                   # unticking YouTube on Google's page makes no account and takes no seat
    assert [_join(c, monkeypatch, "eve", scope="openid email").headers["location"] for _ in range(2)] == ["/login?e=noscope"] * 2
    assert accounts.by_google("eve") is None and accounts.joined() == n

    r = _join(c, monkeypatch, "ann")
    assert r.status_code == 303 and r.headers["location"] == "/" and accounts.COOKIE in r.cookies
    uid = accounts.by_google("ann")
    assert accounts.prefs(uid)["joined"] and started == ["setup"]
    with store.as_user(uid):
        assert not google.writes_back() and server._queue_rate("hp0KiJs0S5g", "LIKE") == "read-only"
        assert server._me()["sync_likes"] is False

    monkeypatch.setattr(server, "SEATS", accounts.joined() + 5)
    monkeypatch.setattr(llm, "pool_spent", lambda days: llm.POOL_USD - 1)
    assert server._join_state() == "full"     # seats left, but not the budget for one more first setup
    monkeypatch.setattr(llm, "pool_spent", lambda days: 0)
    monkeypatch.setattr(server, "SEATS", accounts.joined())
    r = _join(c, monkeypatch, "bo", scope="openid email")   # the last seat is taken: Bo goes on the waitlist
    assert r.headers["location"] == "/login?e=full" and accounts.by_google("bo") is None
    assert store.db().execute("select count(*) from waitlist where sub='bo'").fetchone()[0] == 1

    con = store.db()
    con.execute("update waitlist set admitted=1 where sub='bo'")
    con.commit()
    assert _join(c, monkeypatch, "bo", mode="login").headers["location"] == "/auth/google/start?mode=join&yt=1"   # signing in joins
    assert _join(c, monkeypatch, "bo", scope="openid email").headers["location"] == "/auth/google/start?mode=join&yt=1"
    r = _join(c, monkeypatch, "bo", start="/auth/google/start?mode=join&yt=1")
    assert r.headers["location"] == "/" and accounts.by_google("bo")
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


def test_the_way_in_is_counted_by_where_people_came_from_never_who(monkeypatch):
    from fastapi.testclient import TestClient
    monkeypatch.setattr(server, "AUTH", True)
    monkeypatch.setattr(server, "SAMPLE_ON", [server._install_sample()])
    con = store.db()
    con.execute("delete from events")   # the data folder is shared by the whole run
    con.commit()
    c = TestClient(server.app)
    page = c.get("/?ref=Reddit", headers={"accept-language": "en-US"}).text
    assert 'property="og:image"' in page and "/static/og-en.png" in page and "drawn as a record" in page
    assert c.cookies.get("zy_r") == "reddit"
    c.get("/", headers={"accept-language": "en-US"})   # a second look from the same browser is not a new visit
    TestClient(server.app).get("/", headers={"referer": "https://www.threads.net/@x/post/1"})
    TestClient(server.app).get("/", headers={"user-agent": "Twitterbot/1.0"})   # a link preview is not a visit
    assert c.post("/api/event", json={"name": "sample_play"}).status_code == 200
    assert c.post("/api/event", json={"name": "anything"}).status_code == 422
    rows = {(r["name"], r["ref"]): r["n"] for r in store.db().execute("select name, ref, n from events")}
    assert rows == {("visit", "reddit"): 1, ("visit", "threads.net"): 1, ("sample_play", "reddit"): 1}
    assert [c[1] for c in store.db().execute("pragma table_info(events)")] == ["day", "name", "ref", "n"]


def test_first_runs_wait_in_order_and_are_told_their_place(monkeypatch):
    monkeypatch.setattr(server, "HEAVY_AT_ONCE", 1)
    first, second, third = ({"msg": ""} for _ in range(3))
    server._line.extend([first, second])
    said = []
    import threading
    t = threading.Thread(target=server._take_turn, args=(third, said.append))
    t.start()
    import time as _t
    _t.sleep(0.2)
    assert said and "2" in said[-1]   # two ahead of it: the one running and the one waiting
    server._leave_line(first)
    server._leave_line(second)
    t.join(2)
    assert not t.is_alive() and len(server._line) == 1 and server._line[0] is third
    server._leave_line(third)


def test_likes_not_read_again_in_30_days_are_deleted_but_the_account_stays(monkeypatch):
    from zhiyin import accounts, google
    monkeypatch.setattr(google, "disconnect", lambda uid: None)
    owner_prefs = accounts.prefs(store.OWNER)
    old, now = time.time() - 29 * 86400, time.time()
    gone = accounts.redeem(accounts.invite("Gone"))
    here = accounts.redeem(accounts.invite("Here"))
    mine = accounts.redeem(accounts.invite("Mine", mine=True))
    for u in (gone, here, mine):
        accounts.set_status(u, "ready")
    accounts.set_prefs(gone, synced=old, google_error="revoked", ref="x")
    accounts.set_prefs(here, synced=now - 3 * 86400)
    accounts.set_prefs(mine, synced=old)
    accounts.set_prefs(store.OWNER, synced=old)
    with store.as_user(gone):
        store.write_json(store.LIBRARY, {"tracks": [{"vid": "a"}]})
        store.write_json(store.GLIMPSE, {"songs": []})
        store.write_json(store.ASKS, {"kept": True})
    con = store.db()
    con.execute("insert into feedback (uid, vid, action, ts) values (?, 'a', 'like', 0)", (gone,))
    con.commit()
    try:
        users = [accounts.get(u) for u in (store.OWNER, gone, here, mine)]
        store.kv_set("forget_from", None)
        assert server._forget_stale(users) == set()   # a server that just got this rule waits a few days first
        assert accounts.get(gone)["status"] == "ready"
        store.kv_set("forget_from", time.time() - 1)
        assert server._forget_stale(users) == {gone}
        u = accounts.get(gone)
        assert u and u["status"] == "new" and "synced" not in u["prefs"] and u["prefs"]["forgot"]
        with store.as_user(gone):
            assert not store.LIBRARY.exists() and not store.GLIMPSE.exists() and store.ASKS.exists()
        assert store.db().execute("select count(*) from feedback where uid=?", (gone,)).fetchone()[0] == 1
        assert accounts.get(here)["status"] == accounts.get(mine)["status"] == "ready"
        assert server._forget_stale([accounts.get(gone)]) == set()   # nothing left to forget: it is new again

        # most listeners unread at once is the connection breaking, not people leaving: nothing is deleted
        many = [accounts.redeem(accounts.invite(f"L{i}")) for i in range(4)]
        for m in many:
            accounts.set_status(m, "ready")
            accounts.set_prefs(m, synced=old)
        assert server._forget_stale([accounts.get(m) for m in many + [here]]) == set()
        assert all(accounts.get(m)["status"] == "ready" for m in many)
    finally:
        accounts.set_prefs(store.OWNER, synced=owner_prefs.get("synced"))


def test_a_failed_read_of_the_likes_waits_before_trying_again(monkeypatch):
    from zhiyin import accounts
    uid = accounts.redeem(accounts.invite("Retry"))
    monkeypatch.setitem(server._jobs, (uid, "sync"), {"running": False, "error": "quota", "ended": time.time() - 3600})
    assert server._sync_waits(uid)
    server._jobs[(uid, "sync")]["ended"] = time.time() - 7 * 3600
    assert not server._sync_waits(uid)
    server._jobs[(uid, "sync")] = {"running": False, "error": None, "ended": time.time()}
    assert not server._sync_waits(uid)   # a read that worked doesn't hold the next one back


def test_a_read_that_worked_counts_even_if_filing_the_new_likes_fails(monkeypatch):
    from zhiyin import accounts, library, profile
    uid = accounts.redeem(accounts.invite("Filed"))
    monkeypatch.setattr(library, "sync_from_google", lambda log=None: {"added": 3, "songs": 30})

    def no_claude(log=None):
        raise RuntimeError("Claude is out")
    monkeypatch.setattr(profile, "absorb_new", no_claude)
    with store.as_user(uid), pytest.raises(RuntimeError):
        server._sync_likes(lambda *a, **k: None)
    assert time.time() - accounts.prefs(uid)["synced"] < 5


def test_likes_a_reread_took_in_join_the_stations_on_the_next_sync(monkeypatch):
    from zhiyin import library, profile
    calls = []
    monkeypatch.setattr(library, "sync_from_google", lambda log=None: {"added": 0, "songs": 30})
    monkeypatch.setattr(profile, "absorb_new", lambda log=None: calls.append(1) or 0)
    server._sync_likes(lambda *a, **k: None)
    assert calls == [1]


def test_first_run_steps_count_once_however_often_it_is_retried():
    from zhiyin import accounts
    con = store.db()
    con.execute("delete from events")
    con.commit()
    uid = accounts.redeem(accounts.invite("Steps"))
    accounts.set_prefs(uid, ref="zhihu")
    with store.as_user(uid):
        for _ in range(3):
            server._milestone("setup_error")
        server._milestone("ready")
    rows = {(r["name"], r["ref"]): r["n"] for r in store.db().execute("select name, ref, n from events")}
    assert rows == {("setup_error", "zhihu"): 1, ("ready", "zhihu"): 1}


def test_made_up_sources_cannot_grow_the_counts_without_end():
    con = store.db()
    con.execute("delete from events")
    con.commit()
    for i in range(store.REFS_A_DAY + 5):
        store.count("visit", f"r{i}")
    refs = {r["ref"] for r in store.db().execute("select ref from events")}
    assert len(refs) == store.REFS_A_DAY + 1 and "other" in refs


def test_a_first_run_that_fails_leaves_the_line():
    from zhiyin import accounts
    uid = accounts.redeem(accounts.invite("Fails"))

    def boom(log):
        raise RuntimeError("nope")
    with store.as_user(uid):
        j = server._start("setup", boom)
    for _ in range(50):
        if not j["running"]:
            break
        time.sleep(0.05)
    assert not j["running"] and j["error"] == "nope" and not any(x is j for x in server._line)


def test_an_account_without_a_youtube_channel_is_told_what_to_do(monkeypatch):
    import httpx
    from zhiyin import accounts, google

    def refuse(uid, method, path, cost, **kw):
        r = httpx.Response(401, json={"error": {"errors": [{"reason": "youtubeSignupRequired"}]}},
                           request=httpx.Request(method, f"{google.API}/{path}"))
        r.raise_for_status()
    monkeypatch.setattr(google, "_call", refuse)
    uid = accounts.redeem(accounts.invite("NoChannel"))
    with store.as_user(uid):
        with pytest.raises(google.NoChannel):
            server._setup(lambda *a, **k: None)
        me = server._me()
    assert me["status"] == "error" and me["setup_issue"] == "nochannel"


def test_what_zhiyin_is_and_does_with_google_data_reads_without_signing_in(monkeypatch):
    from fastapi.testclient import TestClient
    monkeypatch.setattr(server, "AUTH", True)
    c = TestClient(server.app)
    for lang, word in (("en-US", "youtube.readonly"), ("zh-TW", "唯讀"), ("zh-CN", "只读")):
        page = c.get("/about", headers={"accept-language": lang}).text
        assert word in page and 'href="/privacy"' in page and "<!--lang" not in page
    monkeypatch.setattr(server, "CDN", "")
    assert "{cdn}" not in c.get("/privacy").text and "Cloudflare" not in c.get("/privacy").text
    monkeypatch.setattr(server, "CDN", "Cloudflare")
    page = c.get("/privacy", headers={"accept-language": "en-US"}).text
    assert "<b>Cloudflare</b>" in page and "{cdn}" not in page and 'href="/about"' in page
    for path in ("/", "/about", "/privacy"):
        assert "no-transform" in c.get(path).headers["cache-control"]   # a CDN must not inject its analytics


def test_a_request_can_be_taken_off_the_list_one_or_all():
    from fastapi.testclient import TestClient
    with store.as_user(store.OWNER):
        store.write_json(store.ASKS, [{"created": 3.5, "q": "c", "picks": []}, {"created": 2.25, "q": "b", "picks": []},
                                      {"created": 1.0, "q": "a", "picks": []}])
    c = TestClient(server.app)
    assert [a["q"] for a in c.post("/api/ask/delete", json={"created": 2.25}).json()["asks"]] == ["c", "a"]
    assert c.post("/api/ask/delete", json={}).json()["asks"] == []


def test_a_station_keeps_their_words_and_can_be_repicked_alone(monkeypatch):
    from fastapi.testclient import TestClient
    from zhiyin import edition, llm, settings
    c = TestClient(server.app)
    with store.as_user(store.OWNER):
        assert c.post("/api/settings/lane", json={"key": "jazz", "note": "  少点  trap 鼓点 "}).status_code == 200
        assert settings.lane_view({"key": "jazz"})["note"] == "少点 trap 鼓点"
    started = {}
    monkeypatch.setattr(llm, "unavailable", lambda *a: None)
    monkeypatch.setattr(server, "_start", lambda name, fn: started.update(name=name, fn=fn))
    monkeypatch.setattr(edition, "build", lambda log=None, only=None: started.update(only=only))
    c.post("/api/refresh", json={"lanes": ["jazz"]})
    started["fn"](print)
    assert started["only"] == {"jazz"}
    c.post("/api/refresh")
    started["fn"](print)
    assert started["only"] is None


def test_a_new_edition_comes_a_week_after_the_last_at_five(monkeypatch):
    import datetime as dt
    made = dt.datetime(2026, 10, 20, 9, 30)
    ed = {"created": made.timestamp()}

    class Now(dt.datetime):
        at = None

        @classmethod
        def now(cls, tz=None):
            return cls.at
    monkeypatch.setattr(server.dt, "datetime", Now)
    for at, stale in ((dt.datetime(2026, 10, 21, 6), False), (dt.datetime(2026, 10, 27, 4, 59), False),
                      (dt.datetime(2026, 10, 27, 5), True)):
        Now.at = at
        assert server._edition_stale(ed) is stale, at
    Now.at = dt.datetime(2026, 10, 28, 6)
    assert not server._edition_stale({**ed, "checked": dt.datetime(2026, 10, 27, 5, 30).timestamp()})   # nothing played: checked, wait another week
    assert server._edition_stale(None)


def test_only_the_owner_sees_who_else_listens(monkeypatch):
    from fastapi.testclient import TestClient
    from zhiyin import accounts
    monkeypatch.setattr(server, "AUTH", True)
    friend = accounts.redeem(accounts.invite("Ming"))
    second = accounts.redeem(accounts.invite("", mine=True))
    for uid in (friend, second):   # the owner's own second account is a listener too, not the admin
        c = TestClient(server.app)
        c.cookies.set(accounts.COOKIE, accounts.new_session(uid))
        assert c.get("/api/users").status_code == 403
        assert not c.get("/api/state").json()["me"]["owner"]   # the page shows the friends list only to the owner
    owner = TestClient(server.app)
    owner.cookies.set(accounts.COOKIE, accounts.new_session(store.OWNER))
    assert {u["name"] for u in owner.get("/api/users").json()["users"]} >= {"Ming"}


def _ne(i, title, artist, dur=200, ar=None):
    return {"vid": f"n{i}", "ne": i, "ne_ar": ar or [i * 10], "title": title, "artists": [{"name": artist}], "album": None,
            "dur": dur, "liked_est": f"2026-0{1 + i % 9}-01", "source": "163", "long": False, "pic": "", "year": 0, "pop": 50}


def _hit(vid, title, artist, dur=200, kind="ATV"):
    return {"vid": vid, "title": title, "artists": [{"name": artist, "id": f"UC{vid}"}], "album": None, "type": kind, "dur": dur}


def test_a_netease_like_is_found_on_youtube_music_by_title_length_and_artist_in_either_script(monkeypatch):
    from zhiyin import library, netease, ytm
    asked = []
    monkeypatch.setattr(netease, "aliases", lambda aid: asked.append(aid) or (["Eason Chan"] if aid == 10 else []))
    hits = {
        "陈奕迅 爱情转移": [_hit("cover0000a", "爱情转移", "陈影"),                 # the same script, another singer: a cover
                        _hit("karaoke00a", "愛情轉移 (Karaoke)", "Eason Chan"),
                        _hit("easonchan1", "愛情轉移", "Eason Chan")],            # NetEase knows him by this name too
        "许巍 曾经的你": [_hit("xuwei00000", "曾经的你 - The Way You Are", "Xu Wei", dur=230)],   # half a minute off
        "Charlie Puth LA Girls": [_hit("davidtort1", "LA Girls", "David Tort")],
        "五月天 拥抱": [_hit("mayday0001", "擁抱", "五月天", dur=203)],
        "宋冬野 斑马，斑马": [_hit("songdongye", "斑马，斑马", "Song Dongye")],     # pinyin, and no NetEase alias
        "那英 默": [_hit("nayingmo01", "默 - Mo", "Na Ying")],
        "Álvaro Soler Sofía": [_hit("alvarosofi", "Sofia", "Alvaro Soler")],
        "宋冬野 安和桥": [_hit("songdongy2", "安和桥", "Sun Yanzi")],
    }
    monkeypatch.setattr(ytm, "search", lambda q, kind="songs", limit=10: hits.get(q, []))
    assert library.match_app(_ne(1, "爱情转移", "陈奕迅"))["vid"] == "easonchan1" and asked == [10]
    assert library.match_app(_ne(2, "曾经的你", "许巍")) is None
    assert library.match_app(_ne(3, "LA Girls", "Charlie Puth")) is None
    assert library.match_app(_ne(4, "拥抱", "五月天"))["vid"] == "mayday0001"
    assert library.match_app(_ne(5, "斑马，斑马", "宋冬野"))["vid"] == "songdongye"
    assert library.match_app(_ne(6, "默", "那英"))["vid"] == "nayingmo01"
    assert library.match_app(_ne(7, "Sofía", "Álvaro Soler"))["vid"] == "alvarosofi"
    assert library.match_app(_ne(8, "安和桥", "宋冬野")) is None   # another singer's pinyin


def test_netease_likes_become_the_library_and_an_unliked_song_leaves(monkeypatch):
    from zhiyin import accounts, candidates, library, netease
    uid = accounts.redeem(accounts.invite("Lin"))
    likes = [_ne(1, "爱情转移", "陈奕迅"), _ne(2, "孤岛", "思敏哥哥"), _ne(3, "拥抱", "五月天")]
    found = {1: _hit("easonchan1", "愛情轉移", "Eason Chan"), 3: _hit("mayday0001", "擁抱", "五月天")}
    monkeypatch.setattr(library, "match_app", lambda t: found.get(t["ne"]))
    monkeypatch.setattr(netease, "aliases", lambda aid: [])
    monkeypatch.setattr(netease, "ranking", lambda owner: {3: 100} if owner == 77 else {})

    def got():
        return {"key": "163:5", "owner": 77, "tracks": list(likes), "total": len(likes)}
    seen = []
    with store.as_user(uid):
        r = library.sync_from_app("x", log=lambda *a, **k: None, glimpsed=lambda: seen.append(store.read_json(store.GLIMPSE)), got=got())
        assert r["first"] and r["songs"] == 2 and r["unmatched"] == 1 and len(seen[0]["songs"]) == 3
        lib = library.load()
        assert [(t["vid"], t["rank"], t["ne_score"]) for t in lib] == [("easonchan1", 0, None), ("mayday0001", 1, 100)]
        assert lib[0]["liked_est"] == "2026-02-01" and lib[0]["source"] == "163" and not store.GLIMPSE.exists()
        known = candidates.Known(lib, {})
        # the one YouTube Music has under another name is already theirs, in either script
        assert known.reject({"vid": "other00001", "title": "孤島", "artists": [{"name": "思敏哥哥"}]}) == "same song"
        assert known.reject({"vid": "other00002", "title": "爱情转移 (Live)", "artists": [{"name": "陈奕迅"}]}) == "same song"

        likes[:] = [_ne(4, "红玫瑰", "陈奕迅"), likes[0], likes[1]]   # one new like; 拥抱 unliked on NetEase
        found[4] = _hit("easonchan2", "紅玫瑰", "Eason Chan")
        r = library.sync_from_app("x", log=lambda *a, **k: None, got=got())
        assert (r["added"], r["removed"], r["first"]) == (1, 1, False)
        assert [(t["vid"], t["rank"]) for t in library.load()] == [("easonchan2", -1), ("easonchan1", 0)]



def test_qq_music_likes_are_matched_with_qq_names_and_kept_without_a_ranking(monkeypatch):
    from zhiyin import accounts, library, netease, qqmusic, ytm
    uid = accounts.redeem(accounts.invite("Qi"))
    asked = []
    monkeypatch.setattr(qqmusic, "aliases", lambda mid: asked.append(mid) or (["Eason Chan"] if mid == "S1" else []))
    monkeypatch.setattr(netease, "aliases", lambda aid: pytest.fail("a QQ Music singer looked up on NetEase"))
    monkeypatch.setattr(netease, "ranking", lambda owner: pytest.fail("QQ Music has no ranking to read"))
    hits = {"陈奕迅 富士山下": [_hit("easonfuji1", "富士山下", "Eason Chan")],
            "华莎 (화사) Maria": [_hit("hwasamaria", "Maria", "화사")],
            "G.E.M.邓紫棋 光年之外": [_hit("gemlight01", "光年之外", "G.E.M.")]}
    monkeypatch.setattr(ytm, "search", lambda q, kind="songs", limit=10: hits.get(q, []))

    def qq(i, title, singer, mid):
        return {**_ne(i, title, singer, ar=[mid]), "vid": f"q{i}", "source": "qq", "pop": None, "released": "2009-04-14"}
    likes = [qq(1, "富士山下", "陈奕迅", "S1"), qq(2, "Maria", "华莎 (화사)", "S2"), qq(3, "光年之外", "G.E.M.邓紫棋", "S3"),
             qq(4, "某首独占", "某人", "S4")]
    assert library.match_app(likes[0])["vid"] == "easonfuji1" and asked == ["S1"]   # the name QQ Music gives him in English
    assert library.match_app(likes[1])["vid"] == "hwasamaria"                         # the name inside her QQ Music name
    with store.as_user(uid):
        r = library.sync_from_app("x", log=lambda *a, **k: None, got={"key": "qq:u:oK**", "owner": None, "tracks": likes, "total": 4})
        lib = library.load()
        assert r["unmatched"] == 1 and {t["source"] for t in lib} == {"qq"} and lib[0]["ne_score"] is None
        assert (store.read_json(store.LIBRARY) or {})["source"] == "qq"
        # the taste's name is asked from the year each song came out, not from like dates QQ Music never showed
        from zhiyin import llm, profile
        seen = {}
        monkeypatch.setattr(llm, "call", lambda prompt, system, schema, **k: seen.update(prompt=prompt, system=system) or {"label": "港乐"})
        accounts.set_prefs(uid, netease={"link": "https://y.qq.com/n/ryqq/playlist/7256912512"})
        assert profile.label() == "港乐"
        assert seen["prompt"].startswith("2009 | ") and "QQ Music doesn't show when a song was liked" in seen["system"]


def test_a_netease_card_becomes_an_account_with_google_saying_only_who_they_are(monkeypatch):
    from urllib.parse import parse_qs, urlparse
    from fastapi.testclient import TestClient
    from zhiyin import accounts, google, llm
    monkeypatch.setattr(server, "AUTH", True)
    monkeypatch.setattr(llm, "HOSTED", True)
    monkeypatch.setattr(llm, "API_KEY", True)
    monkeypatch.setattr(google, "client", lambda: {"id": "x", "secret": "y"})
    started = []
    monkeypatch.setattr(server, "_start", lambda kind, fn: started.append((store.uid(), kind)))
    monkeypatch.setattr(server, "SEATS", accounts.joined() + 1)
    link = "分享歌单: https://music.163.com/playlist?id=24381616&userid=1 (来自@网易云音乐)"

    def come(who):
        monkeypatch.setattr(google, "exchange", lambda code, v: {"id_token": who, "scope": "openid email"})
        monkeypatch.setattr(google, "claims", lambda tok: {"sub": tok, "email": f"{tok}@example.com", "name": tok.title()})
        c = TestClient(server.app)
        assert c.post("/api/card/follow", json={"link": "not a link"}).status_code == 422
        r = c.post("/api/card/follow", json={"link": link})
        assert r.json()["go"] == "/auth/google/start?mode=join&src=163" and "zy_n" in r.cookies
        r = c.get(r.json()["go"], follow_redirects=False)
        assert "youtube" not in r.headers["location"]      # nothing is asked of their YouTube
        state = parse_qs(urlparse(r.headers["location"]).query)["state"][0]
        return c.get(f"/auth/google/callback?state={state}&code=x", follow_redirects=False)

    r = come("mei")
    uid = accounts.by_google("mei")
    assert r.headers["location"] == "/" and accounts.COOKIE in r.cookies and uid
    assert accounts.prefs(uid)["netease"] == {"link": link} and started == [(uid, "setup")]
    assert accounts.get(uid)["email"] == "mei@example.com" and not google.connected(uid)
    with store.as_user(uid):
        assert server._app_likes() == link and server._can_read(accounts.get(uid))

    r = come("kai")                                        # no seat left: waits, and the link waits too
    assert r.headers["location"] == "/login?e=full" and accounts.by_google("kai") is None
    con = store.db()
    assert con.execute("select src from waitlist where sub='kai'").fetchone()["src"] == link
    con.execute("update waitlist set admitted=1 where sub='kai'")
    con.commit()
    r = _join(TestClient(server.app), monkeypatch, "kai", mode="login")   # let in: signing in starts from NetEase
    uid = accounts.by_google("kai")
    assert r.headers["location"] == "/" and accounts.prefs(uid)["netease"] == {"link": link} and started[-1] == (uid, "setup")


def test_a_qq_music_card_follows_the_same_way_and_the_account_knows_its_app(monkeypatch):
    from urllib.parse import parse_qs, urlparse
    from fastapi.testclient import TestClient
    from zhiyin import accounts, google, llm
    monkeypatch.setattr(server, "AUTH", True)
    monkeypatch.setattr(llm, "HOSTED", True)
    monkeypatch.setattr(llm, "API_KEY", True)
    monkeypatch.setattr(google, "client", lambda: {"id": "x", "secret": "y"})
    monkeypatch.setattr(server, "_start", lambda kind, fn: None)
    monkeypatch.setattr(server, "SEATS", accounts.joined() + 1)
    link = "https://i.y.qq.com/n2/m/share/profile_v2/index.html?encrypt_uin=oKcPoKoP7i4soz**"
    c = TestClient(server.app)
    r = c.post("/api/card/follow", json={"link": "https://y.qq.com/n/ryqq/songDetail/002q83Sd2G7Y7D"}, headers={"accept-language": "zh-CN"})
    assert r.status_code == 422 and "一首歌" in r.json()["detail"] and "QQ 音乐" in r.json()["detail"]
    r = c.post("/api/card/follow", json={"link": link})
    assert r.json()["go"] == "/auth/google/start?mode=join&src=163"
    day = store.db().execute("select sum(n) from events where name='join_qq'").fetchone()[0]
    assert day == 1
    monkeypatch.setattr(google, "exchange", lambda code, v: {"id_token": "qiao", "scope": "openid email"})
    monkeypatch.setattr(google, "claims", lambda tok: {"sub": tok, "email": f"{tok}@example.com", "name": tok.title()})
    r = c.get(r.json()["go"], follow_redirects=False)
    state = parse_qs(urlparse(r.headers["location"]).query)["state"][0]
    c.get(f"/auth/google/callback?state={state}&code=x", follow_redirects=False)
    uid = accounts.by_google("qiao")
    assert accounts.prefs(uid)["netease"] == {"link": link}
    c.cookies.set(accounts.COOKIE, accounts.new_session(uid))
    assert c.get("/api/state").json()["me"]["netease"]["app"] == "qq"


def test_an_account_without_likes_yet_can_start_from_netease_but_not_change_source(monkeypatch):
    from fastapi import HTTPException
    from zhiyin import accounts, google, netease
    uid = accounts.redeem(accounts.invite("Yu"))
    started = []
    monkeypatch.setattr(server, "_start", lambda kind, fn: started.append(kind))
    monkeypatch.setattr(netease, "likes", lambda link: {"key": "163:9", "owner": 1, "tracks": [], "total": 30})
    with store.as_user(uid):
        server.app_use(server.LinkReq(link="https://music.163.com/#/user/home?id=1"))
        assert accounts.prefs(uid)["netease"] == {"link": "https://music.163.com/playlist?id=9"} and started == ["setup"]
        monkeypatch.setattr(google, "connected", lambda u=None: True)
        with pytest.raises(HTTPException) as e:
            server.app_use(server.LinkReq(link="https://music.163.com/playlist?id=9"))
        assert e.value.status_code == 409
    monkeypatch.setattr(google, "disconnect", lambda u: None)
    server._forget_youtube(uid)                            # unreadable for 30 days: the link goes with the likes
    assert "netease" not in accounts.prefs(uid)


WECHAT_IOS = ("Mozilla/5.0 (iPhone; CPU iPhone OS 18_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 "
              "MicroMessenger/8.0.54(0x18003637) NetType/WIFI Language/zh_CN")
LINE_ANDROID = ("Mozilla/5.0 (Linux; Android 14; Pixel 8 Build/AP2A; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 "
                "Chrome/130.0.6723.58 Mobile Safari/537.36 Line/14.19.1")
SAFARI = ("Mozilla/5.0 (iPhone; CPU iPhone OS 18_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.1 "
          "Mobile/15E148 Safari/604.1")
HOME_SCREEN = "Mozilla/5.0 (iPhone; CPU iPhone OS 18_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148"


def test_inside_wechat_or_line_signing_in_moves_to_the_phones_browser_and_keeps_the_netease_link(monkeypatch):
    import json
    import re
    from urllib.parse import parse_qs, unquote, urlparse
    from fastapi.testclient import TestClient
    from zhiyin import accounts, google, llm
    monkeypatch.setattr(server, "AUTH", True)
    monkeypatch.setattr(llm, "HOSTED", True)
    monkeypatch.setattr(llm, "API_KEY", True)
    monkeypatch.setattr(google, "client", lambda: {"id": "x", "secret": "y"})
    monkeypatch.setattr(server, "SEATS", accounts.joined() + 5)
    c = TestClient(server.app)

    def start(ua, path="/auth/google/start?mode=join"):
        return c.get(path, headers={"user-agent": ua}, follow_redirects=False)

    r = start(WECHAT_IOS)                                  # Google would answer 403 disallowed_useragent
    assert r.status_code == 200
    gate = json.loads(re.search(r"const G = (\{.*?\});", r.text).group(1))
    assert gate["mode"] == "outside" and gate["app"] == "wechat" and gate["url"].endswith("/auth/google/start?mode=join")
    for ua in (SAFARI, HOME_SCREEN):                       # a real browser, and a home-screen web app, go straight on
        assert "accounts.google.com" in start(ua).headers["location"]

    link = "https://music.163.com/playlist?id=24381616"
    assert c.post("/api/card/follow", json={"link": link}).status_code == 200
    gate = json.loads(re.search(r"const G = (\{.*?\});", start(WECHAT_IOS, "/auth/google/start?mode=join&src=163").text).group(1))
    assert unquote(parse_qs(urlparse(gate["url"]).query)["ne"][0]) == link   # the browser has no cookie: the link travels
    r = start(LINE_ANDROID, "/auth/google/start?mode=join&src=163")
    assert r.status_code == 303 and r.headers["location"].startswith("/card?ne=") and r.headers["location"].endswith("&openExternalBrowser=1")


def test_their_own_likes_are_found_in_either_script_by_title_singer_or_both():
    from zhiyin import library
    uid = "finder01"
    with store.as_user(uid):
        library.save([
            {"rank": 0, "vid": "aaaaaaaaaa1", "title": "愛情轉移", "artists": [{"name": "陳奕迅"}], "album": {"name": "認了吧"}, "dur": 260, "long": False},
            {"rank": 1, "vid": "aaaaaaaaaa2", "title": "富士山下", "artists": [{"name": "陳奕迅"}], "album": None, "dur": 259, "long": False},
            {"rank": 2, "vid": "aaaaaaaaaa3", "title": "Love Story", "artists": [{"name": "Taylor Swift"}], "album": None, "dur": 235, "long": False},
            {"rank": 3, "vid": "aaaaaaaaaa4", "title": "她說", "artists": [{"name": "林俊傑"}], "album": None, "dur": 320, "long": False},
        ])
        assert [t["vid"] for t in library.find("爱情")] == ["aaaaaaaaaa1"]                 # simplified finds traditional
        assert [t["vid"] for t in library.find("陈奕迅")] == ["aaaaaaaaaa1", "aaaaaaaaaa2"]   # a singer: newest first
        assert [t["vid"] for t in library.find("富士 陈奕迅")] == ["aaaaaaaaaa2"]            # every word must be there
        assert [t["vid"] for t in library.find("love")][0] == "aaaaaaaaaa3"                 # a title beats an album or a singer
        assert library.find("   ") == [] and library.find("周杰伦") == []


def test_a_library_too_small_for_stations_is_read_again_and_goes_on_by_itself(monkeypatch):
    calls = []
    monkeypatch.setattr(server, "_reread_likes", lambda log: calls.append("read") or {"songs": n})
    monkeypatch.setattr(server, "_setup", lambda log: calls.append("setup") or "built")
    n = server.MIN_LIKES - 1
    assert server._look_again(print) == {"songs": n} and calls == ["read"]
    n = server.MIN_LIKES
    assert server._look_again(print) == "built" and calls == ["read", "read", "setup"]


def test_old_lyrics_without_word_timing_are_looked_up_once_more_behind_the_scenes(monkeypatch):
    import json
    import threading
    from zhiyin import lyrics
    monkeypatch.setattr(threading, "Thread", lambda target, daemon: type("T", (), {"start": lambda s: target()})())
    old = {"vid": "oldlyric001", "found": True, "source": "LRCLIB", "words": False, "lines": [{"t": 1, "x": "a"}], "ts": lyrics.RECHECK_BEFORE - 60}
    for vid, words in (("oldlyric001", True), ("oldlyric002", False)):
        lyrics._path(vid).write_text(json.dumps({**old, "vid": vid}))
        found = {"vid": vid, "found": True, "source": "NetEase", "words": words, "lines": [{"t": 1, "x": "a", "w": [[1, 0.5, "a"]]}], "ts": 2e9}
        monkeypatch.setattr(lyrics, "resolve", lambda *a, f=found: f)
        assert lyrics.get(vid, "t", ["a"])["source"] == "LRCLIB"          # shown as it was, this once
    assert json.loads(lyrics._path("oldlyric001").read_text())["source"] == "NetEase"
    kept = json.loads(lyrics._path("oldlyric002").read_text())
    assert kept["source"] == "LRCLIB" and kept["rechecked"]
    monkeypatch.setattr(lyrics, "resolve", lambda *a: pytest.fail("looked up again"))
    lyrics.get("oldlyric002", "t", ["a"])                                  # once is enough
