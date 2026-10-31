import threading
import time

import pytest

from zhiyin import llm, store


@pytest.fixture
def hosted(monkeypatch):
    def setup(oauth=False, key=False, worker=False):
        monkeypatch.setattr(llm, "HOSTED", True)
        monkeypatch.setattr(llm, "OAUTH", oauth)
        monkeypatch.setattr(llm, "API_KEY", key)
        monkeypatch.setattr(llm, "WORKER", worker)
    return setup


def test_a_subscription_only_serves_its_owner(hosted):
    hosted(oauth=True, worker=True)
    assert llm.source(store.OWNER) == "subscription"
    assert llm.source("u1") is None
    hosted(worker=True)
    assert llm.source(store.OWNER) == "worker"
    assert llm.source("u1") is None
    hosted(worker=True, key=True)
    assert llm.source("u1") == "key"


def test_the_owner_runs_on_the_key_when_there_is_one_and_outside_the_listeners_pool(hosted, monkeypatch):
    hosted(oauth=True, worker=True, key=True)
    monkeypatch.setattr(llm, "worker_online", lambda: True)
    assert llm.source(store.OWNER) == "key"      # the subscription is kept for the owner's own work
    with llm.background():
        assert llm.source(store.OWNER) == "key"  # the weekly edition goes as a batch
    calls = []
    monkeypatch.setattr(llm, "run_api", lambda prompt, system, schema, model, timeout, retries, effort:
                        calls.append((model, effort)) or {"data": {}, "usd": 3.0, "tok": [50_000, 2_000, 0, 0]})
    monkeypatch.setattr(llm, "POOL_USD", 2.0)
    pool = llm.pool_spent(30)
    with store.as_user(store.OWNER):
        llm.call("p", "s", {}, model="opus")
        assert llm.unavailable() is None                # the pool being spent doesn't stop the owner
    assert calls == [("opus", "high")] and llm.pool_spent(30) == pool
    u = llm.used(store.OWNER, 1)
    assert (u["in"], u["out"]) >= (50_000, 2_000) and u["usd"] >= 3.0
    assert llm.view(store.OWNER)["used"]["today"] == u and "used" not in llm.view("u1")


def test_the_shared_key_keeps_to_its_pool_and_its_pace(hosted, monkeypatch):
    hosted(key=True)
    monkeypatch.setattr(llm, "POOL_USD", 30.0)
    llm._record("u3", "key", 0.3)
    llm._record("u4", "key", 1.8)
    assert llm.unavailable("u5") is None
    with llm.background():
        assert "明天" in llm.unavailable("u5")   # $2.1 today is past twice the even pace of $1 a day
    llm._record("u4", "key", 28)
    assert "这个月" in llm.unavailable("u5")


def test_only_the_owner_runs_on_the_owners_claude(hosted):
    from zhiyin import accounts
    friend = accounts.redeem(accounts.invite("Ming"))
    hosted(worker=True)
    assert llm.source(store.OWNER) == "worker" and llm.source(friend) is None
    hosted(oauth=True)
    assert llm.source(store.OWNER) == "subscription" and llm.source(friend) is None
    hosted(oauth=True, key=True)
    assert llm.source(store.OWNER) == "key" and llm.source(friend) == "key"


def test_on_the_mac_it_is_whatever_claude_is_signed_in_with():
    assert llm.source(store.OWNER) == "here"


def test_a_listener_without_claude_is_told_so(hosted):
    hosted(oauth=True)
    with store.as_user("u1"), pytest.raises(llm.NoClaude):
        llm.call("p", "s", {})


def test_each_source_hides_the_other_credential(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "t")
    assert "ANTHROPIC_API_KEY" not in llm._env("subscription")
    assert "CLAUDE_CODE_OAUTH_TOKEN" not in llm._env("key")
    assert llm._env("here") is None


def test_the_worker_runs_the_owners_call(hosted):
    hosted(worker=True)
    llm._seen[0] = time.time()

    def mac():
        jobs = llm.take(5, set())
        llm.answer(jobs[0]["id"], {"data": {"echo": jobs[0]["prompt"]}, "usd": 0.25})
    threading.Thread(target=mac).start()
    with store.as_user(store.OWNER):
        before = llm.spent(store.OWNER)
        assert llm.call("hello", "s", {}, timeout=5, retries=0) == {"echo": "hello"}
        assert llm.spent(store.OWNER) == round(before + 0.25, 2)


