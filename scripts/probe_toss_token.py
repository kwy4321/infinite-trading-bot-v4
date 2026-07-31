#!/usr/bin/env python3
"""Toss OAuth token probe — run on VM: python scripts/probe_toss_token.py"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from account.account import AccountPaths
from broker.rate_limiter import RateLimiter
from broker.toss_auth import TossAuth
from config.settings import reload_settings


def main() -> int:
    settings = reload_settings()
    paths = AccountPaths()
    auth = TossAuth(
        settings.toss_client_id,
        settings.toss_client_secret,
        paths.token_cache,
        RateLimiter(),
    )
    auth.sync_credentials(settings.toss_client_id, settings.toss_client_secret)

    out = {
        "has_toss": settings.has_toss,
        "client_id_len": len(settings.toss_client_id or ""),
        "client_secret_len": len(settings.toss_client_secret or ""),
        "cache_path": str(paths.token_cache),
        "cache_exists": paths.token_cache.is_file(),
        "status_before": auth.get_status(),
        "probe": auth.probe_refresh(),
    }
    if out["probe"].get("ok"):
        out["status_after_refresh"] = auth.force_refresh()
    print(json.dumps(out, ensure_ascii=False, indent=2, default=str))
    return 0 if out["probe"].get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
