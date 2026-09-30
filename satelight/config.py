"""Every number that fixes the shape of the system lives here and nowhere else.

Most of these are consequences of measurements recorded in docs/05-data-sources.md, not
preferences. Read docs/03-limitations.md before changing any of them.
"""

from datetime import date
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
CACHE = DATA / "cache"
CUBE = DATA / "cube"
RUNS = ROOT / "runs"
OUTPUT = DATA / "output"

# ---------------------------------------------------------------- the common grid (L4)

# The DUACS 0.25 deg lattice: cell centres at x.125, edges on the quarter degree.
LON_EDGES = (45.0, 105.0)
LAT_EDGES = (5.0, 30.0)
RES = 0.25
LON = np.round(np.arange(LON_EDGES[0] + RES / 2, LON_EDGES[1], RES), 3)   # 240
LAT = np.round(np.arange(LAT_EDGES[0] + RES / 2, LAT_EDGES[1], RES), 3)   # 100
NLON, NLAT = LON.size, LAT.size

# ---------------------------------------------------------------- depth (L5)

DEPTHS = np.array([0, 5, 10, 20, 30, 50, 75, 100, 125, 150, 200, 300, 500, 700, 1000],
                  dtype=np.float32)

# GLORYS12 native levels, read from the store on 2026-09-27 (docs/05-data-sources.md 1).
# Only the levels that bracket a target depth are fetched.
GLORYS_LEVELS = np.array([
    0.494, 1.541, 2.646, 3.819, 5.078, 6.441, 7.93, 9.573, 11.405, 13.467, 15.81, 18.496,
    21.599, 25.211, 29.445, 34.434, 40.344, 47.374, 55.764, 65.807, 77.854, 92.326,
    109.729, 130.666, 155.851, 186.126, 222.475, 266.04, 318.127, 380.213, 453.938,
    541.089, 643.567, 763.333, 902.339, 1062.44])

ZERO_METRE_RULE = ("0 m is GLORYS's top level (0.494 m), taken as the surface. The SST "
                   "input is never copied into the output.")
VERTICAL_METHOD = "linear in depth between the two GLORYS levels bracketing each target"


def bracket(depth: float) -> tuple[int, int, float]:
    """(upper level index, lower level index, weight on the lower) for one target depth.
    0 m is the top level alone, by ZERO_METRE_RULE."""
    z = GLORYS_LEVELS
    if depth <= z[0]:
        return 0, 0, 0.0
    hit = np.flatnonzero(np.isclose(z, depth, atol=1e-3))
    if hit.size:
        return int(hit[0]), int(hit[0]), 0.0
    lo = int(np.searchsorted(z, depth))
    return lo - 1, lo, float((depth - z[lo - 1]) / (z[lo] - z[lo - 1]))


BRACKETS = [bracket(d) for d in DEPTHS]
NEEDED_LEVELS = sorted({i for a, b, _ in BRACKETS for i in (a, b)})

# A 0.25 deg cell is water at a native level when at least this share of its area is
# water in GLORYS at that level. A target depth is valid only where both bracketing
# levels are, so nothing is ever extrapolated below the sea floor (hard rule 4).
OCEAN_FRACTION_MIN = 0.5

# ---------------------------------------------------------------- time (L2, L3)

# The satellite-salinity window. Starts on the first day of GLORYS's geoChunked time
# block 3 (measured), so the fetch does not pay for 5.7 earlier years to get one month;
# ends on the last day of the reprocessed SSS record, so no reprocessed/NRT join is
# needed (D-06).
WINDOW = (date(2010, 2, 4), date(2024, 12, 15))

# The extended comparison (docs/11-deferred.md D-07): the same model trained from 1993,
# the first year every source covers. Salinity before about 2010 is not from SMOS or
# SMAP, so any run that uses these years is labelled as the extended-window comparison,
# never as the model. Validation and test blocks are unchanged.
EXTENDED_START = date(1993, 1, 1)

