import json
import os
import subprocess
import threading
import time

# Subscription CLI, not an API key: the user runs Claude through `claude` and wants no key in this project.
# --tools "" and --setting-sources "" keep each call to ~600 tokens of overhead instead of ~35k.
BASE = ["claude", "-p", "--tools", "", "--setting-sources", "", "--strict-mcp-config",
        "--no-session-persistence", "--output-format", "json"]


# Each call is a ~255 MB process. A 2 GB host has well under 1 GB to spare: it allows two, and starts the
# second only while the machine still has room.
_slots = threading.BoundedSemaphore(int(os.environ.get("ZHIYIN_LLM_CONCURRENCY", 4)))
_active = [0]
_count = threading.Lock()


def _room() -> bool:
    try:
        for line in open("/proc/meminfo"):
            if line.startswith("MemAvailable:"):
                return int(line.split()[1]) > 450_000
    except OSError:
        pass
    return True


def _run(cmd, prompt, timeout):
    with _slots:
        while _active[0] and not _room():
            time.sleep(5)
        with _count:
            _active[0] += 1
        try:
            return subprocess.run(cmd, input=prompt, capture_output=True, text=True, timeout=timeout, cwd="/tmp")
        finally:
            with _count:
                _active[0] -= 1


class LLMError(RuntimeError):
    pass


def call(prompt: str, system: str, schema: dict, model: str = "sonnet", timeout: int = 600, retries: int = 2) -> dict:
    cmd = BASE + ["--model", model, "--system-prompt", system, "--json-schema", json.dumps(schema)]
    last = None
    for attempt in range(retries + 1):
        try:
            p = _run(cmd, prompt, timeout)
            out = json.loads(p.stdout)
            if out.get("is_error"):
                raise LLMError(out.get("result") or p.stderr[:500])
            data = out.get("structured_output")
            if data is None:
                data = json.loads(out["result"])
            return data
        except (subprocess.TimeoutExpired, json.JSONDecodeError, LLMError, KeyError) as e:
            last = e
            time.sleep(3 * (attempt + 1))
    raise LLMError(f"claude -p failed after {retries + 1} attempts: {last}")
