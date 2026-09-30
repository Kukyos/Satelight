"""Every picture the deck uses, made from the harness output and the viewer captures.

    python submission/figures.py

Reads data/eval-latest.json (numbers, never typed), data/figures/ (the harness's cyclone
and embedding figures) and submission/figures/shot-*.png (submission/capture.cjs). Writes
submission/figures/deck-*.png, each cropped to the aspect of the slide frame it fills, so
nothing is stretched when build.py swaps it in.
"""

import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
FIG = Path(__file__).resolve().parent / "figures"
HARNESS_FIG = ROOT / "data" / "figures"
E = json.loads((ROOT / "data" / "eval-latest.json").read_text().replace("NaN", "null"))
HEAD = f"{E['selection']['headline']} (selected)"

# The deck's own colours (read from the P3 slides): navy accent, ink, grey text.
NAVY, INK, GREY, WARM = "#1F4E79", "#16202B", "#4F5B69", "#E07B39"


def fit(src: Path | Image.Image, aspect: float, focus=(0.5, 0.5), out: str = "") -> Image.Image:
    """Crop to width/height = aspect around a focus point (fractions of the image)."""
    im = Image.open(src) if isinstance(src, Path) else src
    w, h = im.size
    if w / h > aspect:
        cw, ch = round(h * aspect), h
    else:
        cw, ch = w, round(w / aspect)
    x = min(max(0, round(focus[0] * w - cw / 2)), w - cw)
    y = min(max(0, round(focus[1] * h - ch / 2)), h - ch)
    im = im.crop((x, y, x + cw, y + ch)).convert("RGB")
    if out:
        im.save(FIG / out, quality=92)
    return im


def rmse_chart() -> None:
    """RMSE against held-out Argo by depth, per basin, headline beside floor and ceiling
    (hard rule 8). Fills the slide-4 chart area, 8.95 x 5.0 in."""
    plt.rcParams.update({"font.family": "Arial", "font.size": 11, "axes.edgecolor": "#C9D1DA",
                         "axes.labelcolor": GREY, "xtick.color": GREY, "ytick.color": GREY})
    depths = E["depths"]
    fig, axs = plt.subplots(1, 3, figsize=(8.95, 4.95), sharey=True, constrained_layout=True)
    regions = [("North Indian Ocean (whole box)", "Whole box"), ("Bay of Bengal", "Bay of Bengal"),
               ("Arabian Sea", "Arabian Sea")]
    y = list(range(len(depths)))
    for ax, (key, title) in zip(axs, regions):
        t = E["argo"][key]
        for name, lab, col, ls, lw in (("climatology", "Climatology (floor)", "#8C97A6", (0, (3, 3)), 1.8),
                                       (HEAD, "OceanEmbed (satellites only)", NAVY, "-", 2.8),
                                       ("GLORYS (ceiling)", "GLORYS (ceiling, saw these floats)", WARM, "-", 1.6)):
            ax.plot([s["rmse"] for s in t[name]], y, ls=ls, lw=lw, color=col, label=lab, marker="o", ms=3)
        n = sum(s["n"] for s in t["climatology"])
        ax.set_title(f"{title}\n{n:,} cast-depth pairs", fontsize=11, color=INK, fontweight="bold")
        ax.grid(axis="x", color="#E6EAEE")
        ax.set_xlim(left=0)
        ax.set_xlabel("RMSE (°C)")
    axs[0].set_yticks(y, [f"{d:g}" for d in depths])
    axs[0].invert_yaxis()
    axs[0].set_ylabel("depth (m)")
    h, l = axs[0].get_legend_handles_labels()
    fig.legend(h, l, loc="outside lower center", ncol=3, frameon=False, fontsize=10.5)
    fig.savefig(FIG / "deck-rmse.png", dpi=220)
    plt.close(fig)


def logo() -> None:
    """The viewer's favicon (viewer/index.html) at a size a slide can use: the water
    column, surface to depth, as three shortening lines."""
    s = 512
    im = Image.new("RGB", (s, s), "#FFFFFF")
    d = ImageDraw.Draw(im)
    u = s / 16
    d.rounded_rectangle((0, 0, s - 1, s - 1), radius=3 * u, fill="#0D1B2A")
    for x0, x1, yy in ((2, 14, 5), (4, 12, 8), (6, 10, 11)):
        d.line((x0 * u, yy * u, x1 * u, yy * u), fill="#F5C542", width=round(1.6 * u))
    im.save(FIG / "deck-logo.png")


def crops() -> None:
    fit(FIG / "shot-hero-view.png", 7150608 / 3767328, (0.5, 0.56), "deck-hero.jpg")
    # The panel from its header (float, cycle, day) down; the slide caption carries the rest.
    fit(FIG / "shot-profile.png", 2034540 / 2395728, (0.5, 0.0), "deck-profile.jpg")
    # The cyclone figure's map panels, without its axes: top row is 0 m.
    cy = Image.open(HARNESS_FIG / "cyclone_mocha.png")
    w, h = cy.size
    tl = cy.crop((round(0.050 * w), round(0.068 * h), round(0.430 * w), round(0.476 * h)))
    tr = cy.crop((round(0.488 * w), round(0.068 * h), round(0.868 * w), round(0.476 * h)))
    fit(tl, 2034540 / 2395728, (0.5, 0.5), "deck-mocha-small.jpg")
    fit(tl, 2406729 / 3310128, (0.5, 0.5), "deck-mocha-rec.jpg")
    fit(tr, 2406729 / 3310128, (0.5, 0.5), "deck-mocha-glorys.jpg")
    wide = 3891058 / 3310128
    fit(FIG / "shot-arabian-view.png", wide, (0.5, 0.55), "deck-arabian.jpg")
    fit(FIG / "shot-error-view.png", wide, (0.5, 0.55), "deck-error.jpg")
    emb = Image.open(HARNESS_FIG / "embedding_hybrid_2023-07-15.png")
    w, h = emb.size   # axes span about 7-94 % across, 7-86 % down
    emb = emb.crop((round(0.07 * w), round(0.07 * h), round(0.93 * w), round(0.855 * h)))
    fit(emb, wide, (0.55, 0.5), "deck-embedding.jpg")


if __name__ == "__main__":
    FIG.mkdir(exist_ok=True)
    rmse_chart()
    logo()
    crops()
    print("figures ok:", sorted(p.name for p in FIG.glob("deck-*")))
