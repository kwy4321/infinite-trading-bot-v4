#!/usr/bin/env python3
"""설정 로드 확인 — 서버: python3 scripts/check_env.py"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from config.settings import ROOT as PROJECT_ROOT, get_settings, google_sheets_issues, resolve_service_account_path


def main() -> int:
    env_path = PROJECT_ROOT / ".env"
    settings = get_settings()
    json_path = resolve_service_account_path(settings.google_service_account_json)
    issues = google_sheets_issues(settings)
    info = {
        "env_file": str(env_path),
        "env_exists": env_path.is_file(),
        "google_sheets_enabled": settings.google_sheets_enabled,
        "google_spreadsheet_id": settings.google_spreadsheet_id or "",
        "google_service_account_json": settings.google_service_account_json or "",
        "service_account_file_exists": json_path is not None,
        "service_account_resolved": str(json_path) if json_path else "",
        "has_google_sheets": settings.has_google_sheets,
        "google_sheets_link": settings.google_sheets_link or "",
        "sheets_issues": issues,
    }
    print(json.dumps(info, ensure_ascii=False, indent=2))
    if issues:
        print("\n⚠️ Google Sheets 설정:")
        for item in issues:
            print(f"   - {item}")
        print("\n.env 예시:")
        print("   GOOGLE_SHEETS_ENABLED=true")
        print("   GOOGLE_SPREADSHEET_ID=스프레드시트ID")
        print("   GOOGLE_SERVICE_ACCOUNT_JSON=data/google-service-account.json")
        print("   GOOGLE_SHEETS_URL=https://docs.google.com/spreadsheets/d/...")
        print("\nJSON 파일을 data/google-service-account.json 에 두고 봇 재시작.")
        return 1
    print("\n✅ Google Sheets 설정 OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
