# Privacy

Updated October 28, 2026. The public-facing policy is served at `/privacy` in English, Simplified Chinese and
Traditional Chinese. Bill Chan operates `zhiyin.billpwchan.art`; a self-hosted copy has its own operator. Self-hosted
copies do not automatically send data to the project author. For the official deployment, privacy requests can be
sent to [billpwchan@gmail.com](mailto:billpwchan@gmail.com), the configured Google OAuth support address.
The operator of a hosted service receives and stores the data needed to run it. The only analytics are daily counts kept on the server itself (below).

## How Google user data is used

Google account ID, email and name identify the listener, link their account and let them sign in again. Access and
refresh tokens authorize Google requests, including background library refreshes while the page is closed.
`youtube.readonly` reads liked videos and dates, ratings, subscriptions and own-playlist entries. The API can return
non-music videos and channels before filtering; categories, durations and channel topics identify music.

Music IDs, titles, artists and dates build the library, Your Ear disc, taste name and portrait, stations and weekly
recommendation explanations. Disliked music is excluded; playlist entries identify songs already known; subscribed
artists guide discovery. Relevant music preferences are sent to Anthropic for inference, as disclosed below and
before connecting Google. Google account identifiers, email and OAuth tokens are not included in Claude prompts.

An optional write grant lets the listener synchronize likes (including previously recorded Zhiyin likes when
enabled), remove their rating when undoing a like, and save a station as a **private** YouTube playlist. Saved
playlists remain on YouTube until the listener removes them there. The deployment's selected write permission is
`youtube` by default; `ZHIYIN_YOUTUBE_WRITE_SCOPE=https://www.googleapis.com/auth/youtube.force-ssl` opts a review
deployment into the alternative supported by these write methods. No new scope should reach production users
before verification. Run `zhiyin oauth-scopes` for the actual requested scope set.

