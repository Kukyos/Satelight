"""The embedding engine and the profile decoder.

    surface state (C x 100 x 240)
        -> encoder -> per-cell embedding  e(x, y)  (D numbers per cell per day)
                   -> daily embedding     g        (the deepest layer, averaged over the
                                                    basin: 256 numbers for the U-Net,
                                                    192 for the hybrid)
        -> decoder -> temperature at 15 depths per cell

The embedding is the product, not a hidden layer: it is saved per cell per day and
inspected on its own (docs/03-limitations.md L10). The decoder is a per-cell MLP, so
everything spatial the model knows has to pass through e.

Two encoders, compared by the harness rather than by feel:

  unet    a convolutional U-Net (problem statement 4a)
  hybrid  a convolutional stem, then a transformer over the whole basin, then a
          convolutional up-path (4e: attention-based hybrid). Attention lets the Bay of
          Bengal read the Arabian Sea's winds in one step, which a CNN needs depth for.
"""

from __future__ import annotations

import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.nn.attention import SDPBackend, sdpa_kernel

PAD_H = 104  # 100 rows padded so three halvings divide evenly


def block(cin: int, cout: int) -> nn.Sequential:
    return nn.Sequential(
        nn.Conv2d(cin, cout, 3, padding=1), nn.GroupNorm(8, cout), nn.GELU(),
        nn.Conv2d(cout, cout, 3, padding=1), nn.GroupNorm(8, cout), nn.GELU())


class UNet(nn.Module):
    def __init__(self, cin: int, emb: int, width: int = 32, dropout: float = 0.0):
        super().__init__()
        self.drop = nn.Dropout2d(dropout)
        w = [width, width * 2, width * 4, width * 8]
        self.down = nn.ModuleList([block(cin, w[0]), block(w[0], w[1]), block(w[1], w[2])])
        self.mid = block(w[2], w[3])
        self.up = nn.ModuleList([
            nn.ConvTranspose2d(w[3], w[2], 2, stride=2),
            nn.ConvTranspose2d(w[2], w[1], 2, stride=2),
            nn.ConvTranspose2d(w[1], w[0], 2, stride=2)])
        self.dec = nn.ModuleList([block(w[3], w[2]), block(w[2], w[1]), block(w[1], w[0])])
        self.head = nn.Conv2d(w[0], emb, 1)
        self.bottleneck_dim = w[3]

    def forward(self, x):
        skips = []
        for d in self.down:
            x = d(x)
            skips.append(x)
            x = F.max_pool2d(x, 2)
        x = self.drop(self.mid(x))
        mid = x
        for up, dec, s in zip(self.up, self.dec, reversed(skips)):
            x = dec(torch.cat([up(x), self.drop(s)], 1))
        return self.head(x), mid


class Hybrid(nn.Module):
    """Conv stem (/4) -> transformer over 26 x 60 = 1560 tokens -> conv up-path."""

    def __init__(self, cin: int, emb: int, width: int = 32, dropout: float = 0.0,
                 dim: int = 192, depth: int = 6, heads: int = 6):
        super().__init__()
        self.s1 = block(cin, width)
        self.s2 = block(width, width * 2)
        self.proj = nn.Conv2d(width * 2, dim, 2, stride=2)
        self.pos = nn.Parameter(torch.zeros(1, dim, PAD_H // 4, 240 // 4))
        nn.init.trunc_normal_(self.pos, std=0.02)
        layer = nn.TransformerEncoderLayer(dim, heads, dim * 4, dropout=dropout, activation="gelu",
                                           batch_first=True, norm_first=True)
        self.tf = nn.TransformerEncoder(layer, depth)
        self.up1 = nn.ConvTranspose2d(dim, width * 2, 2, stride=2)
        self.d1 = block(width * 4, width * 2)
        self.up2 = nn.ConvTranspose2d(width * 2, width, 2, stride=2)
        self.d2 = block(width * 2, width)
        self.head = nn.Conv2d(width, emb, 1)
        self.bottleneck_dim = dim

    def forward(self, x):
        a = self.s1(x)                          # H
        b = self.s2(F.max_pool2d(a, 2))         # H/2
        z = self.proj(b) + self.pos             # H/4
        n, c, h, w = z.shape
        # The fused attention kernels are not deterministic in their backward pass
        # (measured: the same seed gave val losses 4e-3 apart); the math kernel is, so a
        # run is reproducible from its config and seed.
        with sdpa_kernel(SDPBackend.MATH):
            z = self.tf(z.flatten(2).transpose(1, 2)).transpose(1, 2).reshape(n, c, h, w)
        y = self.d1(torch.cat([self.up1(z), b], 1))
        y = self.d2(torch.cat([self.up2(y), a], 1))
        return self.head(y), z


class OceanEmbed(nn.Module):
    def __init__(self, cin: int, arch: str = "unet", emb: int = 32, levels: int = 15,
                 width: int = 32, dropout: float = 0.0):
        super().__init__()
        self.arch = arch
        self.encoder = (UNet if arch == "unet" else Hybrid)(cin, emb, width, dropout)
        self.decoder = nn.Sequential(
            nn.Conv2d(emb, 128, 1), nn.GELU(), nn.Dropout(dropout), nn.Conv2d(128, 128, 1),
            nn.GELU(), nn.Conv2d(128, levels, 1))

    def embed(self, x):
        """(N, C, 100, 240) -> per-cell embedding (N, D, 100, 240), daily (N, G).

        The daily embedding is the trained bottleneck itself, pooled over the basin: no
        extra layer, so nothing in it is untrained."""
        h, w = x.shape[-2:]
        # The U-Net takes any size divisible by 8 (so training can use crops); the
        # hybrid's position embedding fixes it to the whole basin.
        x = F.pad(x, (0, (-w) % 8, 0, (PAD_H - h) if self.arch != "unet" else (-h) % 8))
        e, mid = self.encoder(x)
        return e[..., :h, :w], mid.mean(dim=(2, 3))

    def forward(self, x):
        e, _ = self.embed(x)
        return self.decoder(e)


def masked_mse(pred, target):
    """Mean squared error over cells and levels that exist; masked levels count zero."""
    ok = torch.isfinite(target)
    diff = torch.where(ok, pred - torch.nan_to_num(target), torch.zeros_like(pred))
    return (diff ** 2).sum() / ok.sum().clamp(min=1)


def demo() -> None:
    for arch in ("unet", "hybrid"):
        m = OceanEmbed(14, arch)
        x = torch.randn(2, 14, 100, 240)
        e, g = m.embed(x)
        y = m(x)
        assert e.shape == (2, 32, 100, 240) and y.shape == (2, 15, 100, 240)
        assert g.shape == (2, m.encoder.bottleneck_dim)
        n = sum(p.numel() for p in m.parameters())
        print(f"model ok: {arch}, {n / 1e6:.2f} M parameters")
    t = torch.tensor([[1.0, float("nan")]])
    assert masked_mse(torch.tensor([[2.0, 99.0]]), t).item() == 1.0, "NaN levels do not count"


if __name__ == "__main__":
    demo()
