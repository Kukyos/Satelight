"""Train one model from one config file and one seed.

    python -m satelight.train configs/unet.toml

Writes runs/<name>/: the config as used, the normalisation statistics (train block only),
the loss curves, and the checkpoint with the best validation loss. Model selection looks
at the validation block only; the test block is never loaded here (hard rule 6).
"""

from __future__ import annotations

import json
import shutil
import sys
import time
import tomllib
from datetime import date
from pathlib import Path

import numpy as np
import torch

from . import config, data
from .model import Satelight, masked_mse


def load_config(path: str | Path) -> dict:
    cfg = tomllib.loads(Path(path).read_text())
    cfg.setdefault("inputs", config.INPUTS)
    cfg.setdefault("lags", [0])
    # "absolute": learn temperature. "anomaly": learn the departure from the train-block
    # day-of-year climatology (runs/climatology), which is added back on output. The
    # climatology is a fixed prior fitted on training targets only, like a learned bias
    # per cell and day of year; it is not a daily input (docs/03-limitations.md L9).
    cfg.setdefault("target", "absolute")
    return cfg


def target_offset(cfg: dict, t: np.ndarray) -> np.ndarray | float:
    if cfg.get("target") == "anomaly":
        from .baselines import climatology
        return climatology(t)
    return 0.0


def seed_everything(seed: int) -> None:
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)
    torch.backends.cudnn.benchmark = False
    torch.backends.cudnn.deterministic = True


def _pieces(a: date, b: date) -> list[tuple[date, date]]:
    return [(max(a, date(y, 1, 1)), min(b, date(y, 12, 31))) for y in range(a.year, b.year + 1)]


def prepare(cfg: dict, split: str, stats: data.Stats | None, sea: np.ndarray):
    """A split as normalised float16 arrays, loaded a year at a time so that raw float32
    never has to fit in memory whole. Statistics, when not given, come from a first pass
    over the same years (train block only)."""
    # A config may narrow or widen a split (smoke tests, the extended comparison); by
    # default the blocks in config.SPLITS are used. The test block is never loaded here.
    span = cfg.get("splits", {}).get(split)
    a, b = tuple(date.fromisoformat(d) for d in span) if span else config.SPLITS[split]
    pieces = _pieces(a, b)
    if stats is None:
        nx = ny = None
        for p in pieces:
            x, y, t = data.load_raw(split, cfg["inputs"], lags=cfg["lags"], span=p)
            y = y - target_offset(cfg, t)
            part = [np.nansum(x, axis=(0, 2, 3), dtype=np.float64),
                    np.nansum(x.astype(np.float64) ** 2, axis=(0, 2, 3)),
                    np.isfinite(x).sum(axis=(0, 2, 3)),
                    np.nansum(y, axis=(0, 2, 3), dtype=np.float64),
                    np.nansum(y.astype(np.float64) ** 2, axis=(0, 2, 3)),
                    np.isfinite(y).sum(axis=(0, 2, 3))]
            nx = part if nx is None else [u + v for u, v in zip(nx, part)]
            del x, y
        xm, ym = nx[0] / nx[2], nx[3] / nx[5]
        stats = data.Stats(xm, np.sqrt(nx[1] / nx[2] - xm ** 2), ym, np.sqrt(nx[4] / nx[5] - ym ** 2))
    # Filled in place: concatenating year pieces would hold every year twice.
    n = (b - a).days + 1
    shape = (config.NLAT, config.NLON)
    xa = np.empty((n, data.n_channels(cfg["inputs"], cfg["lags"])) + shape, np.float16)
    yn = np.empty((n, config.DEPTHS.size) + shape, np.float16)
    ts, k = [], 0
    for p in pieces:
        x, y, t = data.load_raw(split, cfg["inputs"], lags=cfg["lags"], span=p)
        xa[k:k + len(t)] = data.assemble(x, t, stats, sea)
        yn[k:k + len(t)] = data.normalise_target(y - target_offset(cfg, t), stats)
        ts.append(t)
        k += len(t)
        del x, y
    return xa[:k], yn[:k], np.concatenate(ts), stats


def build(cfg: dict) -> Satelight:
    return Satelight(data.n_channels(cfg["inputs"], cfg["lags"]), cfg["arch"], cfg.get("emb", 32),
                      width=cfg.get("width", 32), dropout=cfg.get("dropout", 0.0))


def batches(n: int, size: int, rng: np.random.Generator | None):
    order = rng.permutation(n) if rng is not None else np.arange(n)
    for i in range(0, n, size):
        yield order[i:i + size]


