"""Ingest: every source, onto the common grid, one NetCDF per source per year.

    data/cube/<source>/<year>.nc      float32 on the 240 x 100 common grid

Each file carries a `provenance` attribute (JSON): the dataset, the store or granules it
was read from, the regrid stencil, every unit or CF normalisation that had to be assumed
(hard rule 5), and the days that were missing. Existing files are skipped, so a run that
dies is resumed by running it again. Copernicus reads also go through arco.py's chunk
cache, so a half-finished year does not re-download what it already had.

    python -m oceanembed.fetch glorys 2015        # one source, one year
    python -m oceanembed.fetch all                # every source, every year of the window
    python -m oceanembed.fetch static
"""

from __future__ import annotations

import io
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path

import numpy as np
import xarray as xr

from . import cf, config, grid

COPERNICUS = {
    # name: (dataset id, {our variable: store variable}, stencil)
    "sst": ("METOFFICE-GLO-SST-L4-REP-OBS-SST", {"sst": "analysed_sst"}, grid.BLOCK5),
    "sss": ("cmems_obs-mob_glo_phy-sss_my_multi_P1D", {"sss": "sos"}, grid.BLOCK2),
    "ssh": ("c3s_obs-sl_glo_phy-ssh_my_twosat-l4-duacs-0.25deg_P1D",
            {"adt": "adt", "sla": "sla"}, grid.PASS),
    # Mixed-layer depth: the label for the embedding probe (embed.py) only. Never an
    # input and never a target (L9).
    "mld": ("cmems_mod_glo_phy_my_0.083deg_P1D-m", {"mld": "mlotst"}, grid.GLORYS),
}
GLORYS_ID = "cmems_mod_glo_phy_my_0.083deg_P1D-m"
STATIC_ID = "cmems_mod_glo_phy_my_0.083deg_static"
OSCAR = "OSCAR_L4_OC_FINAL_V2.0"
CCMP = "CCMP_WINDS_10M6HR_L4_V3.1"
SOURCES = ["ssh", "sss", "sst", "oscar", "ccmp", "glorys"]


def cube_path(source: str, year: int) -> Path:
    return config.CUBE / source / f"{year}.nc"


def year_days(year: int) -> np.ndarray:
    lo = max(date(year, 1, 1), config.WINDOW[0])
    hi = min(date(year, 12, 31), config.WINDOW[1])
    return config.days(lo, hi)


def _write(source: str, year: int, t: np.ndarray, data: dict, provenance: dict,
           depth: bool = False) -> None:
    dims = ("time", "depth", "lat", "lon") if depth else ("time", "lat", "lon")
    coords = {"time": t.astype("datetime64[ns]"), "lat": config.LAT, "lon": config.LON}
    if depth:
        coords["depth"] = config.DEPTHS
    ds = xr.Dataset({k: (dims, v.astype(np.float32)) for k, v in data.items()}, coords=coords)
    ds.attrs["provenance"] = json.dumps(provenance)
    path = cube_path(source, year)
    path.parent.mkdir(parents=True, exist_ok=True)
    enc = {k: {"zlib": True, "complevel": 1} for k in data}
    tmp = path.with_suffix(".part.nc")
    ds.to_netcdf(tmp, encoding=enc)
    tmp.replace(path)


# ------------------------------------------------------------------ Copernicus

def _window(ds, st: grid.Stencil, step: float, lat_name="latitude", lon_name="longitude"):
    lat = ds[lat_name].values
    lon = ds[lon_name].values
    assert np.all(np.diff(lat) > 0) and np.all(np.diff(lon) > 0), "ascending axes expected"
    j0 = grid.native_start(lat, config.LAT_EDGES[0], st, step)
    i0 = grid.native_start(lon, config.LON_EDGES[0], st, step)
    return slice(j0, j0 + st.native_count(config.NLAT)), slice(i0, i0 + st.native_count(config.NLON))


