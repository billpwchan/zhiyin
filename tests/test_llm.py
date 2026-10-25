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
    assert llm.source(store.OWNER) == "worker"
    assert llm.source("u1") == "key"


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
