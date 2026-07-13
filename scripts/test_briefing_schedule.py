"""브리핑 스킵 로직 단위 테스트."""

from __future__ import annotations

import datetime
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from briefing.market_context import should_skip_scheduled_briefing

KST = ZoneInfo("Asia/Seoul")


def _kst(y, m, d, hour=7) -> datetime.datetime:
    return datetime.datetime(y, m, d, hour, 0, tzinfo=KST)


def test_skip_sunday_morning() -> None:
    assert should_skip_scheduled_briefing(_kst(2026, 7, 12))  # Sun


def test_skip_monday_morning() -> None:
    assert should_skip_scheduled_briefing(_kst(2026, 7, 13))  # Mon


def test_run_tuesday_morning() -> None:
    assert not should_skip_scheduled_briefing(_kst(2026, 7, 14))  # Tue


def test_run_saturday_morning() -> None:
    assert not should_skip_scheduled_briefing(_kst(2026, 7, 11))  # Sat (금요일 마감)


def main() -> None:
    test_skip_sunday_morning()
    test_skip_monday_morning()
    test_run_tuesday_morning()
    test_run_saturday_morning()
    print("test_briefing_schedule OK")


if __name__ == "__main__":
    main()
