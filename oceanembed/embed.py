"""What the embedding captures, measured (docs/03-limitations.md L10).

Called by the harness; its numbers land in docs/13-eval-results.md.

1. **Seasons, never taught.** The daily embedding (one vector per day) is clustered with
   k-means into 4 groups, and the groups are compared with the four Indian Ocean monsoon
   seasons (Dec-Feb winter monsoon, Mar-May spring inter-monsoon, Jun-Sep summer
   monsoon, Oct-Nov autumn inter-monsoon) by normalised mutual information. And for each
   test day, is its nearest neighbour in embedding space (excluding +/-3 days of itself)
   in the same season? Chance is reported beside it.
2. **Mixed-layer depth, never taught.** GLORYS `mlotst` is not an input and not a
   target. A linear probe is fitted from the per-cell embedding to it on the validation
   block and scored on the test block, beside the same probe fitted on the raw eight
   satellite channels at the cell. If the embedding's R^2 is higher, it holds something
   about the upper ocean that the pixel alone does not.
3. **Pictures.** The first three principal components of the per-cell embedding, as RGB,
   for a few test days: data/figures/embedding_<run>_<day>.png.
"""

from __future__ import annotations

import numpy as np

from . import config, data

SEASON_NAMES = ["Winter monsoon (DJF)", "Spring inter-monsoon (MAM)",
                "Summer monsoon (JJAS)", "Autumn inter-monsoon (ON)"]
SAMPLE_CELLS = 1500
MLD_SOURCE = "mld"


def season(t: np.ndarray) -> np.ndarray:
    m = (t.astype("datetime64[M]").astype(int) % 12) + 1
    return np.select([np.isin(m, [12, 1, 2]), np.isin(m, [3, 4, 5]),
                      np.isin(m, [6, 7, 8, 9])], [0, 1, 2], 3)


def season_scores(daily: np.ndarray, t: np.ndarray, seed: int = 0) -> dict:
    from sklearn.cluster import KMeans
    from sklearn.metrics import normalized_mutual_info_score

    s = season(t)
    z = (daily - daily.mean(0)) / (daily.std(0) + 1e-6)
    labels = KMeans(4, n_init=10, random_state=seed).fit_predict(z)
    d = ((z[:, None] - z[None]) ** 2).sum(-1)
    gap = np.abs(np.arange(len(t))[:, None] - np.arange(len(t))[None])
    d[gap <= 3] = np.inf
    nn = d.argmin(1)
    same = float((s[nn] == s).mean())
    chance = float(sum((np.mean(s == k)) ** 2 for k in range(4)))
    rng = np.random.default_rng(seed)
    shuffled = float(normalized_mutual_info_score(rng.permutation(s), labels))
    return {"days": int(len(t)), "kmeans_k": 4,
            "nmi_clusters_vs_season": float(normalized_mutual_info_score(s, labels)),
            "nmi_shuffled_seasons": shuffled,
            "nearest_neighbour_same_season": same,
            "nearest_neighbour_chance": chance}


def _sample(cell: np.ndarray, x: np.ndarray, mld: np.ndarray, sea: np.ndarray, seed: int):
    """Rows of (embedding, raw channels, MLD) from random sea cells on every day."""
    rng = np.random.default_rng(seed)
    js, is_ = np.nonzero(sea)
    E, X, Y = [], [], []
    for d in range(cell.shape[0]):
        k = rng.choice(js.size, SAMPLE_CELLS, replace=False)
        j, i = js[k], is_[k]
        y = mld[d, j, i]
        xr_ = x[d][:, j, i].T
        ok = np.isfinite(y) & np.isfinite(xr_).all(1)
        E.append(cell[d][:, j, i].T[ok])
        X.append(xr_[ok])
        Y.append(y[ok])
    return np.concatenate(E).astype(np.float32), np.concatenate(X), np.concatenate(Y)


