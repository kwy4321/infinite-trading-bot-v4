"""Unit checks for Toss OAuth cache helpers (no network)."""

import datetime
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from broker.toss_auth import TossAuth, _expires_at_from_ttl, _parse_iso_datetime
from broker.rate_limiter import RateLimiter


def test_parse_iso_z_suffix() -> None:
    dt = _parse_iso_datetime("2026-07-31T11:42:00Z")
    assert dt.tzinfo is not None


def test_expires_at_minimum_one_second() -> None:
    before = datetime.datetime.now().astimezone()
    exp = _expires_at_from_ttl(0)
    assert (exp - before).total_seconds() >= 1


def test_expires_at_respects_early_refresh() -> None:
    before = datetime.datetime.now().astimezone()
    exp = _expires_at_from_ttl(3600)
    delta = (exp - before).total_seconds()
    assert 3500 <= delta <= 3600


def test_cache_roundtrip() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        cache = Path(tmp) / "token_cache.json"
        auth = TossAuth("id", "secret", cache, RateLimiter())
        token = "abc123"
        exp = _expires_at_from_ttl(7200)
        auth._save_cache(token, exp)
        auth2 = TossAuth("id", "secret", cache, RateLimiter())
        loaded, loaded_exp = auth2._read_cache_file()
        assert loaded == token
        assert loaded_exp is not None
        assert abs((loaded_exp - exp).total_seconds()) < 2


def test_sync_credentials() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        cache = Path(tmp) / "token_cache.json"
        auth = TossAuth("", "", cache, RateLimiter())
        auth.sync_credentials("  cid  ", " sec ")
        assert auth.client_id == "cid"
        assert auth.client_secret == "sec"


def test_force_refresh_keeps_cache_on_failure() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        cache = Path(tmp) / "token_cache.json"
        auth = TossAuth("id", "secret", cache, RateLimiter())
        exp = _expires_at_from_ttl(7200)
        auth._apply_token("keep-me", exp)

        def _boom():
            raise ValueError("network down")

        auth._request_token = _boom  # type: ignore[method-assign]
        result = auth.force_refresh()
        assert result["reason"] == "refresh_failed"
        assert result.get("remaining_seconds", 0) > 0
        assert auth.get_token() == "keep-me"


def test_sync_credentials_clears_cache_on_change() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        cache = Path(tmp) / "token_cache.json"
        auth = TossAuth("c_old", "s_old", cache, RateLimiter())
        exp = _expires_at_from_ttl(7200)
        auth._apply_token("old-token", exp)
        auth.sync_credentials("c_new123456", "s_newsecret1234567890")
        assert auth.client_id == "c_new123456"
        assert not cache.exists()
        assert auth.get_status()["reason"] == "missing"


def main() -> int:
    test_parse_iso_z_suffix()
    test_expires_at_minimum_one_second()
    test_expires_at_respects_early_refresh()
    test_cache_roundtrip()
    test_sync_credentials()
    test_sync_credentials_clears_cache_on_change()
    test_force_refresh_keeps_cache_on_failure()
    print("test_toss_auth_helpers: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
