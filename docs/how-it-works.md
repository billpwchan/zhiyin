# How Zhiyin picks songs

The short version: YouTube Music's listening graph finds songs, Claude chooses among them like an editor who knows
your library, an audio model keeps out sounds you've turned down, and what you do while listening corrects the
queue as it plays.

The goal is narrow on purpose. A pick is good when you'd like it **on the first listen**. "Sounds similar to your
likes" and "is new to you" both matter less than that.

<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="images/pipeline-dark.svg">
    <img alt="Likes become stations; each station gathers candidates from the YouTube Music graph, filters what you already know, ranks by how many of your songs point at each one, and an editor keeps the few it is sure of." src="images/pipeline-light.svg" width="860">
  </picture>
</p>

## 1. Your likes become stations

Zhiyin reads your liked songs, newest first, so recent taste counts more: a like's weight halves about every
seven months. Claude tags each
song with its language, energy and the moments it suits. Then it groups the library into about eight **stations**,
the kinds of music you actually listen to. For one listener that might be Cantonese R&B, Japanese city-pop groove,
vocal jazz and K-pop girl groups.

A station is more than a mood. It has a scene, languages and lineage, plus seed songs, core artists, artists worth
exploring, an energy range, things to avoid, and a share of new artists. A soft Mandopop ballad doesn't belong in a
jazz station just because it's quiet.

## 2. Candidates come from the listening graph

For each station, Zhiyin collects about 600 candidates:

- the YouTube Music radio and related songs of each seed;
- similar artists, and the artists the editor suggested exploring;
- releases from the station's core artists in the last two years;
- public playlists that already hold at least two of your likes, or many artists you know. These act as a second
  opinion from someone with overlapping taste. A song found *only* in playlists is dropped, because on its own it brings in popular songs from
  outside the station's scene.

## 3. What you already know is filtered out

- songs you've liked, refused, or played or skipped in the last 90 days;
- songs from the last two editions, so "another edition" really brings new songs;
- the same song in another form: live, remix, cover, sped-up or lyric uploads, a music video when you liked the
  audio, and uploads that put the artist in the title ("J Tajor & sunkis - Like I Do");
- artists you've blocked, the wrong language for the station, and long mixes.

Songs that were shown earlier but never played are not used up. They can come back later, behind fresher
candidates of the same strength.

## 4. A graph score narrows it to a shortlist

Each candidate scores higher the more of your seeds lead to it, the closer it sits to your core artists, and if it
is a recent release. A huge hit by an artist you already follow scores lower, since you've probably heard it. The
top 64 go on to the next step.

## 5. Sound vetoes, it doesn't choose

A 30-second preview of each candidate goes through [MuQ-MuLan](https://huggingface.co/OpenMuQ/MuQ-MuLan-large),
which puts audio and text in one 512-dimension space. The preview is decoded in memory and thrown away; only the
vector is kept. The vector is used to:

- **veto** near-copies of sounds you refused or skipped;
- **steer while you listen**: a skip pushes similar-sounding songs down the queue, a like pulls them up, and the
  "quieter", "more energy" and "more new artists" switches re-rank by sound;
- **match words to sound** when you ask for "rainy Sunday afternoon".

It is deliberately *not* used to rank. On held-out likes it barely predicts what you'll like: AUC 0.55–0.61, where
0.5 is a coin flip. Every candidate was already found through your taste, so they all sound like you. Letting
sound choose pulled soft ballads into the jazz station.

## 6. An editor keeps the few it is sure of

Claude (Opus) sees the station, the songs that define it right now, what you recently refused, and a shortlist of 32
with mixed new and familiar artists and, where the pool allows, at most two songs per artist. It returns up to 12 songs with a confidence
score and one line each. The instructions put quality and texture first: real songwriting, a voice and production
worth hearing, the original studio recording. Classics are welcome when they fit and you don't have them yet.
Being obscure is never a reason on its own.

Only songs the editor rates 0.7 or higher go out, up to 8 per station. A station with fewer good picks shows fewer;
if none reach 0.7, its best three go out so the station isn't empty.
The rest become the station's reserve, which plays when the queue runs out.

Listeners on the server's API key get Sonnet as their editor. On the same eight shortlists, Sonnet kept 75% of the
songs Opus kept and its reasons read as well, for a third of the price ($0.13 an edition against $0.39). Haiku cost
$0.02 but kept only half of them and mixed Chinese into English reasons, so it isn't used for picking.

## 7. Last touches

- A music video is swapped for the same recording's audio track when YouTube Music has one: no skits or long intros,
  and the cover art shows instead.
- A song appears once per edition, even when it surfaced in two stations or as both a video and a track.
- Chinese titles, artists and lyrics follow the song's own script (Traditional or Simplified, Hong Kong or Taiwan
  forms).

## Checking it

`zhiyin eval` hides your newest likes, rebuilds candidates from the older ones and counts how many hidden likes the
engine would have surfaced. `zhiyin eval --audio` measures whether sound alone separates them from the engine's own
candidates. Run both before and after changing the engine, and compare a new edition side by side with one you
trusted.

What we learned the hard way:

- **Burning the best songs.** An early version excluded everything shown in the last 28 days. Every rebuild burned
  the best candidates, and later editions were picked from leftovers.
- **Assuming the listener knows the classics.** Telling the editor to assume the listener already knew the classics
  removed songs they went on to like.
- **Tuning weights didn't help.** Seven variants of the graph score made no difference to recall.
