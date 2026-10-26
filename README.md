<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="docs/brand/wordmark-en-on-dark.svg">
    <img alt="Zhiyin" src="docs/brand/wordmark-en-on-light.svg" height="64">
  </picture>
</p>

<p align="center">
  A private radio built from the songs you liked on YouTube Music.<br>
  Every morning it brings a few stations of songs you haven't heard, and says why it picked each one.
</p>

<p align="center">
  <a href="https://zhiyin.billpwchan.art/?ref=github"><b>Try it in your browser</b></a> · sign in with Google, or first listen to a sample listener's stations
</p>

<p align="center">
  <b>English</b> · <a href="README.zh-CN.md">简体中文</a> · <a href="README.zh-TW.md">繁體中文</a>
</p>

<p align="center">
  <a href="https://github.com/billpwchan/zhiyin/actions/workflows/ci.yml"><img alt="CI" src="https://github.com/billpwchan/zhiyin/actions/workflows/ci.yml/badge.svg"></a>
  <a href="LICENSE"><img alt="MIT license" src="https://img.shields.io/badge/license-MIT-lightgrey"></a>
</p>

<p align="center">
  <img alt="The player: stations on the left, the song with its cover and the reason it was picked, and synced lyrics with a translation on the right, a tab away from the rest of the station" src="docs/images/player.webp" width="900">
</p>

Most recommenders work from what millions of other people played next to your song. You get the same few hits,
and "because you listened to X" is all the reasoning you see.

Zhiyin starts from the few hundred songs you chose to like. For each kind of music you listen to, it gathers about
600 candidates from YouTube Music's listening graph, drops everything you already know, and hands a shortlist to
Claude, which reads it like an editor who has been through your whole library. Only the picks it rates 0.7 or higher
go out, so when it isn't sure, a station simply gets fewer songs (its best three if none clear the bar).

## What you get

### A morning edition

About eight stations, one per kind of music you actually play, up to eight songs each, with
one line on why each song is there. Full songs play through YouTube's own player, fading out into the next, with synced lyrics
that can show a translation and romanization.

### Ask in your own words

"A rainy Sunday afternoon", "Japanese city pop to cook to". About a minute later there is
a station for it.

### It listens back

A skip pushes similar-sounding songs down the queue and a like pulls them up, while you listen.
"Quieter", "more energy" and "more new artists" re-rank the station by sound.

### Your ear

A page that draws your whole library as a disc, one ring per year and one sector per kind of music,
and can replay how your taste grew. Claude gives your taste a short name and writes the portrait next to it.
The first time you sign in, the disc is drawn within seconds, while your stations are still being made, and one
tap turns it into a card to share: the name, the disc, and the year by which half your songs had come out.

<p align="center">
  <img alt="Your ear: every liked song is a mark on a disc, by year and by station, next to a written portrait of the listener's taste" src="docs/images/ear.webp" width="900">
</p>

<p align="center">
  <img alt="The player on a phone" src="docs/images/mobile-player.webp" height="520">
  &nbsp;&nbsp;
  <img alt="Your ear on a phone, with the player docked above the tabs" src="docs/images/mobile-ear.webp" height="520">
</p>

<p align="center"><sub>The screenshots show a made-up listener built from public playlists.</sub></p>

The app speaks English, Simplified Chinese and Traditional Chinese, and the editor writes in the one you choose.
Song titles, artists and lyrics stay in their own language and script.

## How it picks

<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="docs/images/pipeline-dark.svg">
    <img alt="Likes become stations; each station gathers candidates, a shortlist is scored, and an editor keeps the picks it is sure of. Skips and likes re-rank the queue while you listen and shape the next edition." src="docs/images/pipeline-light.svg" width="860">
  </picture>
</p>

