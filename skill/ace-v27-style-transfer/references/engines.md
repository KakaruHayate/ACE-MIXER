# Source formats: what each one can supply

Derived by reading the LibreSVIP plugin sources under
`libresvip/plugins/<alias>/` (models, parsers, option classes). The "pitch"
column reflects whether that parser builds a pitch curve
(`edited_params.pitch`); where it is absent, extract f0 from the dry render.

**None of this changes the pipeline.** Every row below still yields notes +
lyrics through `.ufdata`. Engine-specific handling only affects step 1.

## The supported source formats

| alias | format | suffix | pitch curve | notes |
|---|---|---|---|---|
| `ace` | ACE Virtual Singer | `.ace` | yes | |
| `acep` | ACE Studio | `.acep` `.acet` | yes | also carries ACE's own param envelopes |
| `aisp` | AISingers Studio | `.aisp` | yes | |
| `ccs` | CeVIO Creative Studio | `.ccs` | yes | |
| `ds` | DiffSinger parameters | `.ds` | yes | see pitfalls |
| `dspx` | DiffScope Project Exchange | `.dspx` | yes | |
| `dv` | DeepVocal | `.dv` `.sk` | yes | |
| `json` | OpenSVIP | `.json` | — | interchange only |
| `mid` | Standard MIDI | `.mid` `.midi` | yes | lyrics only if lyric meta events exist |
| `mtp` | Muta | `.mtp` | yes | |
| `musicxml` | MusicXML | `.musicxml` `.xml` `.mxl` | note-level | no continuous pitch bend |
| `nn` | NIAONiao | `.nn` | yes | |
| `ppsf` | Piapro Studio | `.ppsf` | yes | |
| `ps_project` | Pocket Singer | `.ps_project` | yes | |
| `s5p` | Synthesizer V Editor | `.s5p` | yes | older SynthV editor |
| `svip` | X Studio | `.svip` | yes | |
| `svip3` | Netease XStudio | `.svip3` | yes | |
| `svp` | Synthesizer V Studio | `.svp` | yes | see pitfalls |
| `tlp` | TuneLab legacy | `.tlp` | yes | |
| `tlpx` | TuneLab | `.tlpx` | yes | |
| `tsmsln` | Techno-Speech Mobile | `.tsmsln` | yes | |
| `tssln` | Techno-Speech Solution | `.tssln` | yes | |
| `ust` | UTAU | `.ust` | sparse | pitch bend is relative and sparse |
| `ustx` | OpenUtau | `.ustx` | yes | see pitfalls |
| `vfp` | VOX Factory | `.vfp` | yes | |
| `vog` | Vogen | `.vog` | **no** | pitch must come from audio |
| `vpr` | New Vocaloid Project | `.vpr` | yes | |
| `vshp` | VocalShifter | `.vshp` | yes | read-only (no generator) |
| `vspx` | VocalSharp | `.vspx` | yes | |
| `vsq` | Vocaloid 2 sequence | `.vsq` | yes | |
| `vsqx` | Vocaloid sequence XML | `.vsqx` | yes | |
| `vvproj` | VOICEVOX | `.vvproj` | yes | |
| `vxf` | VX-β | `.vxf` | yes | |
| `xvsq` | Cadencii | `.xvsq` | yes | |
| `y77` | Yuan77 | `.y77` | yes | |

Write-only or non-note formats (`ass`, `lrc`, `srt`, `svg`) are not sources.

## LibreSVIP CLI mechanics

The GUI build has no working CLI. Use a CLI build:

```bash
libresvip-cli.exe proj convert <in> <out>
```

It is interactive, in three groups:

1. **Import options** — per plugin (import pitch, tempo, breath-note
   handling, note-group splitting…).
2. **Middleware** — pitch transposition, project scaling, lyric pronunciation
   conversion, punctuation removal, short-gap removal, lyric replacement.
   Defaults are off; accept them unless there is a reason.
