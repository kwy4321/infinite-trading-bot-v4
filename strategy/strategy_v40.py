import math
from enum import Enum


class TradingMode(str, Enum):
    NORMAL_EARLY = "NORMAL_EARLY"
    NORMAL_LATE = "NORMAL_LATE"
    REVERSE = "REVERSE"
    ENTRY = "ENTRY"
    FORCE_ONE = "FORCE_ONE"


class InfiniteStrategyV40:
    """라오어 무한매수 4.0 — 순수 계산 (주문·API 없음)."""

    TAKE_PROFIT_PCT = {"TQQQ": 15.0, "SOXL": 20.0}

    def calc_next_t(self, current_t: float, action_type: str) -> float:
        if action_type == "BUY_FULL":
            return current_t + 1.0
        if action_type == "BUY_HALF":
            return current_t + 0.5
        if action_type == "SELL_QUARTER":
            return current_t * 0.75
        if action_type == "SELL_AND_BUY_FULL":
            return (current_t * 0.25) + 1.0
        if action_type == "SELL_AND_BUY_HALF":
            return (current_t * 0.25) + 0.5
        return current_t

    def calc_star_pct(self, ticker: str, t_val: float, split_count: int) -> float:
        t = max(0.0, float(t_val))
        if ticker == "SOXL":
            if split_count == 20:
                return 20.0 - (2.0 * t)
            return 20.0 - t
        if split_count == 20:
            return 15.0 - (1.5 * t)
        if split_count == 30:
            return 15.0 - (0.5 * t)
        if split_count == 50:
            return 15.0 - (0.375 * t)
        if split_count == 60:
            return 15.0 - (0.25 * t)
        return 15.0 - (0.75 * t)

    def calc_star_price(self, avg_price: float, star_pct: float) -> float:
        if avg_price <= 0:
            return 0.0
        return round(avg_price * (1.0 + star_pct / 100.0), 2)

    def calc_buy_trigger_price(self, star_price: float) -> float:
        return max(0.01, round(star_price - 0.01, 2))

    def calc_one_buy_amount(self, principal: float, t_val: float, split_count: int) -> float:
        safe_t = min(float(t_val), split_count - 1)
        denom = split_count - safe_t
        if denom <= 0 or principal <= 0:
            return 0.0
        return principal / denom

    def get_take_profit_pct(self, ticker: str) -> float:
        return self.TAKE_PROFIT_PCT.get(ticker, 15.0)

    def detect_mode(self, qty: int, t_val: float, split_count: int) -> TradingMode:
        if qty <= 0:
            return TradingMode.ENTRY
        if t_val > split_count - 1:
            return TradingMode.REVERSE
        if t_val < split_count / 2:
            return TradingMode.NORMAL_EARLY
        return TradingMode.NORMAL_LATE

    def resolve_mode(
        self, qty: int, t_val: float, split_count: int, force_one: bool = False,
    ) -> TradingMode:
        if force_one:
            return TradingMode.FORCE_ONE
        return self.detect_mode(qty, t_val, split_count)

    def _floor_qty(self, budget: float, price: float) -> int:
        if price <= 0 or budget <= 0:
            return 0
        return math.floor(budget / price)

    def _append_buy(self, plan, price, budget, action, desc):
        qty = self._floor_qty(budget, price)
        if qty <= 0:
            return
        self._append_buy_qty(plan, price, qty, action, desc)

    def _append_buy_qty(self, plan, price, qty, action, desc):
        if price <= 0 or qty <= 0:
            return
        plan["buy_orders"].append({
            "type": "LIMIT", "price": round(price, 2), "qty": int(qty),
            "action": action, "desc": desc, "side": "BUY",
        })

    def _append_sell(self, plan, price, qty, action, desc):
        if qty <= 0:
            return
        plan["sell_orders"].append({
            "type": "LIMIT", "price": round(price, 2), "qty": qty,
            "action": action, "desc": desc, "side": "SELL",
        })

    def _force_one_buy_price(
        self, mode: TradingMode, current_price: float, avg_price: float,
        star_buy: float, premium_pct: int,
    ) -> float:
        if mode in (TradingMode.ENTRY, TradingMode.NORMAL_EARLY):
            return round(current_price * (1.0 + premium_pct / 100.0), 2)
        if mode == TradingMode.NORMAL_LATE and star_buy > 0:
            return star_buy
        if mode == TradingMode.REVERSE:
            return self.calc_buy_trigger_price(star_buy) if star_buy > 0 else current_price
        return round(current_price * (1.0 + premium_pct / 100.0), 2)

    def _append_sell_orders(
        self, plan, avg_price: float, qty: int,
        star_price: float, take_profit_pct: float, reverse: bool = False,
    ) -> None:
        if avg_price <= 0 or qty <= 0:
            return
        qtr = max(1, math.floor(qty / 4))
        rem = qty - qtr
        if star_price > 0:
            label = f"리버스 쿼터 LOC ({qtr}주)" if reverse else f"쿼터 LOC ({qtr}주)"
            self._append_sell(plan, star_price, qtr, "SELL_QUARTER", label)
        if not reverse and rem > 0:
            tp = round(avg_price * (1.0 + take_profit_pct / 100.0), 2)
            self._append_sell(plan, tp, rem, None, f"익절 LOC +{take_profit_pct}% ({rem}주)")

    def _build_force_one_plan(
        self, plan: dict, mode: TradingMode, current_price: float,
        avg_price: float, qty: int, star_buy: float, star_price: float,
        premium_pct: int, take_profit_pct: float,
    ) -> dict:
        plan["mode"] = TradingMode.FORCE_ONE.value
        price = self._force_one_buy_price(
            mode, current_price, avg_price, star_buy, premium_pct,
        )
        self._append_buy_qty(
            plan, price, 1, "BUY_FULL",
            f"강제1회 LOC (${price:.2f} × 1주)",
        )
        if mode == TradingMode.REVERSE:
            self._append_sell_orders(
                plan, avg_price, qty, star_price, take_profit_pct, reverse=True,
            )
        else:
            self._append_sell_orders(
                plan, avg_price, qty, star_price, take_profit_pct,
            )
        return plan

    def get_plan(
        self, ticker: str, current_price: float, avg_price: float,
        qty: int, t_val: float, premium_pct: int,
        principal: float, split_count: int, force_one: bool = False,
    ) -> dict:
        mode = self.detect_mode(qty, t_val, split_count)
        star_pct = self.calc_star_pct(ticker, t_val, split_count)
        take_profit_pct = self.get_take_profit_pct(ticker)
        star_price = self.calc_star_price(avg_price, star_pct) if avg_price > 0 else 0.0
        star_buy = self.calc_buy_trigger_price(star_price) if star_price > 0 else 0.0
        one_buy = self.calc_one_buy_amount(
            principal, 0 if mode == TradingMode.ENTRY else t_val, split_count,
        )
        plan = {
            "mode": mode.value, "star_pct": round(star_pct, 4), "star_price": star_price,
            "one_buy_amount": round(one_buy, 2), "buy_orders": [], "sell_orders": [],
        }

        if force_one and current_price > 0:
            return self._build_force_one_plan(
                plan, mode, current_price, avg_price, qty,
                star_buy, star_price, premium_pct, take_profit_pct,
            )

        if mode == TradingMode.ENTRY:
            big = round(current_price * (1.0 + premium_pct / 100.0), 2)
            self._append_buy(plan, big, one_buy, "BUY_FULL", f"첫 진입 큰수(+{premium_pct}%)")
            return plan

        if mode == TradingMode.REVERSE:
            plan["star_price"] = star_price
            if star_price > 0 and qty > 0:
                q = max(1, math.floor(qty / 4))
                self._append_sell(plan, star_price, q, "SELL_QUARTER", f"리버스 쿼터 LOC ({q}주)")
            if principal > 0 and current_price > 0:
                bp = star_buy if star_buy > 0 else current_price
                self._append_buy(plan, bp, one_buy, "BUY_FULL", "리버스 쿼터매수")
            return plan

        plan["star_price"] = star_price

        if mode == TradingMode.NORMAL_EARLY:
            half = one_buy / 2.0
            self._append_buy(plan, star_buy, half, "BUY_HALF", f"전반전 별지점 (${star_buy})")
            if avg_price > 0:
                self._append_buy(plan, avg_price, half, "BUY_HALF", f"전반전 평단 (${avg_price:.2f})")
            big = round(current_price * (1.0 + premium_pct / 100.0), 2)
            self._append_buy(plan, big, one_buy, "BUY_FULL", f"큰수(+{premium_pct}%)")
        else:
            self._append_buy(plan, star_buy, one_buy, "BUY_FULL", f"후반전 별지점 (${star_buy})")

        if current_price > 0 and one_buy > 0:
            for drop in (10, 15, 20):
                fp = round(current_price * (1.0 - drop / 100.0), 2)
                self._append_buy(plan, fp, one_buy * 0.5, "BUY_HALF", f"하단 방어(-{drop}%)")

        self._append_sell_orders(plan, avg_price, qty, star_price, take_profit_pct)
        return plan

    def summarize(self, ticker, current_price, avg_price, qty, t_val, principal, split_count):
        mode = self.detect_mode(qty, t_val, split_count)
        star_pct = self.calc_star_pct(ticker, t_val, split_count)
        star_price = self.calc_star_price(avg_price, star_pct) if avg_price > 0 else 0.0
        one_buy = self.calc_one_buy_amount(principal, t_val, split_count) if qty > 0 else 0.0
        return {
            "mode": mode.value, "t_val": t_val,
            "star_pct": round(star_pct, 4), "star_price": star_price,
            "one_buy_amount": round(one_buy, 2),
            "take_profit_pct": self.get_take_profit_pct(ticker),
        }
