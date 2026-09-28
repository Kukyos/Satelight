"""S1: re-running the pipeline reproduces the stored cube bit for bit.

Live (network): python -m pytest tests/test_reproduce.py --live"""

import json

import numpy as np
import pytest
import xarray as xr

from oceanembed import config, fetch


@pytest.mark.parametrize("source,year", [("sss", 2015), ("ssh", 2015)])
def test_refetch_is_identical(source, year, tmp_path, monkeypatch, request):
    if not request.config.getoption("--live"):
        pytest.skip("needs the network: run with --live")
    stored = fetch.cube_path(source, year)
    if not stored.exists():
        pytest.skip(f"{stored} not fetched yet")
    monkeypatch.setattr(config, "CUBE", tmp_path)
    fetch.fetch(source, year)
    with xr.open_dataset(stored) as a, xr.open_dataset(tmp_path / source / f"{year}.nc") as b:
        for v in a.data_vars:
            assert np.array_equal(a[v].values, b[v].values, equal_nan=True), v
        pa, pb = json.loads(a.attrs["provenance"]), json.loads(b.attrs["provenance"])
        pa.pop("fetched"), pb.pop("fetched")
        assert pa == pb, "the provenance is identical apart from the fetch date"
