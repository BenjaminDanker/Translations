from __future__ import annotations

"""Simple file helpers used throughout the translation tool‑chain.

Placed in a dedicated module (instead of re‑using the std‑lib ``io``) so we
avoid any naming collision with the built‑in package.
"""

import os
from pathlib import Path
from typing import Union, AnyStr

PathLike = Union[str, os.PathLike]

__all__ = ["read_file", "write_file"]


def read_file(path: PathLike) -> str:
    """Read *path* with UTF‑8 and return its full contents as ``str``."""
    path = Path(path)
    with path.open("r", encoding="utf-8") as fh:
        return fh.read()


def write_file(path: PathLike, data: AnyStr) -> None:
    """Create parent dirs (if needed) and write *data* to *path* in UTF‑8."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    # coerce bytes→str so we never accidentally write raw bytes
    if isinstance(data, bytes):
        data = data.decode("utf-8", "replace")
    with path.open("w", encoding="utf-8") as fh:
        fh.write(str(data))
