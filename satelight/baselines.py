"""The bars a model has to clear, fitted on the train block only.

climatology   GLORYS day-of-year mean over the train block, smoothed with a +/-15-day
              circular window. The floor: it knows the season and the place, nothing
              about today.
linear        one ridge regression per cell, from that cell's eight satellite channels
              and the day of year to its 15 depths. Knows today, but only through a
              straight line at one point.

    python -m satelight.baselines          # fit both, write runs/climatology, runs/linear
"""

from __future__ import annotations

from datetime import date

import numpy as np
import torch

from . import config, data

SMOOTH_DAYS = 15
RIDGE = 1e-2


def _doy(t: np.ndarray) -> np.ndarray:
    """0..365, with 29 February folded onto 28 February so every year has 365 slots."""
    doy = (t - t.astype("datetime64[Y]")).astype(int)
    leap = (t.astype("datetime64[Y]").astype(int) + 1970) % 4 == 0
    return np.where(leap & (doy >= 59), doy - 1, doy)


def fit_climatology() -> None:
    a, b = config.SPLITS["train"]
    s = np.zeros((365, 15, config.NLAT, config.NLON), np.float64)
    n = np.zeros_like(s)
    for y in range(a.year, b.year + 1):
        yv, t = data._read("glorys", "thetao", max(a, date(y, 1, 1)), min(b, date(y, 12, 31)))
        d = _doy(t)
        ok = np.isfinite(yv)
        np.add.at(s, d, np.where(ok, yv, 0.0))
        np.add.at(n, d, ok)
    # Circular +/-15-day smoothing over the day-of-year axis.
    k = np.arange(-SMOOTH_DAYS, SMOOTH_DAYS + 1)
    ss = sum(np.roll(s, i, axis=0) for i in k)
    nn = sum(np.roll(n, i, axis=0) for i in k)
    with np.errstate(invalid="ignore", divide="ignore"):
        clim = np.where(nn > 0, ss / nn, np.nan).astype(np.float32)
    out = config.RUNS / "climatology"
    out.mkdir(parents=True, exist_ok=True)
    np.save(out / "clim.npy", clim)
    print("climatology: fitted on", a, "->", b)


def climatology(t: np.ndarray) -> np.ndarray:
    clim = np.load(config.RUNS / "climatology" / "clim.npy", mmap_mode="r")
    return np.asarray(clim[_doy(t)])


def _features(x: np.ndarray, t: np.ndarray, stats: data.Stats) -> np.ndarray:
    """(T, C, H, W) raw -> (T, H*W, C+3): normalised channels, sin/cos day, bias."""
    xn = np.nan_to_num((x - stats.x_mean[None, :, None, None]) / stats.x_std[None, :, None, None])
    T = x.shape[0]
    doy = data.doy_fields(t)
    f = np.concatenate([xn.reshape(T, x.shape[1], -1),
                        np.broadcast_to(doy[:, :, None], (T, 2, xn.shape[2] * xn.shape[3])),
                        np.ones((T, 1, xn.shape[2] * xn.shape[3]), np.float32)], axis=1)
    return f.transpose(0, 2, 1).astype(np.float32)


def fit_linear() -> None:
    """Normal equations per cell, accumulated a year at a time on the CPU and solved on
    the GPU a slice of cells at a time: the whole train block never has to fit in 8 GB."""
    a, b = config.SPLITS["train"]
    pieces = [(max(a, date(y, 1, 1)), min(b, date(y, 12, 31))) for y in range(a.year, b.year + 1)]
    x0, y0, _ = data.load_raw("train", config.INPUTS, span=pieces[0])
    stats = data.compute_stats(x0, y0)  # the first train year: centring only, not a score
    del x0, y0
    xtx = xty = None
    level_ok = None
    n = 0
    for p in pieces:
        x, y, t = data.load_raw("train", config.INPUTS, span=p)
        f = torch.from_numpy(_features(x, t, stats)).cuda()                  # (T, P, F)
        yt = torch.from_numpy(y.reshape(len(y), 15, -1)).cuda().transpose(1, 2)  # (T, P, 15)
        ok = torch.isfinite(yt).all(dim=0)
        level_ok = ok if level_ok is None else level_ok & ok
        yt = torch.nan_to_num(yt)
        part_xtx = torch.einsum("tpf,tpg->pfg", f, f).cpu()
        part_xty = torch.einsum("tpf,tpl->pfl", f, yt).cpu()
        xtx = part_xtx if xtx is None else xtx + part_xtx
        xty = part_xty if xty is None else xty + part_xty
        n += len(t)
        del x, y, f, yt
    nf = xtx.shape[-1]
    coef = torch.linalg.solve(xtx + RIDGE * n * torch.eye(nf), xty)
    out = config.RUNS / "linear"
    out.mkdir(parents=True, exist_ok=True)
    np.save(out / "coef.npy", coef.numpy())
    np.save(out / "level_ok.npy", level_ok.cpu().numpy())
    stats.save(out / "stats.json")
    print("linear: fitted on", n, "train days")


def linear(x: np.ndarray, t: np.ndarray) -> np.ndarray:
    out = config.RUNS / "linear"
    coef = torch.from_numpy(np.load(out / "coef.npy")).cuda()
    level_ok = np.load(out / "level_ok.npy")
    stats = data.Stats.load(out / "stats.json")
    p = np.concatenate([torch.einsum("tpf,pfl->tpl",
                                     torch.from_numpy(_features(x[i:i + 64], t[i:i + 64], stats)).cuda(),
                                     coef).cpu().numpy() for i in range(0, len(t), 64)])
    p[:, ~level_ok] = np.nan
    return p.transpose(0, 2, 1).reshape(len(t), 15, config.NLAT, config.NLON)


def demo() -> None:
    t = np.array(["2011-02-28", "2012-02-29", "2012-03-01", "2011-12-31", "2012-12-31"],
                 dtype="datetime64[D]")
    assert _doy(t).tolist() == [58, 58, 59, 364, 364], _doy(t)
    print("baselines ok: leap days fold onto 365 slots")


if __name__ == "__main__":
    import sys
    if "--demo" in sys.argv:
        demo()
    else:
        fit_climatology()
        fit_linear()
