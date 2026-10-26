import contextlib
import contextvars
import datetime as dt
import json
import os
import secrets
import subprocess
import threading
import time

from . import i18n, store

# A Claude login (the owner's, here or on the Mac worker) is reached through the Claude Code CLI. An API key goes to
# the Messages API directly: plan-included API credits don't cover Claude Code, the SDK reports exact usage, and a
# call is a socket instead of a ~255 MB process.
# --tools "" and --setting-sources "" keep each CLI call to ~600 tokens of overhead instead of ~35k.
BASE = ["claude", "-p", "--tools", "", "--setting-sources", "", "--strict-mcp-config",
        "--no-session-persistence", "--output-format", "json"]

# Whose Claude runs a call. Anthropic's terms keep a Claude subscription to its owner's own use, so on a server it
# serves only the owner (logged in on the server, or on the Mac worker); everyone else runs on the operator's API key.
HOSTED = os.environ.get("ZHIYIN_AUTH") == "1"
OAUTH = bool(os.environ.get("CLAUDE_CODE_OAUTH_TOKEN"))
API_KEY = bool(os.environ.get("ANTHROPIC_API_KEY"))
WORKER = bool(os.environ.get("ZHIYIN_WORKER_TOKEN"))
# The operator's key is one pool for everyone (a plan's monthly API credit, say): POOL_USD over any 30 days, spent no
# faster than twice the even pace on any one day, and at most DAILY_USD a day for one listener.
POOL_USD = float(os.environ.get("ZHIYIN_KEY_MONTHLY_USD", 100))
DAILY_USD = float(os.environ.get("ZHIYIN_LISTENER_DAILY_USD", 0.5))
# A first setup reads the whole library once (about $2 for 800 likes): its own allowance, outside the day's, per 800
# songs so a big library isn't cut off halfway, up to FIRST_RUN_MAX.
FIRST_RUN_USD = float(os.environ.get("ZHIYIN_LISTENER_FIRST_RUN_USD", 4))
FIRST_RUN_MAX = float(os.environ.get("ZHIYIN_LISTENER_FIRST_RUN_MAX_USD", 20))
# What runs on the key for listeners when code asks for a model; the owner's own accounts keep what they asked for.
# Measured on the same shortlists (2026-10-25): see docs/how-it-works.md.
KEY_MODEL = {"opus": os.environ.get("ZHIYIN_KEY_OPUS", "sonnet"), "sonnet": os.environ.get("ZHIYIN_KEY_SONNET", "sonnet"),
             "haiku": "haiku"}
# Naming strangers' NetEase likes (cards.py), all of them together, each day, inside the month's pool. Haiku names
# 600 likes for under a cent (measured 2026-10-26), so this is several hundred names a day.
CARD_DAILY_USD = float(os.environ.get("ZHIYIN_CARD_DAILY_USD", 2))
# The owner's own ceiling, far above a normal day (~$1-2), so a runaway loop or a stolen session can't drain the plan.
OWNER_DAILY_USD = float(os.environ.get("ZHIYIN_OWNER_DAILY_USD", 10))
WORKER_GONE_S = 120   # the worker long-polls every 25 s, so this much silence means the Mac is asleep or off
PICKUP_S = 60

# Each call is a ~255 MB process. A 2 GB host has well under 1 GB to spare: it allows two, and starts the
# second only while the machine still has room.
_background = contextvars.ContextVar("llm_background", default=False)


@contextlib.contextmanager
def background():
    """Work nobody is waiting for (the scheduled morning edition): the owner's waits for the Mac rather than spending
    the shared key, and anyone's waits a day rather than run ahead of the pool's pace."""
    t = _background.set(True)
    try:
        yield
    finally:
        _background.reset(t)


_first_run = contextvars.ContextVar("llm_first_run", default=None)


@contextlib.contextmanager
def first_run():
    """A listener's first setup. On the key its calls are counted apart ("key:first"), against first_run_allowance over
    30 days rather than the listener's day, so joining doesn't stop halfway or leave them unable to ask that evening."""
    t = _first_run.set({"songs": 0})
    try:
        yield
    finally:
        _first_run.reset(t)


def first_run_songs(n: int) -> None:
    """How many songs this first setup has to read, once that is known: the allowance grows with the library."""
    if (r := _first_run.get()) is not None:
        r["songs"] = n


def first_run_allowance(songs: int = 0) -> float:
    return min(FIRST_RUN_MAX, FIRST_RUN_USD * max(1.0, songs / 800))


def first_run_left(uid: str, songs: int = 0) -> float:
    return first_run_allowance(songs) - spent(uid, days=30, source="key:first")


_slots = threading.BoundedSemaphore(int(os.environ.get("ZHIYIN_LLM_CONCURRENCY", 4)))
_active = [0]
_count = threading.Lock()


