import datetime as dt
import json
import os
import secrets
import subprocess
import threading
import time

from . import store

# Through the Claude Code CLI, so the same call runs on a Claude login or an API key.
# --tools "" and --setting-sources "" keep each call to ~600 tokens of overhead instead of ~35k.
BASE = ["claude", "-p", "--tools", "", "--setting-sources", "", "--strict-mcp-config",
        "--no-session-persistence", "--output-format", "json"]

# Whose Claude runs a call. Anthropic's terms keep a Claude subscription to its owner's own use, so on a server it
# serves only the owner (logged in on the server, or on the Mac worker); everyone else runs on the operator's API key.
HOSTED = os.environ.get("ZHIYIN_AUTH") == "1"
OAUTH = bool(os.environ.get("CLAUDE_CODE_OAUTH_TOKEN"))
API_KEY = bool(os.environ.get("ANTHROPIC_API_KEY"))
WORKER = bool(os.environ.get("ZHIYIN_WORKER_TOKEN"))
DAILY_USD = float(os.environ.get("ZHIYIN_LISTENER_DAILY_USD", 3))   # per invited listener on the operator's key
WORKER_GONE_S = 120   # the worker long-polls every 25 s, so this much silence means the Mac is asleep or off
PICKUP_S = 60

# Each call is a ~255 MB process. A 2 GB host has well under 1 GB to spare: it allows two, and starts the
# second only while the machine still has room.
_slots = threading.BoundedSemaphore(int(os.environ.get("ZHIYIN_LLM_CONCURRENCY", 4)))
_active = [0]
_count = threading.Lock()


class LLMError(RuntimeError):
    usd = 0.0   # what the failed attempts cost anyway


class NoClaude(LLMError):
    pass


def source(uid: str | None = None) -> str | None:
    """'here' (this machine's own `claude` login), 'subscription', 'worker', 'key', or None."""
    uid = uid or store.uid()
    if not HOSTED:
        return "here"
    if uid == store.OWNER:
        return "subscription" if OAUTH else "worker" if WORKER else "key" if API_KEY else None
    return "key" if API_KEY else None


def unavailable(uid: str | None = None) -> str | None:
    """Why this listener's calls can't run right now, or None."""
    uid = uid or store.uid()
    src = source(uid)
    if src is None:
        return "主人还没有为其他听众配置 Claude API key" if uid != store.OWNER else "服务器上还没有配置 Claude"
    if src == "worker" and not worker_online():
        return "Mac 不在线（睡着或关机了）"
    if src == "key" and uid != store.OWNER and spent(uid, days=1) >= DAILY_USD:
        return f"今天的 Claude 额度（${DAILY_USD:g}）用完了，明天再来"
    return None


def require(uid: str | None = None) -> None:
    why = unavailable(uid)
    if why:
        raise NoClaude(why)


def view(uid: str) -> dict:
    src = source(uid)
    return {"source": src, "online": worker_online() if src == "worker" else src is not None, "others": API_KEY}


def call(prompt: str, system: str, schema: dict, model: str = "sonnet", timeout: int = 600, retries: int = 2) -> dict:
    uid = store.uid()
    require(uid)
    src = source(uid)
    try:
        if src == "worker":
            req = {"prompt": prompt, "system": system, "schema": schema, "model": model, "timeout": timeout,
                   "retries": retries}
            out = _via_worker(req, wait=timeout * (retries + 1) + PICKUP_S)
        else:
            out = run_here(prompt, system, schema, model, timeout, retries, env=_env(src))
    except NoClaude:
        raise
    except LLMError as e:
        _record(uid, src, e.usd)
        raise
    _record(uid, src, out.get("usd") or 0)
    return out["data"]


