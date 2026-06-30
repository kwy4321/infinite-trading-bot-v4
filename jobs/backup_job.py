"""Lightweight backup — JSON only, keeps last N zip files."""

import datetime
import zipfile
from pathlib import Path

from config.settings import SYMBOLS


def run_backup(data_root: Path, keep: int = 5) -> Path | None:
    account_dir = data_root / "accounts" / "default"
    account_dir.mkdir(parents=True, exist_ok=True)

    sources: list[tuple[Path, str]] = []
    for sym in SYMBOLS:
        p = account_dir / f"{sym}.json"
        if p.exists():
            sources.append((p, f"{sym}.json"))
    cycles = account_dir / "cycles.json"
    if cycles.exists():
        sources.append((cycles, "cycles.json"))
    runtime = data_root / "runtime_settings.json"
    if runtime.exists():
        sources.append((runtime, "runtime_settings.json"))

    if not sources:
        return None

    out_dir = data_root / "backups"
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M")
    out = out_dir / f"backup_{stamp}.zip"

    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for src, arc in sources:
            zf.write(src, arcname=arc)

    _prune_old_backups(out_dir, keep)
    return out


def _prune_old_backups(out_dir: Path, keep: int) -> None:
    files = sorted(out_dir.glob("backup_*.zip"), key=lambda p: p.stat().st_mtime, reverse=True)
    for old in files[max(keep, 0) :]:
        old.unlink(missing_ok=True)
