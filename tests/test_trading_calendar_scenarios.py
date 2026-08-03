"""가상 시나리오 — 평일·전일 휴일·다음 휴일 매매 사이클·캘린더 게이트."""

from __future__ import annotations

import datetime
from zoneinfo import ZoneInfo

import pytest

from broker.toss_client import TossClient
from briefing.market_context import get_briefing_market_context, should_skip_scheduled_briefing
from core.clock import KST, loc_auto_submit_kst
from cycles.cycle_tracker import CycleTracker
from strategy.fill_processor import FillProcessor
from strategy.session_fill import has_us_session_fill_in_state

KST_TZ = KST


def _rm(enabled: bool) -> dict | None:
    if not enabled:
        return None
    return {"startTime": "23:30", "endTime": "06:00"}


def make_us_calendar(
    *,
    today: str,
    next_bd: str,
    prev_bd: str,
    open_today: bool = True,
    open_next: bool = True,
    open_prev: bool = True,
) -> dict:
    return {
        "today": {"date": today, "regularMarket": _rm(open_today)},
        "nextBusinessDay": {"date": next_bd, "regularMarket": _rm(open_next)},
        "previousBusinessDay": {"date": prev_bd, "regularMarket": _rm(open_prev)},
    }


class CalendarBroker:
    """HTTP 없이 TossClient 캘린더 메서드만 검증."""

    dry_run = False

    def __init__(self, cal: dict):
        self._cal = cal

    def get_us_market_calendar(self) -> dict:
        return self._cal

    def check_us_regular_session(self, target_date: str) -> tuple[bool, str, bool]:
        return TossClient.check_us_regular_session(self, target_date)

    def is_us_market_open_today(
        self, kst_now: datetime.datetime | None = None,
    ) -> bool:
        return TossClient.is_us_market_open_today(self, kst_now)


def _kst(y: int, m: int, d: int, hour: int = 18, minute: int = 5) -> datetime.datetime:
    return datetime.datetime(y, m, d, hour, minute, tzinfo=KST_TZ)


# ── 평일 (감사절 전 수요일) ──────────────────────────────────────────────

WED_PRE_HOLIDAY = make_us_calendar(
    today="2026-11-25",
    next_bd="2026-11-26",
    prev_bd="2026-11-24",
    open_today=True,
    open_next=False,
    open_prev=True,
)

THU_HOLIDAY = make_us_calendar(
    today="2026-11-26",
    next_bd="2026-11-27",
    prev_bd="2026-11-25",
    open_today=False,
    open_next=True,
    open_prev=True,
)

FRI_POST_HOLIDAY = make_us_calendar(
    today="2026-11-27",
    next_bd="2026-11-30",
    prev_bd="2026-11-25",
    open_today=True,
    open_next=True,
    open_prev=True,
)


class TestWeekdayScenario:
    """평일 — 18:05 LOC·계획 브로드캐스트 허용."""

    def test_evening_loc_target_is_kst_date(self):
        when = _kst(2026, 11, 25)
        assert TossClient.target_us_date_for_evening_loc(when) == "2026-11-25"

    def test_regular_session_open_on_weekday(self):
        broker = CalendarBroker(WED_PRE_HOLIDAY)
        open_, us_date, ok = broker.check_us_regular_session("2026-11-25")
        assert ok and open_ and us_date == "2026-11-25"

    def test_market_open_today_at_1805(self):
        broker = CalendarBroker(WED_PRE_HOLIDAY)
        assert broker.is_us_market_open_today(_kst(2026, 11, 25, 18, 5))

    def test_briefing_runs_tuesday_morning(self):
        assert not should_skip_scheduled_briefing(_kst(2026, 11, 24, 7, 0))


class TestNextDayHolidayScenario:
    """다음 날 휴일 — 오늘 저녁 LOC는 실행, 내일 저녁은 스킵."""

    def test_today_evening_runs_before_holiday(self):
        broker = CalendarBroker(WED_PRE_HOLIDAY)
        target = TossClient.target_us_date_for_evening_loc(_kst(2026, 11, 25, 18, 5))
        open_, _, ok = broker.check_us_regular_session(target)
        assert ok and open_

    def test_tomorrow_evening_skips_on_holiday(self):
        broker = CalendarBroker(THU_HOLIDAY)
        target = TossClient.target_us_date_for_evening_loc(_kst(2026, 11, 26, 18, 5))
        open_, _, ok = broker.check_us_regular_session(target)
        assert ok and not open_

    def test_is_us_market_open_false_on_holiday_evening(self):
        broker = CalendarBroker(THU_HOLIDAY)
        assert not broker.is_us_market_open_today(_kst(2026, 11, 26, 18, 0))

    def test_next_business_day_detected_as_closed(self):
        broker = CalendarBroker(WED_PRE_HOLIDAY)
        open_, us_date, ok = broker.check_us_regular_session("2026-11-26")
        assert ok and not open_ and us_date == "2026-11-26"


