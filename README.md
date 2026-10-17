# ACE Mixer

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
