# Privacy

Zhiyin is meant to run for you and a few people you know, on a machine you control. Nothing is sent to the author
of this project, and there is no analytics.

## What is stored

On the machine running Zhiyin:

- your liked songs and when they were liked (if Google says so), the profile built from them, and each edition;
- what you did in Zhiyin: plays, skips, likes, refusals, songs you asked for;
- for listeners who signed in with Google: your Google account id and email, and the access tokens, encrypted with
  a key kept on the server;
- a 512-number sound vector per song, shared by all listeners. Audio itself is never stored: previews are decoded
  in memory and thrown away.

The owner of the server can read all of it. Invite only people who are fine with that.

## What leaves the machine

| Sent to | What | Why |
|---|---|---|
| YouTube Music (unauthenticated) | song and artist ids | radio, related songs, artist pages, playlists, cover art |
| YouTube Data API, with your Google token | your likes; the songs you like in Zhiyin | read likes, like songs back |
| Anthropic (Claude) | song titles and artists from your likes (with the month you liked them) and the candidates, station descriptions, songs you refused and why, what you typed into "ask", the description set with `zhiyin about`, and lyrics that need translating | tags, stations, picks and lyric translations |
| Deezer, Apple iTunes Search | song title and artist | find a 30-second preview to listen to |
| NetEase Cloud Music, LRCLIB, YouTube Music | song title, artist, length | lyrics |
| The YouTube embedded player, in your browser | the video being played | playback, under YouTube's own terms |

Your Google token is only used for your own account. It is never sent anywhere but Google.

## Removing someone

On a server, delete `data/users/<id>/` and the listener's rows:

```sh
docker exec zhiyin python -c "
from zhiyin import store
con = store.db()
for t in ('feedback', 'shown', 'plays', 'sessions', 'invites', 'outbox'): con.execute(f'delete from {t} where uid=?', ('<id>',))
con.execute('delete from users where id=?', ('<id>',)); con.commit()"
```

They can also revoke Zhiyin's access at [myaccount.google.com/permissions](https://myaccount.google.com/permissions).
