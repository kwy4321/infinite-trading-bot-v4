"""LOC 대체 — 미국 장 마감(16:00 ET) 직전 지정가 DAY 주문.

토스 Open API에는 LOC가 없어, 장 마감 직전 LIMIT+DAY로 대체한다.
LOC 매도: 종가 >= 지정가일 때만 체결 (유리할 때).
매수·쿼터매도·익절매도 모두 같은 시각에 제출한다.
"""

from enum import Enum

# 장 마감 몇 초 전에 주문을 넣을지 (종가 근사 스냅샷 시점).
# 30초면 종가와 가격차는 미미하면서 통신·재시도 여유가 충분하다.
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
    """종가 근사가(price)로 LOC를 흉내낸다 — 평단가·별값 매매를 그대로 반영.

    각 주문은 자기 LOC 기준가(order["price"])를 들고 있다:
      · 평단가 매수  → 기준가 = 평단가
      · 별값 매수    → 기준가 = 별값(별% 적용가)
      · 큰수매수(T=0 첫 매수) → 기준가 = 현재가 × (1+%)
      · 하단방어 → 기준가 = 평단가 × (1−%)
      · 쿼터 매도    → 기준가 = 별값
      · 익절 매도    → 기준가 = 평단 + 익절%

    매수: 종가 <= 기준가 일 때만 체결 (종가가 사기로 한 값 이하면 산다)
    매도: 종가 >= 기준가 일 때만 체결 (종가가 팔기로 한 값 이상이면 판다)
    price<=0 (가격 미상·DRY)면 게이트 없이 그대로 둔다.
    """
    if price <= 0:
        return {
            "buy_orders": list(filtered.get("buy_orders", [])),
            "sell_orders": list(filtered.get("sell_orders", [])),
        }
    buys = [o for o in filtered.get("buy_orders", []) if price <= o["price"]]
    sells = [o for o in filtered.get("sell_orders", []) if price >= o["price"]]
    return {"buy_orders": buys, "sell_orders": sells}
