#!/usr/bin/env python3
"""Toss OAuth token probe — run on VM: python scripts/probe_toss_token.py

토스가 실제로 돌려준 status/code/message + 캐시 저장까지 확인.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from account.account import AccountPaths
from broker.rate_limiter import RateLimiter
from broker.toss_auth import BASE_URL, TossAuth
from config.network import fetch_public_ip
from config.settings import reload_settings
from config.toss_credentials import diagnose_toss_credentials


def _public_ip() -> str:
    return fetch_public_ip() or "(확인 실패)"


def _raw_token_request(client_id: str, client_secret: str) -> dict:
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
    auth = TossAuth(
        settings.toss_client_id,
        settings.toss_client_secret,
        paths.token_cache,
        RateLimiter(),
    )

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
        "cache_exists_before": paths.token_cache.is_file(),
    }

    if settings.has_toss:
        out["toss_response"] = _raw_token_request(
            settings.toss_client_id,
            settings.toss_client_secret,
        )
        try:
            auth.ensure_token_status()
            token_status = auth.get_status()
            out["cache_saved"] = paths.token_cache.is_file()
            out["status_after"] = token_status
        except Exception as exc:
            out["cache_error"] = str(exc)

    print(json.dumps(out, ensure_ascii=False, indent=2, default=str))

    resp = out.get("toss_response") or {}
    ok = resp.get("status") == 200 and out.get("cache_saved")

    if ok:
        print("\n✅ 토큰 발급·캐시 저장 성공")
        print(f"   이 서버 IP({out['public_ip']})가 WTS 허용 IP에 등록돼 있어야 봇도 동작합니다.")
        print("   Cloud Shell에서 실행했다면 VM 반영: bash scripts/cloudshell_bot.sh restart")
        return 0

    print("\n❌ 토큰 발급/캐시 실패")
    if resp.get("body"):
        print("   toss_response.body = 토스가 준 실제 사유")
    print(f"   WTS 허용 IP에 이 서버 IP 등록: {out['public_ip']}")
    print("   Cloud Shell 성공 + VM 실패 → VM IP도 따로 등록 + cloudshell_bot.sh restart")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
