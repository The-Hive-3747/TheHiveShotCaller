"""Locate bundled resources (ui/, bin/, fixtures/) from source or a PyInstaller build."""

from __future__ import annotations

import sys
from pathlib import Path


def base_dir() -> Path:
    """Project root from source; _MEIPASS (or exe dir) when frozen."""
    if getattr(sys, "frozen", False):
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            return Path(meipass)
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def resource_path(rel: str | Path) -> Path:
    """Absolute path of a bundled resource, e.g. resource_path('ui')."""
    return base_dir() / rel
