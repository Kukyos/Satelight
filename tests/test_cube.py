"""The stored training cube obeys the standard (S2a, S2b, S6a, hard rules 3-5).

Runs over whatever data/cube holds; skipped when nothing has been fetched."""

import json

import numpy as np
import pytest
import xarray as xr

from oceanembed import config

FILES = sorted(p for p in config.CUBE.glob("*/*.nc") if ".part" not in p.name)


@pytest.mark.skipif(not FILES, reason="no cube fetched yet")
@pytest.mark.parametrize("path", FILES, ids=lambda p: f"{p.parent.name}/{p.name}")
def test_cube_file(path):
    with xr.open_dataset(path) as ds:
        assert np.array_equal(ds["lat"].values, config.LAT), "S2a: the common latitudes exactly"
        assert np.array_equal(ds["lon"].values, config.LON), "S2a: the common longitudes exactly"
        t = ds["time"].values.astype("datetime64[D]")
        assert np.all(np.diff(t) == np.timedelta64(1, "D")), "S2b: one step per calendar day"
        prov = json.loads(ds.attrs["provenance"])
        assert prov.get("regrid"), "hard rule 5: the regrid method is recorded"
        assert "missing_days" in prov, "missing days are recorded, even when none"
        logged = set(prov["missing_days"]) | set(prov.get("empty_days", []))
        for v in ds.data_vars:
            a = ds[v].values
            empty = np.isnan(a.reshape(a.shape[0], -1)).all(axis=1)
            unlogged = set(t[empty].astype(str)) - logged
            assert not unlogged, f"S2b: {v} has no value on unlogged days {sorted(unlogged)}"
        if path.parent.name == "glorys":
            assert np.array_equal(ds["depth"].values, config.DEPTHS), "S6a: exactly the 15 depths"
            v = ds["thetao"].isel(time=0).values
            deep_nan = np.isnan(v[-1]) & ~np.isnan(v[0])
            assert deep_nan.any(), "hard rule 4: shelf cells are masked at 1000 m"
            # Once a column stops, it never restarts deeper: nothing extrapolated below.
            ok = np.isfinite(v)
            assert not np.any(~ok[:-1] & ok[1:]), "no value below a masked level"
            finite = v[ok]
            assert finite.min() > -2.5 and finite.max() < 40, "Argo global range"
