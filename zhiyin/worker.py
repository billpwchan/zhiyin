"""Runs on the Mac. The server has no room for the audio model, so this asks it what it wants heard, embeds those
songs here and sends the vectors back. Whatever this Mac already heard is sent without listening again.

A server without a Claude login of its own also hands this Mac the owner's Claude calls, which run on the
`claude` login here. The server only sends the owner's calls; other listeners never run on this subscription."""
import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import httpx

from . import audio, llm, store

CONF = store.DATA / "worker.json"   # {"url": "https://…", "token": "…"}, written by deploy/worker-setup.sh


def conf() -> dict:
    return json.loads(CONF.read_text())


def run_once(log=print) -> int:
    c = conf()
    h = {"X-Worker-Token": c["token"]}
    w = httpx.get(f"{c['url']}/api/worker/wanted", headers=h, timeout=30).raise_for_status().json()
    tracks, texts = w["tracks"], w["texts"]
    if not tracks and not texts:
        return 0
    log(f"server wants {len(tracks)} songs, {len(texts)} texts")
    stats = audio.ensure(tracks, log=log, timeout=3 * 3600, texts=texts)
    rows, tv = audio.rows_for([t["vid"] for t in tracks], texts)
    httpx.post(f"{c['url']}/api/worker/result", headers=h, json={"audio": rows, "text": tv},
               timeout=120).raise_for_status()
    log(f"sent {len(rows)} songs ({stats})")
    return len(rows)


MODELS = {"opus", "sonnet", "haiku"}
_inflight: set[str] = set()   # told to the server on every poll, so a call lost on the way gets offered again
_inflight_lock = threading.Lock()


def _answer(c: dict, h: dict, j: dict, log) -> None:
    try:
        if j.get("model") not in MODELS:
            raise llm.LLMError(f"model {j.get('model')!r} not allowed")
        body = llm.run_here(str(j["prompt"]), str(j["system"]), dict(j["schema"]), j["model"],
                            min(int(j.get("timeout", 600)), 1800), min(int(j.get("retries", 2)), 3))
    except Exception as e:   # whatever went wrong, the server must hear back instead of waiting it out
        body = {"error": str(e)[:500] or type(e).__name__, "usd": getattr(e, "usd", 0)}
    try:
        for attempt in range(3):
            try:
                httpx.post(f"{c['url']}/api/worker/llm/{j['id']}", headers=h, json=body, timeout=30).raise_for_status()
                return
            except httpx.HTTPError as e:
                log(f"worker llm answer: {e}")
                time.sleep(5 * (attempt + 1))
    finally:
        with _inflight_lock:
            _inflight.discard(j["id"])


def llm_loop(log=print) -> None:
    c = conf()
    h = {"X-Worker-Token": c["token"]}
    with ThreadPoolExecutor(4) as ex:
        while True:
            with _inflight_lock:
                have = ",".join(sorted(_inflight))
            try:
                jobs = httpx.get(f"{c['url']}/api/worker/llm", headers=h, params={"wait": 25, "have": have},
                                 timeout=60).raise_for_status().json()
                for j in jobs:
                    log(f"claude call for the server ({j.get('model')})")
                    with _inflight_lock:
                        _inflight.add(j["id"])
                    ex.submit(_answer, c, h, j, log)
            except Exception as e:   # this thread is the only one doing it; it must not die
                log(f"worker llm: {e}")
                time.sleep(30)


def loop(log=print) -> None:
    threading.Thread(target=llm_loop, args=(log,), daemon=True).start()
    while True:
        try:
            n = run_once(log)
        except (httpx.HTTPError, RuntimeError, OSError) as e:
            log(f"worker: {e}")
            n = 0
        time.sleep(20 if n else 120)
