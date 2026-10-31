from urllib.parse import parse_qs, urlsplit

import pytest
from fastapi.testclient import TestClient

from zhiyin import accounts, google, server, store


@pytest.mark.parametrize("write_scope", [google.YT_SCOPE, google.YT_FORCE_SSL])
def test_feature_scopes_and_manifest_match_the_real_authorization_requests(monkeypatch, write_scope):
    monkeypatch.setattr(google, "client", lambda: {"id": "review-client"})
    monkeypatch.setattr(google, "WRITE_SCOPE", write_scope)
    for flow, connect, write, expected in (
        ("sign_in", False, False, set(google.BASE_SCOPES.split())),
        ("connect", True, False, {*google.BASE_SCOPES.split(), google.YT_READ}),
        ("optional_write", True, True, {*google.BASE_SCOPES.split(), write_scope}),
    ):
        q = parse_qs(urlsplit(google.auth_url("state", "challenge", connect, write=write)).query)
        assert set(q["scope"][0].split()) == expected
        assert set(google.scope_manifest()["flows"][flow]) == expected
        assert q["state"] == ["state"] and q["code_challenge_method"] == ["S256"]
        assert (q.get("access_type") == ["offline"]) is connect
    assert set(google.scope_manifest()["all_requested_scopes"]) == {
        *google.BASE_SCOPES.split(), google.YT_READ, write_scope,
    }


@pytest.mark.parametrize("scope,can_write", [(google.YT_READ, False), (google.YT_SCOPE, True),
                                           (google.YT_FORCE_SSL, True)])
def test_granted_tokens_keep_working_across_a_write_scope_migration(scope, can_write):
    uid = accounts.create("Scope review")
    google.save_tokens(uid, {"access_token": "access-test", "refresh_token": "refresh-test", "scope": scope})
    assert google.connected(uid)
    assert google.writes_back(uid) is can_write
    raw = store.db().execute("select tokens from users where id=?", (uid,)).fetchone()[0]
    assert b"access-test" not in raw and b"refresh-test" not in raw
    assert "tokens" not in accounts.get(uid)


def test_write_upgrade_backfills_previous_likes_only_after_the_grant(monkeypatch):
    monkeypatch.setattr(server, "AUTH", True)
    monkeypatch.setattr(google, "client", lambda: {"id": "review-client"})
    monkeypatch.setattr(google, "WRITE_SCOPE", google.YT_FORCE_SSL)
    monkeypatch.setattr(server, "_start", lambda *args: None)
    uid = accounts.create("Upgrade review")
    accounts.link_google(uid, "upgrade-sub", "review@example.com", "Reviewer")
    accounts.set_prefs(uid, sync_likes=False)
    google.save_tokens(uid, {"access_token": "access-test", "refresh_token": "refresh-test", "scope": google.YT_READ})
    con = store.db()
    con.execute("insert into feedback (vid, action, ts, uid) values ('upgrade-song', 'like', 1, ?)", (uid,))
    con.commit()
    client = TestClient(server.app)
    client.cookies.set(accounts.COOKIE, accounts.new_session(uid))
    result = client.post("/api/account/sync-likes", json={"on": True}, headers={"X-Zhiyin-Uid": uid})
    assert result.status_code == 200 and "grant" in result.json()
    assert not accounts.prefs(uid)["sync_likes"]
    assert con.execute("select count(*) from outbox where uid=?", (uid,)).fetchone()[0] == 0
    redirect = client.get(result.json()["grant"], follow_redirects=False)
    q = parse_qs(urlsplit(redirect.headers["location"]).query)
    assert google.YT_FORCE_SSL in q["scope"][0].split() and google.YT_SCOPE not in q["scope"][0].split()
    monkeypatch.setattr(google, "exchange", lambda *args: {
        "id_token": "test-id", "scope": google.YT_FORCE_SSL, "access_token": "access-test",
    })
    monkeypatch.setattr(google, "claims", lambda *args: {
        "sub": "upgrade-sub", "email": "review@example.com", "name": "Reviewer",
    })
    result = client.get("/auth/google/callback", params={"state": q["state"][0], "code": "test-code"},
                        follow_redirects=False)
    assert result.status_code == 303
    assert accounts.prefs(uid)["sync_likes"] and google.writes_back(uid)
    assert google._load(uid)["refresh_token"] == "refresh-test"
    assert [r["vid"] for r in con.execute("select vid from outbox where uid=?", (uid,))] == ["upgrade-song"]
    assert store.kv_get(f"oauth:{q['state'][0]}") is None


def test_oauth_callback_rejects_a_different_browser_before_exchanging_tokens(monkeypatch):
    monkeypatch.setattr(server, "AUTH", True)
    monkeypatch.setattr(google, "client", lambda: {"id": "review-client"})

    def unexpected_exchange(*args):
        pytest.fail("a different browser must not exchange the authorization code")

    monkeypatch.setattr(google, "exchange", unexpected_exchange)
    original = TestClient(server.app)
    redirect = original.get("/auth/google/start?mode=login", follow_redirects=False)
    state = parse_qs(urlsplit(redirect.headers["location"]).query)["state"][0]
    response = TestClient(server.app).get("/auth/google/callback", params={"state": state, "code": "test-code"},
                                          follow_redirects=False)
    assert response.headers["location"] == "/?google=stale"


def test_expired_google_data_is_removed_even_during_grace_and_outages(monkeypatch):
    import time
    from zhiyin import cards

    monkeypatch.setattr(google, "disconnect", lambda uid: None)
    removed_cards = []
    monkeypatch.setattr(cards, "drop", removed_cards.append)
    expired = []
    for i in range(4):
        uid = accounts.redeem(accounts.invite(f"Expired review {i}"))
        accounts.link_google(uid, f"expired-review-{i}", f"expired{i}@example.com", "Reviewer")
        accounts.set_status(uid, "ready")
        accounts.set_prefs(uid, synced=time.time() - 31 * 86400)
        with store.as_user(uid):
            store.write_json(store.LIBRARY, {"tracks": [{"vid": "expired-song", "source": "google"}]})
            store.write_json(store.ASKS, [{"q": "rainy afternoon", "created": 1, "lang": "en",
                                          "intent": "Generated title", "picks": [{"vid": "derived-song"}]}])
        expired.append(uid)
    # Both holds are active, but neither extends retention beyond 30 days.
    store.kv_set("forget_from", time.time() + 3 * 86400)
    store.kv_set("forget_held", time.time())
    try:
        assert server._forget_stale([accounts.get(uid) for uid in expired]) == set(expired)
        assert set(removed_cards) == set(expired)
        for uid in expired:
            assert accounts.get(uid)["status"] == "new"
            with store.as_user(uid):
                assert not store.LIBRARY.exists()
                assert store.read_json(store.ASKS) == [{"q": "rainy afternoon", "created": 1, "lang": "en", "picks": []}]
    finally:
        store.kv_set("forget_from", time.time() - 1)
        store.kv_set("forget_held", None)