def _units(da, name: str, values: np.ndarray, notes: list[str]) -> np.ndarray:
    units = str(da.attrs.get("units", "")).strip()
    if units.lower() in ("k", "kelvin", "kelvins"):
        notes.append(f"{name}: units {units!r}; converted to degree_Celsius by subtracting 273.15")
        return values - 273.15
    if not units:
        notes.append(f"{name}: no units attribute; taken as the product manual's units")
    return values


def _time_index(ds, t: np.ndarray) -> tuple[np.ndarray, list[str]]:
    """Positions of each wanted day on the store's time axis, -1 where it is missing."""
    have = ds["time"].values.astype("datetime64[D]")
    pos = np.searchsorted(have, t)
    pos = np.clip(pos, 0, have.size - 1)
    ok = have[pos] == t
    missing = [str(d) for d in t[~ok]]
    return np.where(ok, pos, -1), missing


def _read_days(da, pos: np.ndarray, sel: dict) -> np.ndarray:
    """Contiguous runs of present days, read one run at a time (a run is one zarr read)."""
    out = np.full((pos.size,) + tuple(s.stop - s.start for s in sel.values()), np.nan, np.float32)
    present = np.flatnonzero(pos >= 0)
    if present.size == 0:
        return out
    breaks = np.flatnonzero(np.diff(pos[present]) != 1) + 1
    for run in np.split(present, breaks):
        # A month at a time bounds memory: the store decodes int16 to float64.
        for part in np.array_split(run, max(1, run.size // 31)):
            a = da.isel(time=slice(int(pos[part[0]]), int(pos[part[-1]]) + 1), **sel).values
            out[part] = a.astype(np.float32)
    return out


def _fetch_copernicus(source: str, year: int) -> None:
    from . import arco

    dataset_id, variables, st = COPERNICUS[source]
    store = arco.open_store(dataset_id, service="arco-time-series")
    ds = store.ds
    step = float(np.diff(ds["latitude"].values[:2])[0])
    ys, xs = _window(ds, st, step)
    t = year_days(year)
    pos, missing = _time_index(ds, t)
    data, notes, cf_reports = {}, [], {}
    for ours, theirs in variables.items():
        da = ds[theirs]
        if "elevation" in da.dims or "depth" in da.dims:
            da = da.isel({d: 0 for d in ("elevation", "depth") if d in da.dims})
        a = _units(da, ours, _read_days(da, pos, {"latitude": ys, "longitude": xs}), notes)
        data[ours], _ = grid.regrid(a, st)
        cf_reports[ours] = cf.normalise_variable(da, ours).as_dict()
    _write(source, year, t, data, {
        "source": source, "dataset_id": dataset_id, "store": store.url,
        "variables": variables, "regrid": st.method, "normalisations": notes,
        "cf": cf_reports, "missing_days": missing, "fetched": str(date.today()),
    })


GLORYS_BLOCK = 2081   # days per time chunk of the GLORYS time-series store (measured)
GLORYS_TMP = config.CACHE / "glorys025"


def _glorys_block(k: int) -> None:
    """Every needed level of one GLORYS time chunk, regridded, as .npy on disk.

    Measured 2026-09-27: reading a year at a time decompressed each 2081-day chunk once
    per month and pinned one core. Here each level's chunks are read once, packed int16,
    for the whole block, then decoded and regridded 100 days at a time."""
    from . import arco

    store = arco.open_store(GLORYS_ID, service="arco-time-series", raw=True)
    ds = store.ds
    ys, xs = _window(ds, grid.GLORYS, 1 / 12)
    t = ds["time"].values.astype("datetime64[D]")[k * GLORYS_BLOCK:(k + 1) * GLORYS_BLOCK]
    keep = (t >= np.datetime64(config.WINDOW[0])) & (t <= np.datetime64(config.WINDOW[1]))
    i0, i1 = k * GLORYS_BLOCK + int(np.argmax(keep)), k * GLORYS_BLOCK + int(keep.sum()) + int(np.argmax(keep))
    GLORYS_TMP.mkdir(parents=True, exist_ok=True)
    np.save(GLORYS_TMP / f"b{k}_days.npy", t[keep])
    # The time-series store orders its vertical axis as elevation, deepest first
    # (measured 2026-09-27); each wanted level is found by value, never by position.
    elev = ds["elevation"].values
    da = ds["thetao"]
    scale = float(da.attrs.get("scale_factor", 1.0))
    offset = float(da.attrs.get("add_offset", 0.0))
    fill = da.attrs.get("_FillValue", da.encoding.get("_FillValue"))
    assert fill is not None and da.dtype == np.int16, "packed int16 with a fill value expected"
    for lev in config.NEEDED_LEVELS:
        out = GLORYS_TMP / f"b{k}_{lev:02d}.npy"
        if out.exists():
            continue
        e = int(np.argmin(np.abs(elev + config.GLORYS_LEVELS[lev])))
        assert abs(-elev[e] - config.GLORYS_LEVELS[lev]) < 0.01, (elev[e], config.GLORYS_LEVELS[lev])
        packed = da.isel(elevation=e, time=slice(i0, i1), latitude=ys, longitude=xs).values
        mean = np.empty((packed.shape[0], config.NLAT, config.NLON), np.float32)
        for s0 in range(0, packed.shape[0], 100):
            p = packed[s0:s0 + 100]
            v = p.astype(np.float32) * scale + offset
            v[p == fill] = np.nan
            m, share = grid.regrid(v, grid.GLORYS)
            m[share < config.OCEAN_FRACTION_MIN] = np.nan
            mean[s0:s0 + 100] = m
        tmp = out.with_suffix(".part.npy")
        np.save(tmp, mean)
        tmp.replace(out)
        print(f"  glorys block {k} level {config.GLORYS_LEVELS[lev]:7.2f} m", flush=True)


def _fetch_glorys(year: int) -> None:
    """Temperature at the 15 target depths, from the 27 GLORYS levels that bracket them."""
    from . import arco

    t = year_days(year)
    have = arco.open_store(GLORYS_ID, service="arco-time-series", raw=True
                           ).ds["time"].values.astype("datetime64[D]")
    blocks = sorted({int(np.searchsorted(have, d) // GLORYS_BLOCK) for d in (t[0], t[-1])})
    for k in range(blocks[0], blocks[-1] + 1):
        _glorys_block(k)
    days = {k: np.load(GLORYS_TMP / f"b{k}_days.npy") for k in range(blocks[0], blocks[-1] + 1)}
    levels = {}
    for lev in config.NEEDED_LEVELS:
        parts, got = [], []
        for k, dk in days.items():
            sel = (dk >= t[0]) & (dk <= t[-1])
            parts.append(np.load(GLORYS_TMP / f"b{k}_{lev:02d}.npy", mmap_mode="r")[sel])
            got.append(dk[sel])
        levels[lev] = np.concatenate(parts)
        got = np.concatenate(got)
    missing = [str(d) for d in np.setdiff1d(t, got)]
    assert not missing, f"GLORYS days missing in {year}: {missing[:5]}"
    out = np.full((t.size, config.DEPTHS.size, config.NLAT, config.NLON), np.nan, np.float32)
    for n, (a, b, w) in enumerate(config.BRACKETS):
        # NaN in either bracketing level stays NaN: never extrapolated (hard rule 4).
        out[:, n] = (1 - w) * levels[a] + w * levels[b]
    store = arco.open_store(GLORYS_ID, service="arco-time-series", raw=True)
    _write("glorys", year, t, {"thetao": out}, {
        "source": "glorys", "dataset_id": GLORYS_ID, "store": store.url,
        "variable": "thetao (sea_water_potential_temperature, degrees_C)",
        "regrid": grid.GLORYS.method,
        "ocean_fraction_min": config.OCEAN_FRACTION_MIN,
        "native_levels_used": [float(config.GLORYS_LEVELS[k]) for k in config.NEEDED_LEVELS],
        "zero_metre_rule": config.ZERO_METRE_RULE, "vertical": config.VERTICAL_METHOD,
        "mask": "a target depth is NaN wherever either bracketing level has less than "
                "ocean_fraction_min water: cells shallower than a level are masked",
        "missing_days": missing, "fetched": str(date.today()),
    }, depth=True)


def _fetch_static() -> None:
    """Sea-floor depth on the common grid (a static input, and the shelf mask's source)."""
    from . import arco

    store = arco.open_store(STATIC_ID, service="static-arco", part="bathy")
    ds = store.ds
    ys, xs = _window(ds, grid.GLORYS, 1 / 12)
    d = ds["deptho"].isel(latitude=ys, longitude=xs).values.astype(np.float64)
    mean, share = grid.regrid(d, grid.GLORYS)
    path = config.CUBE / "static.nc"
    path.parent.mkdir(parents=True, exist_ok=True)
    xr.Dataset({"deptho": (("lat", "lon"), mean), "sea_share": (("lat", "lon"), share)},
               coords={"lat": config.LAT, "lon": config.LON},
               attrs={"provenance": json.dumps({"dataset_id": STATIC_ID, "store": store.url,
                                                "regrid": grid.GLORYS.method})}
               ).to_netcdf(path)


# ------------------------------------------------------------------ NASA PO.DAAC

def _earthdata():
    import truststore
    truststore.inject_into_ssl()
    import earthaccess
    auth = earthaccess.login(strategy="netrc")
    assert auth.authenticated, "Earthdata login failed: check ~/.netrc"
    return earthaccess


def _granules(ea, short_name: str, year: int) -> dict:
    t = year_days(year)
    found = ea.search_data(short_name=short_name, temporal=(str(t[0]), str(t[-1])))
    out = {}
    for g in found:
        day = np.datetime64(g["umm"]["TemporalExtent"]["RangeDateTime"]["BeginningDateTime"][:10])
        out[day] = g
    return out


# Server-side subsets through PO.DAAC's OPeNDAP (DAP4). Measured 2026-09-27: the box
# alone is 0.2 MB (OSCAR, 3.6 s) and 0.75 MB (CCMP, 6.2 s) a day, against 33 MB for a
# whole global file and ~20-50 s for HTTP range reads of it on this link. The index
# ranges below are checked against the coordinates the server sends back, every file.
OPENDAP = "https://opendap.earthdata.nasa.gov/collections/{collection}/granules/{granule}.dap.nc4"
SUBSET = {
    # OSCAR: centres on the quarter degree, stored (time, longitude, latitude). The half
    # shift needs the 241 x 101 centres from 45.0 E / 5.0 N to 105.0 E / 30.0 N.
    "oscar": "/u[0:1:0][180:1:420][379:1:479];/v[0:1:0][180:1:420][379:1:479];"
             "/lon[180:1:420];/lat[379:1:479]",
    # CCMP: centres at x.125, the common lattice itself, stored (time, latitude, longitude).
    "ccmp": "/uwnd[0:1:3][380:1:479][180:1:419];/vwnd[0:1:3][380:1:479][180:1:419];"
            "/longitude[180:1:419];/latitude[380:1:479]",
}


def _read_oscar(ds) -> tuple[np.ndarray, np.ndarray]:
    lon, lat = ds["lon"].values, ds["lat"].values
    assert np.isclose(lon[0], 45.0) and np.isclose(lon[-1], 105.0), (lon[0], lon[-1])
    assert np.isclose(lat[0], 5.0) and np.isclose(lat[-1], 30.0), (lat[0], lat[-1])
    # Stored (time, longitude, latitude): transposed to (lat, lon).
    u = ds["u"].values[0].T.astype(np.float64)
    v = ds["v"].values[0].T.astype(np.float64)
    return grid.regrid(u, grid.HALF_SHIFT)[0], grid.regrid(v, grid.HALF_SHIFT)[0]


def _read_ccmp(ds) -> tuple[np.ndarray, np.ndarray]:
    assert np.allclose(ds["longitude"].values, config.LON, atol=1e-3)
    assert np.allclose(ds["latitude"].values, config.LAT, atol=1e-3)
    assert ds["uwnd"].shape[0] == 4, "CCMP day files hold four synoptic times"
    return ds["uwnd"].values.mean(axis=0), ds["vwnd"].values.mean(axis=0)


def _fetch_podaac(source: str, year: int) -> None:
    ea = _earthdata()
    short, reader, names = {
        "oscar": (OSCAR, _read_oscar, ("uc", "vc")),
        "ccmp": (CCMP, _read_ccmp, ("uw", "vw")),
    }[source]
    session = ea.get_requests_https_session()
    t = year_days(year)
    granules = _granules(ea, short, year)
    out = {n: np.full((t.size, config.NLAT, config.NLON), np.nan, np.float32) for n in names}
    missing, sources = [], []

    def one(i: int):
        g = granules.get(t[i])
        if g is None:
            return i, None, None
        url = OPENDAP.format(collection=g["meta"]["collection-concept-id"],
                             granule=g["umm"]["GranuleUR"])
        err = None
        for attempt in range(5):
            try:
                r = session.get(url, params={"dap4.ce": SUBSET[source]}, timeout=300)
                r.raise_for_status()
                with xr.open_dataset(io.BytesIO(r.content), engine="h5netcdf") as ds:
                    return i, reader(ds), g["umm"]["GranuleUR"]
            except Exception as e:  # network: retry, then record the day as missing
                err = e
                time.sleep(5 * (attempt + 1))
        print(f"  {source} {t[i]} failed: {err}", flush=True)
        return i, None, None

    with ThreadPoolExecutor(8) as pool:
        for i, uv, name in pool.map(one, range(t.size)):
            if uv is None:
                missing.append(str(t[i]))
                continue
            out[names[0]][i], out[names[1]][i] = uv
            sources.append(name)
    _write(source, year, t, out, {
        "source": source, "short_name": short,
        "host": "opendap.earthdata.nasa.gov (server-side DAP4 subset of the PO.DAAC granule)",
        "subset": SUBSET[source],
        "regrid": (grid.HALF_SHIFT if source == "oscar" else grid.PASS).method,
        "temporal": ("daily mean of the four 6-hourly analyses (00, 06, 12, 18 UTC)"
                     if source == "ccmp" else "native daily"),
        "granules": len(sources), "first_granule": min(sources, default=None),
        "last_granule": max(sources, default=None),
        "missing_days": missing, "fetched": str(date.today()),
    })


# ------------------------------------------------------------------ driver

def fetch(source: str, year: int) -> None:
    if cube_path(source, year).exists():
        return
    t0 = time.time()
    # A campus link drops connections now and then (seen 2026-09-27 on the Earthdata
    # login). A source-year is retried whole; the Copernicus chunk cache keeps what it had.
    for attempt in range(6):
        try:
            if source == "glorys":
                _fetch_glorys(year)
            elif source in COPERNICUS:
                _fetch_copernicus(source, year)
            else:
                _fetch_podaac(source, year)
            break
        except (OSError, RuntimeError, ConnectionError) as e:
            if attempt == 5:
                raise
            print(f"{source} {year}: {type(e).__name__}: {e}; retry {attempt + 1} in "
                  f"{60 * (attempt + 1)} s", flush=True)
            time.sleep(60 * (attempt + 1))
    print(f"{source} {year} done in {time.time() - t0:.0f} s", flush=True)


def years() -> list[int]:
    return list(range(config.WINDOW[0].year, config.WINDOW[1].year + 1))


if __name__ == "__main__":
    args = sys.argv[1:]
    if args[:1] == ["static"]:
        _fetch_static()
        print("static done")
        sys.exit()
    wanted = SOURCES if args[:1] == ["all"] else [args[0]]
    ys = [int(a) for a in args[1:]] or years()
    for s in wanted:
        for y in ys:
            fetch(s, y)
