"""LOC/MOC 대체 — Job별 지정가 제출 시각 (KST)."""

from enum import Enum


class JobPhase(str, Enum):
    JOB1_TAKE_PROFIT = "job1"   # 17:00 / 18:00 pre-market
    JOB2_SETTLE = "job2"        # 23:00 / 00:00
    JOB3_BUY = "job3"           # 05:30
    JOB4_REPORT = "job4"        # 06:15


# summer/winter handled in executor via NY DST
JOB_SCHEDULE_KST = {
    JobPhase.JOB1_TAKE_PROFIT: {"summer": (17, 0), "winter": (18, 0)},
    JobPhase.JOB2_SETTLE: {"summer": (23, 0), "winter": (0, 0)},
    JobPhase.JOB3_BUY: {"summer": (5, 30), "winter": (5, 30)},
    JobPhase.JOB4_REPORT: {"summer": (6, 15), "winter": (6, 15)},
    "morning_briefing": {"summer": (7, 0), "winter": (7, 0)},
}


def filter_orders_for_phase(plan: dict, phase: JobPhase) -> dict:
    """Job 단계별로 넣을 주문만 필터."""
    if phase == JobPhase.JOB1_TAKE_PROFIT:
        return {"buy_orders": [], "sell_orders": [
            o for o in plan.get("sell_orders", [])
            if "익절" in o.get("desc", "")
        ]}
    if phase == JobPhase.JOB3_BUY:
        return {
            "buy_orders": plan.get("buy_orders", []),
            "sell_orders": [
                o for o in plan.get("sell_orders", [])
                if "익절" not in o.get("desc", "")
            ],
        }
    return {"buy_orders": [], "sell_orders": []}
