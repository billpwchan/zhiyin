"""Runs on the Mac. The server has no room for the audio model, so this asks it what it wants heard, embeds those
songs here and sends the vectors back. Whatever this Mac already heard is sent without listening again."""
import json
import time

import httpx

from . import audio, store

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


def loop(log=print) -> None:
    while True:
        try:
            n = run_once(log)
        except (httpx.HTTPError, RuntimeError, OSError) as e:
            log(f"worker: {e}")
            n = 0
        time.sleep(20 if n else 120)
