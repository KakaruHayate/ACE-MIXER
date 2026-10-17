# ACE Mixer

## Start here

Copy the block below to an agent that can run local commands. If it finishes,
the machine is ready and the agent only needs a folder and a ratio from you.

```text
Set up ACE Mixer and get it ready, then stop.

1. Download the prebuilt binary from
   https://github.com/KakaruHayate/ACE-MIXER/releases/latest
   (ace-mixer.exe). If github.com is slow, the repo mirror is
   https://gitclone.com/github.com/KakaruHayate/ACE-MIXER — a 502 there
   usually means it is still caching; retry after a minute.

2. If you prefer building from source:
     git clone https://github.com/KakaruHayate/ACE-MIXER
     # mirror: git clone https://gitclone.com/github.com/KakaruHayate/ACE-MIXER.git
     cd ACE-MIXER
     uv venv && uv pip install -e .
     uv run ace-mixer doctor

3. You need, on this machine:
   - ACE Studio running, with a Verse 2.7 track that already holds notes
   - a CLI build of LibreSVIP (the GUI build has no CLI); set LIBRESVIP_CLI
     to its path if it is not in a default location
   - Python 3.10+ with uv, only if you build from source

4. Run:  ace-mixer doctor      (or: uv run ace-mixer doctor)
   It prints one line per dependency. Do not continue if any line says FAIL:
   report that line instead. When all three say OK, reply exactly
   "ACE Mixer is ready" and wait for me to give you a folder and a ratio.
```

## What it does

Move another singing synthesizer's **singing style** onto an **ACE Studio
Verse 2.7** track.

You give it a folder with two files:

- a project any [LibreSVIP](https://github.com/SoulMelody/LibreSVIP) build can
  read (`.ustx`, `.svp`, `.ds`, `.vsqx`, `.ccs`, `.ppsf`, …)
- the **dry render** of that same project

It reads the project for *what is sung* (notes, lyrics, absolute pitch), reads
the render for *how it is sung* (air / tension / falsetto / energy), and writes
those curves into the target clip — optionally blended with what the ACE voice
would have done on its own.

```text
project  ──► .ufdata ──► notes + absolute pitch curve
dry render ─► four ACE parameter curves
                    └─► mix at ratio w ──► clip's `user` layer
```

## Why curves and not voice blending

Verse 2.7 is a `timbreOnly` model: `blend add --style` is an error there, so
voice blending can mix timbre but never style. The four parameter curves are
the only channel that carries *how* a phrase is sung.

## Requirements

| | |
|---|---|
| ACE Studio | running, with `acestudio-cli` (ships with the app) |
| A Verse 2.7 track | with a non-empty sing clip |
| `libresvip-cli` | a CLI build of LibreSVIP (the GUI build has none) |
| Python 3.10+ | only if you run from source; the exe needs nothing |

## Install

Hand [`INSTALL_PROMPT.md`](INSTALL_PROMPT.md) to an agent, or install by hand:

```bash
git clone https://github.com/KakaruHayate/ACE-MIXER
cd ACE-MIXER
uv venv && uv pip install -e .
uv run ace-mixer doctor
```

Mainland China mirror: `git clone
https://gitclone.com/github.com/KakaruHayate/ACE-MIXER.git`. The mirror caches
on first request, so an initial 502 just means "retry in a minute".

Prebuilt: grab `ace-mixer.exe` from
[Releases](https://github.com/KakaruHayate/ACE-MIXER/releases/latest) — no
Python needed.

## Use

```bash
ace-mixer run --dir "D:/sessions/song" --ratio 0.5
```

- `--ratio 0` keeps the ACE voice's own expression, `1` keeps only the source's
  shape, `0.5` is the usual starting point.
- `--mode match` (default) matches the source's mean and spread to the ACE
  baseline first, so only the *shape* transfers. `--mode direct` carries the
  source's overall tendency as well.
- `--import-notes` also replaces the clip's notes with the project's.
- `--dry-run` reports everything without writing.

Check the tool chain first:

```bash
ace-mixer doctor
```

## What it writes

Only the four parameters' `user` layer on the target clip:

```text
effective = user (where user has a value) else baseline
```

It never touches the voice library or any blend recipe.

## Limits

- **Verse 2.7 only.** Other ACE model generations expose different layers and
  parameter ranges.
- The source must be a **dry** render: reverb, compression or EQ change the
  measured air and spectral slope.
- Curves exist only where the render is voiced; silence stays silent.
- Pitch is import-only. Once the `.ufdata` is in, no ACE CLI surface reads or
  writes the pitch curve.

## Licence

MIT.
