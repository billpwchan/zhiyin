<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="docs/brand/wordmark-on-dark.svg">
    <img alt="知音 Zhiyin" src="docs/brand/wordmark-on-light.svg" height="72">
  </picture>
</p>

<p align="center">
  A music player that reads your YouTube Music likes and, every morning, brings a short edition of songs
  you're likely to love on the first listen.
</p>

<p align="center">
  <a href="https://github.com/billpwchan/zhiyin/actions/workflows/ci.yml"><img alt="CI" src="https://github.com/billpwchan/zhiyin/actions/workflows/ci.yml/badge.svg"></a>
  <a href="LICENSE"><img alt="MIT license" src="https://img.shields.io/badge/license-MIT-lightgrey"></a>
  <img alt="Python 3.13" src="https://img.shields.io/badge/python-3.13-lightgrey">
  <a href="README.zh-CN.md">中文</a>
</p>

<p align="center">
  <img alt="The player: a station list on the left, the current song with its cover, why it was picked, and the queue" src="docs/images/player.webp" width="900">
</p>

知音 (*zhīyīn*) is the friend who truly knows your music. Streaming apps recommend from what millions of people
play; Zhiyin starts from the few hundred songs you chose to like, and keeps only the picks it is sure of.

## What it does

- **A daily edition.** About eight stations, one for each kind of music you actually listen to, with up to eight
  songs each and one line on why. When the editor isn't sure, a station gets fewer songs, not filler.
- **A real player.** Full songs through YouTube's embedded player, crossfades, synced lyrics with translation and
  romanization, a floating mini player (Chrome), media keys and keyboard control.
- **Ask in your own words.** "A rainy Sunday afternoon", "Japanese city pop to cook to".
- **It listens back.** A skip pushes similar-sounding songs down the queue and a like pulls them up. On a server
  setup, your likes are written back to YouTube Music.
- **Your ear.** A page that draws your whole library, when you liked each song and which station it belongs to,
  with a written portrait of your taste.

<p align="center">
  <img alt="Your ear: every liked song as a mark on a disc, by year and station" src="docs/images/ear.webp" width="900">
</p>

<p align="center">
  <img alt="The player on a phone" src="docs/images/mobile-player.webp" height="560">
  &nbsp;&nbsp;
  <img alt="Your ear on a phone, with the player docked below" src="docs/images/mobile-ear.webp" height="560">
</p>

The interface is in Chinese. Song titles, artists and lyrics stay in their own language and script.

## How it picks

YouTube Music's listening graph finds about 600 candidates per station. Songs you know are filtered out, a graph
score narrows them to 64, and an audio model vetoes sounds you've turned down. Then Claude, acting as an editor who
knows your library, keeps the few it is confident about.

<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="docs/images/pipeline-dark.svg">
    <img alt="Likes become stations; each station gathers candidates, a shortlist is scored, and an editor keeps the picks it is sure of. Skips and likes re-rank the queue while you listen and shape the next edition." src="docs/images/pipeline-light.svg" width="860">
  </picture>
</p>

Sound is used to veto and to steer, never to rank: on held-out likes, audio similarity barely beats a coin flip.
[How it works](docs/how-it-works.md) explains each step and what was learned the hard way.

## Run it on your Mac

You need Python 3.13, [uv](https://docs.astral.sh/uv/), a YouTube Music account with some liked songs, and
[Claude Code](https://docs.claude.com/en/docs/claude-code) signed in (a Claude subscription or an API key).

```sh
git clone https://github.com/billpwchan/zhiyin && cd zhiyin
uv sync
uv run zhiyin auth       # save YouTube Music request headers (it walks you through it)
uv run zhiyin sync       # read your liked songs
uv run zhiyin profile    # stations and the portrait, a few minutes
uv run zhiyin listen     # hear a preview of every like, about an hour, once
uv run zhiyin refresh    # the first edition
uv run zhiyin serve      # open http://localhost:8817
```

`uv run zhiyin service install` keeps it running from login, with a new edition every morning at 05:00.

To share it with a few friends, each signing in with their own Google account, see
[running it on a server](docs/self-hosting.md). Your Claude subscription covers only your own listening, since
Anthropic doesn't let an app route other people's requests through it; friends run on an API key you add
([whose Claude](docs/self-hosting.md#whose-claude)).

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

Everything is stored on the machine you run it on. Song titles and artists go to Claude to build stations and pick
songs; nothing goes to the author of this project. [Privacy](docs/privacy.md) lists every outside service and what
it receives.

## Credits

- [ytmusicapi](https://github.com/sigma67/ytmusicapi) for YouTube Music.
- [MuQ-MuLan](https://huggingface.co/OpenMuQ/MuQ-MuLan-large) for sound. Its weights are licensed CC BY-NC 4.0,
  so the audio features are for non-commercial use.
- Previews from Deezer and Apple's iTunes Search; lyrics from NetEase Cloud Music, [LRCLIB](https://lrclib.net)
  and YouTube Music.
- The mark is drawn from Noto Sans CJK (SIL Open Font License).
- The [design notes](docs/design.md) (in Chinese) record the interface rules and where they came from.

Zhiyin is not affiliated with YouTube, Google or Anthropic.

## License

[MIT](LICENSE)
