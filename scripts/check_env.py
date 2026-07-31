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


def _mask(s: str) -> str:
    s = (s or "").strip()
    if not s:
        return ""
    if len(s) <= 8:
        return "***"
    return f"{s[:4]}…{s[-4:]}"


def main() -> int:
    env_path = ROOT / ".env"
    if not env_path.is_file():
        print(f"❌ .env 없음: {env_path}")
        return _EXIT_ERROR

    try:
        from config.settings import (
            ROOT as PROJECT_ROOT,
            google_sheets_issues,
            is_dry_mode,
            list_env_file_key_names,
            reload_settings,
            resolve_service_account_path,
            resolve_summarizer_api_key,
        )
    except ImportError as exc:
        _print_runtime_error(exc)
        return _EXIT_ERROR

    try:
        settings = reload_settings()
        summ_key, summ_src = resolve_summarizer_api_key(settings.summarizer_provider)
        json_path = resolve_service_account_path(settings.google_service_account_json)
        issues = google_sheets_issues(settings)
        dry = is_dry_mode(settings, force_live=False)
        llm_keys = [
            k for k in list_env_file_key_names()
            if "API" in k.upper() or "GEMINI" in k.upper() or "SUMMARIZER" in k.upper()
        ]
        info = {
            "env_file": str(PROJECT_ROOT / ".env"),
            "env_exists": True,
            "dry_run_env": settings.dry_run,
            "has_toss": settings.has_toss,
            "toss_client_id": _mask(settings.toss_client_id),
            "trading_mode": "DRY" if dry else "LIVE",
            "briefing_enabled": settings.briefing_enabled,
            "summarizer_api_key_set": bool(summ_key),
            "summarizer_api_key_from": summ_src or "",
            "summarizer_api_key_masked": _mask(summ_key),
            "env_llm_key_names": llm_keys,
            "summarizer_provider": settings.summarizer_provider,
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

        config_ok = True
        if dry:
            print("\n⚠️ DRY 모드 — 실주문·실계좌 조회 안 함")
            if not settings.has_toss:
                print("   - TOSS_CLIENT_ID / TOSS_CLIENT_SECRET 확인")
            if settings.dry_run:
                print("   - .env DRY_RUN=false 또는 텔레그램 설정→💹 실거래 켜기")
            config_ok = False

        if issues:
            print("\n⚠️ Google Sheets 설정 미완료")
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
            config_ok = False

        if settings.briefing_enabled and not summ_key:
            print("\n💡 아침 브리핑 AI: SUMMARIZER_API_KEY 또는 GOOGLE_API_KEY(Gemini) 설정")
            if llm_keys:
                print(f"   .env 변수는 있음: {', '.join(llm_keys)} — 값·형식 확인")
        elif summ_key:
            print(f"\n✅ 브리핑 AI 키 인식 ({summ_src}) — {_mask(summ_key)}")

        if config_ok:
            print("\n✅ 설정 OK")
            print(f"   거래: {'LIVE' if not dry else 'DRY'}")
            if settings.has_google_sheets:
                print(f"   Sheets: {settings.google_sheets_link}")
            return _EXIT_OK

        return _EXIT_CONFIG
    except Exception as exc:
        _print_runtime_error(exc)
        return _EXIT_ERROR


if __name__ == "__main__":
    raise SystemExit(main())