1. Claude sorts your likes into stations, each with its scene, languages, seed songs and core artists.
2. YouTube Music's radio, related artists, and public playlists that already hold your songs supply the candidates.
3. A graph score keeps the 64 that most of your seeds point to.
4. An audio model, [MuQ-MuLan](https://huggingface.co/OpenMuQ/MuQ-MuLan-large), vetoes sounds you've turned down.
5. Claude keeps the few it is confident about and writes why.

Sound vetoes and steers but never ranks. On held-out likes, audio similarity scored an AUC of 0.55–0.61, barely
better than a coin flip. [How it works](docs/how-it-works.md) has every step and the mistakes behind these choices.

|  | A streaming app's radio | Zhiyin |
|---|---|---|
| Starts from | what other listeners play next to your song | the songs you liked, recent ones weighted most |
| Why this song | "because you listened to X" | a line about the song, next to the like of yours it is closest to, which you can play to compare |
| When it has nothing good | keeps the queue full | plays fewer songs |
| Songs you already know | come back often | filtered out, along with their live, remix and cover versions; a song you've heard never comes back |

## Run it

You need Python 3.13, [uv](https://docs.astral.sh/uv/), a YouTube Music account with some liked songs, and
[Claude Code](https://docs.claude.com/en/docs/claude-code). Zhiyin calls Claude through the `claude` command: set
`ANTHROPIC_API_KEY` (a normal day costs $1–2), or sign the CLI in to your own Claude plan.

```sh
git clone https://github.com/billpwchan/zhiyin && cd zhiyin && uv sync
uv run zhiyin auth     # connect YouTube Music; it walks you through it
uv run zhiyin setup    # read your likes, find your stations, pick the first edition (about an hour)
uv run zhiyin serve    # open http://localhost:8817
```

`uv run zhiyin service install` keeps it running from login and builds a new edition every morning at 05:00.

To run it on a server for yourself and a few friends, each signing in with their own Google account, see
[running it on a server](docs/self-hosting.md). Every account is separate, with its own likes, stations and history.

<details>
<summary>Keyboard</summary>

| Key | |
|---|---|
| <kbd>Space</kbd> | play / pause |
| <kbd>N</kbd> <kbd>P</kbd> | next, previous |
| <kbd>←</kbd> <kbd>→</kbd> | back or forward 10 seconds |
| <kbd>L</kbd> <kbd>X</kbd> | like, not for me |
| <kbd>1</kbd>–<kbd>9</kbd> | switch station |
| <kbd>/</kbd> | ask |
| <kbd>G</kbd> | lyrics; <kbd>T</kbd> translation, <kbd>R</kbd> romanization, <kbd>[</kbd> <kbd>]</kbd> nudge timing |
| <kbd>F</kbd> | immersive view, cover and lyrics only |
| <kbd>M</kbd> | mini player |

</details>

## Privacy

Your likes, plays and stations stay on the machine you run it on. Song titles and artist names go to Claude to
build stations and pick songs, and nothing reaches the author of this project. [Privacy](docs/privacy.md) lists
every outside service and what it receives.

## Why "Zhiyin"

知音 (*zhīyīn*) comes from an old story. The musician Bo Ya played of high mountains and flowing water, and only his
friend Zhong Ziqi heard what he meant. When Zhong Ziqi died, Bo Ya broke his strings and never played again. Since
then the word has meant the friend who truly understands. The mark is that mountain-and-water line, curling into an
ear.

I built it because the recommendations I got judged mechanically: one song played, more of the same returned. I
wanted something that had read all my likes and picked the way a friend would.

## Credits

- [ytmusicapi](https://github.com/sigma67/ytmusicapi) for YouTube Music.
- [MuQ-MuLan](https://huggingface.co/OpenMuQ/MuQ-MuLan-large) for sound. Its weights are licensed CC BY-NC 4.0, so
  the audio features are for non-commercial use.
- Previews from Deezer and Apple's iTunes Search; lyrics from NetEase Cloud Music, [LRCLIB](https://lrclib.net) and
  YouTube Music.
- The wordmarks are set in Inter and Noto Sans CJK (SIL Open Font License).
- The [design notes](docs/design.md) (in Chinese) record the interface rules and where they came from.

Zhiyin is not affiliated with YouTube, Google or Anthropic.

## License

[MIT](LICENSE)
