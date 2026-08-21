from __future__ import annotations

import math
from enum import Enum


class TradingMode(str, Enum):
    NORMAL_EARLY = "NORMAL_EARLY"
    NORMAL_LATE = "NORMAL_LATE"
    REVERSE = "REVERSE"
    ENTRY = "ENTRY"
    FORCE_ONE = "FORCE_ONE"


# 리버스 T·매도·매수 action (V4.0 PDF)
REVERSE_SELL_FIRST = "REVERSE_SELL_FIRST"
REVERSE_SELL = "REVERSE_SELL"
REVERSE_BUY = "REVERSE_BUY"


class InfiniteStrategyV40:
    """라오어 무한매수 4.0 — 순수 계산 (주문·API 없음)."""

    TAKE_PROFIT_PCT = {"TQQQ": 15.0, "SOXL": 20.0}
    REVERSE_EXIT_DROP = {"TQQQ": 0.15, "SOXL": 0.20}

    # ------------------------------------------------------------------ T
    def calc_next_t(
        self, current_t: float, action_type: str, split_count: int = 40,
    ) -> float:
        act = action_type or ""
        if act in (REVERSE_SELL_FIRST, REVERSE_SELL):
            return self.calc_next_t_reverse_sell(current_t, split_count)
        if act == REVERSE_BUY:
            return self.calc_next_t_reverse_buy(current_t, split_count)
        if act == "BUY_FULL":
            return current_t + 1.0
        if act == "BUY_HALF":
            return current_t + 0.5
        if act == "SELL_QUARTER":
            return current_t * 0.75
        if act == "SELL_AND_BUY_FULL":
            return (current_t * 0.25) + 1.0
        if act == "SELL_AND_BUY_HALF":
            return (current_t * 0.25) + 0.5
        return current_t

    @staticmethod
    def calc_next_t_reverse_sell(t_val: float, split_count: int) -> float:
        if split_count == 20:
            return float(t_val) * 0.9
        return float(t_val) * 0.95

    @staticmethod
    def calc_next_t_reverse_buy(t_val: float, split_count: int) -> float:
        t = float(t_val)
        sc = float(split_count)
        return t + (sc - t) * 0.25

    # ------------------------------------------------------------------ normal star
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

    # ------------------------------------------------------------------ reverse (PDF)
    @staticmethod
    def reverse_sell_divisor(split_count: int) -> int:
        """40분할→20등분, 20분할→10등분."""
        if split_count == 20:
            return 10
        if split_count == 40:
            return 20
        return max(1, split_count // 2)

    @staticmethod
    def calc_reverse_sell_qty(qty: int, split_count: int) -> int:
        if qty <= 0:
            return 0
        div = InfiniteStrategyV40.reverse_sell_divisor(split_count)
        return max(1, math.floor(qty / div))

    @staticmethod
    def calc_reverse_star(close_prices: list, fallback: float = 0.0) -> float:
        """리버스 별지점 = 직전 5거래일 종가 평균."""
        vals: list[float] = []
        for item in close_prices or []:
            if isinstance(item, dict):
                p = float(item.get("close", 0) or 0)
            else:
                try:
                    p = float(item)
                except (TypeError, ValueError):
                    p = 0.0
            if p > 0:
                vals.append(p)
        recent = vals[-5:]
        if not recent:
            return round(fallback, 2) if fallback > 0 else 0.0
        return round(sum(recent) / len(recent), 2)

    @staticmethod
    def calc_reverse_quarter_buy_budget(available_cash: float) -> float:
        """쿼터매수 = (잔금 + 매도금) / 4."""
        if available_cash <= 0:
            return 0.0
        return available_cash / 4.0

    def reverse_exit_drop_pct(self, ticker: str) -> float:
        return self.REVERSE_EXIT_DROP.get(ticker.upper(), 0.15)

    def should_exit_reverse(self, ticker: str, avg_price: float, close_price: float) -> bool:
        """평단 대비 낙폭이 TQQQ -15% / SOXL -20% 보다 작아지면 일반모드 복귀."""
        if avg_price <= 0 or close_price <= 0:
            return False
        floor = avg_price * (1.0 - self.reverse_exit_drop_pct(ticker))
        return close_price > floor

    def sync_reverse_flags(self, st: dict) -> dict:
        """T 소진·종료 조건에 따라 리버스 자동 ON/OFF (수동 토글 없음)."""
        qty = int(st.get("qty", 0))
        t_val = float(st.get("T", 0.0))
        split = int(st.get("split_count", 40))

        if qty <= 0 or t_val <= split - 1:
            st["reverse_mode"] = False
            st["reverse_first_day"] = False
            st["reverse_exited"] = False
            return st

        if st.get("reverse_exited"):
            st["reverse_mode"] = False
            st["reverse_first_day"] = False
            return st

        if not st.get("reverse_mode"):
            st["reverse_first_day"] = True
        st["reverse_mode"] = True
        return st

    def maybe_exit_reverse(
        self, st: dict, ticker: str, close_price: float,
    ) -> bool:
        """종가 기준 종료 — job4/sync 에서만 호출. True=종료됨."""
        if not st.get("reverse_mode"):
            return False
        avg = float(st.get("avg_price", 0.0))
        if not self.should_exit_reverse(ticker, avg, close_price):
            return False
        st["reverse_mode"] = False
        st["reverse_first_day"] = False
        st["reverse_exited"] = True
        return True

    # ------------------------------------------------------------------ shared
    def calc_one_buy_amount(self, principal: float, t_val: float, split_count: int) -> float:
        safe_t = min(float(t_val), split_count - 1)
        denom = split_count - safe_t
        if denom <= 0 or principal <= 0:
            return 0.0
        return principal / denom

    def calc_premium_buy_price(self, current_price: float, premium_pct: int) -> float:
        if current_price <= 0:
            return 0.0
        return round(current_price * (1.0 + premium_pct / 100.0), 2)

    def get_take_profit_pct(self, ticker: str) -> float:
        return self.TAKE_PROFIT_PCT.get(ticker, 15.0)

    def resolve_take_profit(self, ticker: str, override: float | None = None) -> float:
        if override and float(override) > 0:
            return float(override)
        return self.get_take_profit_pct(ticker)

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
        *, reverse_active: bool = False,
    ) -> TradingMode:
        if force_one:
            return TradingMode.FORCE_ONE
        if qty > 0 and reverse_active:
            return TradingMode.REVERSE
        return self.detect_mode(qty, t_val, split_count)

    def resolve_mode_from_state(self, st: dict) -> TradingMode:
        self.sync_reverse_flags(st)
        return self.resolve_mode(
            int(st.get("qty", 0)),
            float(st.get("T", 0.0)),
            int(st.get("split_count", 40)),
            st.get("force_one", False),
            reverse_active=st.get("reverse_mode", False),
        )

    def get_plan_from_state(
        self, ticker: str, current_price: float, st: dict, premium_pct: int,
        *, available_cash: float | None = None,
    ) -> dict:
        self.sync_reverse_flags(st)
        cash = available_cash
        if cash is None:
            cash = float(st.get("principal", 0.0))
        return self.get_plan(
            ticker,
            current_price,
            float(st.get("avg_price", 0.0)),
            int(st.get("qty", 0)),
            float(st.get("T", 0.0)),
            premium_pct,
            float(st.get("principal", 0.0)),
            int(st.get("split_count", 40)),
            st.get("force_one", False),
            take_profit_pct=st.get("take_profit_pct"),
            reverse_mode=st.get("reverse_mode", False),
            reverse_first_day=st.get("reverse_first_day", False),
            close_prices=st.get("close_prices") or [],
            available_cash=cash,
            state_out=st,
        )

    def _floor_qty(self, budget: float, price: float) -> int:
        if price <= 0 or budget <= 0:
            return 0
        return math.floor(budget / price)

    def _append_buy(self, plan, price, budget, action, desc):
        qty = self._floor_qty(budget, price)
        if qty <= 0:
            return
        self._append_buy_qty(plan, price, qty, action, desc)

    def _append_star_buy(
        self, plan, star_price: float, star_pct: float, one_buy: float,
    ) -> None:
        if star_price <= 0 or one_buy <= 0:
            return
        half = one_buy / 2.0
        qty = self._floor_qty(half, star_price)
        if qty <= 0 and one_buy >= star_price:
            qty = 1
        if qty <= 0:
            return
        self._append_buy_qty(
            plan, star_price, qty, "BUY_HALF",
            f"별 +{star_pct:g}% (${star_price:.2f})",
        )

    def _append_buy_qty(self, plan, price, qty, action, desc, *, exec_type: str = "LOC"):
        if price <= 0 or qty <= 0:
            return
        plan["buy_orders"].append({
            "type": "LIMIT", "exec": exec_type, "price": round(price, 2),
            "qty": int(qty), "action": action, "desc": desc, "side": "BUY",
        })

    def _append_sell(self, plan, price, qty, action, desc, *, exec_type: str = "LOC"):
        if qty <= 0:
            return
        plan["sell_orders"].append({
            "type": "LIMIT" if exec_type != "MOC" else "MOC",
            "exec": exec_type,
            "price": round(price, 2) if price > 0 else 0.0,
            "qty": qty, "action": action, "desc": desc, "side": "SELL",
        })

    def _force_one_buy_price(
        self, mode: TradingMode, current_price: float, avg_price: float,
        star_buy: float, premium_pct: int,
    ) -> float:
        if mode == TradingMode.ENTRY:
            return self.calc_premium_buy_price(current_price, premium_pct)
        if mode == TradingMode.NORMAL_LATE and star_buy > 0:
            return star_buy
        if mode == TradingMode.REVERSE:
            return star_buy if star_buy > 0 else current_price
        if star_buy > 0:
            return star_buy
        return current_price

    def _append_sell_orders(
        self, plan, avg_price: float, qty: int,
        star_price: float, take_profit_pct: float,
    ) -> None:
        if avg_price <= 0 or qty <= 0:
            return
        qtr = max(1, math.floor(qty / 4))
        rem = qty - qtr
        if star_price > 0:
            self._append_sell(
                plan, star_price, qtr, "SELL_QUARTER", f"쿼터 LOC ({qtr}주)",
            )
        if rem > 0:
            tp = round(avg_price * (1.0 + take_profit_pct / 100.0), 2)
            self._append_sell(plan, tp, rem, None, f"익절 LOC +{take_profit_pct}% ({rem}주)")

    def _build_reverse_plan(
        self, plan: dict, ticker: str, qty: int, split_count: int,
        reverse_first_day: bool, star_price: float, available_cash: float,
    ) -> dict:
        """V4.0 PDF — 소진 후 리버스: MOC 첫매도 / 별 위 LOC매도 / 별 아래 쿼터매수."""
        sell_qty = self.calc_reverse_sell_qty(qty, split_count)
        star_buy = self.calc_buy_trigger_price(star_price) if star_price > 0 else 0.0
        plan["star_price"] = star_price
        plan["star_buy"] = star_buy
        plan["reverse_first_day"] = reverse_first_day
        plan["reverse_star"] = star_price
        plan["available_cash"] = round(available_cash, 2)
        quarter_budget = self.calc_reverse_quarter_buy_budget(available_cash)
        plan["quarter_buy_budget"] = round(quarter_budget, 2)

        if reverse_first_day and sell_qty > 0:
            self._append_sell(
                plan, 0, sell_qty, REVERSE_SELL_FIRST,
                f"리버스 첫매도 MOC ({sell_qty}주)",
                exec_type="MOC",
            )
            return plan

        if star_price > 0 and sell_qty > 0:
            self._append_sell(
                plan, star_price, sell_qty, REVERSE_SELL,
                f"리버스 LOC매도 ({sell_qty}주) @ 별 ${star_price:.2f}",
            )

        if quarter_budget > 0 and star_buy > 0:
            self._append_buy(
                plan, star_buy, quarter_budget, REVERSE_BUY,
                f"리버스 쿼터매수 (잔금÷4 ${quarter_budget:.0f})",
            )
        return plan

    def _build_force_one_plan(
        self, plan: dict, mode: TradingMode, current_price: float,
        avg_price: float, qty: int, star_buy: float, star_price: float,
        premium_pct: int, take_profit_pct: float, split_count: int,
        reverse_first_day: bool, available_cash: float,
    ) -> dict:
        plan["mode"] = TradingMode.FORCE_ONE.value
        if mode == TradingMode.REVERSE:
            self._build_reverse_plan(
                plan, "", qty, split_count, reverse_first_day,
                star_price, available_cash,
            )
            if not reverse_first_day:
                price = self._force_one_buy_price(
                    mode, current_price, avg_price, star_buy, premium_pct,
                )
                plan["buy_orders"].insert(0, {
                    "type": "LIMIT", "exec": "LOC", "price": round(price, 2),
                    "qty": 1, "action": "BUY_FULL",
                    "desc": f"강제1회 LOC (${price:.2f} × 1주)", "side": "BUY",
                })
            return plan
        price = self._force_one_buy_price(
            mode, current_price, avg_price, star_buy, premium_pct,
        )
        self._append_buy_qty(
            plan, price, 1, "BUY_FULL",
            f"강제1회 LOC (${price:.2f} × 1주)",
        )
        self._append_sell_orders(
            plan, avg_price, qty, star_price, take_profit_pct,
        )
        return plan

    def get_plan(
        self, ticker: str, current_price: float, avg_price: float,
        qty: int, t_val: float, premium_pct: int,
        principal: float, split_count: int, force_one: bool = False,
        take_profit_pct: float | None = None,
        *, reverse_mode: bool = False,
        reverse_first_day: bool = False,
        close_prices: list | None = None,
        available_cash: float = 0.0,
        state_out: dict | None = None,
    ) -> dict:
        mode = self.resolve_mode(
            qty, t_val, split_count, force_one, reverse_active=reverse_mode,
        )
        star_pct = self.calc_star_pct(ticker, t_val, split_count)
        take_profit_pct = self.resolve_take_profit(ticker, take_profit_pct)
        normal_star = self.calc_star_price(avg_price, star_pct) if avg_price > 0 else 0.0
        reverse_star = self.calc_reverse_star(
            close_prices or [], fallback=current_price or normal_star,
        )
        star_price = reverse_star if mode == TradingMode.REVERSE else normal_star
        star_buy = self.calc_buy_trigger_price(star_price) if star_price > 0 else 0.0
        one_buy = self.calc_one_buy_amount(
            principal, 0 if mode == TradingMode.ENTRY else t_val, split_count,
        )
        plan = {
            "mode": mode.value,
            "star_pct": round(star_pct, 4),
            "star_price": star_price,
            "star_buy": star_buy,
            "take_profit_pct": take_profit_pct,
            "current_price": round(current_price, 2) if current_price > 0 else 0.0,
            "avg_price": round(avg_price, 4),
            "premium_pct": premium_pct,
            "one_buy_amount": round(one_buy, 2),
            "buy_orders": [],
            "sell_orders": [],
            "reverse_mode": mode == TradingMode.REVERSE,
            "reverse_first_day": reverse_first_day,
        }
        if state_out is not None:
            state_out["reverse_mode"] = mode == TradingMode.REVERSE
            state_out["reverse_first_day"] = reverse_first_day

        if force_one and current_price > 0:
            return self._build_force_one_plan(
                plan, mode, current_price, avg_price, qty,
                star_buy, star_price, premium_pct, take_profit_pct,
                split_count, reverse_first_day, available_cash,
            )

        if mode == TradingMode.ENTRY and t_val < 1:
            big = self.calc_premium_buy_price(current_price, premium_pct)
            self._append_buy(plan, big, one_buy, "BUY_FULL", f"첫 진입 큰수(+{premium_pct}%)")
            return plan
        if mode == TradingMode.ENTRY:
            return plan

        if mode == TradingMode.REVERSE:
            return self._build_reverse_plan(
                plan, ticker, qty, split_count, reverse_first_day,
                star_price, available_cash,
            )

        plan["star_price"] = normal_star
        star_buy = self.calc_buy_trigger_price(normal_star) if normal_star > 0 else 0.0
        plan["star_buy"] = star_buy

        half = one_buy / 2.0
        if avg_price > 0:
            self._append_buy(plan, avg_price, half, "BUY_HALF", f"평단 (${avg_price:.2f})")
        if normal_star > 0:
            self._append_star_buy(plan, normal_star, star_pct, one_buy)

        self._append_sell_orders(plan, avg_price, qty, normal_star, take_profit_pct)
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
