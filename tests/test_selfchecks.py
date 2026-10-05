"""Every module's self-check, as one pytest run: python -m pytest tests"""

import importlib

import pytest

MODULES = ["config", "grid", "arco", "argo", "baselines", "evaluate", "embed", "model", "globe"]


@pytest.mark.parametrize("name", MODULES)
def test_demo(name):
    importlib.import_module(f"satelight.{name}").demo()


def test_calendar_off():
    """`doy = false` zeroes exactly the two day-of-year channels and nothing else (D-09)."""
    import numpy as np

    from satelight import config, data
    if not (config.CUBE / "static.nc").exists():
        pytest.skip("cube not built")
    sea = data.sea_mask()
    t = np.array(["2023-03-01", "2023-08-01"], dtype="datetime64[D]")
    x = np.ones((2, 8) + sea.shape, np.float32)
    s = data.Stats(np.zeros(8), np.ones(8), np.zeros(15), np.ones(15))
    on, off = data.assemble(x, t, s, sea), data.assemble(x, t, s, sea, with_doy=False)
    assert on.shape == off.shape
    assert not off[:, 11:13].any() and on[:, 11:13].any()
    assert np.array_equal(np.delete(on, [11, 12], 1), np.delete(off, [11, 12], 1))
