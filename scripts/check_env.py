#!/usr/bin/env python3
"""설정 로드 확인 — 서버: python3 scripts/check_env.py"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from config.settings import ROOT as PROJECT_ROOT, get_settings


def main() -> int:
    env_path = PROJECT_ROOT / ".env"
    settings = get_settings()
    info = {
        "env_file": str(env_path),
        "env_exists": env_path.is_file(),
        "streamlit_url_raw": settings.streamlit_url or "",
        "streamlit_link": settings.streamlit_link or "",
        "google_sheets_enabled": settings.google_sheets_enabled,
        "has_google_sheets": settings.has_google_sheets,
        "google_sheets_link": settings.google_sheets_link or "",
    }
    print(json.dumps(info, ensure_ascii=False, indent=2))
    if not info["streamlit_link"]:
        print("\n⚠️ STREAMLIT_URL 이 비어 있습니다. .env 수정 후:")
        print("   sudo systemctl restart infinite-trading-bot")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
