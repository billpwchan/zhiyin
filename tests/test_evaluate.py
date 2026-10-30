import json

from zhiyin import accounts, evaluate, store


def window(uid, k, hits):
    pool = [{"vid": f"c{k}x{i:03d}", "title": f"t{i}", "artists": [{"name": "a"}], "album": None, "year": None,
             "familiar": 0, "knows": None, "via": []} for i in range(100)]
    lane = {"key": "jazz", "head": "LANE: jazz", "pool": pool, "hits": {pool[i]["vid"]: f"like{k}{i}" for i in hits}}
    d = evaluate._dir() / uid
    d.mkdir(parents=True, exist_ok=True)
    w = {"uid": uid, "window": k, "size": 60, "train": 300, "later": 60, "own": [f"like{k}{i}" for i in hits], "lanes": [lane]}
    store.write_json(d / f"w{k}.json", w)
    return w, pool


def answer(w, arm, seed, vids):
    with (evaluate._dir() / "results.jsonl").open("a") as f:
        f.write(json.dumps({"id": evaluate._request_id(w, "jazz", arm, seed), "vids": vids, "usd": 0.1}) + "\n")


def test_each_arm_is_scored_on_the_same_songs_they_went_on_to_like():
    # the graph keeps the pool's first 64; the songs they liked later sit at 10 and at 80
    w, pool = window("evalA", 0, [10, 80])
    vids = [c["vid"] for c in pool]
    for s in range(3):
        answer(w, "opus", s, [vids[80]] + vids[:63])        # every read finds the one the graph misses
        answer(w, "sonnet", s, vids[20:84] if s else vids[:64])   # two reads of three don't keep the one at 10
    r = evaluate.screen_report(("opus", "sonnet"), 3, log=lambda *_: None)
    assert r["units"] == 2
    assert r["kept"] == {"graph": 1, "opus x1": 2, "opus x3": 2, "sonnet x1": 1, "sonnet x3": 1}
    assert abs(r["per_read_usd"]["opus"] - 0.1) < 1e-9


def test_only_the_owners_own_accounts_are_read():
    accounts.redeem(accounts.invite("friend"))
    mine = accounts.redeem(accounts.invite("me again", mine=True))
    con = store.db()
    con.execute("update users set status='ready'")
    con.commit()
    assert set(evaluate.owner_accounts()) <= {store.OWNER, mine} and mine in evaluate.owner_accounts()


def test_a_like_from_after_the_window_is_reported_beside_it_not_scored():
    w, pool = window("evalB", 1, [10, 80])
    w["own"] = ["like110"]   # the like at 80 came after this window
    store.write_json(evaluate._dir() / "evalB" / "w1.json", w)
    r = evaluate.screen_report(("opus",), 1, log=lambda *_: None)
    assert r["later"] - r["units"] >= 1
    assert r["kept_later"]["graph"] - r["kept"]["graph"] == 0   # the graph's top 64 never held the one at 80
