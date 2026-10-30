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
    sub.add_parser("oauth-scopes", help="print this deployment's exact Google OAuth scopes (no credentials)")
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
    sub.add_parser("check-key", help="one tiny call on the server's API key, the way listeners' calls are made")
    p = sub.add_parser("stats", help="the way in, counted per day and by where people came from")
    p.add_argument("--days", type=int, default=7)
    p = sub.add_parser("waitlist", help="who asked to join while the seats were full (ZHIYIN_SEATS)")
    p.add_argument("--admit", metavar="EMAIL", help="let this person in on their next Google sign-in, seats or not")
    p = sub.add_parser("cards", help="cards shared by link (/c/...), newest first")
    p.add_argument("--rm", metavar="ID", help="take one down")
    p = sub.add_parser("about", help="tell the editor who you are (languages, where you grew up); shown in its prompts")
    p.add_argument("text", nargs="?")
    sub.add_parser("worker", help="on the Mac: hear the songs the server asks for, and run the owner's Claude calls if the server has no login")
    p = sub.add_parser("quality", help="how the recommended songs fared on their first listen (set ZHIYIN_USER for another listener)")
    p.add_argument("--days", type=int, default=14)
    p = sub.add_parser("eval", help="offline check: hide your newest likes and see if the engine finds them")
    p.add_argument("--holdout", type=int, default=60)
    p.add_argument("--audio", action="store_true", help="check whether sound alone predicts new likes")
    p = sub.add_parser("eval-screen", help="offline check of the screen on rolling held-out windows of your own accounts' "
                                          "likes: build the pools, submit the reads as one batch, collect, report")
    p.add_argument("step", choices=("build", "submit", "collect", "report"))
    p.add_argument("--windows", type=int, default=4)
    p.add_argument("--size", type=int, default=60, help="likes per window")
    p.add_argument("--arms", default="opus,sonnet", help="comma-separated: opus, sonnet, opus-medium, sonnet-medium")
    p.add_argument("--passes", type=int, default=3)
    p.add_argument("--go", action="store_true", help="submit for real (without it: the estimate only)")
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
    elif a.cmd == "oauth-scopes":
        import json
        from . import google
        print(json.dumps(google.scope_manifest(), indent=2))
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
    elif a.cmd == "check-key":
        from . import llm
        if not llm.API_KEY:
            sys.exit("no ANTHROPIC_API_KEY on this server")
        try:
            print(llm.run_api("Reply with the single word: ready", "Answer in JSON.",
                              {"type": "object", "properties": {"word": {"type": "string"}}, "required": ["word"]},
                              "haiku", 60, 0)["data"]["word"])
        except llm.LLMError as e:
            sys.exit(str(e))
    elif a.cmd == "stats":
        import time
        since = time.strftime("%Y-%m-%d", time.localtime(time.time() - (a.days - 1) * 86400))
        steps = ["visit", "yt_down", "sample_play", "join_start", "join_cancel", "join_noscope", "join_full", "join_ok",
                 "first_disc", "named", "ready", "thin", "no_channel", "setup_error", "share_open", "share_send", "share_save", "share_copy",
                 "card_try", "card_made", "card_named", "card_private", "card_few", "card_link", "card_song", "card_upstream",
                 "card_shared", "card_view", "join_163", "join_qq", "inapp"]
        rows = store.db().execute("select ref, name, sum(n) n from events where day >= ? group by ref, name", (since,)).fetchall()
        refs = sorted({r["ref"] for r in rows}, key=lambda x: -sum(r["n"] for r in rows if r["ref"] == x))
        got = {(r["ref"], r["name"]): r["n"] for r in rows}
        used = [s for s in steps if any((r, s) in got for r in refs)]
        print(f"since {since}")
        print(f"{'from':18}" + "".join(f"{s:>13}" for s in used))
        for r in refs:
            print(f"{r or '(unknown)':18}" + "".join(f"{got.get((r, s), 0):>13}" for s in used))
    elif a.cmd == "cards":
        import time
        from . import cards
        if a.rm:
            print(f"removed {a.rm}" if cards.remove(a.rm, operator=True) else f"no card {a.rm}")
        for c in cards.listing():
            print(f"{time.strftime('%m-%d %H:%M', time.localtime(c['created']))}  /c/{c['id']:10} {c['views']:>5} views  "
                  f"{c['n']:>5} likes since {c['since']}  {c['uid'] or '-':10} {c['label']}")
    elif a.cmd == "waitlist":
        import time
        con = store.db()
        if a.admit:
            n = con.execute("update waitlist set admitted=? where lower(email)=lower(?)", (time.time(), a.admit)).rowcount
            con.commit()
            print(f"admitted {a.admit}: they get in on their next 'Join with Google'" if n else f"{a.admit} is not on the waitlist")
        for r in con.execute("select email, name, ts, lang, admitted, src from waitlist order by ts"):
            print(f"{time.strftime('%m-%d %H:%M', time.localtime(r['ts']))}  {r['email']:32} {r['name'] or '-':16} "
                  f"{r['lang'] or '-':8} {'NetEase' if r['src'] else 'YouTube':8} {'admitted' if r['admitted'] else 'waiting'}")
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
    elif a.cmd == "quality":
        from . import quality
        prof = store.read_json(store.PROFILE) or {}
        quality.print_report(quality.report(a.days), {l["key"]: l["name"] for l in prof.get("lanes", [])})
    elif a.cmd == "eval-screen":
        from . import evaluate
        arms = tuple(a.arms.split(","))
        if a.step == "build":
            for uid in evaluate.owner_accounts():
                with store.as_user(uid):
                    evaluate.screen_build(a.windows, a.size)
        elif a.step == "submit":
            evaluate.screen_submit(arms, a.passes, a.go)
        elif a.step == "collect":
            evaluate.screen_collect()
        else:
            evaluate.screen_report(arms, a.passes)
    elif a.cmd == "eval":
        from . import evaluate
        evaluate.audio_check(a.holdout) if a.audio else evaluate.run(a.holdout)
    return 0


if __name__ == "__main__":
    sys.exit(main())
