"""session_fill — 18:05 KST LOC 스킵 판별 단위 테스트."""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from strategy.market_schedule import loc_auto_submit_kst
from strategy.session_fill import (
    has_us_session_fill_in_state,
    order_submitted_before_regular_open,
    regular_open_kst_fallback,
)

KST = ZoneInfo("Asia/Seoul")
SUBMIT_KST = datetime(2026, 7, 10, 18, 5, tzinfo=KST)


class _FakeCycles:
    def __init__(self, trades: list | None = None):
        self._trades = trades or []

    def get_symbol_data(self, _symbol: str) -> dict:
        return {"current": {"trades": self._trades}}


def test_loc_auto_submit_is_1805_kst() -> None:
    assert loc_auto_submit_kst("2026-07-10") == SUBMIT_KST


def test_early_submission_blocks_auto_run() -> None:
    """7/10 18:00 접수 → 18:05 자동접수 스킵."""
    entry = {
        "symbol": "SOXL",
        "qty": 1,
        "ordered_at": "2026-07-10T18:00:00+09:00",
    }
    assert order_submitted_before_regular_open(entry, "2026-07-10", SUBMIT_KST)
    st = {"fill_log": [entry]}
    assert has_us_session_fill_in_state(st, "SOXL", "2026-07-10", _FakeCycles(), SUBMIT_KST)


def test_previous_day_submission_does_not_block_today() -> None:
    """7/9 접수 → 7/10 18:05 스킵에 안 걸림."""
    entry = {
        "symbol": "SOXL",
        "qty": 2,
        "ordered_at": "2026-07-09T18:05:00+09:00",
        "filled_at": "2026-07-10T05:30:00+09:00",
    }
    assert not order_submitted_before_regular_open(entry, "2026-07-10", SUBMIT_KST)
    st = {"fill_log": [entry]}
    assert not has_us_session_fill_in_state(st, "SOXL", "2026-07-10", _FakeCycles(), SUBMIT_KST)


def test_submission_at_1805_does_not_block() -> None:
    """18:05 접수는 '18:05 이전' 스킵에 해당하지 않음."""
    entry = {
        "symbol": "SOXL",
        "qty": 1,
        "ordered_at": "2026-07-10T18:05:00+09:00",
    }
    assert not order_submitted_before_regular_open(entry, "2026-07-10", SUBMIT_KST)


def test_dawn_fill_without_order_time_does_not_block() -> None:
    entry = {
        "symbol": "SOXL",
        "qty": 2,
        "filled_at": "2026-07-10T05:30:00+09:00",
    }
    assert not order_submitted_before_regular_open(entry, "2026-07-10", SUBMIT_KST)


def test_fallback_matches_schedule() -> None:
    assert regular_open_kst_fallback("2026-07-10") == loc_auto_submit_kst("2026-07-10")


def main() -> None:
    test_loc_auto_submit_is_1805_kst()
    test_early_submission_blocks_auto_run()
    test_previous_day_submission_does_not_block_today()
    test_submission_at_1805_does_not_block()
    test_dawn_fill_without_order_time_does_not_block()
    test_fallback_matches_schedule()
    print("test_session_fill OK")


if __name__ == "__main__":
    main()
