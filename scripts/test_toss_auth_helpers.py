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


def main() -> int:
    test_parse_iso_z_suffix()
    test_expires_at_minimum_one_second()
    test_expires_at_respects_early_refresh()
    test_cache_roundtrip()
    print("test_toss_auth_helpers: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
