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
