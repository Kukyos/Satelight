"""Every module's self-check, as one pytest run: python -m pytest tests"""

import importlib

import pytest

MODULES = ["config", "grid", "arco", "argo", "baselines", "evaluate", "embed", "model"]


@pytest.mark.parametrize("name", MODULES)
def test_demo(name):
    importlib.import_module(f"oceanembed.{name}").demo()
