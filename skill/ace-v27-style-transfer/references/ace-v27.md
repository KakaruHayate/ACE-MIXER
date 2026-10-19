# ACE Studio Verse 2.7: parameters and layers

## Layer model

V2.7 runs the `singing-mamba` engine generation. Per clip:

```text
Param     baseline  user  envelope  direct  global
air       ro        rw    -         -       -
falsetto  ro        rw    -         -       -
tension   ro        rw    -         -       -
energy    ro        rw    -         -       -
formant   -         -     -         -       -
```

```text
effective = user (where user has a value) else baseline
```

`user` is an **absolute override**, not a delta: writing `0.3` makes
`effective` exactly `0.3`. All four parameters are `[0, 1]` (`scale: model`).

`formant` and `pitch` report no layers on this generation; both refuse reads
and writes. `pitch` refusal text: *"the channel stores a delta while the draw
primitive takes absolute pitch, and anchors and vibrato ride on top"* — an
unexposed API surface, not an engine limitation.

## Parameter definitions

All four are computed by ACE's local analysis chain from audio.

| channel | definition | inputs |
|---|---|---|
| `energy` | `clamp(v/5.2, 0, 1)`, `v` from a 128-band log-mel chain | audio |
| `air` | `clamp(1/(1+10^(m/10)), 0, 1)`, `m` = mean dB of HNR bands 12…16 | audio + f0 |
| `tension` | `clamp((20·log10(g₁/((S(2f₀)/2S(f₀))·g₂)) + 2.2)/5, 0, 1)` | audio + f0 |
| `falsetto` | `clamp((−log₂(Rd) + 2.3)/6.6, 0, 1)` | audio + f0 |

`tension` and `falsetto` share one estimated `Rd`.

### Rd estimation

```text
per frame:
  harmonic amplitudes (4-period Blackman window, per-harmonic correlation)
  × radiation correction g(y) = y·A/√(y²+A²), A = 1.441012389579915
  match against 64 LF templates, Rd = linspace(0.02, 3.0, 64), f0 = 200 Hz
      template[k][j] = (spec_Rd_k((j+1)·200 Hz) / (j+1))²
  minimise Itakura–Saito divergence (level-normalised at j = 0)
  argmin → parabola vertex → linear interpolation between grid points
```

Result is continuous, not a grid value.

### HNR bands (for `air`)

24 bands, equal steps on the ERB-rate scale:

```text
band[i] = 228.8 · ((1 + (fs/2)/228.8)^(i/24) − 1)
```

`air` averages bands 12…16, roughly 2.0–5.6 kHz at 44.1 kHz.

### Box-Cox

Applied to `tension` and `falsetto` before the final normalisation:

```text
boxcox(x) = sign(x) · ((|x| + 1)^λ − 1) / λ / N
tension :  λ = 0.7119 (x≥0) / 1.2881 (x<0),  N = 4.0847
falsetto:  λ = 0.742  (x≥0) / 1.258  (x<0),  N = 0.8039
```

## Frame rates

The whole local analysis chain shares one frame grid:

```text
sr = 44100, hop = 256, nfft = 2048
    -> 172.265625 fps, 5.805 ms per frame
```

| stage | rate |
|---|---|
| energy (128-band mel STFT) | 172.27 fps |
| per-harmonic analysis (4-period Blackman) | 172.27 fps |
| HNR / air (24 bands) | 172.27 fps |
| Rd (LF template matching) | 172.27 fps |
| tension / falsetto | 172.27 fps |
| gaussian smoothing | 4 frames sigma, 16 frames radius = 23.2 ms / 92.9 ms |
| Rd three-point smoothing | 3 frames = 17.4 ms (`round(0.02 / (hop/sr))`) |
| **stored curve (dense layer)** | **960 ticks/s** |

So the analysis runs at 172.27 Hz while the curve is stored per tick at
960 Hz: about **5.57 ticks per analysis frame**. Do not confuse the two rates.

### Model side (local ONNX, turbo mode)

`<ACE Studio>/mlaudio/` ships the local pipeline as ONNX. The graphs give the
model's own grid:

| model | shapes | what it says |
|---|---|---|
| `refinegan2_sota_grouped_fp16.onnx` | mel `[1,128,960]` -> `[1,16,15360]` | ConvTranspose strides `4·4·4·2·2 = 256`; `960 × 256 = 245 760` samples = 5.5728 s, i.e. hop 256 @ 44.1 kHz |
| `dcae_decoder_v4lite_1024_fp16.onnx` | codes `[1,6,64,8]` -> mel `[1,1,1024,128]` | 64 codes expand to 1024 mel frames: **16 mel frames per code** |
| `mel2pitch_12M_1000k_fp32_dyn.onnx` | mel `[1,128,T]` -> f0 `[1,1,T]` | same mel grid |
| `mel2dur.onnx` | mel `[1,94,T]` -> logits `[1,T,1024]` | 94-bin feature, side model |

So the codec runs at `172.27 / 16 = 10.77 fps` (92.9 ms per code frame, ~89
ticks), and one inference chunk is 1024 mel frames (5.944 s) from 64 codes.

`dcae_decoder` takes only `codes`; the four vocal parameters are not its
inputs, so in turbo mode they reach the audio through the mel/pulse path
upstream of the vocoder.

What is **not** measured: the frame rate of the payload sent to the remote
model. The project stores curves per tick; whether the upload resamples them
needs a packet capture.

An earlier empirical alignment suggested ~174.5 fps (5.5 ticks per frame),
1.3% above the static constant. Treat the constant as authoritative.

Running the chain at hop 512 instead of 256 halves the frame rate to
86.13 fps, doubles the gaussian time constant to 46.4 ms, and changes the Rd
smoothing kernel from 3 frames to 2. All three change the measured curves.

## Timing

- Dense layers are one value per clip-local tick.
- 480 ticks/beat; at 120 BPM that is **960 ticks/second**.
- Frame → tick mapping must use absolute seconds; a residual under one frame
  (5.8 ms) is inaudible.
- A write must stay inside the clip's visible span; exceeding it is rejected.

## Model behaviour

V2.7 is `timbreOnly: true`. `blend add --style` errors on this model, so voice
blending mixes timbre only. Style must come from the four parameter curves.

Parameter ranges observed on fresh, unrendered clips are placeholders
(`tension` 0.333, `energy`/`falsetto` 0). Render once before reading
`baseline` for blending.
