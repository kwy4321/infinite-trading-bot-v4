"""체결 반영 → T값·수량·회차 금액."""

from strategy.strategy_v40 import InfiniteStrategyV40


class FillProcessor:
    def __init__(self, strategy: InfiniteStrategyV40 = None):
        self.strategy = strategy or InfiniteStrategyV40()

    def apply_buy_fill(self, state: dict, order: dict, cycles, symbol: str) -> dict:
        qty = int(order["qty"])
        price = float(order["price"])
        usd = price * qty
        t_after = self.strategy.calc_next_t(float(state["T"]), order.get("action", "BUY_FULL"))

        old_q, old_a = int(state["qty"]), float(state["avg_price"])
        new_q = old_q + qty
        if new_q > 0:
            state["avg_price"] = round((old_q * old_a + qty * price) / new_q, 4)
        state["qty"] = new_q
        state["T"] = t_after

        cycles.ensure_current(symbol, state["principal"])
        cycles.record_buy(symbol, usd, t_after, state["principal"])
        return state

    def apply_sell_fill(self, state: dict, order: dict, cycles, symbol: str):
        qty = int(order["qty"])
        price = float(order["price"])
        usd = price * qty
        action = order.get("action")
        t_after = float(state["T"])
        if action:
            t_after = self.strategy.calc_next_t(t_after, action)

        state["qty"] = max(0, int(state["qty"]) - qty)
        if state["qty"] == 0:
            state["avg_price"] = 0.0
        state["T"] = t_after if state["qty"] > 0 else 0.0

        completed = cycles.record_sell(symbol, usd, t_after, state["qty"], state["principal"])
        return state, completed
