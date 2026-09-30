"""Hidden heatwaves: water 50–150 m down in a marine heatwave while the surface looks normal.

A satellite sees the surface. A heatwave that sits below it (a warm eddy, a deepened warm
layer) is invisible to SST alone, and Argo samples it only where a float happens to be.
The reconstruction is daily and everywhere, so it can flag it.

**Definition** (Hobday et al. 2016, Progress in Oceanography 141, 227–238), applied to a
layer instead of the surface:

  * the quantity is the depth-mean temperature of the 50–150 m layer (levels 50, 75, 100,
    125, 150 m, trapezoidal), and separately the 0 m temperature;
  * the threshold is its 90th percentile for that day of year and cell, over the training
    years, in an 11-day window centred on the day (Hobday's ±5 days);
  * **hidden**: the layer above its threshold while the surface is at or below its own;
  * on the map, the layer must stay above its threshold for 5 or more consecutive days
    (Hobday's minimum duration). A single Argo cast cannot show duration, so the harness
    scores the one-day condition and says so.

The baseline is GLORYS over the training years (2010-02-04 → 2020-12-31), not Hobday's
30 years: the record here is shorter (docs/10-unsourced.md). It is a fixed baseline, so a
warming trend shows up as more exceedances, as Hobday recommends.

    python -m satelight.heatwave          # self-check, no data
    python -m satelight.heatwave --fit    # the baseline, from the GLORYS cube (a few minutes)
"""

from __future__ import annotations

import sys
from datetime import date
from functools import lru_cache

import numpy as np

from . import config

LAYER = (50.0, 150.0)
WINDOW = 5                 # days either side (Hobday et al. 2016)
PCTL = 90.0
MIN_DAYS = 5
PATH = config.RUNS / "heatwave" / "p90.npz"


def _layer_index() -> np.ndarray:
    z = config.DEPTHS
    return np.flatnonzero((z >= LAYER[0]) & (z <= LAYER[1]))


def layer_mean(t: np.ndarray, axis: int = 0) -> np.ndarray:
    """Depth-mean over the 50–150 m levels along `axis` (the 15-level axis), trapezoidal.
    NaN where any of those levels is missing (shallower than 150 m, or a gap)."""
    k = _layer_index()
    z = config.DEPTHS[k]
    v = np.take(t, k, axis=axis)
    w = np.zeros(z.size)
    w[:-1] += np.diff(z) / 2
    w[1:] += np.diff(z) / 2
    shape = [1] * v.ndim
    shape[axis] = z.size
    return (v * (w / w.sum()).reshape(shape)).sum(axis=axis)


def fit() -> None:
    from .baselines import _doy
    from .data import _read

    a, b = config.SPLITS["train"]
    sub, surf, doys = [], [], []
    for y in range(a.year, b.year + 1):
        v, t = _read("glorys", "thetao", max(a, date(y, 1, 1)), min(b, date(y, 12, 31)))
        sub.append(layer_mean(v, axis=1).astype(np.float32))
        surf.append(v[:, 0].astype(np.float32))
        doys.append(_doy(t))
        print("heatwave baseline: read", y)
    sub, surf, doys = np.concatenate(sub), np.concatenate(surf), np.concatenate(doys)
    p_sub = np.full((365,) + sub.shape[1:], np.nan, np.float32)
    p_surf = np.full_like(p_sub, np.nan)
    for d in range(365):
        near = np.abs((doys - d + 182) % 365 - 182) <= WINDOW
        with np.errstate(all="ignore"):
            p_sub[d] = np.nanpercentile(sub[near], PCTL, axis=0)
            p_surf[d] = np.nanpercentile(surf[near], PCTL, axis=0)
    PATH.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(PATH, sub=p_sub, surf=p_surf, fitted_on=f"{a} -> {b}")
    print("heatwave baseline written:", PATH)


@lru_cache(maxsize=1)
def baseline() -> tuple[np.ndarray, np.ndarray]:
    """(365, H, W) 90th percentiles of the 50–150 m layer and of 0 m."""
    z = np.load(PATH)
    return z["sub"], z["surf"]


def hidden(profile: np.ndarray, doy: int, j: int, i: int) -> tuple[float, float]:
    """One 15-level profile at cell (j, i): (subsurface flag, hidden flag) as 1.0 / 0.0,
    NaN where the layer or the surface has no value."""
    p_sub, p_surf = baseline()
    s = float(layer_mean(profile))
    top = float(profile[0])
    if not (np.isfinite(s) and np.isfinite(top) and np.isfinite(p_sub[doy, j, i])):
        return np.nan, np.nan
    warm = s > p_sub[doy, j, i]
    return float(warm), float(warm and top <= p_surf[doy, j, i])


def runs_of(flags: np.ndarray, centre: int, n: int = MIN_DAYS) -> np.ndarray:
    """(T, ...) booleans -> where day `centre` lies in a run of at least n True days."""
    T = flags.shape[0]
    out = np.zeros(flags.shape[1:], bool)
    for s in range(max(0, centre - n + 1), min(centre, T - n) + 1):
        out |= flags[s:s + n].all(axis=0)
    return out


def demo() -> None:
    lin = np.array([30.0, 29.5, 29.0, 28.0, 27.0, 25.0, 23.0, 21.0, 19.0, 17.0, 14.0, 12.0, 10.0, 8.0, 6.0])
    # 50..150 m: 25, 23, 21, 19, 17 at 50, 75, 100, 125, 150 m; equal spacing -> weights 1,2,2,2,1
    assert np.isclose(layer_mean(lin), (25 + 2 * 23 + 2 * 21 + 2 * 19 + 17) / 8)
    gap = lin.copy()
    gap[7] = np.nan
    assert np.isnan(layer_mean(gap)), "a missing level in the layer: no value, nothing guessed"
    f = np.array([0, 1, 1, 1, 1, 1, 0, 1, 1, 0], bool)[:, None]
    assert runs_of(f, 3)[0] and runs_of(f, 5)[0], "inside a 5-day run"
    assert not runs_of(f, 7)[0], "a 2-day run is not a heatwave"
    assert not runs_of(f, 0)[0]
    print("heatwave ok: layer mean, 5-day runs")


if __name__ == "__main__":
    fit() if "--fit" in sys.argv else demo()
