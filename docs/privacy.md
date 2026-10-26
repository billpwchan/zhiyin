# Privacy

Zhiyin is meant to run on a machine you control, for you, the people you invite and, if you open seats, people
who join on their own. Nothing is sent to the author of this project. The only analytics are daily counts kept on
the server itself (below).

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

Someone listening to the sample without signing in leaves no record of themselves: their plays are not recorded.
The first page they open sets a cookie, `zy_r`, holding the link that brought them (`?ref=`, `utm_source`, or the
referring site's host name) for 30 days. The server keeps one table of counts per day and per link: visits, sample
plays, joins and how they ended, first records, names, finished first runs and shares (`zhiyin stats`). A new account
carries its link in its settings for at most 30 days, so the steps of its first run can be counted. No row names a
person.

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
- the first quick list of liked videos, used to draw the record before the library exists, is deleted as soon as
  the library is written;
- facts about a video from YouTube's API (category, length, channel), shared by all listeners, are fetched again
  when needed after 30 days, and deleted if nobody needed them in that time;
- deleting an account deletes everything about it at once.

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