def evaluate(model, xa, yn, stats, device, size=8) -> tuple[float, np.ndarray]:
    """Validation loss (normalised) and RMSE per level in degrees C."""
    model.eval()
    se = np.zeros(yn.shape[1])
    cnt = np.zeros(yn.shape[1])
    loss, n = 0.0, 0
    with torch.no_grad(), torch.autocast("cuda", dtype=torch.bfloat16):
        for idx in batches(len(xa), size, None):
            xb = torch.from_numpy(xa[idx]).to(device).float()
            yb = torch.from_numpy(yn[idx]).to(device).float()
            p = model(xb).float()
            loss += masked_mse(p, yb).item() * len(idx)
            n += len(idx)
            ok = torch.isfinite(yb)
            d = torch.where(ok, p - torch.nan_to_num(yb), torch.zeros_like(p)) ** 2
            se += d.sum(dim=(0, 2, 3)).cpu().numpy()
            cnt += ok.sum(dim=(0, 2, 3)).cpu().numpy()
    rmse = np.sqrt(se / np.maximum(cnt, 1)) * stats.y_std
    return loss / n, rmse


def train(cfg_path: str) -> Path:
    cfg = load_config(cfg_path)
    out = config.RUNS / cfg["name"]
    out.mkdir(parents=True, exist_ok=True)
    shutil.copy(cfg_path, out / "config.toml")
    seed_everything(cfg["seed"])
    device = "cuda"
    sea = data.sea_mask()

    t0 = time.time()
    xtr, ytr, _, stats = prepare(cfg, "train", None, sea)
    xva, yva, _, _ = prepare(cfg, "val", stats, sea)
    stats.save(out / "stats.json")
    print(f"data: train {len(xtr)} days, val {len(xva)} days, {time.time() - t0:.0f} s",
          flush=True)

    model = build(cfg).to(device)
    opt = torch.optim.AdamW(model.parameters(), lr=cfg["lr"], weight_decay=cfg.get("wd", 1e-4))
    steps = cfg["epochs"] * int(np.ceil(len(xtr) / cfg["batch"]))
    sched = torch.optim.lr_scheduler.OneCycleLR(opt, cfg["lr"], total_steps=steps, pct_start=0.05)
    rng = np.random.default_rng(cfg["seed"])
    # Regularisers, each chosen on the validation block: random crops of the basin (the
    # U-Net only), Gaussian noise on the satellite channels (z-score units).
    crop = cfg.get("crop")
    assert not crop or cfg["arch"] == "unet", "the hybrid needs the whole basin"
    noise = cfg.get("noise", 0.0)
    n_sat = len(cfg["inputs"]) * len(cfg["lags"])
    history, best = [], float("inf")
    for epoch in range(cfg["epochs"]):
        model.train()
        tl, n, te = 0.0, 0, time.time()
        for idx in batches(len(xtr), cfg["batch"], rng):
            xb, yb = xtr[idx], ytr[idx]
            if crop:
                j0 = int(rng.integers(0, config.NLAT - crop[0] + 1))
                i0 = int(rng.integers(0, config.NLON - crop[1] + 1))
                xb = xb[..., j0:j0 + crop[0], i0:i0 + crop[1]]
                yb = yb[..., j0:j0 + crop[0], i0:i0 + crop[1]]
            xb = torch.from_numpy(np.ascontiguousarray(xb)).to(device).float()
            yb = torch.from_numpy(np.ascontiguousarray(yb)).to(device).float()
            if noise:
                g = torch.Generator(device=device).manual_seed(int(rng.integers(1 << 31)))
                xb[:, :n_sat] += noise * torch.randn(xb[:, :n_sat].shape, device=device,
                                                     generator=g) * xb[:, -1:]
            with torch.autocast("cuda", dtype=torch.bfloat16):
                loss = masked_mse(model(xb).float(), yb)
            opt.zero_grad(set_to_none=True)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            opt.step()
            sched.step()
            tl += loss.item() * len(idx)
            n += len(idx)
        vl, rmse = evaluate(model, xva, yva, stats, device)
        history.append({"epoch": epoch + 1, "train_loss": tl / n, "val_loss": vl,
                        "val_rmse_per_depth": [round(float(r), 4) for r in rmse],
                        "seconds": round(time.time() - te, 1)})
        flag = ""
        if vl < best:
            best = vl
            torch.save(model.state_dict(), out / "best.pt")
            flag = " *"
        print(f"epoch {epoch + 1:3d} train {tl / n:.4f} val {vl:.4f} "
              f"rmse@0/100/300m {rmse[0]:.3f}/{rmse[7]:.3f}/{rmse[11]:.3f} C "
              f"{time.time() - te:.0f}s{flag}", flush=True)
        (out / "history.json").write_text(json.dumps(history, indent=1))
    return out


def load_model(run: str | Path, device: str = "cuda"):
    run = Path(run) if Path(run).exists() else config.RUNS / str(run)
    cfg = load_config(run / "config.toml")
    model = build(cfg).to(device)
    model.load_state_dict(torch.load(run / "best.pt", map_location=device))
    model.eval()
    return model, cfg, data.Stats.load(run / "stats.json")


if __name__ == "__main__":
    train(sys.argv[1])
