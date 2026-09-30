"""S3: the stored cube equals the source, regridded by hand, on one real day.

Independent of the ingest path on purpose: Copernicus stores are opened decoded (not raw),
cells are picked by coordinate value (not index), and the PO.DAAC files are whole global
granules (not the OPeNDAP subset). Each regrid is written out here as plain numpy.

Live (network): python -m pytest tests/test_sources.py --live"""

import warnings

import numpy as np
import pytest
import xarray as xr

from satelight import arco, config, fetch

DAY = np.datetime64("2015-06-15")
BOX = dict(latitude=slice(5.0, 30.0), longitude=slice(45.0, 105.0))


def cube(source: str, var: str) -> np.ndarray:
    with xr.open_dataset(fetch.cube_path(source, DAY.astype(object).year)) as ds:
        return ds[var].sel(time=DAY).values


def nanmean(a: np.ndarray, axis) -> np.ndarray:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)   # all-land blocks stay NaN
        return np.nanmean(a, axis=axis)


def block_nanmean(a: np.ndarray, k: int) -> np.ndarray:
    return nanmean(a.reshape(a.shape[0] // k, k, a.shape[1] // k, k), axis=(1, 3))


def same(ours: np.ndarray, want: np.ndarray, atol: float) -> None:
    assert ours.shape == want.shape == (config.NLAT, config.NLON), (ours.shape, want.shape)
    assert np.array_equal(np.isnan(ours), np.isnan(want)), "the land/sea mask differs"
    assert np.nanmax(np.abs(ours - want)) < atol, np.nanmax(np.abs(ours - want))


@pytest.fixture
def live(request):
    if not request.config.getoption("--live"):
        pytest.skip("needs the network: run with --live")


@pytest.mark.parametrize("source,var,theirs,k,offset", [
    ("sst", "sst", "analysed_sst", 5, 273.15),     # S3a: 0.05 deg, 5 x 5 block mean, K -> C
    ("sss", "sss", "sos", 2, 0.0),                 # S3b: 0.125 deg, 2 x 2 block mean
    ("ssh", "sla", "sla", 1, 0.0),                 # S3c: pass-through
    ("ssh", "adt", "adt", 1, 0.0),
])
def test_copernicus(live, source, var, theirs, k, offset):
    dataset_id = fetch.COPERNICUS[source][0]
    ds = arco.open_store(dataset_id, service="arco-geo-series").ds
    da = ds[theirs].sel(time=DAY, **BOX)
    da = da.isel({d: 0 for d in ("elevation", "depth") if d in da.dims})
    a = da.values.astype(np.float64) - offset
    assert a.shape == (config.NLAT * k, config.NLON * k), a.shape
    same(cube(source, var), block_nanmean(a, k), atol=1e-6 if k == 1 else 1e-4)


def _granule(short_name: str, tmp_path) -> xr.Dataset:
    ea = fetch._earthdata()
    g = ea.search_data(short_name=short_name, temporal=(str(DAY), str(DAY)))
    g = [x for x in g if x["umm"]["TemporalExtent"]["RangeDateTime"]["BeginningDateTime"][:10] == str(DAY)]
    assert len(g) == 1, len(g)
    path = ea.download(g, str(tmp_path))[0]
    return xr.open_dataset(path)


def test_oscar(live, tmp_path):
    """S3d: OSCAR centres sit on the quarter degree, half a cell off the lattice; each
    common cell is the mean of the four surrounding OSCAR cells."""
    with _granule(fetch.OSCAR, tmp_path) as ds:
        for var, ours in (("u", "uc"), ("v", "vc")):
            lon, lat = ds["lon"].values, ds["lat"].values
            a = ds[var].isel(time=0, longitude=(lon >= 45.0) & (lon <= 105.0),
                             latitude=(lat >= 5.0) & (lat <= 30.0))
            a = a.transpose("latitude", "longitude").values.astype(np.float64)
            assert a.shape == (config.NLAT + 1, config.NLON + 1), a.shape
            four = np.stack([a[:-1, :-1], a[1:, :-1], a[:-1, 1:], a[1:, 1:]])
            same(cube("oscar", ours), nanmean(four, axis=0), atol=1e-5)


def test_ccmp(live, tmp_path):
    """S3e: the daily wind is the mean of the four 6-hourly analyses."""
    with _granule(fetch.CCMP, tmp_path) as ds:
        assert ds.sizes["time"] == 4
        for var, ours in (("uwnd", "uw"), ("vwnd", "vw")):
            a = ds[var].sel(**BOX).values.astype(np.float64)
            same(cube("ccmp", ours), a.mean(axis=0), atol=1e-5)
