import pytest

from zhiyin import server, store


def test_likes_made_before_connecting_go_across_once():
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