def _env(src: str) -> dict | None:
    drop = {"subscription": ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN"), "key": ("CLAUDE_CODE_OAUTH_TOKEN",)}.get(src)
    return None if drop is None else {k: v for k, v in os.environ.items() if k not in drop}


def _room() -> bool:
    try:
        for line in open("/proc/meminfo"):
            if line.startswith("MemAvailable:"):
                return int(line.split()[1]) > 450_000
    except OSError:
        pass
    return True


def _run(cmd, prompt, timeout, env):
    with _slots:
        while _active[0] and not _room():
            time.sleep(5)
        with _count:
            _active[0] += 1
        try:
            return subprocess.run(cmd, input=prompt, capture_output=True, text=True, timeout=timeout, cwd="/tmp", env=env)
        finally:
            with _count:
                _active[0] -= 1


def run_here(prompt: str, system: str, schema: dict, model: str, timeout: int, retries: int, env=None) -> dict:
    cmd = BASE + ["--model", model, "--system-prompt", system, "--json-schema", json.dumps(schema)]
    last, usd = None, 0.0
    for attempt in range(retries + 1):
        try:
            p = _run(cmd, prompt, timeout, env)
            out = json.loads(p.stdout)
            # what the call would cost on an API key; a subscription reports it too
            usd += out.get("total_cost_usd") or 0
            if out.get("is_error"):
                raise LLMError(out.get("result") or p.stderr[:500])
            data = out.get("structured_output")
            if data is None:
                data = json.loads(out["result"])
            return {"data": data, "usd": usd}
        except (subprocess.TimeoutExpired, json.JSONDecodeError, LLMError, KeyError) as e:
            last = e
            time.sleep(3 * (attempt + 1))
    err = LLMError(f"claude -p failed after {retries + 1} attempts: {last}")
    err.usd = usd
    raise err


def _record(uid: str, src: str, usd: float) -> None:
    con = store.db()
    con.execute("insert into usage values (?, ?, ?, 1, ?) on conflict(uid, day, source) do update "
                "set calls = calls + 1, usd = usd + excluded.usd", (uid, dt.date.today().isoformat(), src, usd))
    con.commit()


def spent(uid: str, days: int = 7) -> float:
    since = (dt.date.today() - dt.timedelta(days=days - 1)).isoformat()
    r = store.db().execute("select coalesce(sum(usd), 0) from usage where uid=? and day>=?", (uid, since)).fetchone()
    return round(r[0], 2)


# ---------- calls handed to the Mac worker ----------
_queue: dict[str, dict] = {}
_queue_cv = threading.Condition()
_seen = [0.0]


def worker_online() -> bool:
    return time.time() - _seen[0] < WORKER_GONE_S


def _via_worker(req: dict, wait: float) -> dict:
    if not worker_online():
        raise NoClaude("Mac 不在线（睡着或关机了）")
    jid = secrets.token_hex(8)
    job = {"req": req, "taken": False, "done": threading.Event(), "out": None}
    with _queue_cv:
        _queue[jid] = job
        _queue_cv.notify_all()
    try:
        deadline = time.time() + wait
        while not job["done"].wait(5):
            if not worker_online():
                raise LLMError("Mac 中途离线了")
            if time.time() > deadline:
                raise LLMError("Mac 上的 Claude 没有按时答复")
        if "error" in job["out"]:
            err = LLMError(job["out"]["error"])
            err.usd = job["out"].get("usd") or 0
            raise err
        return job["out"]
    finally:
        with _queue_cv:
            _queue.pop(jid, None)


def take(wait: float, have: set[str] | None) -> list[dict]:
    """The worker's long poll: every call nobody has taken yet, waiting up to `wait` seconds for one to arrive.
    `have` is what the worker is still running; a call handed out but not there was lost on the way, or went down
    with a crashed worker, and is offered again. A worker that doesn't say what it holds never gets a re-offer."""
    with _queue_cv:
        _seen[0] = time.time()
        for jid, j in _queue.items():
            if have is not None and j["taken"] and jid not in have and not j["done"].is_set():
                j["taken"] = False
        if all(j["taken"] for j in _queue.values()):
            _queue_cv.wait(wait)
        _seen[0] = time.time()
        out = []
        for jid, j in _queue.items():
            if not j["taken"]:
                j["taken"] = True
                out.append({"id": jid, **j["req"]})
        return out


def answer(jid: str, out: dict) -> None:
    with _queue_cv:
        j = _queue.get(jid)
    if j:
        j["out"] = out
        j["done"].set()
