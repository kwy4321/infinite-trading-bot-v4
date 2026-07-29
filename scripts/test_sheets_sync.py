#!/usr/bin/env python3
"""Google Sheets 동기화 테스트 — 서버에서: python scripts/test_sheets_sync.py"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import App
from integrations.google_sheets import sync_ledger


def main() -> int:
    app = App.create()
    result = sync_ledger(app)
    print(result)
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