def mld_probe(run: str) -> dict:
    """Linear probe for mixed-layer depth: fit on val, score on test."""
    from sklearn.linear_model import Ridge
    from sklearn.metrics import r2_score

    from .predict import predict_span

    sea = data.sea_mask()
    rows = {}
    for split in ("val", "test"):
        a, b = config.SPLITS[split]
        _, t, (cell, _) = predict_span(run, a, b, with_embedding=True)
        x, _, tx = data.load_raw(split, config.INPUTS, with_target=False)
        mld, tm = data._read(MLD_SOURCE, "mld", a, b)
        common = np.intersect1d(np.intersect1d(t, tx), tm)
        pick = lambda arr, tt: arr[np.searchsorted(tt, common)]  # noqa: E731
        rows[split] = _sample(pick(cell, t), pick(x, tx), pick(mld, tm), sea, seed=1)
        del cell, x, mld
    (Ev, Xv, Yv), (Et, Xt, Yt) = rows["val"], rows["test"]
    mu, sd = Xv.mean(0), Xv.std(0) + 1e-6
    out = {"fit_on": "val block", "scored_on": "test block",
           "rows_fit": int(Yv.size), "rows_scored": int(Yt.size),
           "label": "GLORYS mlotst (mixed-layer depth, m): never an input, never a target"}
    for name, (fv, ft) in {"embedding (32 per cell)": (Ev, Et),
                           "raw satellite channels (8 per cell)": ((Xv - mu) / sd, (Xt - mu) / sd)
                           }.items():
        m = Ridge(alpha=1.0).fit(fv, Yv)
        out[name] = {"r2_test": float(r2_score(Yt, m.predict(ft)))}
    return out


def pictures(run: str, days: list[str]) -> list[str]:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import xarray as xr

    from .predict import EMB_DIR

    sea = data.sea_mask()
    fig_dir = config.DATA / "figures"
    fig_dir.mkdir(parents=True, exist_ok=True)
    written = []
    for day in days:
        path = EMB_DIR / f"{run}_{day[:4]}.nc"
        if not path.exists():
            continue
        with xr.open_dataset(path) as ds:
            e = ds["cell"].sel(time=day).values.astype(np.float32)   # (D, H, W)
        v = e[:, sea].T
        v = v - v.mean(0)
        _, _, vt = np.linalg.svd(v, full_matrices=False)
        pc = v @ vt[:3].T
        lo, hi = np.percentile(pc, [2, 98], axis=0)
        rgb = np.clip((pc - lo) / (hi - lo), 0, 1)
        img = np.ones((config.NLAT, config.NLON, 3)) * 0.08
        img[sea] = rgb
        plt.figure(figsize=(9.6, 4.4), dpi=150)
        plt.imshow(img, origin="lower", extent=[45, 105, 5, 30])
        plt.title(f"OceanEmbed per-cell embedding, first 3 principal components as RGB — {day}")
        plt.xlabel("longitude (°E)")
        plt.ylabel("latitude (°N)")
        out = fig_dir / f"embedding_{run}_{day}.png"
        plt.savefig(out, bbox_inches="tight", facecolor="white")
        plt.close()
        written.append(out.name)
    return written


def inspect(run: str) -> dict:
    import xarray as xr

    from .predict import EMB_DIR

    files = sorted(EMB_DIR.glob(f"{run}_*.nc"))
    out = {"run": run}
    if files:
        with xr.open_mfdataset(files) as ds:
            daily = ds["daily"].values
            t = ds["time"].values.astype("datetime64[D]")
        out["seasons"] = season_scores(daily, t)
        out["figures"] = pictures(run, ["2023-01-15", "2023-07-15", "2024-05-01", "2024-10-15"])
    try:
        out["mld_probe"] = mld_probe(run)
    except FileNotFoundError as e:
        out["mld_probe_error"] = f"MLD not fetched: {e}"
    return out


def demo() -> None:
    t = np.array(["2023-01-05", "2023-04-01", "2023-07-01", "2023-10-20", "2023-12-31"],
                 dtype="datetime64[D]")
    assert season(t).tolist() == [0, 1, 2, 3, 0]
    rng = np.random.default_rng(0)
    tt = config.days(config.SPLITS["test"][0], config.SPLITS["test"][1])
    s = season(tt)
    daily = rng.normal(size=(tt.size, 8)) + 4 * np.eye(4, 8)[s]
    r = season_scores(daily, tt)
    assert r["nmi_clusters_vs_season"] > 0.8 > r["nmi_shuffled_seasons"], r
    print("embed ok: seasons recovered from a planted signal, shuffled control near zero")


if __name__ == "__main__":
    demo()
