import argparse
import sys
import webbrowser

from . import store


def main():
    ap = argparse.ArgumentParser(prog="zhiyin", description="知音: a recommender built on your own YouTube Music likes")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("import", help="load a liked-songs TSV exported from the browser")
    p.add_argument("tsv")
    sub.add_parser("auth", help="connect your YouTube Music account (you paste request headers)")
    sub.add_parser("sync", help="re-read likes from your account (needs auth)")
    p = sub.add_parser("profile", help="rebuild the taste profile (tags, lanes, portrait)")
    p.add_argument("--model", default="opus")
    sub.add_parser("listen", help="fetch a preview of every liked song and learn what it sounds like (once, ~1 hour)")
    sub.add_parser("refresh", help="build a new edition of recommendations")
    sub.add_parser("setup", help="first run: sync, profile, listen and refresh in one go (about an hour)")
    p = sub.add_parser("ask", help="ask for songs in your own words")
    p.add_argument("question")
    p = sub.add_parser("serve", help="run the app")
    p.add_argument("--port", type=int, default=8817)
    p.add_argument("--no-open", action="store_true")
    p = sub.add_parser("service", help="keep the app (or, with --worker, the worker) running from login (macOS launchd)")
    p.add_argument("action", choices=["install", "uninstall", "status"])
    p.add_argument("--worker", action="store_true")
    p = sub.add_parser("invite", help="make an invite link for a friend (or, with --owner, a sign-in link for yourself; "
                                      "with --mine, another account of your own)")
    p.add_argument("name", nargs="?", default="")
    p.add_argument("--owner", action="store_true")
    p.add_argument("--mine", action="store_true", help="another account of yours: it runs on your Claude")
    sub.add_parser("users", help="who has joined")
    p = sub.add_parser("waitlist", help="who asked to join while the seats were full (ZHIYIN_SEATS)")
    p.add_argument("--admit", metavar="EMAIL", help="let this person in on their next Google sign-in, seats or not")
    p = sub.add_parser("about", help="tell the editor who you are (languages, where you grew up); shown in its prompts")
    p.add_argument("text", nargs="?")
    sub.add_parser("worker", help="on the Mac: hear the songs the server asks for, and run the owner's Claude calls if the server has no login")
    p = sub.add_parser("eval", help="offline check: hide your newest likes and see if the engine finds them")
    p.add_argument("--holdout", type=int, default=60)
    p.add_argument("--audio", action="store_true", help="check whether sound alone predicts new likes")
    a = ap.parse_args()

    if a.cmd in ("setup", "profile", "refresh", "ask"):
        from . import accounts, i18n
        i18n.migrate()
        if not accounts.prefs(store.uid()).get("lang"):   # nobody has opened the app yet to say which language
            accounts.set_prefs(store.uid(), lang=i18n.system())
            print(f"writing in {i18n.of()} (set ZHIYIN_LANG=en, zh-Hans or zh-Hant to choose; switch later in Settings)")

    if a.cmd == "import":
        from . import library
        recs = library.import_snapshot(a.tsv)
        library.estimate_like_dates(recs)
        library.save(recs)
        print(f"{len(recs)} likes imported")
    elif a.cmd == "auth":
        print("1. In Chrome open https://music.youtube.com (signed in), DevTools > Network, filter 'browse',\n"
              "   click any request, copy its Request Headers.\n"
              f"2. Run:  uv run ytmusicapi browser --file {store.AUTH}\n"
              "   and paste the headers, then press Ctrl-D.\n"
              "Headers expire every few weeks; when sync or playlists start failing, repeat this.")
    elif a.cmd == "sync":
        from . import library
        recs = library.sync_from_account()
        library.estimate_like_dates(recs)
        library.save(recs)
        print(f"{len(recs)} likes synced")
    elif a.cmd == "profile":
        from . import profile
        prof = profile.build(a.model)
        print(f"{len(prof['lanes'])} lanes: " + ", ".join(l["name"] for l in prof["lanes"]))
    elif a.cmd == "listen":
        from . import audio, library
        print(audio.ensure([t for t in library.load() if not t["long"]], timeout=4 * 3600, itunes_budget=2000))
    elif a.cmd == "service":
        from . import service
        getattr(service, a.action)(**({"worker": a.worker} if a.action == "install" else {}))
    elif a.cmd == "invite":
        from . import accounts, google, llm
        if not (a.owner or a.mine) and llm.HOSTED and not llm.API_KEY:
            raise SystemExit("set ANTHROPIC_API_KEY on the server first: a Claude subscription is for your own use, "
                             "so other listeners run on an API key (docs/self-hosting.md)")
        tok = accounts.invite(a.name or ("me" if a.owner else "我的另一个账号" if a.mine else "friend"),
                              uid=store.OWNER if a.owner else None, mine=a.mine)
        print(f"{google.public_url()}/i/{tok}  (valid {accounts.INVITE_DAYS} days)")
    elif a.cmd == "users":
        from . import accounts, llm
        for u in accounts.users():
            seen = __import__("time").strftime("%m-%d %H:%M", __import__("time").localtime(u["last_seen"])) if u["last_seen"] else "-"
            print(f"{u['id']:10} {u['name'] or '-':12} {u['status']:9} {u.get('email') or '-':28} last seen {seen}  "
                  f"claude {llm.source(u['id']) or 'none'}, ${llm.spent(u['id']):.2f} in 7 days")
    elif a.cmd == "waitlist":
        import time
        con = store.db()
        if a.admit:
            n = con.execute("update waitlist set admitted=? where lower(email)=lower(?)", (time.time(), a.admit)).rowcount
            con.commit()
            print(f"admitted {a.admit}: they get in on their next 'Join with Google'" if n else f"{a.admit} is not on the waitlist")
        for r in con.execute("select email, name, ts, lang, admitted from waitlist order by ts"):
            print(f"{time.strftime('%m-%d %H:%M', time.localtime(r['ts']))}  {r['email']:32} {r['name'] or '-':16} "
                  f"{r['lang'] or '-':8} {'admitted' if r['admitted'] else 'waiting'}")
    elif a.cmd == "about":
        from . import accounts
        if a.text is not None:
            accounts.set_prefs(store.OWNER, about=a.text.strip() or None)
        print(accounts.prefs(store.OWNER).get("about") or "(not set: the editor infers it from your likes)")
    elif a.cmd == "worker":
        from . import worker
        worker.loop()
    elif a.cmd == "refresh":
        from . import edition
        edition.build()
    elif a.cmd == "setup":
        from . import audio, edition, library, profile
        recs = library.sync_from_account()
        library.estimate_like_dates(recs)
        library.save(recs)
        print(f"{len(recs)} likes synced")
        prof = profile.build()
        print(f"{len(prof['lanes'])} lanes: " + ", ".join(l["name"] for l in prof["lanes"]))
        print(audio.ensure([t for t in library.load() if not t["long"]], timeout=4 * 3600, itunes_budget=2000))
        edition.build()
        print("ready: uv run zhiyin serve")
    elif a.cmd == "ask":
        from . import ask
        r = ask.run(a.question)
        for p in r["picks"]:
            print(f"{p['title']} — {', '.join(x['name'] for x in p['artists'])}  ·  {p['reason']}")
    elif a.cmd == "serve":
        import uvicorn
        if not a.no_open:
            webbrowser.open(f"http://localhost:{a.port}")
        uvicorn.run("zhiyin.server:app", host="127.0.0.1", port=a.port, log_level="warning")
    elif a.cmd == "eval":
        from . import evaluate
        evaluate.audio_check(a.holdout) if a.audio else evaluate.run(a.holdout)
    return 0


if __name__ == "__main__":
    sys.exit(main())
