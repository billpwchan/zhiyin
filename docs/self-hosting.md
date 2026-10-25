# Running Zhiyin

There are two setups. Start with the first; move to the second when a friend wants in.

| | On your Mac | On a server, for you and a few friends |
|---|---|---|
| Listeners | you | you plus whoever you invite |
| Likes come from | `zhiyin sync` with YouTube Music headers | each listener's Google sign-in |
| Likes you make in Zhiyin | stay in Zhiyin | are written back to YouTube Music |
| Audio model | runs locally | runs on a Mac worker; the server only asks |
| Claude | your own `claude` login | your subscription for you; an API key for anyone you invite |
| Needs | macOS or Linux, Python 3.13, [uv](https://docs.astral.sh/uv/), Claude | Docker, a domain, a Google Cloud project, a Mac for the worker |

## Whose Claude

Zhiyin calls Claude through the [Claude Code](https://docs.claude.com/en/docs/claude-code) CLI (`claude -p`), and
every call is billed to someone. Anthropic's [legal and compliance
page](https://code.claude.com/docs/en/legal-and-compliance#authentication-and-credential-use) sets who that can be.
A Claude subscription (Pro, Max) is for ordinary use by its owner, and an app may not route requests through it on
behalf of other people. An API key from the [Claude Console](https://platform.claude.com/) is different: the same
page allows configuring your own key for use by your own authorized users, as long as the usage is billed to you
and not resold. That fits a few people you know. Opening Zhiyin to the public is another matter: the page's section
on offering Claude Code in products expects each end user to bring their own credentials.

| Who is listening | Whose Claude runs their calls |
|---|---|
| you, on your Mac | your `claude` login there, a subscription or an API key |
| you, on your server | your subscription: a token on the server if you added one, otherwise the Mac worker |
| another account of yours (a second YouTube library) | the same as you: it is still you listening |
| anyone you invite | your API key on the server, billed to you per use |

The server holds to this. Your subscription only ever runs your own calls, and inviting someone stays closed until
the server has an API key. Without a token on the server, your calls go to the Mac worker, which runs them on the
`claude` login there, even when the server has an API key (that key is for the people you invite). While the Mac
sleeps, the morning edition waits for it. With no worker either, your calls use the API key.

On an API key, for a library of about 800 likes: a daily edition costs about $0.50 (measured: eight Opus calls),
a first setup about $2 (tagging every like, finding the stations and the first edition; estimated from its prompt
sizes), and an ask about $0.10 (estimated: one Opus pick plus a small plan).
Each invited listener can spend up to $3 a day (`ZHIYIN_LISTENER_DAILY_USD`); past that, asks and rebuilds wait
for the next day. `zhiyin users` and the 朋友 panel show what each listener used over the last seven days, priced
as on an API key.

## On your Mac

```sh
git clone https://github.com/billpwchan/zhiyin && cd zhiyin
uv sync                      # includes the audio model's dependencies (torch, MuQ)
claude                       # sign in once, then quit
uv run zhiyin auth           # explains how to save YouTube Music request headers for ytmusicapi
uv run zhiyin sync           # read your liked songs
uv run zhiyin about "I grew up in Taipei and listen in Mandarin, Japanese and English"   # optional
uv run zhiyin profile        # stations and the portrait (a few minutes)
uv run zhiyin listen         # a 30-second preview of every like through the audio model (about an hour, once)
uv run zhiyin refresh        # the first edition
uv run zhiyin serve          # http://localhost:8817
```

To keep it running from login, run `uv run zhiyin service install`. It builds a fresh edition every morning at
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
```

Secrets live in `/opt/zhiyin/secrets/zhiyin.env` on the server, never in the repository. Data lives in
`/opt/zhiyin/data`.

| Variable | What it is |
|---|---|
| `ZHIYIN_PUBLIC_URL` | the site's address; set by the deploy scripts from `SITE` |
| `CLAUDE_CODE_OAUTH_TOKEN` | optional: your subscription on the server, for your own calls (`deploy/claude-token.sh`) |
| `ANTHROPIC_API_KEY` | optional: an API key for invited listeners (`deploy/claude-token.sh --api-key`) |
| `ZHIYIN_LISTENER_DAILY_USD` | what each invited listener may spend on your API key per day (default 3) |
| `ZHIYIN_OWNER_DAILY_USD` | a ceiling on your own calls per day, priced as on an API key (default 10); a normal day is $1–2 |
| `ZHIYIN_WORKER_TOKEN` | shared with the worker; `deploy/worker-setup.sh` creates both ends |
| `ZHIYIN_LLM_CONCURRENCY` | parallel `claude -p` calls (the image sets 2) |
| `TZ` | the time zone the morning edition (05:00) follows, e.g. `Asia/Taipei`; the image defaults to UTC |
| `ZHIYIN_YT_REGION` | YouTube region code for what is available, e.g. `TW`; empty lets YouTube go by the server's IP |
| `ZHIYIN_YT_LANGUAGE` | the language titles and artist names are read in (default `zh_TW`) |

### 2. Let Claude in

With the worker running (step 5), your own listening needs nothing more: the server hands your calls to the Mac.
Two optional additions, each run in your own terminal; whatever you paste is not shown and goes straight to the
server, which then checks that Claude answers.

- `deploy/claude-token.sh` puts your subscription on the server (`claude setup-token`), so your editions no longer
  wait for the Mac to be awake.
- `deploy/claude-token.sh --api-key` adds an API key, which is what invited listeners run on. Without one you
  can't invite anyone. `--remove-api-key` takes it away again.

### 3. Google sign-in

Each listener signs in with Google, and Zhiyin reads their liked songs through the YouTube Data API. Liking a song
in Zhiyin likes it on YouTube Music too; "not for me" stays in Zhiyin.

1. In [Google Cloud Console](https://console.cloud.google.com/), create a project and enable **YouTube Data API v3**.
2. Under **OAuth consent screen**, choose *External*. On **Branding**, set the home page to your site and the privacy
   policy to `https://<your site>/privacy` (Zhiyin serves it; Google won't publish an app without both), and add
   your domain under authorized domains. Then publish the app on **Audience**. You don't need verification for a
   handful of people: Google shows them an "unverified app" notice first, and allows up to 100 users.
3. Under **Credentials**, create an **OAuth client ID** of type *Web application*. Add
   `https://<your site>/auth/google/callback` as an authorized redirect URI, and download the JSON.
4. Run `deploy/google-client.sh ~/Downloads/client_secret_….json`. It checks the client and installs it as
   `data/google_client.json`. No restart is needed.

The scopes are `openid email profile` to sign in, plus `youtube` to read likes and rate videos. Tokens are encrypted
at rest with a key in `data/secret.key`.

### 4. Invite people

```sh
docker exec zhiyin zhiyin invite --owner      # a sign-in link for yourself
docker exec zhiyin zhiyin invite "Ming"       # a link for a friend, valid 14 days
docker exec zhiyin zhiyin users
```

A friend opens the link and connects Google. Their first edition takes about ten minutes; the page says when it's
ready. Invites need an API key on the server (step 2). Once a listener has connected Google, links no longer sign
them in: on another device they sign in with the same Google account, so a forwarded link opens nothing.

Have a second YouTube Music account of your own? Under 朋友, "加你自己的另一个账号" (or `zhiyin invite --mine`) makes
a link for it. It keeps its own likes and stations, runs on your Claude like your main account, and needs no API
key. Each account shows a bookmark under 账号 (`/auth/google/start?mode=login&as=<email>`): with both Google
accounts signed in to the browser, one click switches between them.

### 5. Start the audio worker

On the Mac, in a clone of this repository, run `deploy/worker-setup.sh`. It makes a worker token, stores it on both
sides and installs `zhiyin worker` as a login service. One worker hears songs for every listener, since a song's
vector doesn't depend on who likes it. If the server has no Claude token of its own, the worker also runs your
Claude calls, and only yours. Run one worker, not two. Those calls reach it through the running server, so start a rebuild from the page
(or let the morning schedule do it); a separate `docker exec zhiyin zhiyin refresh` can't reach the worker.

Once the server is your home, the Mac is only its worker. Don't also keep `zhiyin serve` running there: it is a
separate copy with its own history, and builds its own, different edition every morning.

## Data

| Where | What |
|---|---|
| `data/zhiyin.db` | SQLite: listeners, sessions, feedback, plays, editions shown, sound vectors |
| `data/users/<id>/` | each listener's likes, profile, current edition and settings (JSON) |
| `data/cache/` | YouTube Music responses, lyrics and cover art |
| `data/secret.key`, `data/google_client.json`, `data/worker.json` | secrets; back them up, never commit them |

Removing a listener's folder and rows removes them completely. See [privacy](privacy.md).
