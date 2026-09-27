"""Every source onto the common grid (docs/03-limitations.md L4), with nothing invented.

One operation covers every case: a separable weighted stencil. Each common-grid cell is
the area-weighted mean of the native cells that overlap it, over the native cells that
have a value. The share of the cell's area that had a value comes back beside the mean.

    source     native centres     stencil per axis         what it is
    OSTIA      x.025, 0.05 deg    [1,1,1,1,1], stride 5    exact block mean
    SSS        x.0625, 0.125 deg  [1,1], stride 2          exact block mean
    DUACS      x.125, 0.25 deg    [1], stride 1            pass-through
    CCMP       x.125, 0.25 deg    [1], stride 1            pass-through
    GLORYS     x.000, 1/12 deg    [1/2,1,1,1/2], stride 3  exact conservative mean: the
                                                           two edge cells straddle the
                                                           0.25 deg cell edge, so half of
                                                           each lies inside
    OSCAR      x.00, 0.25 deg     [1,1], stride 1          half-cell shift: the mean of
                                                           the four surrounding cells,
                                                           i.e. bilinear at the midpoint

Only the OSCAR row is an interpolation rather than an average of what lies inside the
cell, and its provenance says so. Nothing is ever made finer than its source.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from . import config


@dataclass(frozen=True)
class Stencil:
    weights: tuple[float, ...]
    stride: int
    method: str

    def native_count(self, n_out: int) -> int:
        """How many native points along an axis produce n_out common cells."""
        return self.stride * (n_out - 1) + len(self.weights)


BLOCK5 = Stencil((1.0,) * 5, 5, "5 x 5 block mean (exact: native cells nest in the 0.25 deg cell)")
BLOCK2 = Stencil((1.0, 1.0), 2, "2 x 2 block mean (exact: native cells nest in the 0.25 deg cell)")
PASS = Stencil((1.0,), 1, "pass-through (native grid is the common grid)")
GLORYS = Stencil((0.5, 1.0, 1.0, 0.5), 3,
                 "conservative 1/12 -> 0.25 deg mean, weights [1/2,1,1,1/2] per axis at "
                 "stride 3: GLORYS centres sit on multiples of 1/12 deg, so the outer two "
                 "native cells straddle the common cell's edges and count half")
HALF_SHIFT = Stencil((1.0, 1.0), 1,
                     "half-cell shift: OSCAR centres sit on the quarter degree, half a cell "
                     "from the common lattice; each common cell is the mean of the four "
                     "surrounding OSCAR cells (bilinear interpolation at the midpoint)")


def _apply_axis(a: np.ndarray, st: Stencil, n_out: int, axis: int) -> np.ndarray:
    a = np.moveaxis(a, axis, -1)
    out = np.zeros(a.shape[:-1] + (n_out,), dtype=np.float64)
    stop = st.stride * (n_out - 1) + 1
    for i, w in enumerate(st.weights):
        out += w * a[..., i:i + stop:st.stride]
    return np.moveaxis(out, -1, axis)


def regrid(a: np.ndarray, st: Stencil, ny: int = config.NLAT, nx: int = config.NLON
           ) -> tuple[np.ndarray, np.ndarray]:
    """(..., native_lat, native_lon) -> ((..., ny, nx) mean, (..., ny, nx) valid share).

    The native array must start at the common grid's south-west edge (the stencil's first
    point) and hold exactly `st.native_count` points along each axis."""
    assert a.shape[-2:] == (st.native_count(ny), st.native_count(nx)), \
        (a.shape, st.native_count(ny), st.native_count(nx))
    finite = np.isfinite(a)
    num = _apply_axis(_apply_axis(np.where(finite, a, 0.0), st, nx, -1), st, ny, -2)
    den = _apply_axis(_apply_axis(finite.astype(np.float64), st, nx, -1), st, ny, -2)
    total = sum(st.weights) ** 2
    with np.errstate(invalid="ignore", divide="ignore"):
        mean = np.where(den > 0, num / den, np.nan)
    return mean.astype(np.float32), (den / total).astype(np.float32)


def native_start(coords: np.ndarray, edge: float, st: Stencil, step: float) -> int:
    """Index of the stencil's first native point for a grid whose SW edge is `edge`.

    For stencils whose weights all equal 1 and whose native cells nest (block means and
    pass-through), that is the first centre inside the edge. For the GLORYS stencil and
    the half shift, it is the centre on the edge itself."""
    target = edge + (step / 2 if st in (BLOCK5, BLOCK2, PASS) else 0.0)
    i = int(np.argmin(np.abs(coords - target)))
    assert abs(coords[i] - target) < step / 4, (coords[i], target)
    return i


def demo() -> None:
    rng = np.random.default_rng(0)

    # A block mean of a field equals the plain mean of each block.
    a = rng.normal(size=(2, 500, 1200))
    m, f = regrid(a, BLOCK5)
    assert np.allclose(m[1, 3, 7], a[1, 15:20, 35:40].mean(), atol=1e-5)
    assert np.all(f == 1)

    # Land: a block half NaN averages the other half and reports share 0.5.
    b = np.ones((10, 10)) * 2.0
    b[:, :5] = np.nan
    m, f = regrid(b, BLOCK5, 2, 2)
    assert np.isclose(m[0, 1], 2.0) and np.isclose(f[0, 1], 1.0) and np.isnan(m[0, 0])

    # GLORYS: a linear field x -> its value at the cell centre, exactly, because the
    # [1/2,1,1,1/2] stencil is symmetric about it.
    x = np.arange(config.LON_EDGES[0], config.LON_EDGES[1] + 1e-9, 1 / 12)
    y = np.arange(config.LAT_EDGES[0], config.LAT_EDGES[1] + 1e-9, 1 / 12)
    assert (y.size, x.size) == (GLORYS.native_count(100), GLORYS.native_count(240)) == (301, 721)
    field = np.add.outer(0 * y, x)
    m, f = regrid(field, GLORYS)
    assert np.allclose(m[0], config.LON, atol=1e-4), "GLORYS stencil is centred on x.125"
    assert np.allclose(f, 1)

    # OSCAR: centres on the quarter degree, 241 x 101 points -> centred on x.125 too.
    xo = np.arange(45.0, 105.0 + 1e-9, 0.25)
    yo = np.arange(5.0, 30.0 + 1e-9, 0.25)
    m, _ = regrid(np.add.outer(yo, 0 * xo), HALF_SHIFT)
    assert np.allclose(m[:, 0], config.LAT, atol=1e-4)
    print("grid ok: block means exact, GLORYS and OSCAR stencils centred on the lattice")


if __name__ == "__main__":
    demo()
