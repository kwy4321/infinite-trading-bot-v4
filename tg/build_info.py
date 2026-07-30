"""Running build metadata (deploy verification)."""

from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def git_rev() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=ROOT,
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except Exception:
        return "?"


def ledger_ui_label() -> str:
    if (ROOT / "tg" / "ledger_redirect.py").exists():
        return "구 UI (설명칸)"
    return "신 UI"
