"""Toss Open API — token issue, file cache, refresh, 401 retry test."""

import datetime
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

from account.account import AccountPaths
from broker.rate_limiter import RateLimiter
from broker.toss_auth import TossAuth
from broker.toss_client import TossClient


def _token_hint(token: str) -> str:
    if len(token) <= 12:
        return "(too short)"
    return f"{token[:8]}...{token[-4:]}"


def _read_cache(path: Path) -> dict | None:
    if not path.exists():
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")

    client_id = os.getenv("TOSS_CLIENT_ID", "").strip()
    client_secret = os.getenv("TOSS_CLIENT_SECRET", "").strip()
    account_seq = os.getenv("TOSS_ACCOUNT_SEQ", "1").strip()
    dry_run = os.getenv("DRY_RUN", "false").lower() == "true"

    if not client_id or not client_secret:
        print("ERROR: TOSS_CLIENT_ID / TOSS_CLIENT_SECRET 가 .env 에 없습니다.")
        return 1

    paths = AccountPaths()
    cache_path = paths.token_cache
    limiter = RateLimiter()

    print("=== Toss API 토큰 테스트 ===")
    print(f"cache: {cache_path}")
    print(f"DRY_RUN={dry_run} (API 호출 테스트는 DRY_RUN=false 일 때만)")
    print()

    # --- 1) 신규 발급 ---
    if cache_path.exists():
        cache_path.unlink()
        print("[1/5] 기존 token_cache.json 삭제")

    print(f"client_id: {_token_hint(client_id)} (len={len(client_id)})")
    print()

    auth = TossAuth(client_id, client_secret, cache_path, limiter)
    try:
        t1 = auth.get_token()
    except Exception as exc:
        print(f"[1/5] FAIL — 토큰 발급: {exc}")
        print()
        print("확인:")
        print("  1) VM .env 의 TOSS_CLIENT_ID / TOSS_CLIENT_SECRET (PC .env 와 별개)")
        print("  2) 따옴표·공백 없이 한 줄 (예: TOSS_CLIENT_ID=tsck_live_...)")
        print("  3) 토스 Open API 콘솔에서 키 재발급·앱 활성 상태")
        return 1
    cached = _read_cache(cache_path)
    if not cached or "expires_at" not in cached:
        print("[1/5] FAIL — cache 파일 생성 안 됨")
        return 1
    print(f"[1/5] OK — 신규 토큰 발급 {_token_hint(t1)}")
    print(f"       expires_at: {cached['expires_at']}")

    # --- 2) 메모리 캐시 재사용 ---
    t2 = auth.get_token()
    if t1 != t2:
        print("[2/5] FAIL — 연속 get_token() 결과가 다름 (캐시 미사용?)")
        return 1
    print(f"[2/5] OK — 메모리 캐시 재사용 {_token_hint(t2)}")

    # --- 3) 파일 캐시에서 로드 ---
    auth2 = TossAuth(client_id, client_secret, cache_path, limiter)
    t3 = auth2.get_token()
    if t3 != t1:
        print("[3/5] FAIL — 재시작 후 파일 캐시 토큰 불일치")
        return 1
    print(f"[3/5] OK — 새 TossAuth 인스턴스가 파일 캐시 로드 {_token_hint(t3)}")

    # --- 4) invalidate 후 재발급 ---
    auth.invalidate()
    if cache_path.exists():
        cache_path.unlink()
    t4 = auth.get_token()
    if not t4:
        print("[4/5] FAIL — invalidate 후 재발급 실패")
        return 1
    print(f"[4/5] OK — invalidate + 재발급 {_token_hint(t4)}")

    if dry_run:
        print()
        print("[5/5] SKIP — DRY_RUN=true 이라 API 호출·401 재시도 테스트 생략")
        print()
        print("토큰 발급·캐시 테스트 통과.")
        print("API까지 확인: .env 에 DRY_RUN=false 후 다시 실행")
        return 0

    # --- 5) API 호출 + 401 재시도 ---
    broker = TossClient(auth, account_seq, limiter, dry_run=False)
    print("[5/5] API 호출 (buying-power)...")
    try:
        buying = broker.get_buying_power("USD")
        cash = buying.get("cashBuyingPower", buying)
        print(f"       OK — cashBuyingPower: {cash}")
    except Exception as exc:
        print(f"[5/5] FAIL — API 호출: {exc}")
        return 1

    print("[5/5] 401 재시도 시뮬레이션 (만료 토큰 주입)...")
    auth._token = "invalid-token-for-refresh-test"
    auth._expires_at = datetime.datetime.now().astimezone() + datetime.timedelta(hours=1)
    try:
        buying2 = broker.get_buying_power("USD")
        cash2 = buying2.get("cashBuyingPower", buying2)
        print(f"       OK — 401 후 재발급·재시도 성공, cashBuyingPower: {cash2}")
    except Exception as exc:
        print(f"[5/5] FAIL — 401 재시도: {exc}")
        return 1

    print()
    print("Toss API 토큰 테스트 전부 통과.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
