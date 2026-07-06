"""미국 장 개장(09:30 ET) 시 LIMIT+DAY 예약 주문.

토스 Open API에는 LOC가 없어, 장 시작 시점에 전략 계획가로 지정가 DAY 주문을 넣는다.
장중 가격이 지정가에 도달하면 체결되고, 당일 미체결분은 자동 취소된다.
"""

from enum import Enum


class JobPhase(str, Enum):
    JOB1_LOC_CLOSE = "job1"   # /job1 수동 — job3와 동일
    JOB2_SETTLE = "job2"      # 예약 (미사용)
    JOB3_LOC_CLOSE = "job3"   # 장 개장 예약 주문 (매수+매도 전체)
    JOB4_REPORT = "job4"


# KST = US 동부 09:30 장 개장 (서머 22:30 / 윈터 23:30)
JOB_SCHEDULE_KST = {
    JobPhase.JOB3_LOC_CLOSE: {"summer": (22, 30), "winter": (23, 30)},
    JobPhase.JOB4_REPORT: {"summer": (6, 15), "winter": (6, 15)},
    "morning_briefing": {"summer": (7, 0), "winter": (7, 0)},
}


def filter_orders_for_phase(plan: dict, phase: JobPhase) -> dict:
    """장 개장 — 매수·매도(쿼터+익절) 전부 계획가로 예약."""
    if phase in (JobPhase.JOB1_LOC_CLOSE, JobPhase.JOB3_LOC_CLOSE):
        return {
            "buy_orders": list(plan.get("buy_orders", [])),
            "sell_orders": list(plan.get("sell_orders", [])),
        }
    return {"buy_orders": [], "sell_orders": []}
