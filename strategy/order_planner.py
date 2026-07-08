"""미국 장 마감 LOC — 토스 Open API LIMIT + CLS.

LIVE: 계획된 지정가로 CLS 주문 제출, 종가 경매에서 조건 충족 시 체결.
DRY_RUN: 종가 근사가로 gate_orders_by_close_price 시뮬레이션.
매수·쿼터매도·익절매도 모두 같은 시각(한국 새벽, 미국 종가)에 제출한다.
"""

from enum import Enum

# 장 마감 몇 초 전에 주문을 넣을지 (종가 근사 스냅샷 시점).
CLOSE_LEAD_SECONDS = 30


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
    "market_open_plan": {"summer": (22, 30), "winter": (23, 30)},
}


def filter_orders_for_phase(plan: dict, phase: JobPhase) -> dict:
    """장 마감 LOC — 매수·매도(쿼터+익절) 전부 같은 타이밍."""
    if phase in (JobPhase.JOB1_LOC_CLOSE, JobPhase.JOB3_LOC_CLOSE):
        return {
            "buy_orders": list(plan.get("buy_orders", [])),
            "sell_orders": list(plan.get("sell_orders", [])),
        }
    return {"buy_orders": [], "sell_orders": []}


def gate_orders_by_close_price(filtered: dict, price: float) -> dict:
    """종가 근사가(price)로 LOC 조건 판정 — 매수 limit 이상·매도 limit 이하일 때 통과."""
    if price <= 0:
        return {"buy_orders": [], "sell_orders": []}
    buys = [o for o in filtered.get("buy_orders", []) if price <= o["price"]]
    sells = [o for o in filtered.get("sell_orders", []) if price >= o["price"]]
    return {"buy_orders": buys, "sell_orders": sells}


def resolve_loc_side_conflict(gated: dict) -> dict:
    """매수·매도 LOC가 동시에 조건 충족 시 매도 우선 — 토스 opposite-pending(422) 방지."""
    buys = list(gated.get("buy_orders") or [])
    sells = list(gated.get("sell_orders") or [])
    if buys and sells:
        return {"buy_orders": [], "sell_orders": sells}
    return {"buy_orders": buys, "sell_orders": sells}


def prepare_loc_orders(filtered: dict, close_price: float) -> list[dict]:
    """종가 스냅샷 기준 LOC 제출 목록 (LIVE·DRY_RUN 공통)."""
    gated = gate_orders_by_close_price(filtered, close_price)
    picked = resolve_loc_side_conflict(gated)
    return picked["buy_orders"] + picked["sell_orders"]
