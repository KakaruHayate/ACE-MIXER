"""Extract ACE V2.7's four vocal parameters from a dry vocal render.

CPU only (numpy). The LF/Rd mathematics is the vendored ACE analysis chain in
``chain.py``; this module supplies f0, the analysis frames, and the tick grid.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import numpy as np

SR = 44100
HOP = 512
NFFT = 2048
TICKS_PER_SEC = 960.0
PARAMS = ("air", "tension", "falsetto", "energy")

_chain = None


def chain():
    global _chain
    if _chain is None:
        path = Path(__file__).with_name("chain.py")
        spec = importlib.util.spec_from_file_location("ace_mixer.chain", path)
        mod = importlib.util.module_from_spec(spec)
        sys.modules["ace_mixer.chain"] = mod
        spec.loader.exec_module(mod)
        _chain = mod
    return _chain


def read_wav(path: str) -> np.ndarray:
    """Minimal RIFF reader: PCM16/24/32 and IEEE float32, any channel count."""
    blob = open(path, "rb").read()
    if blob[:4] != b"RIFF":
        raise ValueError("not a RIFF/WAVE file: %s" % path)
    pos, tag, nch, sr, bits, data = 12, None, None, None, None, None
    while pos + 8 <= len(blob):
        cid = blob[pos : pos + 4]
        size = int.from_bytes(blob[pos + 4 : pos + 8], "little")
        body = blob[pos + 8 : pos + 8 + size]
        if cid == b"fmt ":
            tag = int.from_bytes(body[0:2], "little")
            nch = int.from_bytes(body[2:4], "little")
            sr = int.from_bytes(body[4:8], "little")
            bits = int.from_bytes(body[14:16], "little")
        elif cid == b"data":
            data = body
        pos += 8 + size + (size & 1)
    if data is None:
        raise ValueError("no data chunk in %s" % path)

    if bits == 32 and tag == 3:
        x = np.frombuffer(data, dtype="<f4").astype(np.float64)
    elif bits == 32:
        x = np.frombuffer(data, dtype="<i4").astype(np.float64) / 2147483648.0
    elif bits == 16:
        x = np.frombuffer(data, dtype="<i2").astype(np.float64) / 32768.0
    elif bits == 24:
        raw = np.frombuffer(data, dtype=np.uint8).reshape(-1, 3)
        v = (
            raw[:, 0].astype(np.int32)
            | (raw[:, 1].astype(np.int32) << 8)
            | (raw[:, 2].astype(np.int32) << 16)
        )
        v = np.where(v >= 1 << 23, v - (1 << 24), v)
        x = v.astype(np.float64) / float(1 << 23)
    else:
        raise ValueError("unsupported wav: tag=%s bits=%s" % (tag, bits))

    if nch > 1:
        x = x.reshape(-1, nch).mean(axis=1)
    if sr != SR:
        n_out = int(round(len(x) * SR / sr))
        x = np.interp(np.arange(n_out) / SR, np.arange(len(x)) / sr, x)
    return x.astype(np.float32)


def yin_f0(
    x: np.ndarray, fmin: float = 60.0, fmax: float = 1000.0, win: int = 1024, thresh: float = 0.15
) -> np.ndarray:
    """YIN with an FFT-accelerated difference function."""
    n_frames = max(0, (len(x) - win) // HOP + 1)
    lag_min = max(2, int(SR / fmax))
    lag_max = min(win - 1, int(SR / fmin))
    n_lags = lag_max + 1
    nfft = 1 << int(np.ceil(np.log2(win + lag_max + 1)))
    out = np.zeros(n_frames, dtype=np.float32)

    for i in range(n_frames):
        seg = x[i * HOP : i * HOP + win + lag_max].astype(np.float64)
        if len(seg) < win + lag_max:
            seg = np.pad(seg, (0, win + lag_max - len(seg)))
        if float(np.sqrt(np.mean(seg[:win] ** 2))) < 1e-4:
            continue

        spec = np.fft.rfft(seg, nfft)
        ac = np.fft.irfft(spec * np.conj(spec), nfft)[:n_lags]
        csum = np.concatenate(([0.0], np.cumsum(seg**2)))
        d = np.maximum(csum[win] + (csum[win : win + n_lags] - csum[0:n_lags]) - 2.0 * ac, 0.0)

        cum = np.cumsum(d[1:])
        denom = cum / np.arange(1, n_lags)
        cmnd = np.ones(n_lags)
        cmnd[1:] = d[1:] / np.where(denom > 1e-12, denom, 1e-12)

        lag = -1
        for tau in range(lag_min, lag_max):
            if cmnd[tau] < thresh:
                while tau + 1 < lag_max and cmnd[tau + 1] < cmnd[tau]:
                    tau += 1
                lag = tau
                break
        if lag < 0:
            continue

        y0, y1, y2 = cmnd[lag - 1], cmnd[lag], cmnd[lag + 1]
        den = y0 - 2.0 * y1 + y2
        delta = 0.5 * (y0 - y2) / den if abs(den) > 1e-12 else 0.0
        out[i] = SR / (lag + delta)
    return out


def f0_from_ufdata(path: str, n_frames: int) -> np.ndarray | None:
    """Reuse a .ufdata pitch curve instead of estimating f0 again."""
    import json

    doc = json.loads(open(path, encoding="utf-8").read())
    pitch = (doc.get("project", {}).get("tracks") or [{}])[0].get("pitch") or {}
    ticks = np.asarray(pitch.get("ticks") or [], dtype=np.float64)
    values = pitch.get("values") or []
    if not len(ticks) or not len(values):
        return None
    midi = np.where(
        np.asarray([np.nan if v is None else float(v) for v in values]) > 0,
        np.asarray([np.nan if v is None else float(v) for v in values]),
        np.nan,
    )
    grid = np.arange(n_frames) * (HOP / SR)
    m = np.interp(grid, ticks / TICKS_PER_SEC, midi, left=np.nan, right=np.nan)
    f0 = np.where(np.isfinite(m), 440.0 * 2.0 ** ((m - 69.0) / 12.0), 0.0)
    return f0.astype(np.float32)


def _pnorm(a: np.ndarray, mask: np.ndarray) -> np.ndarray:
    lo, hi = np.percentile(a[mask], [1, 99])
    if not np.isfinite(lo) or not np.isfinite(hi) or hi <= lo:
        return np.clip(a, 0.0, 1.0)
    return np.clip((a - lo) / (hi - lo), 0.0, 1.0)


def _frame_rms(x: np.ndarray, n_frames: int) -> np.ndarray:
    """RMS of each analysis frame's NFFT window, via a prefix sum."""
    need = max(0, (n_frames - 1) * HOP + NFFT)
    if len(x) < need:
        x = np.pad(x, (0, need - len(x)))
    cs = np.concatenate(([0.0], np.cumsum(x.astype(np.float64) ** 2)))
    starts = np.arange(n_frames) * HOP
    ends = starts + NFFT
    return np.sqrt(np.maximum(cs[ends] - cs[starts], 0.0) / NFFT)


