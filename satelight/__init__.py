"""Satelight: subsurface temperature from surface satellite observations (SIH 2026, PS 26066)."""

import os
from pathlib import Path

# Credentials live in a local, gitignored .env (Copernicus) and ~/.netrc (Earthdata).
_env = Path(__file__).resolve().parents[1] / ".env"
if _env.exists():
    for _line in _env.read_text().splitlines():
        _k, _, _v = _line.strip().partition("=")
        if _k and not _k.startswith("#") and _v:
            os.environ.setdefault(_k, _v)
