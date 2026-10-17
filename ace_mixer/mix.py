"""Blend an external curve with the engine's own baseline.

Pure functions: no audio, no subprocess, so this is the easiest part to test.
"""

from __future__ import annotations

import numpy as np


def _arr(values: list[float | None]) -> np.ndarray:
    return np.array([np.nan if v is None else float(v) for v in values], dtype=float)


def blend(
    base: list[float | None],
    external: list[float | None],
    w: float,
    mode: str = "match",
    value_range: tuple[float, float] = (0.0, 1.0),
) -> tuple[list[float | None], dict[str, float]]:
    """Mix ``external`` into ``base`` at weight ``w``.

    ``mode='match'`` standardises the external curve to the baseline's mean and
    spread first, so only its shape transfers. ``mode='direct'`` mixes the raw
    normalised values, carrying the source's overall tendency too.

    Returns the mixed curve plus a small stats dict for reporting.
    """
    if not 0.0 <= w <= 1.0:
        raise ValueError("w must be within [0, 1]")
    if mode not in ("match", "direct"):
        raise ValueError("mode must be 'match' or 'direct'")

    b = _arr(base)
    e = _arr(external)
    n = min(len(b), len(e))
    b, e = b[:n], e[:n]
    voiced = np.isfinite(e)
    if voiced.sum() < 2:
        raise ValueError("external curve has no voiced ticks")

    bv, ev = b[voiced], e[voiced]
    usable = np.isfinite(bv)
    lo, hi = value_range

    stats: dict[str, float] = {"voiced": float(voiced.sum()), "ticks": float(n)}

    if usable.sum() < 2:
        mixed = np.clip(ev, lo, hi)
        stats["baseline"] = 0.0
    else:
        bf = np.where(usable, bv, float(np.nanmean(bv[usable])))
        if mode == "match":
            b_mean, b_std = float(np.nanmean(bf)), float(np.nanstd(bf))
            e_mean, e_std = float(np.nanmean(ev)), float(np.nanstd(ev))
            ev = (ev - e_mean) / (e_std + 1e-9) * (b_std + 1e-9) + b_mean
            stats.update(ext_mean=e_mean, base_mean=b_mean, ext_std=e_std, base_std=b_std)
        mixed = np.clip((1.0 - w) * bf + w * ev, lo, hi)
        stats["baseline"] = 1.0

    out = np.full(n, np.nan)
    out[voiced] = mixed
    stats["mean"] = float(np.nanmean(out))
    stats["min"] = float(np.nanmin(out))
    stats["max"] = float(np.nanmax(out))
    return [None if not np.isfinite(v) else round(float(v), 5) for v in out], stats


def summarize(curve: list[float | None]) -> dict[str, float]:
    a = _arr(curve)
    finite = np.isfinite(a)
    if not finite.any():
        return {"ticks": float(len(a)), "voiced": 0.0}
    return {
        "ticks": float(len(a)),
        "voiced": float(finite.sum()),
        "min": float(np.nanmin(a)),
        "max": float(np.nanmax(a)),
        "mean": float(np.nanmean(a)),
    }
