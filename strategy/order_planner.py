"""LOC 대체 — 미국 장 마감(16:00 ET) 직전 지정가 DAY 주문.

토스 Open API에는 LOC가 없어, 장 마감 직전 LIMIT+DAY로 대체한다.
LOC 매도: 종가 >= 지정가일 때만 체결 (유리할 때).
매수·쿼터매도·익절매도 모두 같은 시각에 제출한다.
"""

from enum import Enum


class JobPhase(str, Enum):
    JOB1_LOC_CLOSE = "job1"   # /job1 수동 — job3와 동일
    JOB2_SETTLE = "job2"      # 예약 (미사용)
    JOB3_LOC_CLOSE = "job3"   # 장 마감 LOC (매수+매도 전체)
    JOB4_REPORT = "job4"


# KST = US 동부 16:00 장 마감 직전 (서머 05:00 / 윈터 06:00)
JOB_SCHEDULE_KST = {
    JobPhase.JOB3_LOC_CLOSE: {"summer": (5, 0), "winter": (6, 0)},
    JobPhase.JOB4_REPORT: {"summer": (6, 15), "winter": (6, 15)},
    "morning_briefing": {"summer": (7, 0), "winter": (7, 0)},
}


def filter_orders_for_phase(plan: dict, phase: JobPhase) -> dict:
    """장 마감 LOC — 매수·매도(쿼터+익절) 전부 같은 타이밍."""
    if phase in (JobPhase.JOB1_LOC_CLOSE, JobPhase.JOB3_LOC_CLOSE):
        return {
            "buy_orders": list(plan.get("buy_orders", [])),
            "sell_orders": list(plan.get("sell_orders", [])),
        }
    return {"buy_orders": [], "sell_orders": []}
