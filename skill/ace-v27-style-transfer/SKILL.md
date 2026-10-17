---
name: ace-v27-style-transfer
description: Move another singing synthesizer's vocal style onto an ACE Studio Verse 2.7 voice. Converts any LibreSVIP-readable project to ACE notes plus an absolute pitch curve, extracts air/tension/falsetto/energy from the source dry render, and writes them to the clip's user layer, optionally blended with the engine's own baseline. Use only for ACE Studio Verse 2.7; other ACE model generations use a different layer model.
---

# Cross-engine style transfer onto ACE Studio V2.7

## Entry point

The pipeline is packaged as **ACE-MIXER**
(<https://github.com/KakaruHayate/ACE-MIXER>). One command runs all of it:

```bash
ace-mixer run --dir <folder-with-project-and-dry-render> --ratio 0.5
```

From a source checkout, use `uv run ace-mixer ...` instead. Run
`ace-mixer doctor` first; it reports whether `acestudio-cli`, `libresvip-cli`
and a Verse 2.7 track are all present, and refuses nothing else.

## Scope

ACE Studio **Verse 2.7** only. On this model the four vocal parameters are
writable through a single absolute `user` layer, and the model is
`timbreOnly` — voice blending cannot carry singing style, so parameter
curves are the only transfer channel.

Two facts drive the whole design:

1. **ACE's four parameters are audio features**, so they are computed from the
   source's dry render, not read from the source project.
2. **The source project is only needed for what is sung**: notes, lyrics, and
   the absolute pitch contour.

## Inputs

- **Source project** in any LibreSVIP-readable format (see
  `references/engines.md`)
- **Source dry render**: monophonic, no reverb/EQ/compression, same notes as
  the project

Phoneme sequences and phoneme durations are **not** inputs. `.ufdata` carries
only `key / tickOn / tickOff / lyric` per note; ACE runs its own G2P.

## Workflow

### 1. Convert the project to `.ufdata`

`ace-mixer` shells out to `libresvip-cli`. Two import options matter:

- **pitch import** — enable it; the output carries a frame-level absolute pitch
  curve (`ticks` / `values` / `isAbsolute: true`, values are MIDI semitones,
  `0` means "no pitch").
- **rest / breath note handling** — the rest and breath note lyrics the plugin
  lists are dropped or converted automatically. Do not hand-edit them.

If a newer OpenUtau project fails on `MaskedCurve`, the tool strips those
declarations and retries by itself (see `references/engines.md`).

### 2. Import into ACE

```bash
acestudio-cli import file --path out.ufdata --track-uuid <UUID> --pos 0t
```

Project-type imports reject `--on-occupied`. `ace-mixer run --import-notes`
does this step and re-reads the clip.

### 3. Render once

The engine's `baseline` is a placeholder until it has analysed the clip
(observed: constant `0.333` for tension, `0` for energy/falsetto). Render the
clip once so `baseline` becomes real, otherwise a blend has nothing to blend
with. Without it, `ace-mixer` writes the external curve unchanged and says so.

### 4. Extract curves from the dry render

`ace-mixer` runs YIN for the voicing decision and the vendored ACE analysis
chain for the four parameters, on the clip's tick grid.

Rules that matter:

- **UV comes from the audio**, never from the source project's f0. A pitch
  curve imported from `.ufdata` is continuous and carries no gap markers, so
  f0 alone would mark every frame voiced.
- Curves are left empty on unvoiced ticks so they align with ACE's own
  `unvoiced` ranges.
- **Normalise per parameter** (1st–99th percentile over voiced ticks).
  Cross-engine absolute levels are meaningless: ACE's `air`, for example,
  saturates near 1.0 on other engines' renders while still carrying ~11 dB of
  real dynamic range.

### 5. Blend with the engine's baseline

- `--mode match` (default): match the external curve's mean and spread to the
  baseline, then mix. Keeps the engine's overall tendency.
- `--mode direct`: mix raw normalised values. Carries the source's tendency.
- `--ratio 0` reproduces the engine's own take; `--ratio 1` is the external
  shape.

### 6. Verify

- Read back each parameter: `user` and `effective` must agree on voiced ticks.
- Confirm unvoiced ticks stayed empty rather than being filled with a default.
- Render the same span and compare against the source dry render; a mismatch
  larger than a frame (~10 ms) means the tick base is wrong.

## Invariants worth remembering

- `effective = user` where `user` has a value, otherwise `baseline`.
- All four parameters are `[0, 1]` on V2.7. Writes outside that are rejected.
- `formant` is **not available** on V2.7 — do not plan a mapping into it.
- Pitch curves are import-only: after import, no CLI surface reads or writes
  them. Treat f0 as one-shot.
- Writes are chunked; the clip's visible span is a hard bound.
- Tick rate is 960 ticks/second at 120 BPM (480 ticks/beat).
- Never touch the voice library or blend recipes. `ace-mixer` only writes the
  clip's `user` layer.

## References

- `references/engines.md` — every LibreSVIP format, what it can supply, and
  per-format pitfalls. Read the row for your source format before converting.
- `references/ace-v27.md` — the four parameters' exact definitions, layer
  semantics, and the value ranges ACE expects.
