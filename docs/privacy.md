# Privacy

Zhiyin is meant to run on a machine you control, for you, the people you invite and, if you open seats, people
who join on their own. Nothing is sent to the author
of this project, and there is no analytics.

## What is stored

On the machine running Zhiyin:

- your liked songs and when they were liked (if Google says so), the profile built from them, and each edition;
- what you did in Zhiyin: plays, skips, likes, refusals, songs you asked for;
- for listeners who signed in with Google: your Google account id, email and name, and the access tokens, encrypted with
  a key kept on the server;
- how many Claude calls each listener made per day, and what they would cost on an API key;
- a 512-number sound vector per song, shared by all listeners. Audio itself is never stored: previews are decoded
  in memory and thrown away;
- for people who asked to join while the seats were full: their Google account id, email, name, language and when
  they asked, until they are let in (the row is then deleted) or removed.

Someone listening to the sample without signing in leaves nothing behind: their plays are not recorded.

The owner of the server can read all of it. The join sheet and the welcome page link to the privacy page, which
says so.

## What leaves the machine

| Sent to | What | Why |
|---|---|---|
| YouTube Music (unauthenticated) | song and artist ids | radio, related songs, artist pages, playlists, cover art |
| YouTube Data API, with your Google token | your likes; the songs you like in Zhiyin, once you turn on writing likes back | read likes, like songs back |
| Anthropic (Claude), under the account that runs your calls ([whose Claude](self-hosting.md#whose-claude)) | song titles and artists from your likes (with the month you liked them) and the candidates, station descriptions, songs you refused and why, what you typed into "ask", the description set with `zhiyin about`, lyrics that need translating, and, when you switch between English and Chinese, the portrait and reasons it wrote earlier | tags, stations, picks, a short name for your taste, lyric translations and rewritten text |
| Deezer, Apple iTunes Search | song title and artist | find a 30-second preview to listen to |
| NetEase Cloud Music, LRCLIB, YouTube Music | song title, artist, length | lyrics |
| The YouTube embedded player, in your browser | the video being played | playback, under YouTube's own terms |

Your Google token is only used for your own account. It is never sent anywhere but Google.

When the server has no Claude login of its own, the owner's calls (and only the owner's) are run by the owner's
Mac worker, so those prompts pass through that Mac on their way to Anthropic. Lyric translations are kept per song
and shown to every listener who plays it, whoever's Claude made them.

## Removing someone

On a server, delete `data/users/<id>/` and the listener's rows:

```sh
docker exec zhiyin python -c "
from zhiyin import store
con = store.db()
for t in ('feedback', 'shown', 'plays', 'sessions', 'invites', 'outbox', 'usage'): con.execute(f'delete from {t} where uid=?', ('<id>',))
con.execute('delete from users where id=?', ('<id>',)); con.commit()"
docker exec zhiyin python -c "from zhiyin import store; con = store.db(); con.execute('delete from waitlist where email=?', ('<email>',)); con.commit()"
```

They can also revoke Zhiyin's access at [myaccount.google.com/permissions](https://myaccount.google.com/permissions).
