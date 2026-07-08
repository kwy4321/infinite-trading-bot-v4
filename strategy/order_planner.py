"""미국 장 마감 LOC — 토스 Open API LIMIT + CLS.

프리마켓(한국 18:00 KST)에 CLS 주문 접수 → 종가 경매에서 조건 충족 시 체결.
"""

from enum import Enum


class JobPhase(str, Enum):
    JOB1_LOC_CLOSE = "job1"   # /job1 수동 — job3와 동일
    JOB2_SETTLE = "job2"      # 예약 (미사용)
    JOB3_LOC_CLOSE = "job3"   # 장중 CLS 접수 (매수+매도)
    JOB4_REPORT = "job4"


# KST 일정 — LOC 접수는 프리마켓 18:00, 체결 반영은 새벽 job4
JOB_SCHEDULE_KST = {
    JobPhase.JOB4_REPORT: {"summer": (6, 15), "winter": (6, 15)},
    "morning_briefing": {"summer": (7, 0), "winter": (7, 0)},
    "premarket_loc": {"summer": (18, 0), "winter": (18, 0)},
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
    """DRY_RUN·종가 시뮬 — 종가 스냅샷으로 어떤 LOC가 체결됐을지 판정."""
    gated = gate_orders_by_close_price(filtered, close_price)
    picked = resolve_loc_side_conflict(gated)
    return picked["buy_orders"] + picked["sell_orders"]


def pick_loc_submit_side(filtered: dict, plan: dict) -> dict:
    """CLS 접수 시 매수·매도 동시 불가 — 전략상 한쪽만 제출."""
    buys = list(filtered.get("buy_orders") or [])
    sells = list(filtered.get("sell_orders") or [])
    if not buys or not sells:
        return {"buy_orders": buys, "sell_orders": sells}
    mode = str(plan.get("mode") or "")
    cur = float(plan.get("current_price") or 0)
    star = float(plan.get("star_price") or 0)
    if mode == "REVERSE" and sells:
        return {"buy_orders": [], "sell_orders": sells}
    if star > 0 and cur >= star and sells:
        return {"buy_orders": [], "sell_orders": sells}
    return {"buy_orders": buys, "sell_orders": []}


def prepare_loc_submit_orders(filtered: dict, plan: dict) -> list[dict]:
    """장중 CLS 접수용 — 계획 지정가 그대로, 종가는 거래소가 판정."""
    picked = pick_loc_submit_side(filtered, plan)
    return picked["buy_orders"] + picked["sell_orders"]
