"""session_fill — 저녁 LOC 스킵 판별 단위 테스트."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from strategy.session_fill import fill_blocks_evening_loc, has_us_session_fill_in_state


class _FakeCycles:
    def __init__(self, trades: list | None = None):
        self._trades = trades or []

    def get_symbol_data(self, _symbol: str) -> dict:
        return {"current": {"trades": self._trades}}


def test_dawn_fill_from_previous_evening_loc_does_not_block_today() -> None:
    """7/9 18:05 접수 → 7/10 새벽 체결은 7/10 저녁 LOC 스킵에 안 걸림."""
    entry = {
        "symbol": "SOXL",
        "qty": 2,
        "ordered_at": "2026-07-09T18:05:00+09:00",
        "filled_at": "2026-07-10T05:30:00+09:00",
    }
    assert not fill_blocks_evening_loc(entry, "2026-07-10")
    st = {"fill_log": [entry]}
    assert not has_us_session_fill_in_state(st, "SOXL", "2026-07-10", _FakeCycles())


def test_same_day_evening_loc_blocks_duplicate() -> None:
    """7/10 18:05 접수분은 7/10 저녁 LOC 중복 스킵."""
    entry = {
        "symbol": "SOXL",
        "qty": 1,
        "ordered_at": "2026-07-10T18:06:00+09:00",
        "filled_at": "2026-07-11T05:30:00+09:00",
    }
    assert fill_blocks_evening_loc(entry, "2026-07-10")
    st = {"fill_log": [entry]}
    assert has_us_session_fill_in_state(st, "SOXL", "2026-07-10", _FakeCycles())


def test_dawn_only_timestamp_on_target_us_date_does_not_block() -> None:
    """ET 기준 당일 체결이라도 새벽(18시 전)이면 스킵 안 함."""
    entry = {
        "symbol": "SOXL",
        "qty": 2,
        "filled_at": "2026-07-10T05:30:00+09:00",
    }
    assert not fill_blocks_evening_loc(entry, "2026-07-10")


def main() -> None:
    test_dawn_fill_from_previous_evening_loc_does_not_block_today()
    test_same_day_evening_loc_blocks_duplicate()
    test_dawn_only_timestamp_on_target_us_date_does_not_block()
    print("test_session_fill OK")


if __name__ == "__main__":
    main()
