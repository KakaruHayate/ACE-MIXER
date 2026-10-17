import wave
from pathlib import Path

import numpy as np
import pytest

from ace_mixer import curves


def write_wav(path: Path, samples: np.ndarray, rate: int = 44100, channels: int = 1) -> None:
    data = np.clip(samples * 32767.0, -32768, 32767).astype("<i2")
    with wave.open(str(path), "wb") as w:
        w.setnchannels(channels)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(data.tobytes())


def test_read_wav_mono16(tmp_path: Path) -> None:
    t = np.arange(4410) / 44100.0
    sig = 0.5 * np.sin(2 * np.pi * 220.0 * t)
    p = tmp_path / "a.wav"
    write_wav(p, sig)
    x = curves.read_wav(str(p))
    assert len(x) == 4410
    assert x.dtype == np.float32
    assert 0.4 < float(np.max(np.abs(x))) < 0.6


def test_read_wav_downmixes_stereo(tmp_path: Path) -> None:
    t = np.arange(1000) / 44100.0
    left = 0.5 * np.sin(2 * np.pi * 200.0 * t)
    right = -left
    inter = np.empty(2000)
    inter[0::2] = left
    inter[1::2] = right
    p = tmp_path / "b.wav"
    write_wav(p, inter, channels=2)
    x = curves.read_wav(str(p))
    assert len(x) == 1000
    assert float(np.max(np.abs(x))) < 1e-3


def test_f0_from_ufdata_roundtrip(tmp_path: Path) -> None:
    import json

    doc = {
        "project": {
            "tracks": [
                {
                    "pitch": {
                        "ticks": [0, 960, 1920],
                        "values": [69.0, 69.0, 69.0],
                        "isAbsolute": True,
                    }
                }
            ]
        }
    }
    p = tmp_path / "a.ufdata"
    p.write_text(json.dumps(doc), encoding="utf-8")
    f0 = curves.f0_from_ufdata(str(p), 10)
    assert f0 is not None
    assert np.allclose(f0, 440.0, rtol=1e-4)


def test_frame_rms_matches_direct_computation() -> None:
    x = np.random.default_rng(0).normal(0, 0.1, 5000).astype(np.float32)
    n = 4
    rms = curves._frame_rms(x, n)
    for i in range(n):
        seg = x[i * curves.HOP : i * curves.HOP + curves.NFFT].astype(np.float64)
        assert rms[i] == pytest.approx(float(np.sqrt(np.mean(seg**2))), rel=1e-9)