3. **Export options** — tempo, default singer, breath length, lyric language.

Accept defaults by feeding blank lines:

```powershell
("`n" * 20) | & libresvip-cli.exe proj convert in out.ufdata
```

Inspect a plugin's options without converting:

```bash
libresvip-cli.exe plugin list
libresvip-cli.exe plugin detail <alias>
```

## Pitfalls by format

### OpenUtau `.ustx`

Newer projects fail to load with:

```text
Input tag 'MaskedCurve' found ... expected tags: 'Curve', 'Numerical', 'Options'
  expressions.rpit / expressions.pito
```

Those two expressions are declared as masked curves this build's model does
not know. Strip them and retry:

```bash
python scripts/strip_masked_curves.py in.ustx out.ustx
libresvip-cli.exe proj convert out.ustx result.ufdata
```

Verified: the result had the same note count and timing as the project
(719 notes / 225 660 ticks).

**No usable pitch is lost by stripping.** The `ustx` parser builds pitch from
note pitch + portamento, plus the `pitd` (pitch deviation) curve; it never
reads `masked_curves`. So `rpit` (rendered pitch, a cache) and `pito` (pitch
override) were already ignored before the strip — removing the declarations
only lets the model validate. If a project's pitch was hand-drawn with the
override tool, that contour is not transferred by this route; take the pitch
from the render instead.

`MaskedCurve` appears nowhere in LibreSVIP's source and was absent from
upstream `main` as well, so this was a real format gap rather than a stale
build. It is also OpenUtau-specific: every other plugin has its own schema and
would fail differently if the app were newer than the converter.

Fixed upstream in **SoulMelody/LibreSVIP#2124** (adds a `MaskedCurveExpression`
to the expression union). Once a LibreSVIP build includes it, the strip step
becomes unnecessary — keep the exe only for older builds.

The plugin already handles the format's special lyrics — 呼吸音歌词
`Asp AP`, 休止符歌词 `R SP`. Leave them at default; breath and rest notes are
dropped for you.

### DiffSinger `.ds`

Two duration fields exist and are not interchangeable:

- `note_dur` — note-level. **This is what the LibreSVIP parser reads.**
- `note_dur_seq` — in OpenUtau exports this often holds *phoneme* durations.

A `.ds` that fills only `note_dur_seq` parses to zero notes (the output
`.ufdata` is a few hundred bytes). Populate `note_dur` from authoritative note
timing.

Also: `.ds` lyrics may be pinyin while `ph_seq` holds X-SAMPA phonemes, and
`text` must line up with the slur groups the parser walks. If `text` and
`note_seq` disagree in length, rebuild `text` per slur group before
converting.

### Synthesizer V `.svp` / `.s5p`

The pitch import option defaults to **`plain` = only the edited parts**. For a
full contour transfer set 音高信息输入模式 to `full`. Otherwise the imported
pitch curve is note-level for untouched notes.

Other options worth knowing:

- 换气音符处理方式 — `convert` (default) turns breath notes into breath
  markers; `ignore` drops them entirely.
- 音符组导入方式 — `split` (default) can explode the track count; `merge`
  keeps original positions.

### MIDI / MusicXML

Both carry notes and (usually) lyrics, but no continuous pitch contour worth
transferring. Use the audio for f0.

### UTAU `.ust`

Pitch bend is relative and sparsely anchored; treat it as note-level only.

## Evidence status

- The format table, the `.ufdata` model, and every option name above were read
  from the bundled LibreSVIP sources, not from documentation.
- End-to-end conversions verified on this machine: OpenUtau `.ustx` → `.ufdata`
  (after stripping `MaskedCurve`) and DiffSinger `.ds` → `.ufdata`.
- The remaining formats were not converted here. The pitch column reflects
  what each parser constructs; if a conversion yields no pitch curve, fall
  back to audio-extracted f0 — the pipeline does not depend on it.