MODELS = {"opus": "claude-opus-5-5", "sonnet": "claude-sonnet-5-5", "haiku": "claude-haiku-5-5"}
# $ per million tokens: input, output, cache write (5 min), cache read. Haiku's are for prompts up to 100K tokens.
PRICES = {"opus": (4, 20, 5, 0.2), "sonnet": (2, 10, 2.5, 0.1), "haiku": (0.1, 0.5, 0.125, 0.01)}
_UNSUPPORTED = ("minimum", "maximum", "minItems", "maxItems", "minLength", "maxLength", "pattern")


class LLMError(RuntimeError):
    usd = 0.0   # what the failed attempts cost anyway


class NoClaude(LLMError):
    pass


def source(uid: str | None = None) -> str | None:
    """'here' (this machine's own `claude` login), 'subscription', 'worker', 'key', or None."""
    uid = uid or store.uid()
    if store.is_sample(uid):
        return None   # the sample listener never spends anyone's Claude
    if not HOSTED:
        return "here"
    if store.is_owners(uid):
        if OAUTH:
            return "subscription"
        if WORKER and (worker_online() or not API_KEY or _background.get()):
            return "worker"
        return "key" if API_KEY else None
    return "key" if API_KEY else None


def unavailable(uid: str | None = None) -> str | None:
    """Why this listener's calls can't run right now, or None."""
    uid = uid or store.uid()
    src = source(uid)
    mine = store.is_owners(uid)
    if src is None:
        return i18n.tr("服务器上还没有配置 Claude" if mine else "主人还没有为其他听众配置 Claude API key", i18n.of(uid))
    if src == "worker" and not worker_online():
        return i18n.tr("Mac 不在线（睡着或关机了）", i18n.of(uid))
    if src == "key":
        if pool_spent(30) >= POOL_USD:
            return i18n.tr("这个月大家共用的 Claude 额度用完了，过几天会恢复", i18n.of(uid))
        if _background.get() and pool_spent(1) >= 2 * POOL_USD / 30:
            return i18n.tr("今天大家共用的 Claude 额度到了上限，明天再挑", i18n.of(uid))
        if uid == store.CARDS:
            if spent(uid, days=1) >= CARD_DAILY_USD:
                return i18n.tr("今天起名字的额度用完了，明天再来起名", i18n.of(uid))
        elif not mine and (r := _first_run.get()) is not None:
            if first_run_left(uid, r["songs"]) <= 0:
                return i18n.tr("第一次准备用完了它的 Claude 额度；额度按 30 天计算，过些天再试", i18n.of(uid))
        elif not mine and spent(uid, days=1, source="key") >= DAILY_USD:
            return i18n.tr("你今天的 Claude 额度用完了，明天再来", i18n.of(uid))
    if HOSTED and mine and spent(uid, days=1) >= OWNER_DAILY_USD:
        return i18n.tr("今天的 Claude 额度（${cap}）用完了，明天再来", i18n.of(uid), cap=f"{OWNER_DAILY_USD:g}")
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
    if src == "key" and not store.is_owners(uid):
        model = KEY_MODEL[model]
    try:
        if src == "worker":
            req = {"prompt": prompt, "system": system, "schema": schema, "model": model, "timeout": timeout,
                   "retries": retries}
            out = _via_worker(req, wait=timeout * (retries + 1) + PICKUP_S)
        elif src == "key" and _background.get():
            out = run_batch(prompt, system, schema, model)
        elif src == "key":
            out = run_api(prompt, system, schema, model, timeout, retries)
        else:
            out = run_here(prompt, system, schema, model, timeout, retries, env=_env(src))
    except NoClaude:
        raise
    except LLMError as e:
        _record(uid, _tally(uid, src), e.usd)
        raise
    _record(uid, _tally(uid, src), out.get("usd") or 0)
    return out["data"]


def _tally(uid: str, src: str) -> str:
    return "key:first" if src == "key" and _first_run.get() is not None and not store.is_owners(uid) else src


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


def strict(schema):
    """The CLI's schemas, as structured outputs accept them: closed objects, range limits moved into the text."""
    if isinstance(schema, list):
        return [strict(x) for x in schema]
    if not isinstance(schema, dict):
        return schema
    out = {k: strict(v) for k, v in schema.items() if k not in _UNSUPPORTED}
    limits = [f"{k} {schema[k]}" for k in _UNSUPPORTED if k in schema]
    if limits:
        out["description"] = "; ".join(filter(None, [schema.get("description"), *limits]))
    if out.get("type") == "object":
        out["additionalProperties"] = False
    return out


_client = []


def _api():
    if not _client:
        import anthropic
        _client.append(anthropic.Anthropic(max_retries=0))
    return _client[0]


