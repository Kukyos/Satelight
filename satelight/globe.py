"""The whole planet's sea surface temperature for one day, painted around the cube.

Display only: never an input, never a target, never scored. The cube is our box; what the
globe needs around it is what a satellite saw on the same day, so the reconstruction sits
inside the real ocean instead of on a blank planet. OSTIA, the same product family the
model reads for its SST input, so nothing here comes from GLORYS (hard rule 7).

    python -m satelight.globe                 # self-check, no network
    python -m satelight.globe 2023-05-17 ...  # fetch and cache those days

Native 0.05° -> 0.25° by 5 × 5 block mean (hard rule 3), one float16 file per day in
data/cache/globe/. A block counts as sea when at least half its native cells are sea.
The reprocessed product up to its last day, the near-real-time one after it, and the file
records which.
"""

from __future__ import annotations

import sys
from functools import lru_cache

import numpy as np

from . import config

REP = "METOFFICE-GLO-SST-L4-REP-OBS-SST"
NRT = "METOFFICE-GLO-SST-L4-NRT-OBS-SST-V2"
BLOCK = 5
SEA_MIN = 13          # of 25 native cells; ponytail: half, the same spirit as the box's sea share
CACHE = config.CACHE / "globe"


@lru_cache(maxsize=2)
def _store(dataset_id: str):
    from . import arco
    return arco.open_store(dataset_id, service="arco-geo-series", raw=True)


def block_mean(a: np.ndarray, k: int = BLOCK, need: int = SEA_MIN) -> np.ndarray:
    """(H, W) native -> (H/k, W/k), mean of the finite cells, NaN where fewer than `need`."""
    h, w = a.shape[0] // k, a.shape[1] // k
    b = a[:h * k, :w * k].reshape(h, k, w, k)
    n = np.isfinite(b).sum(axis=(1, 3))
    s = np.nansum(b, axis=(1, 3))
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.where(n >= need, s / n, np.nan).astype(np.float32)


def sst(day: str) -> tuple[np.ndarray, str]:
    """(720, 1440) °C, south first, west first from 180°W; and the dataset it came from."""
    CACHE.mkdir(parents=True, exist_ok=True)
    path = CACHE / f"sst_{day.replace('-', '')}.npz"
    if path.exists():
        z = np.load(path)
        return z["sst"].astype(np.float32), str(z["source"])
    from .fetch import _decode
    for dataset_id in (REP, NRT):
        s = _store(dataset_id)
        first, last = s.coverage()
        if first <= day <= last:
            da = s.ds["analysed_sst"]
            packed = da.sel(time=day).values
            v = _decode(packed, da.attrs)
            if str(da.attrs.get("units", "")).lower() in ("k", "kelvin"):
                v = v - 273.15
            out = block_mean(v)
            np.savez_compressed(path, sst=out.astype(np.float16), source=dataset_id)
            return out, dataset_id
    raise FileNotFoundError(f"no OSTIA analysis covers {day}")


def demo() -> None:
    a = np.arange(100, dtype=np.float32).reshape(10, 10)
    a[:5, :5] = np.nan
    a[5, 5] = np.nan
    m = block_mean(a)
    assert m.shape == (2, 2)
    assert np.isnan(m[0, 0])                               # all land
    assert np.isclose(m[1, 1], np.nanmean(a[5:, 5:]))      # one cell missing, still sea
    b = a.copy()
    b[:5, 5:] = np.nan
    b[0, 5:] = 1.0                                         # 5 of 25 sea: land
    assert np.isnan(block_mean(b)[0, 1])
    print("globe ok")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        for d in sys.argv[1:]:
            v, src = sst(d)
            print(d, src, f"{np.nanmin(v):.2f} .. {np.nanmax(v):.2f} °C")
    else:
        demo()
