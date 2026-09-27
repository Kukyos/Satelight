"""Train one model from one config file and one seed.

    python -m oceanembed.train configs/unet.toml

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
from pathlib import Path

import numpy as np
import torch

from . import config, data
from .model import OceanEmbed, masked_mse


def load_config(path: str | Path) -> dict:
    cfg = tomllib.loads(Path(path).read_text())
    cfg.setdefault("inputs", config.INPUTS)
    return cfg


def seed_everything(seed: int) -> None:
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)
    torch.backends.cudnn.benchmark = False
    torch.backends.cudnn.deterministic = True


def prepare(cfg: dict, split: str, stats: data.Stats | None, sea: np.ndarray):
    x, y, t = data.load_raw(split, cfg["inputs"])
    if stats is None:
        stats = data.compute_stats(x, y)
    xa = data.assemble(x, t, stats, sea)
    yn = data.normalise_target(y, stats)
    return xa, yn, t, stats


def build(cfg: dict) -> OceanEmbed:
    return OceanEmbed(data.n_channels(cfg["inputs"]), cfg["arch"], cfg.get("emb", 32),
                      cfg.get("daily", 64), width=cfg.get("width", 32))


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
    history, best = [], float("inf")
    for epoch in range(cfg["epochs"]):
        model.train()
        tl, n, te = 0.0, 0, time.time()
        for idx in batches(len(xtr), cfg["batch"], rng):
            xb = torch.from_numpy(xtr[idx]).to(device).float()
            yb = torch.from_numpy(ytr[idx]).to(device).float()
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
