#!/usr/bin/env python3
"""Google Sheets 동기화 테스트 — 봇 VM에서: python3 scripts/test_sheets_sync.py [-v]"""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import App
from integrations.google_sheets import sync_ledger
from reporting.dashboard_data import ledger_data_sources, prepare_ledger_for_export


def main() -> int:
    parser = argparse.ArgumentParser(description="Google Sheets ledger sync test")
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="로컬 data 파일·fill_log 건수 출력",
    )
    args = parser.parse_args()

    app = App.create()
    if args.verbose:
        print("=== 로컬 데이터 (동기화 전) ===")
        print(json.dumps(ledger_data_sources(app), ensure_ascii=False, indent=2))
        prep = prepare_ledger_for_export(app)
        print("=== fill_log → cycles 반영 ===")
        print(json.dumps(prep, ensure_ascii=False, indent=2))
        print("=== 동기화 후 데이터 ===")
        print(json.dumps(ledger_data_sources(app), ensure_ascii=False, indent=2))

    result = sync_ledger(app)
    print(result)
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