class TestPreviousDayHolidayScenario:
    """전일 휴일 — 복귀 첫 거래일 저녁 LOC·브리핑 정상."""

    def test_post_holiday_evening_runs(self):
        broker = CalendarBroker(FRI_POST_HOLIDAY)
        target = TossClient.target_us_date_for_evening_loc(_kst(2026, 11, 27, 18, 5))
        open_, _, ok = broker.check_us_regular_session(target)
        assert ok and open_

    def test_briefing_after_holiday_uses_prev_close(self):
        # KST 금 07:00 = NY 목 17:00 — API today=목(휴일), prev=수(마감)
        broker = CalendarBroker(THU_HOLIDAY)
        ctx = get_briefing_market_context(broker, _kst(2026, 11, 27, 7, 0))
        assert ctx["session_date"] == "2026-11-25"
        assert ctx["us_holiday"] is True
        assert ctx["holiday_date"] == "2026-11-26"

    def test_briefing_saturday_shows_friday_session(self):
        broker = CalendarBroker(FRI_POST_HOLIDAY)
        ctx = get_briefing_market_context(broker, _kst(2026, 11, 28, 7, 0))
        assert ctx["session_date"] == "2026-11-27"
        assert ctx["us_holiday"] is False

    def test_briefing_weekday_shows_just_closed_session(self):
        """KST 화 07:00 = NY 월 마감 직후 → 월요일 세션."""
        cal = make_us_calendar(
            today="2026-11-30",
            next_bd="2026-12-01",
            prev_bd="2026-11-27",
            open_today=True,
            open_next=True,
            open_prev=True,
        )
        broker = CalendarBroker(cal)
        ctx = get_briefing_market_context(broker, _kst(2026, 12, 1, 7, 0))
        assert ctx["session_date"] == "2026-11-30"


class TestCalendarFailClosed:
    """캘린더 3일 윈도 밖 target — today 폴백 대신 휴장 처리."""

    def test_unknown_target_date_is_closed(self):
        cal = make_us_calendar(
            today="2026-11-25",
            next_bd="2026-11-26",
            prev_bd="2026-11-24",
        )
        broker = CalendarBroker(cal)
        open_, us_date, ok = broker.check_us_regular_session("2026-12-01")
        assert ok and not open_ and us_date == "2026-12-01"


class TestSessionFillAcrossDays:
    """매매 사이클 — 평일 체결 후 휴일·복귀일 중복 LOC 방지."""

    @pytest.fixture
    def cycle_setup(self, tmp_path):
        cycles = CycleTracker(data_dir=tmp_path)
        processor = FillProcessor()
        state = {
            "T": 0.0,
            "qty": 0,
            "avg_price": 0.0,
            "principal": 10000.0,
            "split_count": 40,
            "fill_log": [],
        }
        return cycles, processor, state

    def _buy(self, processor, state, cycles, us_date: str, hour: int = 18, minute: int = 5):
        ordered = f"{us_date}T{hour:02d}:{minute:02d}:00+09:00"
        order = {
            "qty": 2,
            "price": 50.0,
            "action": "STAR_BUY",
            "ordered_at": ordered,
            "desc": "별 매수",
        }
        processor.apply_buy_fill(state, order, cycles, "TQQQ")
        state.setdefault("fill_log", []).append(
            {"symbol": "TQQQ", "qty": 2, "ordered_at": ordered},
        )

    def test_weekday_buy_then_holiday_no_duplicate_block(self, cycle_setup):
        """수요일 매수 → 목요일(휴일) — fill_log가 수요일이라 목요일 자동 LOC는 막히지 않음."""
        cycles, processor, state = cycle_setup
        self._buy(processor, state, cycles, "2026-11-25")
        submit_kst = loc_auto_submit_kst("2026-11-26")
        assert not has_us_session_fill_in_state(
            state, "TQQQ", "2026-11-26", cycles, submit_kst,
        )

    def test_same_day_early_submit_blocks_auto_loc(self, cycle_setup):
        """당일 18:00 수동 접수 → 18:05 자동 스킵."""
        cycles, processor, state = cycle_setup
        entry = {
            "symbol": "TQQQ",
            "qty": 1,
            "ordered_at": "2026-11-25T18:00:00+09:00",
        }
        state["fill_log"] = [entry]
        submit_kst = loc_auto_submit_kst("2026-11-25")
        assert has_us_session_fill_in_state(
            state, "TQQQ", "2026-11-25", cycles, submit_kst,
        )

    def test_post_holiday_resumes_cycle(self, cycle_setup):
        """휴일 전 매수 → 복귀일 추가 매수 — T·수량 누적."""
        cycles, processor, state = cycle_setup
        self._buy(processor, state, cycles, "2026-11-25")
        t_after_first = state["T"]
        self._buy(processor, state, cycles, "2026-11-27")
        assert state["qty"] == 4
        assert state["T"] > t_after_first
        cur = cycles.get_symbol_data("TQQQ")["current"]
        assert cur["buy_count"] == 2


class TestTradingDayHelpers:
    """KST↔US 거래일 키 일관성."""

    def test_evening_loc_equals_morning_job(self):
        when = _kst(2026, 7, 14, 6, 15)
        assert (
            TossClient.target_us_date_for_evening_loc(when)
            == TossClient.target_us_date_for_morning_job(when)
        )

    def test_loc_submit_time_is_1805_kst(self):
        dt = loc_auto_submit_kst("2026-11-25")
        assert dt.hour == 18 and dt.minute == 5
        assert dt.tzinfo is KST_TZ