# Contiguous blocks, a month or more apart. The test block is never touched in training
# or model selection (hard rule 6).
SPLITS = {
    "train": (date(2010, 2, 4), date(2020, 12, 31)),
    "val": (date(2021, 2, 1), date(2022, 11, 30)),
    "test": (date(2023, 1, 1), date(2024, 12, 15)),
}

# ---------------------------------------------------------------- basins

# Rectangles inside the box, on the common grid. Land is masked separately.
BASINS = {
    "Bay of Bengal": {"lon": (78.0, 100.0), "lat": (5.0, 23.0)},
    "Arabian Sea": {"lon": (50.0, 77.0), "lat": (5.0, 26.0)},
}

# ---------------------------------------------------------------- cyclone cases (N3)

# Two cyclones inside the test block. Dates from IMD RSMC New Delhi: depression formed,
# and landfall. "Before" is 3 days before the depression, "after" 3 days after landfall.
# The boxes are ours, drawn to enclose the track the IMD bulletins describe
# (10-unsourced.md).
CYCLONES = {
    "Mocha": {"basin": "Bay of Bengal", "depression": date(2023, 5, 9),
              "landfall": date(2023, 5, 14), "lon": (87.0, 94.0), "lat": (10.0, 19.0),
              "source": "IMD RSMC New Delhi, ESCS Mocha bulletins, 9-14 May 2023"},
    "Biparjoy": {"basin": "Arabian Sea", "depression": date(2023, 6, 6),
                 "landfall": date(2023, 6, 15), "lon": (63.0, 70.0), "lat": (12.0, 22.0),
                 "source": "IMD RSMC New Delhi, ESCS Biparjoy report, 6-19 June 2023"},
}
CYCLONE_MARGIN_DAYS = 3

# Tropical cyclone heat potential (Leipper and Volgenau 1972): heat above 26 degC.
# cp0 is the TEOS-10 constant; the reference density is our stated choice (10-unsourced.md).
TCHP_T = 26.0
CP0 = 3991.86795711963      # J kg-1 K-1, TEOS-10
RHO_REF = 1025.0            # kg m-3

# ---------------------------------------------------------------- inputs (L9)

# Channel order of the model input. Satellite surface observations only.
INPUTS = ["sst", "sss", "adt", "sla", "uc", "vc", "uw", "vw"]
STATIC = ["lat", "lon", "bathy", "doy_sin", "doy_cos"]

# Argo QC flags we accept: good, probably good, changed, interpolated. Everything else
# is kept and counted as rejected, never dropped (hard rule 2).
QC_ACCEPT = frozenset("1258")

HTTP_TIMEOUT = 120


def days(start: date, end: date) -> np.ndarray:
    return np.arange(np.datetime64(start), np.datetime64(end, "D") + np.timedelta64(1, "D"), dtype="datetime64[D]")


def demo() -> None:
    assert (NLON, NLAT) == (240, 100)
    assert LON[0] == 45.125 and LAT[-1] == 29.875
    assert BRACKETS[0] == (0, 0, 0.0), "0 m is the top level alone"
    for d, (a, b, w) in zip(DEPTHS[1:], BRACKETS[1:]):
        assert GLORYS_LEVELS[a] <= d <= GLORYS_LEVELS[b] and 0 <= w <= 1, d
    assert len(NEEDED_LEVELS) == 27, len(NEEDED_LEVELS)
    tr, va, te = SPLITS["train"], SPLITS["val"], SPLITS["test"]
    assert (va[0] - tr[1]).days >= 30 and (te[0] - va[1]).days >= 30, "blocks a month apart"
    assert tr[0] == WINDOW[0] and te[1] == WINDOW[1]
    print("config ok: 240x100 grid, 15 depths from 27 native levels, split gaps >= 30 d")


if __name__ == "__main__":
    demo()
