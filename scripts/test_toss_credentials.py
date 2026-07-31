"""Unit checks for Toss credential normalize/diagnose (no network)."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from config.toss_credentials import (
    diagnose_toss_credentials,
    normalize_toss_credentials,
    toss_env_alias_conflicts,
)


def test_normalize_strips_quotes() -> None:
    cid, sec, notes = normalize_toss_credentials('"c_abc123"', "'s_secret456'")
    assert cid == "c_abc123"
    assert sec == "s_secret456"
    assert not notes


def test_swap_detected() -> None:
    cid, sec, notes = normalize_toss_credentials("s_secret456", "c_abc123")
    assert cid == "c_abc123"
    assert sec == "s_secret456"
    assert any("뒤바뀜" in n for n in notes)


def test_diagnose_format_ok() -> None:
    d = diagnose_toss_credentials("c_live_abc", "s_live_xyz")
    assert d["id_format_ok"]
    assert d["secret_format_ok"]
    assert d["has_toss"]


def test_diagnose_wrong_slot() -> None:
    d = diagnose_toss_credentials("s_only_secret", "c_only_id")
    assert d["id_format_ok"]
    assert d["secret_format_ok"]


def test_strip_trailing_comma() -> None:
    cid, sec, _ = normalize_toss_credentials("c_abc123,", "s_secret456;")
    assert cid == "c_abc123"
    assert sec == "s_secret456"


def test_alias_conflict_detected() -> None:
    notes = toss_env_alias_conflicts({
        "TOSS_CLIENT_ID": "c_old",
        "TOSS_API_KEY": "c_new",
    })
    assert notes


def main() -> int:
    test_normalize_strips_quotes()
    test_swap_detected()
    test_diagnose_format_ok()
    test_diagnose_wrong_slot()
    test_strip_trailing_comma()
    test_alias_conflict_detected()
    print("test_toss_credentials: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
