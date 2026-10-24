# Running Zhiyin

There are two setups. Start with the first; move to the second when a friend wants in.

| | On your Mac | On a server, for you and a few friends |
|---|---|---|
| Listeners | you | you plus whoever you invite |
| Likes come from | `zhiyin sync` with YouTube Music headers | each listener's Google sign-in |
| Likes you make in Zhiyin | stay in Zhiyin | are written back to YouTube Music |
| Audio model | runs locally | runs on a Mac worker; the server only asks |
| Needs | macOS or Linux, Python 3.13, [uv](https://docs.astral.sh/uv/), Claude | Docker, a domain, a Google Cloud project, Claude, a Mac for the audio worker |

Zhiyin calls Claude through the [Claude Code](https://docs.claude.com/en/docs/claude-code) CLI (`claude -p`), so it
uses your Claude subscription, or an API key if `ANTHROPIC_API_KEY` is set. A daily edition is about ten calls.

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

The server runs one small container: about 150 MB, plus up to two `claude -p` processes of about 255 MB each.
A 2 GB machine is enough. It has no room for the audio model, so a Mac (or any machine with the `audio`
dependency group) runs `zhiyin worker`. The worker polls the server for songs it wants heard and sends the vectors
back. Editions are built without waiting for it; sound fills in when the worker catches up.

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
| `CLAUDE_CODE_OAUTH_TOKEN` | from `claude setup-token`; `deploy/claude-token.sh` puts it in place without echoing it |
| `ZHIYIN_WORKER_TOKEN` | shared with the audio worker; `deploy/worker-setup.sh` creates both ends |
| `ZHIYIN_LLM_CONCURRENCY` | parallel `claude -p` calls (the image sets 2) |
| `TZ` | the time zone the morning edition (05:00) follows, e.g. `Asia/Taipei`; the image defaults to UTC |
| `ZHIYIN_YT_REGION` | YouTube region code for what is available, e.g. `TW`; empty lets YouTube go by the server's IP |
| `ZHIYIN_YT_LANGUAGE` | the language titles and artist names are read in (default `zh_TW`) |

### 2. Let Claude in

Run `deploy/claude-token.sh` in your own terminal. It runs `claude setup-token`, asks you to paste the token
(nothing is shown), stores it on the server and checks that the editor answers.

### 3. Google sign-in

Each listener signs in with Google, and Zhiyin reads their liked songs through the YouTube Data API. Liking a song
in Zhiyin likes it on YouTube Music too; "not for me" stays in Zhiyin.

1. In [Google Cloud Console](https://console.cloud.google.com/), create a project and enable **YouTube Data API v3**.
2. Under **OAuth consent screen**, choose *External*, add your domain under authorized domains, and publish the app.
   You don't need verification for a handful of people: Google shows them an "unverified app" notice first, and
   allows up to 100 users.
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
ready.

### 5. Start the audio worker

On the Mac, in a clone of this repository, run `deploy/worker-setup.sh`. It makes a worker token, stores it on both
sides and installs `zhiyin worker` as a login service. One worker serves every listener, since a song's vector
doesn't depend on who likes it.

## Data

| Where | What |
|---|---|
| `data/zhiyin.db` | SQLite: listeners, sessions, feedback, plays, editions shown, sound vectors |
| `data/users/<id>/` | each listener's likes, profile, current edition and settings (JSON) |
| `data/cache/` | YouTube Music responses, lyrics and cover art |
| `data/secret.key`, `data/google_client.json`, `data/worker.json` | secrets; back them up, never commit them |

Removing a listener's folder and rows removes them completely. See [privacy](privacy.md).
