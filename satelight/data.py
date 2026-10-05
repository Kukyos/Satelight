"""The training cube: per-year NetCDF files -> normalised arrays in memory.

Inputs are the eight satellite channels (L9) plus static fields, never anything from
GLORYS except the sea-floor depth. Targets are GLORYS temperature at the 15 depths.

    x   (T, C, 100, 240)  float16   z-scored, land and missing = 0, plus a sea-mask channel
    y   (T, 15, 100, 240) float16   z-scored per level, NaN where the level is masked

Normalisation statistics come from the train block only and are saved beside the run, so
the val and test blocks never inform them (hard rule 6).
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import xarray as xr

from . import config
from .fetch import cube_path

SOURCE_OF = {"sst": "sst", "sss": "sss", "adt": "ssh", "sla": "ssh",
             "uc": "oscar", "vc": "oscar", "uw": "ccmp", "vw": "ccmp"}


def _years(a: date, b: date) -> list[int]:
    return list(range(a.year, b.year + 1))


def _read(source: str, var: str, a: date, b: date,
          root: Path | None = None) -> tuple[np.ndarray, np.ndarray]:
    parts, times = [], []
    for y in _years(a, b):
        with xr.open_dataset(cube_path(source, y, root)) as ds:
            d = ds[var].sel(time=slice(str(a), str(b)))
            parts.append(d.values.astype(np.float32))
            times.append(d["time"].values.astype("datetime64[D]"))
    return np.concatenate(parts), np.concatenate(times)


def static_fields() -> dict[str, np.ndarray]:
    with xr.open_dataset(config.CUBE / "static.nc") as s:
        depth = s["deptho"].values
    lat2, lon2 = np.meshgrid(config.LAT, config.LON, indexing="ij")
    return {
        "lat": ((lat2 - 17.5) / 7.5).astype(np.float32),
        "lon": ((lon2 - 75.0) / 17.5).astype(np.float32),
        "bathy": np.where(np.isfinite(depth), np.log10(np.maximum(depth, 1.0)) / 3.0 - 1.0, 0.0
                          ).astype(np.float32),
    }


def available(split: str, sources: list[str]) -> bool:
    a, b = config.SPLITS[split]
    return all(cube_path(s, y).exists() for s in sources for y in _years(a, b))


class Stats:
    """Per-channel and per-level mean/std, from the train block."""

    def __init__(self, x_mean, x_std, y_mean, y_std):
        self.x_mean, self.x_std = np.asarray(x_mean, np.float32), np.asarray(x_std, np.float32)
        self.y_mean, self.y_std = np.asarray(y_mean, np.float32), np.asarray(y_std, np.float32)

    def save(self, path: Path) -> None:
        path.write_text(json.dumps({k: getattr(self, k).tolist()
                                    for k in ("x_mean", "x_std", "y_mean", "y_std")}, indent=1))

    @classmethod
    def load(cls, path: Path) -> "Stats":
        return cls(**json.loads(path.read_text()))


def load_raw(split: str, inputs: list[str], with_target: bool = True,
             span: tuple[date, date] | None = None, lags: list[int] = (0,),
             root: Path | None = None):
    """Raw physical fields for a split (or any span): inputs (T, C x len(lags), H, W),
    target (T, 15, H, W) or None, and the days. Days where any input is missing are
    dropped and reported.

    `lags` stacks each input as it was that many days earlier (0 is today). The earlier
    days are read from before the span where they exist; they are satellite inputs only,
    so reaching into the gap before a block never touches a target (hard rule 6)."""
    a, b = span or config.SPLITS[split]
    lead = max(lags)
    a0 = a - timedelta(days=lead) if root else max(a - timedelta(days=lead), min(a, config.WINDOW[0]))
    chans, t = [], None
    for v in inputs:
        arr, tv = _read(SOURCE_OF[v], v, a0, b, root)
        assert t is None or np.array_equal(t, tv), f"time axes differ at {v}"
        t = tv
        chans.append(arr)
    full = np.stack(chans, axis=1)
    keep = t >= np.datetime64(a)
    days = t[keep]
    # Each lag is the input on (day - lag), or the earliest day held if that is before
    # the record (only the first `lead` days of the window are affected).
    stack = []
    for lag in lags:
        idx = np.clip(np.searchsorted(t, days - np.timedelta64(lag, "D")), 0, t.size - 1)
        stack.append(full[idx])
    x = np.concatenate(stack, axis=1)
    del full, stack
    t = days
    y = None
    if with_target:
        y, ty = _read("glorys", "thetao", a, b)
        assert np.array_equal(t, ty), "target and input time axes differ"
    # A day with an input entirely missing (a missing granule) cannot be predicted.
    ok = ~np.all(np.isnan(x), axis=(2, 3)).any(axis=1)
    if not ok.all():
        print(f"{split}: dropped {int((~ok).sum())} days with a missing input", flush=True)
    return x[ok], (y[ok] if y is not None else None), t[ok]


def compute_stats(x: np.ndarray, y: np.ndarray) -> Stats:
    xm = np.nanmean(x, axis=(0, 2, 3))
    xs = np.nanstd(x, axis=(0, 2, 3))
    ym = np.nanmean(y, axis=(0, 2, 3))
    ys = np.nanstd(y, axis=(0, 2, 3))
    return Stats(xm, xs, ym, ys)


def doy_fields(t: np.ndarray) -> np.ndarray:
    doy = (t - t.astype("datetime64[Y]")).astype(int)
    ang = 2 * np.pi * doy / 365.25
    return np.stack([np.sin(ang), np.cos(ang)], axis=1).astype(np.float32)  # (T, 2)


def assemble(x: np.ndarray, t: np.ndarray, stats: Stats, sea: np.ndarray,
             with_doy: bool = True) -> np.ndarray:
    """Normalised model input: inputs, static fields, day of year, sea mask.

    `with_doy=False` zeroes the two day-of-year channels (the channel count is kept), so
    the model never sees the calendar and must read the season from the ocean (D-09)."""
    T = x.shape[0]
    xn = (x - stats.x_mean[None, :, None, None]) / stats.x_std[None, :, None, None]
    xn = np.nan_to_num(xn, nan=0.0)
    st = static_fields()
    static = np.broadcast_to(np.stack([st["lat"], st["lon"], st["bathy"]])[None],
                             (T, 3) + st["lat"].shape)
    d = doy_fields(t) if with_doy else np.zeros((T, 2), np.float32)
    doy = np.broadcast_to(d[:, :, None, None], (T, 2) + st["lat"].shape)
    mask = np.broadcast_to(sea[None, None].astype(np.float32), (T, 1) + sea.shape)
    return np.concatenate([xn, static, doy, mask], axis=1).astype(np.float16)


def sea_mask() -> np.ndarray:
    """Cells with water at the surface in GLORYS (the model's domain)."""
    with xr.open_dataset(config.CUBE / "static.nc") as s:
        return (s["sea_share"].values >= config.OCEAN_FRACTION_MIN)


def normalise_target(y: np.ndarray, stats: Stats) -> np.ndarray:
    return ((y - stats.y_mean[None, :, None, None]) / stats.y_std[None, :, None, None]
            ).astype(np.float16)


def denormalise_target(yn: np.ndarray, stats: Stats) -> np.ndarray:
    return yn * stats.y_std[None, :, None, None] + stats.y_mean[None, :, None, None]


def n_channels(inputs: list[str], lags: list[int] = (0,)) -> int:
    return len(inputs) * len(lags) + 3 + 2 + 1
