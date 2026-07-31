#!/usr/bin/env python3
"""Toss OAuth token probe — run on VM: python scripts/probe_toss_token.py

토스가 실제로 돌려준 status/code/message 를 그대로 출력한다 (키 값은 마스킹).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from account.account import AccountPaths
from broker.toss_auth import BASE_URL
from config.settings import reload_settings
from config.toss_credentials import diagnose_toss_credentials


def _public_ip() -> str:
    """WTS 허용 IP 와 비교할 서버 공인 IP."""
    for url in ("https://api.ipify.org", "https://ifconfig.me/ip"):
        try:
            res = requests.get(url, timeout=5)
            if res.ok:
                return res.text.strip()
        except requests.RequestException:
            continue
    return "(확인 실패)"


def _raw_token_request(client_id: str, client_secret: str) -> dict:
    """마스킹 없이 토스 응답 본문을 그대로 수집."""
    try:
        res = requests.post(
            f"{BASE_URL}/oauth2/token",
            data={
                "grant_type": "client_credentials",
                "client_id": client_id,
                "client_secret": client_secret,
            },
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "Accept": "application/json",
            },
            timeout=20,
        )
    except requests.RequestException as exc:
        return {"transport_error": str(exc)}

    try:
        body = res.json()
    except ValueError:
        body = (res.text or "")[:400]

    if isinstance(body, dict) and body.get("access_token"):
        body = {
            "access_token": f"(발급 성공, {len(str(body['access_token']))}자)",
            "expires_in": body.get("expires_in"),
            "token_type": body.get("token_type"),
        }

    return {
        "status": res.status_code,
        "request_id": res.headers.get("X-Request-Id", ""),
        "rate_limit": res.headers.get("X-RateLimit-Limit", ""),
        "body": body,
    }


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    settings = reload_settings()
    cred = diagnose_toss_credentials(settings.toss_client_id, settings.toss_client_secret)
    paths = AccountPaths()

    out = {
        "public_ip": _public_ip(),
        "has_toss": settings.has_toss,
        "client_id": cred["client_id_masked"],
        "client_id_len": cred["client_id_len"],
        "client_secret": cred["client_secret_masked"],
        "client_secret_len": cred["client_secret_len"],
        "id_equals_secret": (
            bool(settings.toss_client_id)
            and settings.toss_client_id == settings.toss_client_secret
        ),
        "credential_notes": cred["notes"],
        "cache_path": str(paths.token_cache),
        "cache_exists": paths.token_cache.is_file(),
    }

    if settings.has_toss:
        out["toss_response"] = _raw_token_request(
            settings.toss_client_id,
            settings.toss_client_secret,
        )

    print(json.dumps(out, ensure_ascii=False, indent=2, default=str))

    resp = out.get("toss_response") or {}
    if resp.get("status") == 200:
        print("\n✅ 토큰 발급 성공 — 봇 재시작하면 반영됩니다.")
        return 0

    print("\n❌ 토큰 발급 실패")
    print("   위 toss_response.body 의 code/message 가 토스가 준 실제 사유입니다.")
    print(f"   허용 IP 확인: WTS 설정 > Open API > 허용 IP 관리 에 {out['public_ip']} 등록 필요")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
