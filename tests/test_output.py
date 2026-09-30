"""The daily output obeys the standard (S6a, E4, hard rules 3-4).

Runs over whatever data/output/daily holds; skipped when nothing has been predicted."""

import json

import numpy as np
import pytest
import xarray as xr

from satelight import config
from satelight.predict import DAILY_DIR, level_mask

FILES = sorted(DAILY_DIR.glob("Satelight_thetao_*.nc"))


@pytest.mark.skipif(not FILES, reason="no output written yet")
def test_daily_output():
    manifest = json.loads((DAILY_DIR / "manifest.json").read_text())
    days = np.array([np.datetime64(f"{p.stem[-8:-4]}-{p.stem[-4:-2]}-{p.stem[-2:]}") for p in FILES])
    want = np.arange(np.datetime64(manifest["span"][0]),
                     np.datetime64(manifest["span"][1]) + np.timedelta64(1, "D"))
    gaps = set(want.astype(str)) - set(days.astype(str))
    assert gaps == set(manifest["days_skipped"]), "E4: one file per day, every gap recorded"
    assert len(days) == manifest["days_written"]
    mask = level_mask()
    for p in FILES[:: max(1, len(FILES) // 25)] + FILES[-1:]:   # a spread of days
        with xr.open_dataset(p) as ds:
            assert np.array_equal(ds["depth"].values, config.DEPTHS), "S6a: exactly 15 levels"
            assert np.array_equal(ds["lat"].values, config.LAT), "E4: the common grid"
            assert np.array_equal(ds["lon"].values, config.LON), "E4: the common grid"
            v = ds["thetao"].values
            assert np.array_equal(np.isfinite(v), mask), "masked exactly where a level is absent"
            ok = np.isfinite(v)
            assert not np.any(~ok[:-1] & ok[1:]), "hard rule 4: no value below a masked level"
            assert json.loads(ds.attrs["provenance"])["model_run"] == manifest["model_run"]