def cost(model: str, u) -> float:
    i, o, w, r = PRICES[model]
    return ((u.input_tokens or 0) * i + (u.output_tokens or 0) * o + (u.cache_creation_input_tokens or 0) * w
            + (u.cache_read_input_tokens or 0) * r) / 1e6


def run_api(prompt: str, system: str, schema: dict, model: str, timeout: int, retries: int) -> dict:
    import anthropic
    last, usd = None, 0.0
    for attempt in range(retries + 1):
        try:
            # the system prompt repeats across a listener's stations and songs, so it is the part worth caching
            with _api().messages.stream(
                    model=MODELS[model], max_tokens=32000, timeout=timeout,
                    system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
                    messages=[{"role": "user", "content": prompt}],
                    output_config={"effort": "medium", "format": {"type": "json_schema", "schema": strict(schema)}}) as st:
                msg = st.get_final_message()
            usd += cost(model, msg.usage)
            if msg.stop_reason in ("refusal", "max_tokens"):
                raise LLMError(f"stopped: {msg.stop_reason}")
            text = next(b.text for b in msg.content if b.type == "text")
            return {"data": json.loads(text), "usd": usd}
        except anthropic.APIStatusError as e:
            last = e
            if e.status_code in (400, 401, 403, 404):
                break   # a bad request or a bad key won't get better by asking again
            time.sleep(3 * (attempt + 1))
        except (anthropic.APIConnectionError, json.JSONDecodeError, LLMError, StopIteration) as e:
            last = e
            time.sleep(3 * (attempt + 1))
    err = LLMError(f"Claude API failed after {attempt + 1} attempts: {last}")
    err.usd = usd
    raise err


BATCH_WAIT_S = 6 * 3600


def run_batch(prompt: str, system: str, schema: dict, model: str) -> dict:
    """Half price for work nobody is waiting on; most batches come back within the hour."""
    api = _api()
    b = api.messages.batches.create(requests=[{"custom_id": "1", "params": {
        "model": MODELS[model], "max_tokens": 32000,
        "system": [{"type": "text", "text": system}],
        "messages": [{"role": "user", "content": prompt}],
        "output_config": {"effort": "medium", "format": {"type": "json_schema", "schema": strict(schema)}}}}])
    deadline = time.time() + BATCH_WAIT_S
    while api.messages.batches.retrieve(b.id).processing_status != "ended":
        if time.time() > deadline:
            api.messages.batches.cancel(b.id)
            raise LLMError("the batch didn't come back in time")
        time.sleep(30)
    r = next(iter(api.messages.batches.results(b.id))).result
    if r.type != "succeeded":
        raise LLMError(f"batch request {r.type}")
    msg = r.message
    usd = cost(model, msg.usage) / 2
    if msg.stop_reason in ("refusal", "max_tokens"):
        err = LLMError(f"stopped: {msg.stop_reason}")
        err.usd = usd
        raise err
    return {"data": json.loads(next(x.text for x in msg.content if x.type == "text")), "usd": usd}


def _record(uid: str, src: str, usd: float) -> None:
    con = store.db()
    con.execute("insert into usage values (?, ?, ?, 1, ?) on conflict(uid, day, source) do update "
                "set calls = calls + 1, usd = usd + excluded.usd", (uid, dt.date.today().isoformat(), src, usd))
    con.commit()


def spent(uid: str, days: int = 7, source: str | None = None) -> float:
    since = (dt.date.today() - dt.timedelta(days=days - 1)).isoformat()
    r = store.db().execute("select coalesce(sum(usd), 0) from usage where uid=? and day>=? and source=coalesce(?, source)",
                           (uid, since, source)).fetchone()
    return round(r[0], 4)


def pool_spent(days: int) -> float:
    since = (dt.date.today() - dt.timedelta(days=days - 1)).isoformat()
    return store.db().execute("select coalesce(sum(usd), 0) from usage where source in ('key', 'key:first') and day>=?",
                              (since,)).fetchone()[0]


# ---------- calls handed to the Mac worker ----------
_queue: dict[str, dict] = {}
_queue_cv = threading.Condition()
_seen = [0.0]


def worker_online() -> bool:
    return time.time() - _seen[0] < WORKER_GONE_S


def _via_worker(req: dict, wait: float) -> dict:
    if not worker_online():
        raise NoClaude(i18n.tr("Mac 不在线（睡着或关机了）"))
    jid = secrets.token_hex(8)
    job = {"req": req, "taken": False, "done": threading.Event(), "out": None}
    with _queue_cv:
        _queue[jid] = job
        _queue_cv.notify_all()
    try:
        deadline = time.time() + wait
        while not job["done"].wait(5):
            if not worker_online():
                raise LLMError(i18n.tr("Mac 中途离线了"))
            if time.time() > deadline:
                raise LLMError(i18n.tr("Mac 上的 Claude 没有按时答复"))
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
