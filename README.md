# ACE Mixer

## Start here

Copy the block below to an agent that can run local commands. If it finishes,
the machine is ready and the agent only needs a folder and a ratio from you.

```text
Set up ACE Mixer and get it ready, then stop.

1. Detect the platform (`uname -m` on macOS). ACE Studio only runs on Windows
   and macOS; on Linux, stop and tell me ACE Mixer cannot run there.
     Windows          -> ace-mixer.exe
     macOS arm64      -> ace-mixer-macos
     macOS Intel      -> no prebuilt; build from source (step 5)

2. Download the ACE Mixer binary:
     Windows:
       curl -L -o ace-mixer.exe https://github.com/KakaruHayate/ACE-MIXER/releases/latest/download/ace-mixer.exe
     macOS:
       curl -L -o ace-mixer-macos https://github.com/KakaruHayate/ACE-MIXER/releases/latest/download/ace-mixer-macos
       chmod +x ace-mixer-macos
   curl does not set the macOS quarantine flag. If you downloaded with a
   browser instead and macOS refuses to run it:
       xattr -d com.apple.quarantine ./ace-mixer-macos

3. Install the skill, otherwise you have the tool but not the know-how:
     curl -L -o ace-mixer-skill.zip https://github.com/KakaruHayate/ACE-MIXER/releases/latest/download/ace-mixer-skill.zip
   Unzip it and put the folder ace-v27-style-transfer into your skills
   directory, keeping the folder name:
     Codex:        $CODEX_HOME/skills        (default ~/.codex/skills)
     Claude Code:  ~/.claude/skills
   Confirm <skills>/ace-v27-style-transfer/SKILL.md exists. If your harness
   has no skills directory, keep the folder and read SKILL.md before running
   anything.

4. Download the LibreSVIP CLI build for this platform from
   https://github.com/SoulMelody/LibreSVIP/releases/latest
   Pick the asset named LibreSVIP-CLI-<version>.<platform>.zip / .tar.gz
   (win-amd64, macos-arm64, macos-x86_64), extract it, and remember the full
   path of libresvip-cli.exe (Windows) or libresvip-cli (macOS).

5. Run:
     Windows:  .\ace-mixer.exe doctor --libresvip "<path>\libresvip-cli.exe"
     macOS:    ./ace-mixer-macos doctor --libresvip "<path>/libresvip-cli"
   It prints one line per dependency: acestudio-cli, libresvip-cli, and a
   Verse 2.7 track. Do not continue if any line says FAIL — report that line
   and stop. When all three say OK, reply exactly "ACE Mixer is ready" and
   wait for me to give you a folder and a ratio.
```

If a download from github.com is slow, `https://gitclone.com` mirrors git
clones (`git clone https://gitclone.com/github.com/KakaruHayate/ACE-MIXER.git`)
but not release assets; a first 502 there just means it is still caching.

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
project    ──► .ufdata ──► notes + absolute pitch curve
dry render ──► four ACE parameter curves
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
| | no Python needed when you use a release binary |

## Install

Hand [`INSTALL_PROMPT.md`](INSTALL_PROMPT.md) to an agent, or install by hand:

- **Windows**: download `ace-mixer.exe` from
  [Releases](https://github.com/KakaruHayate/ACE-MIXER/releases/latest).
- **macOS (Apple Silicon)**: download `ace-mixer-macos`, then `chmod +x` it.
  Intel Macs have no prebuilt binary — the bundled numpy is arm64-only — so
  use the source install below.
- **Skill**: `ace-mixer-skill.zip` from the same release. Unzip it and drop
  `ace-v27-style-transfer/` into your agent's skills directory
  (`$CODEX_HOME/skills`, `~/.codex/skills`, or `~/.claude/skills`). The binary
  is the tool; the skill is what tells an agent how to use it.
- **From source** (any platform, needs Python 3.10+ and `uv`):

  ```bash
  git clone https://github.com/KakaruHayate/ACE-MIXER
  cd ACE-MIXER
  uv venv && uv pip install -e .
  uv run ace-mixer doctor
  ```

  Mainland-China mirror: `git clone
  https://gitclone.com/github.com/KakaruHayate/ACE-MIXER.git`.

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
