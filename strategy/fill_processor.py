"""체결 반영 → T값·수량·회차 금액."""

from strategy.strategy_v40 import InfiniteStrategyV40


class FillProcessor:
    def __init__(self, strategy: InfiniteStrategyV40 = None):
        self.strategy = strategy or InfiniteStrategyV40()

    def apply_buy_fill(
        self, state: dict, order: dict, cycles, symbol: str,
        *, source: str = "bot", note: str = "",
    ) -> dict:
        qty = int(order["qty"])
        price = float(order["price"])
        usd = price * qty
        action = order.get("action", "BUY_FULL")
        t_before = float(state["T"])
        t_after = self.strategy.calc_next_t(t_before, action)

        old_q, old_a = int(state["qty"]), float(state["avg_price"])
        new_q = old_q + qty
        if new_q > 0:
            state["avg_price"] = round((old_q * old_a + qty * price) / new_q, 4)
        state["qty"] = new_q
        state["T"] = t_after
        state["last_t_qty"] = new_q

        cycles.ensure_current(symbol, state["principal"])
        cycles.record_buy(symbol, usd, t_after, state["principal"])
        cycles.record_trade(
            symbol, side="BUY", qty=qty, price=price, action=action,
            t_before=t_before, t_after=t_after,
            avg_after=state["avg_price"], qty_after=new_q,
            source=source, note=note or order.get("desc", ""),
            fill_id=order.get("fill_id"),
            filled_at=order.get("filled_at"),
            order_id=order.get("order_id"),
        )
        return state

    def apply_sell_fill(
        self, state: dict, order: dict, cycles, symbol: str,
        *, source: str = "bot", note: str = "",
    ):
        qty = int(order["qty"])
        price = float(order["price"])
        usd = price * qty
        action = order.get("action")
        t_before = float(state["T"])
        t_after = t_before
        if action:
            t_after = self.strategy.calc_next_t(t_before, action)

        state["qty"] = max(0, int(state["qty"]) - qty)
        if state["qty"] == 0:
            state["avg_price"] = 0.0
        state["T"] = t_after if state["qty"] > 0 else 0.0
        state["last_t_qty"] = int(state["qty"])

        completed = cycles.record_sell(symbol, usd, t_after, state["qty"], state["principal"])
        cycles.record_trade(
            symbol, side="SELL", qty=qty, price=price, action=action,
            t_before=t_before,
            t_after=t_after if state["qty"] > 0 else 0.0,
            avg_after=state["avg_price"], qty_after=int(state["qty"]),
            source=source, note=note or order.get("desc", ""),
            fill_id=order.get("fill_id"),
            filled_at=order.get("filled_at"),
            order_id=order.get("order_id"),
        )
        return state, completed
