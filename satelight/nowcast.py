"""This morning's ocean: the reconstruction run on the latest days the satellites allow.

GLORYS arrives months after the fact; the satellite inputs arrive within days. The model
needs only the inputs, so it can reconstruct the water column long before any
reanalysis of those days exists. This module measures how late each input is, fetches the
near-real-time versions into their own cube (config.CUBE_NRT, never trained on), and runs
two tiers:

  * **fast**: `unet-no-currents-winds` (SST, SSS, ADT, SLA), scored in the harness as an
    ablation; limited by salinity, days behind.
  * **full**: the headline, all eight inputs; limited by the winds (CCMP), weeks behind.

Near-real-time products are not the reprocessed ones the model was trained on: different
missions (DUACS all-satellite at 0.125° against the two-satellite climate series at
0.25°), a different processing stage (OSCAR interim, salinity NRT). `join()` measures each
difference over a period both cover, and the harness scores the nowcast against real-time
Argo casts, which GLORYS has not yet assimilated because it does not reach those days.

    python -m satelight.nowcast latency     # how late each input is, today
    python -m satelight.nowcast fetch       # near-real-time inputs, GLORYS's end -> today
    python -m satelight.nowcast predict     # both tiers -> data/output/nowcast/<tier>/
    python -m satelight.nowcast join        # reprocessed vs near-real-time, 2024 overlap
    python -m satelight.nowcast             # self-check, no network
"""

from __future__ import annotations

import json
import sys
from datetime import date, timedelta

import numpy as np

from . import config, grid

# Same field, near-real-time dataset: (dataset id, {ours: theirs}, stencil onto the grid).
NRT = {
    "sst": ("METOFFICE-GLO-SST-L4-NRT-OBS-SST-V2", {"sst": "analysed_sst"}, grid.BLOCK5),
    "sss": ("cmems_obs-mob_glo_phy-sss_nrt_multi_P1D", {"sss": "sos"}, grid.BLOCK2),
    # 0.125° centres at x.0625: 2 x 2 blocks nest in the 0.25° cell, like salinity.
    "ssh": ("cmems_obs-sl_glo_phy-ssh_nrt_allsat-l4-duacs-0.125deg_P1D",
            {"adt": "adt", "sla": "sla"}, grid.BLOCK2),
}
PODAAC_NRT = {"oscar": "OSCAR_L4_OC_INTERIM_V2.0", "ccmp": "CCMP_WINDS_10M6HR_L4_V3.1"}
GLORYS_END = date(2026, 6, 23)     # measured 2026-09-30 (docs/05-data-sources.md)
START = GLORYS_END + timedelta(days=1)
JOIN = (date(2024, 7, 1), date(2024, 12, 15))   # all-satellite DUACS NRT 0.125° starts 2024-07-01
TIERS = {"fast": "unet-no-currents-winds", "full": "hybrid"}
OUT = config.OUTPUT / "nowcast"
LATENCY = config.DATA / "nowcast-latency.json"


def latency() -> dict:
    """The last day each input (and GLORYS) holds, and its delay from today."""
    from . import arco
    from .fetch import _earthdata
    today = date.today()
    out = {"measured": str(today), "sources": {}}
    for src, (ds_id, _, _) in NRT.items():
        last = arco.open_store(ds_id, service="arco-geo-series").coverage()[1]
        out["sources"][src] = {"dataset": ds_id, "last_day": last}
    ea = _earthdata()
    for src, short in PODAAC_NRT.items():
        found = ea.search_data(short_name=short, temporal=(str(today - timedelta(days=90)), str(today)))
        days = sorted(g["umm"]["TemporalExtent"]["RangeDateTime"]["BeginningDateTime"][:10] for g in found)
        out["sources"][src] = {"dataset": short, "last_day": days[-1] if days else None}
    g = arco.open_store("cmems_mod_glo_phy_my_0.083deg_P1D-m", service="arco-geo-series").coverage()[1]
    out["sources"]["glorys"] = {"dataset": "cmems_mod_glo_phy_my_0.083deg_P1D-m", "last_day": g}
    for v in out["sources"].values():
        v["days_behind"] = (today - date.fromisoformat(v["last_day"])).days if v["last_day"] else None
    LATENCY.write_text(json.dumps(out, indent=1))
    return out


def fetch_span(a: date, b: date) -> None:
    """Near-real-time inputs for a..b (one calendar year) into config.CUBE_NRT."""
    from .fetch import _fetch_copernicus, _fetch_podaac
    assert a.year == b.year, "one year at a time: the cube is one file per source-year"
    t = config.days(a, b)
    for src, spec in NRT.items():
        _fetch_copernicus(src, a.year, t=t, spec=spec, root=config.CUBE_NRT)
        print("nrt", src, a, b, flush=True)
    for src, short in PODAAC_NRT.items():
        _fetch_podaac(src, a.year, t=t, short=short, root=config.CUBE_NRT)
        print("nrt", src, a, b, flush=True)


def predict(tier: str) -> list[str]:
    from .predict import predict_span, write_daily, write_manifest
    from .train import load_model
    run = TIERS[tier]
    _, cfg, _ = load_model(run)
    y, t, _ = predict_span(run, START, date.today(), root=config.CUBE_NRT)
    out = OUT / tier
    extra = {"nowcast": True, "tier": tier,
             "inputs_near_real_time": {**{k: v[0] for k, v in NRT.items()}, **PODAAC_NRT},
             "note": "near-real-time inputs, not the reprocessed ones trained on; see join()"}
    write_daily(run, y, t, cfg, out_dir=out, extra=extra)
    write_manifest(run, START, date.today(), t, out_dir=out)
    days = [str(d) for d in t.astype("datetime64[D]")]
    print(f"nowcast {tier} ({run}): {len(days)} days, {days[0]} -> {days[-1]}")
    return days


def join() -> dict:
    """Reprocessed minus near-real-time, per input, over JOIN in the box: mean and RMS of
    the difference and their correlation. Written into data/nowcast-join.json."""
    from .data import _read
    a, b = JOIN
    if not all((config.CUBE_NRT / s / f"{a.year}.nc").exists() for s in (*NRT, *PODAAC_NRT)):
        fetch_span(a, b)
    out = {"span": [str(a), str(b)], "variables": {}}
    for var, src in (("sst", "sst"), ("sss", "sss"), ("adt", "ssh"), ("sla", "ssh"),
                     ("uc", "oscar"), ("vc", "oscar"), ("uw", "ccmp"), ("vw", "ccmp")):
        rep, tr = _read(src, var, a, b)
        nrt, tn = _read(src, var, a, b, root=config.CUBE_NRT)
        common, ir, inn = np.intersect1d(tr, tn, return_indices=True)
        d = rep[ir] - nrt[inn]
        ok = np.isfinite(d)
        if not ok.any():
            out["variables"][var] = {"days": 0}
            continue
        r = np.corrcoef(rep[ir][ok], nrt[inn][ok])[0, 1]
        out["variables"][var] = {"days": int(common.size), "mean_diff": float(d[ok].mean()),
                                 "rms_diff": float(np.sqrt((d[ok] ** 2).mean())),
                                 "std_rep": float(rep[ir][ok].std()), "r": float(r)}
    (config.DATA / "nowcast-join.json").write_text(json.dumps(out, indent=1))
    return out


def demo() -> None:
    assert START == date(2026, 6, 24)
    for ds_id, variables, st in NRT.values():
        assert st in (grid.BLOCK5, grid.BLOCK2) and variables
    assert set(TIERS) == {"fast", "full"}
    print("nowcast ok: tiers and near-real-time catalogue")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "latency":
        print(json.dumps(latency(), indent=1))
    elif cmd == "fetch":
        fetch_span(START, date.today())
    elif cmd == "predict":
        for tier in TIERS:
            predict(tier)
    elif cmd == "join":
        print(json.dumps(join(), indent=1))
    else:
        demo()
