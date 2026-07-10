"""KST 기준 본장 개장 시각 테스트."""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from strategy.market_schedule import regular_open_kst
from strategy.session_fill import (
    has_us_session_fill_in_state,
    order_submitted_before_regular_open,
    regular_open_kst_fallback,
)

KST = ZoneInfo("Asia/Seoul")


class _FakeCycles:
    def __init__(self, trades: list | None = None):
        self._trades = trades or []

    def get_symbol_data(self, _symbol: str) -> dict:
        return {"current": {"trades": self._trades}}


def test_summer_open_is_2230_kst() -> None:
    open_kst = regular_open_kst("2026-07-10")
    assert open_kst == datetime(2026, 7, 10, 22, 30, tzinfo=KST)


def test_winter_open_is_2330_kst() -> None:
    open_kst = regular_open_kst("2026-01-15")
    assert open_kst == datetime(2026, 1, 15, 23, 30, tzinfo=KST)


def test_premarket_submission_before_open_blocks() -> None:
    """7/10 18:05(본장 전) 접수 → 7/10 본장 LOC 스킵."""
    open_kst = regular_open_kst("2026-07-10")
    entry = {
        "symbol": "SOXL",
        "qty": 1,
        "ordered_at": "2026-07-10T18:05:00+09:00",
    }
    assert order_submitted_before_regular_open(entry, "2026-07-10", open_kst)
    st = {"fill_log": [entry]}
    assert has_us_session_fill_in_state(st, "SOXL", "2026-07-10", _FakeCycles(), open_kst)


def test_previous_day_submission_does_not_block_today() -> None:
    """7/9 접수 → 7/10 본장 LOC 스킵에 안 걸림."""
    open_kst = regular_open_kst("2026-07-10")
    entry = {
        "symbol": "SOXL",
        "qty": 2,
        "ordered_at": "2026-07-09T18:05:00+09:00",
        "filled_at": "2026-07-10T05:30:00+09:00",
    }
    assert not order_submitted_before_regular_open(entry, "2026-07-10", open_kst)
    st = {"fill_log": [entry]}
    assert not has_us_session_fill_in_state(st, "SOXL", "2026-07-10", _FakeCycles(), open_kst)


def test_submission_after_open_does_not_block() -> None:
    entry = {
        "symbol": "SOXL",
        "qty": 1,
        "ordered_at": "2026-07-10T22:35:00+09:00",
    }
    open_kst = regular_open_kst("2026-07-10")
    assert not order_submitted_before_regular_open(entry, "2026-07-10", open_kst)


def test_fallback_matches_kst_schedule() -> None:
    assert regular_open_kst_fallback("2026-07-10") == regular_open_kst("2026-07-10")


def main() -> None:
    test_summer_open_is_2230_kst()
    test_winter_open_is_2330_kst()
    test_premarket_submission_before_open_blocks()
    test_previous_day_submission_does_not_block_today()
    test_submission_after_open_does_not_block()
    test_fallback_matches_kst_schedule()
    print("test_session_fill OK")


if __name__ == "__main__":
    main()
