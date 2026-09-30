"""Cyclone best tracks for the fuel-gauge scenes: IMD's own positions, through IBTrACS.

IBTrACS v04r01 (NOAA NCEI) carries each agency's track side by side; the NEWDELHI_*
columns are IMD RSMC New Delhi's best track, the official one for this basin. Only rows
where IMD gave a position are used (before the depression IMD has none: the storm is not
drawn before IMD tracked it). Display only: nothing here is scored.

    python -m satelight.tracks            # self-check against the cached file, no network
    python -m satelight.tracks --fetch    # download the North Indian file (28 MB)
"""

from __future__ import annotations

import csv
import sys
from functools import lru_cache

from . import config

URL = ("https://www.ncei.noaa.gov/data/international-best-track-archive-for-climate-stewardship-"
       "ibtracs/v04r01/access/csv/ibtracs.NI.list.v04r01.csv")
PATH = config.CACHE / "ibtracs" / "ibtracs.NI.list.v04r01.csv"
# IMD's intensity scale, for the label on each point.
GRADE = {"D": "depression", "DD": "deep depression", "CS": "cyclonic storm",
         "SCS": "severe cyclonic storm", "VSCS": "very severe cyclonic storm",
         "ESCS": "extremely severe cyclonic storm", "SUCS": "super cyclonic storm"}


def fetch() -> None:
    import requests
    import truststore
    truststore.inject_into_ssl()
    PATH.parent.mkdir(parents=True, exist_ok=True)
    r = requests.get(URL, timeout=300)
    r.raise_for_status()
    PATH.write_bytes(r.content)
    print("ibtracs:", PATH, len(r.content), "bytes")


@lru_cache(maxsize=8)
def track(name: str, season: int = 2023) -> list[dict]:
    """[{time, lat, lon, grade, grade_name, wind_kt}] from IMD's columns, in time order."""
    if not PATH.exists():
        raise FileNotFoundError(f"{PATH} missing: python -m satelight.tracks --fetch")
    out = []
    with PATH.open(newline="", encoding="utf-8") as f:
        rows = csv.DictReader(f)
        next(rows)                                   # the units row
        for r in rows:
            if r["NAME"].strip() != name.upper() or r["SEASON"].strip() != str(season):
                continue
            lat, lon = r["NEWDELHI_LAT"].strip(), r["NEWDELHI_LON"].strip()
            if not lat or not lon:
                continue
            g = r["NEWDELHI_GRADE"].strip()
            w = r["NEWDELHI_WIND"].strip()
            out.append({"time": r["ISO_TIME"].strip(), "lat": float(lat), "lon": float(lon),
                        "grade": g, "grade_name": GRADE.get(g, g),
                        "wind_kt": int(w) if w else None})
    return sorted(out, key=lambda p: p["time"])


def demo() -> None:
    if not PATH.exists():
        print("tracks: no cached file, skipped (python -m satelight.tracks --fetch)")
        return
    m = track("Mocha")
    assert m and m[0]["time"].startswith("2023-05-09"), "IMD's first position is the depression"
    assert max(p["wind_kt"] or 0 for p in m) >= 100, "Mocha reached ESCS"
    assert all(5 <= p["lat"] <= 30 for p in m)
    print(f"tracks ok: Mocha {len(m)} IMD positions, Biparjoy {len(track('Biparjoy'))}")


if __name__ == "__main__":
    fetch() if "--fetch" in sys.argv else demo()
