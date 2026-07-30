"""리버스 모드 V4.0 PDF 검증."""
from __future__ import annotations

from strategy.strategy_v40 import (
    REVERSE_BUY,
    REVERSE_SELL,
    REVERSE_SELL_FIRST,
    InfiniteStrategyV40,
    TradingMode,
)

s = InfiniteStrategyV40()
SPLIT = 40
QTY = 200
AVG = 45.0
CURRENT = 42.0
CLOSES = [{"date": f"d{i}", "close": 40.0 + i * 0.5} for i in range(5)]


def run() -> None:
    print("=" * 60)
    print("V4.0 리버스 검증 (40분할, 200주, T=39.5 소진 직후)")
    print("=" * 60)

    # T 공식
    t = 39.5
    t_sell = s.calc_next_t(t, REVERSE_SELL_FIRST, SPLIT)
    t_buy = s.calc_next_t(t_sell, REVERSE_BUY, SPLIT)
    print(f"\n[T] {t} --MOC매도--> {t_sell:.4f}  (기대 37.525)")
    print(f"[T] {t_sell:.4f} --쿼터매수--> {t_buy:.4f}  (기대 38.1438)")
    ok_t = abs(t_sell - 37.525) < 0.001 and abs(t_buy - 38.14375) < 0.001
    print(f"  [{'OK' if ok_t else 'NG'}] T 공식")

    # 매도 수량
    sq = s.calc_reverse_sell_qty(QTY, SPLIT)
    print(f"\n[매도] 200주 ÷ 20 = {sq}주  (첫날·이후 동일 비율)")
    print(f"  [{'OK' if sq == 10 else 'NG'}] 매도 수량")

    # 별지점
    star = s.calc_reverse_star(CLOSES)
    print(f"\n[별] 5일 종가 평균 = ${star:.2f}")
    print(f"  [{'OK' if star > 0 else 'NG'}] 리버스 별")

    # 첫날: MOC만
    st1 = {
        "T": 39.5, "qty": QTY, "avg_price": AVG, "principal": 20000,
        "split_count": SPLIT, "reverse_mode": True, "reverse_first_day": True,
        "close_prices": CLOSES,
    }
    p1 = s.get_plan_from_state("TQQQ", CURRENT, st1, 3, available_cash=400)
    sells1 = p1["sell_orders"]
    buys1 = p1["buy_orders"]
    moc = [o for o in sells1 if o.get("exec") == "MOC"]
    print(f"\n[첫날] 매도 {len(sells1)}건, 매수 {len(buys1)}건, MOC {len(moc)}건")
    print(f"  [{'OK' if len(moc) == 1 and len(buys1) == 0 else 'NG'}] 첫날 MOC만")

    # 2일차: LOC매도 + 쿼터매수
    st2 = dict(st1)
    st2["reverse_first_day"] = False
    p2 = s.get_plan_from_state("TQQQ", CURRENT, st2, 3, available_cash=700)
    qb = p2.get("quarter_buy_budget", 0)
    print(f"\n[2일차] 쿼터매수 예산 ${qb:.0f} (700÷4=175)")
    rev_buy = [o for o in p2["buy_orders"] if o.get("action") == REVERSE_BUY]
    rev_sell = [o for o in p2["sell_orders"] if o.get("action") == REVERSE_SELL]
    print(f"  [{'OK' if abs(qb - 175) < 1 else 'NG'}] 잔금÷4")
    print(f"  [{'OK' if len(rev_buy) == 1 and len(rev_sell) == 1 else 'NG'}] 매도+쿼터매수")

    # 종료 조건
    exit_ok = s.should_exit_reverse("TQQQ", 40.0, 34.1)
    exit_ng = not s.should_exit_reverse("TQQQ", 40.0, 33.0)
    print(f"\n[종료] TQQQ 평단$40, 종가$34.1 → 복귀: {exit_ok}")
    print(f"  [{'OK' if exit_ok and exit_ng else 'NG'}] −15% 회복 조건")

    print("\n" + "=" * 60)


if __name__ == "__main__":
    run()
