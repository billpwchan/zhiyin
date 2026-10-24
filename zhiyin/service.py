"""Run from login with launchd: the app itself (the page is always there and the daily edition is built at 05:00),
or, once the app lives on the server, the audio worker that listens for it."""
import os
import plistlib
import shutil
import subprocess
from pathlib import Path

from . import store

LABEL = "local.zhiyin"
PLIST = Path.home() / "Library/LaunchAgents" / f"{LABEL}.plist"
DOMAIN = f"gui/{os.getuid()}"
LOG = Path.home() / "Library/Logs/zhiyin.log"


def install(worker: bool = False):
    uv = shutil.which("uv")
    claude = shutil.which("claude")
    ffmpeg = shutil.which("ffmpeg")
    if not uv:
        raise SystemExit("uv not found on PATH")
    path = [str(Path(x).parent) for x in (uv, claude, ffmpeg) if x] + ["/usr/bin", "/bin", "/usr/sbin", "/sbin"]
    spec = {
        "Label": LABEL,
        "ProgramArguments": [uv, "run", "--project", str(store.ROOT), "zhiyin", *(["worker"] if worker else ["serve", "--no-open"])],
        "WorkingDirectory": str(store.ROOT),
        "EnvironmentVariables": {"PATH": ":".join(dict.fromkeys(path)), "HOME": str(Path.home())},
        "RunAtLoad": True,
        "KeepAlive": {"SuccessfulExit": False},
        "ThrottleInterval": 30,
        "ProcessType": "Background",
        # launchd may not write into ~/Documents (privacy protection), so the service logs to ~/Library/Logs
        "StandardOutPath": str(LOG),
        "StandardErrorPath": str(LOG),
    }
    PLIST.parent.mkdir(parents=True, exist_ok=True)
    if PLIST.exists():
        subprocess.run(["launchctl", "bootout", f"{DOMAIN}/{LABEL}"], capture_output=True)
    PLIST.write_bytes(plistlib.dumps(spec))
    r = subprocess.run(["launchctl", "bootstrap", DOMAIN, str(PLIST)], capture_output=True, text=True)
    if r.returncode != 0:
        raise SystemExit(f"launchctl bootstrap failed: {r.stderr.strip()}")
    what = "the audio worker" if worker else "http://localhost:8817"
    print(f"installed: {what} now starts at login ({PLIST}, log {LOG})")


def uninstall():
    subprocess.run(["launchctl", "bootout", f"{DOMAIN}/{LABEL}"], capture_output=True)
    PLIST.unlink(missing_ok=True)
    print("uninstalled")


def status():
    r = subprocess.run(["launchctl", "print", f"{DOMAIN}/{LABEL}"], capture_output=True, text=True)
    if r.returncode != 0:
        print("not installed")
        return
    state = next((l.strip() for l in r.stdout.splitlines() if l.strip().startswith("state =")), "")
    pid = next((l.strip() for l in r.stdout.splitlines() if l.strip().startswith("pid =")), "")
    print(f"{LABEL}: {state} {pid}")