Zhiyin does not read Gmail, Drive or contacts, or use these permissions to upload, comment on or delete YouTube
videos. It does not sell Google user data, use it for advertising, share it with data brokers, or use it for credit
assessment or lending. Use and transfer comply with the
[Google API Services User Data Policy](https://developers.google.com/terms/api-services-user-data-policy), including
Limited Use. Google Workspace API data and other Google API data must not be used to develop, improve or train
generalized, non-personalized AI/ML models, by Zhiyin or its providers. The AI calls here perform inference for the
listener's visible features; the audio model runs inference on separately sourced previews and is not trained here.

## How sensitive data is protected

- Google OAuth, YouTube Data API and Anthropic API calls use HTTPS/TLS. Public deployments must use HTTPS.
- OAuth access and refresh tokens are encrypted with Fernet in SQLite. `data/secret.key` is created with mode
  `0600`; the data, cache and users directories have mode `0700`, restricting other operating-system accounts.
- Session and invitation tokens are random and stored as SHA-256 hashes. Session and OAuth cookies are HttpOnly,
  SameSite=Lax and Secure when `ZHIYIN_PUBLIC_URL` is HTTPS. OAuth state is bound to its browser cookie, expires
  after 15 minutes, is consumed once, and is paired with PKCE S256.
- Hosted API requests resolve the signed-in listener and reject writes from a stale account tab; per-user files
  and database rows are accessed in that user's context. Worker endpoints require a separate shared secret.
- Ordinary account responses omit OAuth tokens. The Google password is never received by Zhiyin.

These are specific application controls, **not** full database or backup encryption. Listening files and account
details are not individually encrypted by the application; the operator is responsible for encrypted volumes,
backup protection and restricting administrative access. Humans may read specific Google user data only with the
listener's affirmative agreement, where necessary for security, or as required by law. The operator must verify
the actual host/CDN and Anthropic account settings before publishing claims about them.

## What is stored

On the machine running Zhiyin:

- your liked songs and when they were liked (if Google says so), the profile built from them, and each edition, with
  their translation into the other language once you switch between Chinese and English;
- read from YouTube with the same read-only access, at most once a day along with the likes: the music you gave a
  thumbs-down, the music channels you subscribe to, and the songs in playlists you made (not the ones saved from
  Zhiyin's stations);
- if your likes come from a NetEase Cloud Music or QQ Music profile, and for any profile link you add on Your Ear
  (up to three, kept in your settings until you delete them there): the lists anyone can see there, read at most
  once a week (the playlists you made, the ones by others you keep, and on QQ Music the albums you keep), as each
  list's name, maker and dates, and each song's title, artists, album and release date;
- what you did in Zhiyin: plays, skips, likes, refusals, songs you asked for. Each play records how it started (you
  chose the song, or it played on), how far it got and how long it was, how long since the page was last touched,
  whether the page was in front, and what the page showed with it (the editor's confidence, its place in the
  station); from these, the songs you play often without having liked them (`signals.py`);
- if you import a YouTube Music history from Google Takeout: the file is read in the browser, and only the songs
  played at least twice reach the server, as video id, title, artist, number of plays, number of days, first and
  latest day, and a recency-weighted count of days. It is deleted from Your Ear, or with the account;
- for listeners who signed in with Google: your Google account id, email and name, and the access tokens, encrypted with
  a key kept on the server;
- how many Claude calls each listener made per day, and what they would cost on an API key;
- a 512-number sound vector per song, shared by all listeners. The portrait compares the vectors of your likes, as
  a group, with all the others. Audio itself is never stored: previews are decoded in memory and thrown away;
- for people who asked to join while the seats were full: their Google account id, email, name, language and when
  they asked, until they are let in (the row is then deleted) or removed.

Someone listening to the sample without signing in leaves no record of themselves: their plays are not recorded.
The first page they open sets a cookie, `zy_r`, holding the link that brought them (`?ref=`, `utm_source`, or the
referring site's host name) for 30 days. The server keeps one table of counts per day and per link: visits, sample
plays, joins and how they ended, sign-ins sent from an app's own browser to a real one, first records, names, finished first runs and shares (`zhiyin stats`). A new account
carries its link in its settings for at most 30 days, so the steps of its first run can be counted. No row names a
person.

Someone who makes a record from a NetEase Cloud Music or QQ Music link without signing in (`netease.py`,
`qqmusic.py`, `cards.py`) leaves little more. The public playlist (on QQ Music, the 我喜欢 of the profile linked, or a
public playlist) is read, the record goes back to their browser, and the playlist is not kept. QQ Music's album
covers, which give a record's dots their colour, pass through `/api/img` because their CDN won't let the page read
them, and aren't written to disk (`ytm.PASS_HOSTS`). The
titles and artists of its newest 600 songs go to Anthropic for a name, billed to the server's API key under the
`cards` account and capped at `ZHIYIN_CARD_DAILY_USD` a day (default $2); the name is kept for 7 days in
`card_names`, keyed by a hash of the playlist id and language, so the same list is named once a day (three times if
they ask for another). How many records an address made in the last ten minutes is counted in memory only.

Someone who goes on from such a record to weekly stations ("New songs every week, picked from these",
`/api/card/follow`) signs in with Google for who they are only (openid, email, profile; no YouTube scope). The link
waits for that in a signed cookie, `zy_n`, for at most 15 minutes. Their account then keeps the playlist's address in
its settings (`netease`, for either app), and reads the public likes (and NetEase's 听歌排行) on the same clock as
YouTube likes: every 6 hours while they listen, at least every 25 days while they are away (`library.sync_from_app`).
Each like is looked up on YouTube Music by artist and title (`library.match_app`); a match is kept as a library
record with the app's song id and like date (estimated from release dates for QQ Music, which shows nobody when), and a like with no match keeps only its title, artists and date (`unmatched`), so it is never
recommended back. Of the ranking only each song's score is kept (`ne_score`), as a sign of a favourite. Everything
downstream is the same as for a YouTube library, and the 30-day rule below applies to it too: a playlist that can't
be read for 30 days (made private, deleted) takes the library made from it, and the link, with it. With every seat
taken, the waitlist row keeps the link as well (`src`), and admitting them starts from it.

A card shared by link (`/c/<id>`) is the only thing kept: the 1080×1440 picture in `data/cards/`, and a row with the
name, the number of liked songs, the first year, the language, the account if one shared it, a hash of the key that
takes it down, and how often it was opened. It stays until the browser that made it takes it down, the account that
shared it is deleted, or the operator runs `zhiyin cards --rm <id>`.

## How long it is kept

Zhiyin follows the [Google API Services User Data Policy](https://developers.google.com/terms/api-services-user-data-policy),
including its Limited Use requirements, and YouTube's rule that data from its API is refreshed or deleted within
30 days:

- every listener's likes are read again from YouTube once 25 days have passed since the last read, also while they
  are away (a failed read is tried again every 6 hours);
- when they can't be read for 28 days (access removed in the Google account, the connection dropped, or every read
  failing), what was read from YouTube is deleted: the library, the record drawn from it before the songs were
  matched, tags, profile, stations and the taste's name. The account, its feedback and plays stay, and connecting
  again starts over. The server prints each one it deletes. When more than a quarter of the listeners can't be read
  at once (the connection breaking, not people leaving), it waits up to 2 more days for the operator to fix it,
  then deletes anyway, so nothing outlives 30 days;
- the dislikes, subscriptions and own-playlist songs are re-read with the likes, at most once a day, and deleted
  with them; if they can't be re-read for 28 days they are deleted on their own;
- the first quick list of liked videos, used to draw the record before the library exists, is deleted as soon as
  the library is written;
- facts about a video from YouTube's API (category, length, channel), shared by all listeners, are fetched again
  when needed after 30 days, and deleted if nobody needed them in that time;
- the same limits apply to the operator's accounts connected through Google; a local library imported without
  Google OAuth remains operator-managed. Rollout grace and outage holds cannot extend the 30-day limit;
- when a Google library expires, its shared cards and personalized picks from Ask are removed too. The user's
  original request text, its date and language are kept;
- deleting an account deletes everything about it at once.

The owner of the server can read all of it. The join sheet and the welcome page link to the privacy page, which
says so.

## What leaves the machine

| Sent to | What | Why |
|---|---|---|
| YouTube Music (unauthenticated) | song and artist ids | radio, related songs, artist pages, playlists, cover art |
| YouTube Data API, with your Google token | your likes, thumbs-down music, subscriptions and own playlists; song IDs and ratings when syncing likes; a title, description and song IDs when saving a station | read likes and the other signals, synchronize ratings, create a private playlist at your request |
| Anthropic (Claude), under the account that runs your calls ([whose Claude](self-hosting.md#whose-claude)) | song titles and artists from your likes (with the month you liked them), from the songs you play often or keep in your own playlists without a like, the names, makers, dates and most frequent artists of the lists you keep in NetEase or QQ Music with the artists and a few titles of your own lists there, and the candidates, station descriptions, songs you refused and why (including up to eight thumbs-down titles from YouTube), for the portrait how the songs it picked fared when they played (loved, turned down, skipped in the first seconds, heard through) and which words for a sound your likes lean towards or away from, whether a candidate's artist is a channel you subscribe to, what you typed into "ask", the description set with `zhiyin about`, lyrics that need translating, the lyrics of a song the first time it plays (to mark its chorus and the line it turns on), and, when you switch between English and Chinese, the portrait, stations and reasons it wrote earlier | tags, stations, picks, a short name for your taste, lyric translations, song parts and translations of its own text |
| Deezer, Apple iTunes Search | song title and artist | find a 30-second preview to listen to |
| NetEase Cloud Music, LRCLIB, YouTube Music | song title, artist, length | lyrics |
| NetEase Cloud Music | the playlist or profile id someone pasted to make a record without signing in, or to start stations from; the ids of the artists in it | read that public playlist and 听歌排行, and for a listener whose stations start from a profile or who added one on Your Ear, the other public playlists there once a week; other names of an artist (Eason Chan for 陈奕迅) to find its songs on YouTube Music |
| QQ Music | the encrypted profile id or playlist id someone pasted, for the same; the ids of the singers in it; the album ids of its covers | read that public 我喜欢 or playlist, and for a listener whose stations start from a profile or who added one on Your Ear, the other public lists and albums kept there once a week; other names of a singer; the covers, passed through to the page for its colours |
| YouTube Music (unauthenticated) | the artist and title of each NetEase or QQ Music like | find the same song to play |
| The YouTube embedded player, in your browser | the video being played | playback, under YouTube's own terms |

Your Google token is only used for your own account. It is never sent anywhere but Google.

The operator's hosting provider processes stored service data; a fronting CDN, if configured, sees network requests
and IP addresses. Set `ZHIYIN_CDN` to its real name so `/privacy` identifies it. Deliberately shared cards disclose
the picture and taste summary to anyone with the link. Other disclosure is limited to consented user-facing
features, necessary security investigations and applicable legal requirements; data is not transferred for other
purposes. Third-party services apply their own privacy and retention terms to the data they receive; deleting
Zhiyin's account cannot retract a card someone has copied or a playlist kept in the listener's YouTube account.

When the server has no Claude login of its own, the owner's calls (and only the owner's) are run by the owner's
Mac worker, so those prompts pass through that Mac on their way to Anthropic. Lyric translations and song parts are kept
per song and used for every listener who plays it, whoever's Claude made them.

## Removing someone

On a server, `accounts.delete` removes the listener's folder, rows and shared cards:

```sh
docker exec zhiyin python -c "from zhiyin import accounts; accounts.delete('<id>')"
docker exec zhiyin python -c "from zhiyin import store; con = store.db(); con.execute('delete from waitlist where email=?', ('<email>',)); con.commit()"
```

They can also revoke Zhiyin's access at [myaccount.google.com/permissions](https://myaccount.google.com/permissions).
