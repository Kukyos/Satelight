"""S5: a model run is reproducible from its config file and seed, bit for bit.

Needs the 2010-2011 cube. python -m pytest tests/test_train_repro.py --live"""

import json

import pytest

from satelight import config, train

CONFIG = """name = "repro-{arch}"
arch = "{arch}"
seed = 7
epochs = 1
batch = 8
lr = 2e-3
[splits]
train = ["2010-03-01", "2010-04-30"]
val = ["2010-06-01", "2010-06-30"]
"""


@pytest.mark.parametrize("arch", ["unet", "hybrid"])
def test_same_seed_same_run(arch, tmp_path, monkeypatch, request):
    if not request.config.getoption("--live"):
        pytest.skip("needs the fetched cube and a GPU: run with --live")
    monkeypatch.setattr(config, "RUNS", tmp_path / "runs")
    cfg = tmp_path / f"{arch}.toml"
    cfg.write_text(CONFIG.format(arch=arch))
    histories = []
    for _ in range(2):
        out = train.train(str(cfg))
        histories.append(json.loads((out / "history.json").read_text()))
    for a, b in zip(*histories):
        assert a["train_loss"] == b["train_loss"] and a["val_loss"] == b["val_loss"], (a, b)