def _to_ticks(
    values: np.ndarray, mask: np.ndarray, n_ticks: int, centers: np.ndarray
) -> np.ndarray:
    grid = np.arange(n_ticks, dtype=np.float64) / TICKS_PER_SEC
    out = np.interp(grid, centers, values, left=np.nan, right=np.nan)
    m = np.interp(grid, centers, mask.astype(float), left=0.0, right=0.0) > 0.5
    return np.where(m, out, np.nan)


def extract(
    wav: str, n_ticks: int, f0_ufdata: str | None = None, raw: bool = False
) -> dict[str, list[float | None]]:
    """Return ``{param: [value or None per tick]}``."""
    vp = chain()
    x = read_wav(wav)
    n_ana = max(0, (len(x) - NFFT) // HOP + 1)

    # YIN always runs: its periodicity test decides what is voiced. A pitch
    # curve imported from .ufdata is continuous (it carries no gap markers), so
    # it cannot answer that on its own — it only supplies the f0 value.
    f0_yin = yin_f0(x)
    f0_yin = np.pad(f0_yin, (0, max(0, n_ana - len(f0_yin))))[:n_ana]
    f0_imported = f0_from_ufdata(f0_ufdata, n_ana) if f0_ufdata else None

    n = n_ana
    x = x[: (n - 1) * HOP + NFFT] if n else x
    if f0_imported is not None:
        f0 = np.where(f0_yin[:n] > 0, f0_imported[:n], 0.0)
    else:
        f0 = f0_yin[:n]
    f0 = np.asarray(f0, dtype=np.float32)

    rms = _frame_rms(x, n)
    gate = max(1e-4, 0.05 * float(np.percentile(rms, 95))) if n else 1e-4
    voiced = (f0_yin[:n] > 0) & (rms > gate)

    an = vp.VocalParamAnalyzer(SR, HOP, NFFT)
    amps, _phases, counts = an.harmonics(x, f0)
    hnr = an.hnr_matrix(x, f0, amps, counts)
    breath = an.breathiness(hnr)
    energy = an.energy(x)
    rd = an.rd_estimate(f0, amps, counts)

    t_raw = an.tension_raw(f0, rd)
    t_sm = vp.gaussian_smooth_nan(np.nan_to_num(t_raw, nan=0.0)).astype(np.float32)
    t_sm = np.where(f0 > 1.0, t_sm, 0.0)
    t_bc = an._boxcox(t_sm, vp.TENSION_EXP, vp.TENSION_NORM)

    f_raw = an.falsetto_raw(f0, rd)
    f_sm = vp.gaussian_smooth_nan(np.nan_to_num(f_raw, nan=0.0)).astype(np.float32)
    f_bc = an._boxcox(f_sm, vp.FALSETTO_EXP, vp.FALSETTO_NORM)

    curves = {
        "energy": np.clip(energy[:n] / 5.2, 0.0, 1.0),
        "air": np.clip(breath[:n], 0.0, 1.0),
        "tension": np.clip((t_bc[:n] + 2.2) / 5.0, 0.0, 1.0),
        "falsetto": np.clip((f_bc[:n] + 2.3) / 6.6, 0.0, 1.0),
    }
    centers = np.arange(n) * (HOP / SR) + (NFFT / 2.0) / SR

    out: dict[str, list[float | None]] = {}
    for name, values in curves.items():
        values = np.asarray(values, dtype=np.float64)
        if not raw:
            values = _pnorm(values, voiced)
        ticks = _to_ticks(values, voiced, n_ticks, centers)
        out[name] = [None if not np.isfinite(v) else round(float(v), 5) for v in ticks]
    return out
