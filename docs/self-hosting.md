# Running Zhiyin

There are two setups. Start with the first; move to the second when a friend wants in.

| | On your Mac | On a server, for you and a few friends |
|---|---|---|
| Listeners | you | you, whoever you invite, and as many others as you open seats for |
| Likes come from | `zhiyin sync` with YouTube Music headers | each listener's Google sign-in |
| Likes you make in Zhiyin | stay in Zhiyin | can be written back to YouTube Music, once each listener allows it |
| Audio model | runs locally | runs on a Mac worker; the server only asks |
| Claude | your own `claude` login | your subscription for you; an API key for everyone else |
| Needs | macOS or Linux, Python 3.13, [uv](https://docs.astral.sh/uv/), Claude | Docker, a domain, a Google Cloud project, a Mac for the worker |

## Whose Claude

Every Claude call is billed to someone. Anthropic's [legal and compliance
page](https://code.claude.com/docs/en/legal-and-compliance#authentication-and-credential-use) sets who that can be.
A Claude subscription (Pro, Max) is for ordinary use by its owner, and an app may not route requests through it on
behalf of other people. An API key from the [Claude Console](https://platform.claude.com/) is different: the same
page allows configuring your own key for use by your own authorized users, as long as the usage is billed to you
and not resold. Calls on your subscription go through the [Claude Code](https://docs.claude.com/en/docs/claude-code)
CLI (`claude -p`); calls on an API key go straight to the Messages API, the way any app built on Claude serves its
own users.

| Who is listening | Whose Claude runs their calls |
|---|---|
| you, on your Mac | your `claude` login there, a subscription or an API key |
| you, on your server | your API key if the server has one; otherwise your subscription (a token on the server, or the Mac worker) |
| another account of yours (a second YouTube library) | the same as you: it is still you listening |
| anyone you invite, or who joins on an open seat | your API key on the server, billed to you per use |

The server holds to this. Your subscription only ever runs your own calls, and inviting someone stays closed until
the server has an API key. With a key on the server, your own calls run on it too, so your subscription stays free
for your own work and nothing waits for the Mac; they are counted apart from the listeners' monthly budget, against
your own daily ceiling, run at a higher effort, and your weekly edition goes as a batch at half price. Settings
shows what your calls came to today and over the week, in calls, tokens and dollars. Without a key, your calls go to
a token on the server if you added one, otherwise to the Mac worker, which runs them on the `claude` login there;
while the Mac sleeps, the morning edition waits for it.

Listeners on the API key get Sonnet where you get Opus. On the same shortlists Sonnet kept 75% of Opus's picks and
wrote reasons as good, at a third of the price: an edition of eight stations cost $0.13 against $0.39 (Haiku, at
$0.02, kept half and slipped into the wrong language). Before the editor, Sonnet also reads each station's whole
pool, about $0.075 a station, when what is left of the listener's day covers it (see how-it-works.md, section 4).
A new edition comes once a week, at 05:00 seven days after
the last one; only the stations a listener played from are rebuilt, and those builds go through the Batch API at half
price. A listener who hasn't opened Zhiyin for two weeks gets no new edition until they come back. A first setup for a library of about 800 likes costs about $2.

Three limits keep the key's bill where you set it:

- the key's monthly budget (`ZHIYIN_KEY_MONTHLY_USD`, default 100), counted over the last 30 days;
- scheduled rebuilds may run at no more than twice the even daily pace of that budget;
- each listener's own day (`ZHIYIN_LISTENER_DAILY_USD`, default 0.5); past that, their asks and rebuilds wait for
  the next day;
- each listener's first setup (`ZHIYIN_LISTENER_FIRST_RUN_USD`, default 4 per 800 liked songs, at most
  `ZHIYIN_LISTENER_FIRST_RUN_MAX_USD`, default 20, over 30 days), counted apart from their day so that joining never
  stops halfway. When what is left of the month's budget can't pay for one more first
  setup, new people go on the waitlist even if seats are free.

So open seats to match the budget: a newcomer costs about $2 to set up, then cents a day while they listen.

`zhiyin users` and the 朋友 panel show what each listener used over the last seven days, priced as on an API key.

## On your Mac

```sh
git clone https://github.com/billpwchan/zhiyin && cd zhiyin
uv sync                      # includes the audio model's dependencies (torch, MuQ)
claude                       # sign in once, then quit
uv run zhiyin auth           # explains how to save YouTube Music request headers for ytmusicapi
uv run zhiyin about "I grew up in Taipei and listen in Mandarin, Japanese and English"   # optional
uv run zhiyin setup          # read your likes, find your stations, hear every like once, pick the first edition (about an hour)
uv run zhiyin serve          # http://localhost:8817
```

`setup` runs `sync`, `profile`, `listen` and `refresh` in turn; each can also be run on its own later. The stations
and reasons are written in your system language (set `ZHIYIN_LANG=en`, `zh-Hans` or `zh-Hant` to choose) and can be
switched in Settings.

To keep it running from login, run `uv run zhiyin service install`. It builds a fresh edition every week, at
05:00. In Chrome you can install the page as an app.

The headers that `zhiyin auth` saves expire every few weeks. When `sync` starts failing, save them again.

## On a server

The server runs one small container: about 150 MB, plus up to two `claude -p` processes of about 255 MB each when
it runs Claude itself. A 2 GB machine is enough. It has no room for the audio model, so a Mac (or any machine with
the `audio` dependency group) runs `zhiyin worker`. The worker polls the server for songs it wants heard and sends
the vectors back. Editions are built without waiting for sound; it fills in when the worker catches up.

### 1. Put it behind your reverse proxy

`deploy/compose.yaml` expects an external Docker network that your reverse proxy is on (`GATEWAY_NETWORK`,
default `proxy`), and serves on port 8817 inside it. With Caddy, see `deploy/gateway.caddy.example`.

`deploy/deploy.sh` copies the code to `/opt/zhiyin/releases/<stamp>`, points `/opt/zhiyin/current` at it, builds
the image and restarts. It reads `deploy/local.conf` (git-ignored):

```sh
KEY=~/.ssh/your-key.pem
HOST=ubuntu@your-server
SITE=https://zhiyin.example.com
GATEWAY_NETWORK=proxy
YT_LANGUAGE=en        # optional, see ZHIYIN_YT_LANGUAGE below
```

Secrets live in `/opt/zhiyin/secrets/zhiyin.env` on the server, never in the repository. Data lives in
`/opt/zhiyin/data`.

| Variable | What it is |
|---|---|
| `ZHIYIN_PUBLIC_URL` | the site's address; set by the deploy scripts from `SITE` |
| `CLAUDE_CODE_OAUTH_TOKEN` | optional: your subscription on the server, for your own calls (`deploy/claude-token.sh`) |
| `ANTHROPIC_API_KEY` | optional: an API key for everyone but you (`deploy/claude-token.sh --api-key`) |
| `ZHIYIN_KEY_MONTHLY_USD` | the API key's budget over 30 days (default 100) |
| `ZHIYIN_LISTENER_DAILY_USD` | what each listener may spend on the API key per day (default 0.5) |
| `ZHIYIN_CARD_DAILY_USD` | what naming records made from NetEase or QQ Music links without signing in may spend on the API key per day, all visitors together (default 2; about a fifth of a cent each) |
| `ZHIYIN_KEY_OPUS`, `ZHIYIN_KEY_SONNET` | the model listeners get where you get Opus or Sonnet (defaults `sonnet`, `sonnet`) |
| `ZHIYIN_SEATS` | how many people may join with Google without an invite (default 0: invites only) |
| `ZHIYIN_GOOGLE_VERIFIED` | `1` once Google has verified the app; drops the "unverified app" note from the join sheet |
| `ZHIYIN_HEAVY`, `ZHIYIN_GATHER` | how many first setups, and how many candidate gatherings, run at once (default 2 each) |
| `ZHIYIN_OWNER_DAILY_USD` | a ceiling on your own calls per day, priced as on an API key (default 30); a full edition measured $8.50 for eight stations when Claude read every station's whole pool three times; it now reads it once, about $2.80 less |
| `ZHIYIN_WORKER_TOKEN` | shared with the worker; `deploy/worker-setup.sh` creates both ends |
| `ZHIYIN_LLM_CONCURRENCY` | parallel `claude -p` calls (the image sets 2) |
| `TZ` | the time zone the morning edition (05:00) follows, e.g. `Asia/Taipei`; the image defaults to UTC |
| `ZHIYIN_YT_REGION` | YouTube region code for what is available, e.g. `TW`; empty lets YouTube go by the server's IP |
| `ZHIYIN_YT_LANGUAGE` | the YouTube Music language song titles and artist names are read in (default `en`). It is one setting for the whole server; `zh_TW` reads them the way YouTube Music shows them in Taiwan. Each listener picks the app's own language in Settings |

### 2. Let Claude in

With the worker running (step 5), your own listening needs nothing more: the server hands your calls to the Mac.
Two optional additions, each run in your own terminal; whatever you paste is not shown and goes straight to the
server, which then checks that Claude answers.

- `deploy/claude-token.sh` puts your subscription on the server (`claude setup-token`), so your editions no longer
  wait for the Mac to be awake.
- `deploy/claude-token.sh --api-key` adds an API key, which is what invited listeners run on. Without one you
  can't invite anyone. `--remove-api-key` takes it away again.

### 3. Google sign-in

Each listener signs in with Google, and Zhiyin reads their liked songs through the YouTube Data API. A like in
Zhiyin becomes a like on YouTube Music only for listeners who turn that on; "not for me" always stays in Zhiyin.

1. In [Google Cloud Console](https://console.cloud.google.com/), create a project and enable **YouTube Data API v3**.
2. Under **OAuth consent screen**, choose *External*. On **Branding**, set the home page to your site and the privacy
   policy to `https://<your site>/privacy` (Zhiyin serves it; Google won't publish an app without both), and add
   your domain under authorized domains. Then publish the app on **Audience**. You don't need verification for a
   handful of people: Google shows them an "unverified app" notice first, and allows up to 100 users. Past that,
   Google has to verify the app (the YouTube scopes are sensitive): it reviews the home page, the privacy policy, a
   short video of the sign-in, and how the app uses YouTube.
3. Under **Credentials**, create an **OAuth client ID** of type *Web application*. Add
   `https://<your site>/auth/google/callback` as an authorized redirect URI, and download the JSON.
4. Run `deploy/google-client.sh ~/Downloads/client_secret_….json`. It checks the client and installs it as
   `data/google_client.json`. No restart is needed.

The scopes are `openid email profile` to sign in and `youtube.readonly` to read likes. Writing likes back needs
`youtube` by default, which Zhiyin asks for only when a listener turns it on in Settings; this also enables saving
stations as private playlists. Enabling synchronization queues previous Zhiyin likes too. Tokens are encrypted at
rest with a key in `data/secret.key`. Data directories are restricted to the service's OS account (`0700`); this
does not encrypt the entire library or backups, whose protection remains the operator's responsibility.

For Google verification, run `docker exec zhiyin zhiyin oauth-scopes` to print the actual scope set without
credentials. An isolated review deployment can explicitly set
`ZHIYIN_YOUTUBE_WRITE_SCOPE=https://www.googleapis.com/auth/youtube.force-ssl` in its container environment (for
example, its own `secrets/zhiyin.env`) and restart. This permission supports the app's rating and playlist write
methods; existing `youtube` grants remain usable. Keep newly requested, unverified scopes away from production
traffic. Match the review deployment, Console Data Access and video exactly before submitting.

### 4. Let people in

```sh
docker exec zhiyin zhiyin invite --owner      # a sign-in link for yourself
docker exec zhiyin zhiyin invite "Ming"       # a link for a friend, valid 14 days
docker exec zhiyin zhiyin users
```

A friend opens the link and connects Google. Their first edition takes about ten minutes; the page says when it's
ready. Invites need an API key on the server (step 2). Once a listener has connected Google, links no longer sign
them in: on another device they sign in with the same Google account, so a forwarded link opens nothing.

To let people in without inviting each one, set `ZHIYIN_SEATS` (say `20`) and restart. Anyone who opens the
site without signing in hears a sample listener's stations (the files in `demo/`), read-only, in their browser's
language. Liking, asking or opening Settings there offers "Continue with Google", which makes an account, connects
YouTube Music read-only and starts their setup in one step. Joining needs an API key on the server. When the seats
are taken, people who try go on a waitlist instead:

```sh
docker exec zhiyin zhiyin waitlist                          # who is waiting
docker exec zhiyin zhiyin waitlist --admit ann@example.com  # lets Ann in on her next "Continue with Google"
```

Raising `ZHIYIN_SEATS` lets the next people in on their own. A seat is a joined account, so deleting one frees it.

First runs take a few minutes each and run two at a time (`ZHIYIN_HEAVY`); people further back are told their place
and roughly when theirs starts. To see how people find the site and how far they get, add `?ref=<name>` to the link
you post, then:

```sh
docker exec zhiyin zhiyin stats --days 7   # per source: visits, first listens, joins, records, names, shares
```

Only counts per day are kept, never who. A visitor's source sits in a cookie for 30 days so a later join still
counts for the link that brought them, and a shared card's link carries `?ref=card`.

Have a second YouTube Music account of your own? In Settings, under Friends, "Add another account of yours" (or
`zhiyin invite --mine`) makes a link for it. It is a separate account with its own Google sign-in, likes, stations
and feedback; the only thing it shares with yours is that it runs on your Claude, so it needs no API key. Each
account shows a sign-in bookmark under Account (`/auth/google/start?mode=login&as=<email>`) that opens it directly
in a browser where that Google account is signed in.

### 5. Start the audio worker

On the Mac, in a clone of this repository, run `deploy/worker-setup.sh`. It makes a worker token, stores it on both
sides and installs `zhiyin worker` as a login service. One worker hears songs for every listener, since a song's
vector doesn't depend on who likes it. If the server has no Claude token of its own, the worker also runs your
Claude calls, and only yours. Run one worker, not two. Those calls reach it through the running server, so start a rebuild from the page
(or let the morning schedule do it); a separate `docker exec zhiyin zhiyin refresh` can't reach the worker.

Once the server is your home, the Mac is only its worker. Don't also keep `zhiyin serve` running there: it is a
separate copy with its own history, and builds its own, different edition every week.

## Data

| Where | What |
|---|---|
| `data/zhiyin.db` | SQLite: listeners, sessions, feedback, plays, editions shown, sound vectors, the waitlist |
| `data/users/<id>/` | each listener's likes, profile, current edition and settings (JSON) |
| `data/cache/` | YouTube Music responses, lyrics and cover art |
| `data/secret.key`, `data/google_client.json`, `data/worker.json` | secrets; back them up, never commit them |

Removing a listener's folder and rows removes them completely. See [privacy](privacy.md).
