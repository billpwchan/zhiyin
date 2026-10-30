import time

from fastapi.testclient import TestClient

from zhiyin import quality, rotation, server, settings, signals, store

DAY = 86400


def library(*vids, liked="2026-01-15", **over):
    store.write_json(store.LIBRARY, {"tracks": [
        {"rank": i, "vid": v, "type": "ATV", "title": f"song {v}", "artists": [{"name": f"artist {v}", "id": None}],
         "album": None, "dur": 200, "long": False, "source": "google", "liked_est": liked, **over.get(v, {})}
        for i, v in enumerate(vids)]})


def listen(uid, vid, ts, end="done", pos=200, dur=200, **kw):
    con = store.db()
    for ev, at, p, extra in (("start", ts, 0, kw), (end, ts + max(pos, 1), pos, {})):
        cols = {"vid": vid, "lane": "a", "ts": at, "ev": ev, "pos": p, "uid": uid, "src": "auto", "dur": dur, "test": 0, **extra}
        con.execute(f"insert into plays ({', '.join(cols)}) values ({', '.join('?' * len(cols))})", list(cols.values()))
    con.commit()


def test_a_favourite_rests_about_a_day_and_one_heard_often_rests_longer():
    assert rotation.rest_days(1.0, 1) == 1
    assert rotation.rest_days(0.4, 0) == 1 + 4 * 0.6
    assert rotation.rest_days(1.0, 3) == 4
    assert rotation.rest_days(0.4, 9) == rotation.REST_MAX_D


def test_a_like_is_wanted_more_when_recent_played_or_kept_and_never_past_one():
    now = time.time()
    old, new = {"liked_est": "2016-05-01"}, {"liked_est": time.strftime("%Y-%m-%d", time.localtime(now - 20 * DAY))}
    assert rotation.want(new, None, None, False, now) > rotation.want(old, None, None, False, now)
    assert rotation.want(old, {"w": signals.LOVE}, None, False, now) > rotation.want(old, None, None, True, now) \
        > rotation.want(old, None, None, False, now)
    assert rotation.want(new, {"w": 9 * signals.LOVE}, {"w": 9 * signals.LOVE}, True, now) == 1


def test_a_like_heard_yesterday_waits_and_one_skipped_early_rests_a_fortnight():
    now = time.time()
    with store.as_user("rot1"):
        library("heard000001", "skipped0001", "never000001")
        listen("rot1", "heard000001", now - DAY)
        listen("rot1", "skipped0001", now - DAY, end="skip", pos=4)
        by = {x["vid"]: x for x in rotation.songs()}
    assert now < by["heard000001"]["due"] < now + 5 * DAY
    assert by["heard000001"]["n30"] == 1 and by["heard000001"]["last"]
    assert by["skipped0001"]["due"] >= now - DAY + rotation.SKIP_REST_D * DAY - 60
    assert by["never000001"]["due"] == 0 and by["never000001"]["last"] is None


def test_long_mixes_likes_that_are_not_their_taste_and_ones_that_wont_play_stay_out():
    with store.as_user("rot2"):
        library("keep0000001", "long0000001", "notme000001", "broken00001", **{"long0000001": {"long": True}})
        settings.set_not_me(vid="notme000001")
        listen("rot2", "broken00001", time.time() - 60, end="error", pos=0)
        assert [x["vid"] for x in rotation.songs()] == ["keep0000001"]


def test_not_for_a_while_holds_a_like_back_until_it_is_let_back():
    now = time.time()
    with store.as_user("rot3"):
        library("hush0000001")
        rotation.hush("hush0000001", rotation.HUSH_D)
        assert rotation.songs()[0]["due"] >= now + (rotation.HUSH_D - 1) * DAY
        rotation.hush("hush0000001", 0)
        assert rotation.songs()[0]["due"] == 0


def test_the_likes_and_their_rests_are_each_listeners_own_and_a_play_keeps_its_kind():
    with store.as_user("rotB"):
        library("other000001")
    with store.as_user(store.OWNER):
        library("owner000001")
    c = TestClient(server.app)
    r = c.get("/api/mine").json()
    assert [x["vid"] for x in r["songs"]] == ["owner000001"] and abs(r["now"] - time.time()) < 5
    assert c.post("/api/mine/hush", json={"vid": "owner000001", "days": 60}).status_code == 200
    with store.as_user("rotB"):
        assert not settings.load().get("rest")
    with store.as_user(store.OWNER):
        assert "owner000001" in settings.load()["rest"]
    assert c.post("/api/play", json={"vid": "owner000001", "lane": "mix", "ev": "start", "kind": "fav"}).status_code == 200
    assert store.db().execute("select kind from plays where vid='owner000001'").fetchone()[0] == "fav"
    assert c.post("/api/play", json={"vid": "owner000001", "ev": "start", "kind": "other"}).status_code == 422


def test_your_own_likes_are_measured_apart_from_the_recommendations():
    now = time.time()
    with store.as_user("rot4"):
        listen("rot4", "fav00000001", now - 3600, kind="fav")
        listen("rot4", "again000001", now - 3000, end="skip", pos=3, kind="again")
        g = quality.report(14, "rot4")["groups"]
    assert g["mine"]["fav"]["good"] == 1 and g["mine"]["again"]["early"] == 1
    assert "all" not in g


def test_a_visitor_hears_the_samples_likes_between_its_new_songs_and_cannot_rest_them(monkeypatch):
    monkeypatch.setattr(server, "AUTH", True)
    monkeypatch.setattr(server, "SAMPLE_ON", [server._install_sample()])
    c = TestClient(server.app)
    r = c.get("/api/mine", headers={"accept-language": "en-US"})
    assert r.status_code == 200 and r.json()["songs"]
    assert c.post("/api/mine/hush", json={"vid": r.json()["songs"][0]["vid"], "days": 60}).status_code == 401