def test_an_asleep_worker_fails_fast(hosted):
    hosted(worker=True)
    llm._seen[0] = time.time() - llm.WORKER_GONE_S - 1
    t0 = time.time()
    with store.as_user(store.OWNER), pytest.raises(llm.LLMError):
        llm.call("p", "s", {}, timeout=60)
    assert time.time() - t0 < 1


def test_a_call_the_worker_lost_is_offered_again(hosted):
    hosted(worker=True)
    llm._seen[0] = time.time()

    def mac():
        lost = llm.take(5, set())                 # handed out, but the answer never comes
        again = llm.take(5, set())                # the worker doesn't hold it, so it comes back
        assert [j["id"] for j in again] == [lost[0]["id"]]
        assert llm.take(0, {lost[0]["id"]}) == []  # while the worker holds it, nobody else gets it
        llm.answer(again[0]["id"], {"error": "boom", "usd": 0.1})
    threading.Thread(target=mac).start()
    with store.as_user(store.OWNER), pytest.raises(llm.LLMError, match="boom"):
        llm.call("p", "s", {}, timeout=5, retries=0)


def test_an_invited_listener_stops_at_the_daily_cap(hosted, monkeypatch):
    hosted(key=True)
    monkeypatch.setattr(llm, "DAILY_USD", 1.0)
    llm._record("u2", "key", 1.2)
    assert "额度" in llm.unavailable("u2")
    with store.as_user("u2"), pytest.raises(llm.NoClaude):
        llm.call("p", "s", {})
    llm._record(store.OWNER, "key", 5)
    assert llm.unavailable(store.OWNER) is None   # the owner has a ceiling of their own, far higher
    llm._record(store.OWNER, "key", llm.OWNER_DAILY_USD)
    assert "额度" in llm.unavailable(store.OWNER)


def test_listeners_on_the_key_get_sonnet_where_the_owner_keeps_opus(hosted, monkeypatch):
    from zhiyin import accounts
    hosted(key=True)
    con = store.db()
    con.execute("delete from usage")
    con.commit()
    used = []
    monkeypatch.setattr(llm, "run_api", lambda prompt, system, schema, model, *a: used.append(model) or {"data": {}, "usd": 0})
    friend = accounts.redeem(accounts.invite("Ming"))
    for u in (friend, store.OWNER):
        with store.as_user(u):
            llm.call("p", "s", {}, model="opus")
    assert used == ["sonnet", "opus"]


def test_a_first_setup_has_its_own_allowance_and_leaves_the_day_alone(hosted, monkeypatch):
    from zhiyin import accounts
    hosted(key=True)
    monkeypatch.setattr(llm, "run_api", lambda *a, **k: {"data": {"ok": 1}, "usd": 0.4})
    uid = accounts.redeem(accounts.invite("Newcomer"))
    pool = llm.pool_spent(1)
    with store.as_user(uid):
        with llm.first_run():
            for _ in range(5):   # $2.00 in all, four times the listener's day
                assert llm.call("p", "s", {}) == {"ok": 1}
        assert llm.spent(uid, days=1, source="key") == 0 and llm.unavailable() is None   # they can still ask today
        assert round(llm.pool_spent(1) - pool, 2) == 2.0                                  # the shared budget pays it
        with llm.first_run():
            for _ in range(5):
                llm.call("p", "s", {})
            with pytest.raises(llm.NoClaude):   # a first setup that keeps failing stops at its allowance
                llm.call("p", "s", {})
            llm.first_run_songs(1600)            # unless the library is big: the allowance grows with it
            assert llm.call("p", "s", {}) == {"ok": 1}
        assert llm.first_run_allowance(100_000) == llm.FIRST_RUN_MAX
        llm.call("p", "s", {})
        llm.call("p", "s", {})
        assert llm.unavailable()   # an ordinary day still ends at DAILY_USD


def test_a_listener_on_the_key_gets_the_screen_only_when_their_allowance_covers_it(hosted, monkeypatch):
    from zhiyin import accounts, edition
    hosted(key=True)
    monkeypatch.setattr(llm, "DAILY_USD", 0.5)
    uid = accounts.redeem(accounts.invite("Lan"))
    with store.as_user(uid):
        assert edition.screens(4, "opus") and not edition.screens(8, "opus")   # eight stations by hand cost more than a day
        with llm.background():
            assert edition.screens(8, "opus")                                 # the weekly edition goes at batch prices
        llm._record(uid, "key", 0.3)
        assert not edition.screens(4, "opus")
        with llm.first_run():
            assert edition.screens(8, "opus")                                 # a first setup has its own allowance
    with store.as_user(store.OWNER):
        llm._record(store.OWNER, "key:owner", 20)
        assert edition.screens(8, "opus")
