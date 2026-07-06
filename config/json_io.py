"""Compact JSON read/write — less disk on small VMs."""

import json
import os
import tempfile
from pathlib import Path
from typing import Any


def load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return default


def save_json(path: Path, data: Any, *, compact: bool = True) -> None:
    """Atomic write — temp file then replace to avoid partial JSON on crash."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            if compact:
                json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
            else:
                json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, path)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise
