# Changelog

## Unreleased

- Switching between Chinese and English turns the whole page over at once. What Claude wrote (the portrait, station
  names and descriptions, reasons, asks and the name for your taste) is put into the new language first, and the page
  waits for it instead of mixing the two. What Claude wrote is kept as written, so switching
  back is instant and costs nothing, and text finished after a switch is filled in on the next visit.
- Immersive follows the song. The light is low through the intro, steady in the verses and opens up in each chorus,
  where the line being sung is a size larger. The line the song turns on, chosen once per song by Claude, is held
  alone while it is sung, its letters arriving one after another. The progress bar marks the choruses, and a click
  near one starts it from the top. Entering immersive brings the light up from dark, and a new song's colour spreads
  out from its cover.
- Likes from a NetEase or QQ Music profile bring the rest of the page with them: the playlists you made, the ones by
  others you keep and, on QQ Music, the albums you keep, read once a week. The stations and the portrait read them,
  and their songs are never recommended back to you. Your Ear takes up to three more profile links, such as an older
  account or the app you used before, read the same way.
- A listener whose YouTube likes are too few to start from can switch to their QQ Music or NetEase likes.
- In immersive, switching between the cover and the words no longer leaves YouTube's window where the cover was.
- The ✕ on a song row sits in the middle of its button again.
- Top picks, the first station: the surest songs from every station, taking turns, and where a visit starts.
- A song heard in one station no longer comes round again in another during the same edition.
- On a phone, YouTube's window stays on the player card while the page scrolls and the toolbar folds away, and the cover no longer grows mid-scroll.
- The line under Up next no longer runs into the first song on laptop-sized windows, and lines up on a phone.
- Coming back to the page after the phone paused the song, one tap carries on.
- Songs you play often without liking them now count as your taste: they seed their station, shape your sound and
  are listed on Your Ear, where ♥ keeps one and "Not me" drops it. A Google Takeout export of your YouTube Music
  history can be imported to fill the list at once; the file is read in the browser.
- Your thumbs-down music on YouTube is never recommended, songs in your own playlists count as known, and artists
  you subscribe to are no longer treated as new.
- A song skipped with Next in the first seconds, on its own, counts against its sound; a run of quick skips no longer
  does, and leaving a song early for another station, a song from the list or a closed page says nothing about it.
- Every listen is logged from start to end, however it ends, so "How the picks fare" on Your Ear (and
  `zhiyin quality`) can say how many recommendations were heard through, by station, by the editor's confidence and
  for new artists. One probe song per station measures whether the editor's judgement is worth what it costs.

## 0.1.0 — 2026-10-25

First public release.

- A daily edition: your likes split into stations, each with a handful of picks and one line on why.
- Picks are judged on fit and on the recording itself. Fewer go out when the editor isn't sure.
- Ask for music in your own words.
- Player with synced lyrics (word by word where available, translations, romanization), crossfades, media keys,
  a mini window and an immersive view.
- "Your ear": every like on one record, by year and by station, with a written portrait of your taste.
- Invite a friend or two; each connects their own YouTube Music through Google, and likes sync back.
- Runs on a Mac, or on a small server with the audio model on a Mac worker.
