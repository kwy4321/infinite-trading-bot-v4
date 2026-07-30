#!/usr/bin/env python3
"""설정 로드 확인 — bash scripts/check_env.sh (권장)"""

import json
import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

_EXIT_OK = 0
_EXIT_CONFIG = 1
_EXIT_ERROR = 2


def _print_runtime_error(exc: BaseException) -> None:
    print("\n❌ 스크립트 실행 오류 (설정 문제가 아님)")
    print(f"   {type(exc).__name__}: {exc}")
    print("\n다음으로 실행해 보세요:")
    print("   bash scripts/check_env.sh")
    print("   cd ~/infinite-trading-bot-v4 && bash scripts/check_env.sh")
    traceback.print_exc()


def main() -> int:
    env_path = ROOT / ".env"
    if not env_path.is_file():
        print(f"❌ .env 없음: {env_path}")
        return _EXIT_ERROR

    try:
        from config.settings import (
            ROOT as PROJECT_ROOT,
            google_sheets_issues,
            reload_settings,
            resolve_service_account_path,
        )
    except ImportError as exc:
        _print_runtime_error(exc)
        return _EXIT_ERROR

    try:
        settings = reload_settings()
        json_path = resolve_service_account_path(settings.google_service_account_json)
        issues = google_sheets_issues(settings)
        info = {
            "env_file": str(PROJECT_ROOT / ".env"),
            "env_exists": True,
            "google_sheets_enabled": settings.google_sheets_enabled,
            "google_spreadsheet_id_raw": settings.google_spreadsheet_id or "",
            "resolved_spreadsheet_id": settings.resolved_spreadsheet_id or "",
            "google_sheets_url": settings.google_sheets_url or "",
            "google_service_account_json": settings.google_service_account_json or "",
            "service_account_file_exists": json_path is not None,
            "service_account_resolved": str(json_path) if json_path else "",
            "has_google_sheets": settings.has_google_sheets,
            "google_sheets_link": settings.google_sheets_link or "",
            "sheets_issues": issues,
        }
        print(json.dumps(info, ensure_ascii=False, indent=2))

        if issues:
            print("\n⚠️ Google Sheets 설정 미완료 (Python 오류 아님 — 아래 항목 채우기)")
            for item in issues:
                print(f"   - {item}")
            print("\n.env 예시:")
            print("   GOOGLE_SHEETS_ENABLED=true")
            print("   GOOGLE_SHEETS_URL=https://docs.google.com/spreadsheets/d/스프레드시트ID/edit")
            print("   GOOGLE_SERVICE_ACCOUNT_JSON=data/google-service-account.json")
            print("\nJSON 파일 위치:")
            print(f"   {PROJECT_ROOT / 'data' / 'google-service-account.json'}")
            print("\n설정 후 VM 반영:")
            print("   bash scripts/cloudshell_bot.sh restart")
            return _EXIT_CONFIG

        print("\n✅ Google Sheets 설정 OK")
        print(f"   링크: {settings.google_sheets_link}")
        return _EXIT_OK
    except Exception as exc:
        _print_runtime_error(exc)
        return _EXIT_ERROR


if __name__ == "__main__":
    raise SystemExit(main())
