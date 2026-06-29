"""Zip data folder for backup (.env excluded)."""

import shutil
import datetime
from pathlib import Path


def run_backup(data_root: Path) -> Path:
    data_root.mkdir(parents=True, exist_ok=True)
    stamp = datetime.datetime.now().strftime("%Y%m%d")
    out_dir = data_root / "backups"
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"backup_{stamp}"
    shutil.make_archive(str(out), "zip", data_root)
    return Path(str(out) + ".zip")
