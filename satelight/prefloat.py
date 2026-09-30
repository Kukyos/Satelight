"""Before the floats: the water column in 1993–2009, when Argo had barely begun.

Satellites have watched the sea surface every day since 1993; Argo reached this ocean in
numbers only in the mid-2000s. A model that needs only the surface can reconstruct the
years the floats missed. This runs the headline over the extended cube (D-07) and counts
the floats per year, so the gap it fills is measured, not asserted.

**Labelled a comparison, not the product.** Before about 2010 the salinity input is not
from a salinity satellite (SMOS launched in 2009; 03-limitations.md L9), and the model was
trained on 2010–2020, so these years are outside its training era in both directions.
The harness scores 2005–2009 against delayed-mode Argo, beside climatology and GLORYS.

    python -m satelight.prefloat predict    # 1993–2009 -> data/output/prefloat/ (per year)
    python -m satelight.prefloat floats     # Argo profiles per year in the box (GDAC index)
    python -m satelight.prefloat            # self-check, no data
"""

from __future__ import annotations

import gzip
import json
import sys
from collections import Counter
from datetime import date

import numpy as np

from . import config

RUN = "hybrid"
YEARS = range(1993, 2010)
OUT = config.OUTPUT / "prefloat"
INDEX_URL = "https://data-argo.ifremer.fr/ar_index_global_prof.txt.gz"
INDEX = config.CACHE / "argo_index" / "ar_index_global_prof.txt.gz"
FLOATS = config.DATA / "prefloat-floats.json"
SCORED = (date(2005, 1, 1), date(2009, 12, 31))


def predict() -> None:
    from .predict import predict_span, write_daily
    from .train import load_model
    _, cfg, _ = load_model(RUN)
    extra = {"era": "before the floats (comparison)",
             "note": "salinity before ~2010 is not satellite salinity; trained on 2010-2020"}
    for y in YEARS:
        if len(list(OUT.glob(f"Satelight_thetao_{y}*.nc"))) >= 365:
            continue
        v, t, _ = predict_span(RUN, date(y, 1, 1), date(y, 12, 31))
        write_daily(RUN, v, t, cfg, out_dir=OUT, extra=extra)
        print(f"prefloat {y}: {len(t)} days", flush=True)


def count_rows(lines, box=(config.LON_EDGES, config.LAT_EDGES)) -> Counter:
    """Profiles per year inside the box, from GDAC index lines
    (file,date,latitude,longitude,ocean,profiler_type,institution,date_update)."""
    (lo0, lo1), (la0, la1) = box
    n = Counter()
    for line in lines:
        if line.startswith("#") or line.startswith("file,"):
            continue
        f = line.split(",")
        if len(f) < 4 or not f[1] or not f[2] or not f[3]:
            continue
        try:
            lat, lon = float(f[2]), float(f[3])
        except ValueError:
            continue
        if lo0 <= lon <= lo1 and la0 <= lat <= la1:
            n[int(f[1][:4])] += 1
    return n


def floats() -> dict:
    import requests
    import truststore
    truststore.inject_into_ssl()
    if not INDEX.exists():
        INDEX.parent.mkdir(parents=True, exist_ok=True)
        r = requests.get(INDEX_URL, timeout=600)
        r.raise_for_status()
        INDEX.write_bytes(r.content)
    with gzip.open(INDEX, "rt", encoding="utf-8", errors="replace") as f:
        n = count_rows(f)
    out = {"source": INDEX_URL, "box": {"lon": list(config.LON_EDGES), "lat": list(config.LAT_EDGES)},
           "counted": str(date.today()), "profiles_per_year": {str(k): n[k] for k in sorted(n)}}
    FLOATS.write_text(json.dumps(out, indent=1))
    return out


def demo() -> None:
    lines = ["# header", "file,date,latitude,longitude,ocean,profiler_type,institution,date_update",
             "aoml/1/profiles/R1_001.nc,20050101000000,15.0,88.0,I,846,AO,20200101",
             "aoml/1/profiles/R1_002.nc,20050111000000,15.2,88.1,I,846,AO,20200101",
             "aoml/2/profiles/R2_001.nc,20050111000000,-10.0,88.1,I,846,AO,20200101",
             "aoml/3/profiles/R3_001.nc,,,,I,846,AO,20200101"]
    n = count_rows(lines)
    assert n == Counter({2005: 2}), n
    print("prefloat ok: index rows counted inside the box only")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "predict":
        predict()
    elif cmd == "floats":
        print(json.dumps(floats(), indent=1))
    else:
        demo()
