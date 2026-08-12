"""체결 반영 → T값·수량·회차 금액."""

from strategy.strategy_v40 import (
    REVERSE_BUY,
    REVERSE_SELL,
    REVERSE_SELL_FIRST,
    InfiniteStrategyV40,
)


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
        action = order.get("action") or "BUY_FULL"
        split = int(state.get("split_count", 40))
        t_before = float(state["T"])
        t_after = self.strategy.calc_next_t(t_before, action, split)

        old_q, old_a = int(state["qty"]), float(state["avg_price"])
        new_q = old_q + qty
        if new_q > 0:
            state["avg_price"] = round((old_q * old_a + qty * price) / new_q, 4)
        state["qty"] = new_q
        state["T"] = t_after
        state["last_t_qty"] = new_q

        cycles.ensure_current(symbol, state["principal"])
        with cycles.batch():
            cycles.record_buy(symbol, usd, t_after, state["principal"])
            cycles.record_trade(
                symbol, side="BUY", qty=qty, price=price, action=action,
                t_before=t_before, t_after=t_after,
                avg_after=state["avg_price"], qty_after=new_q,
                source=source, note=note or order.get("desc", ""),
                fill_id=order.get("fill_id"),
                filled_at=order.get("ordered_at") or order.get("filled_at"),
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
        split = int(state.get("split_count", 40))
        t_before = float(state["T"])
        t_after = t_before
        if action:
            t_after = self.strategy.calc_next_t(t_before, action, split)

        if action == REVERSE_SELL_FIRST:
            state["reverse_first_day"] = False

        avg_before = float(state["avg_price"])
        state["qty"] = max(0, int(state["qty"]) - qty)
        if state["qty"] == 0:
            state["avg_price"] = 0.0
            state["reverse_mode"] = False
            state["reverse_first_day"] = False
            state["reverse_exited"] = False
        state["T"] = t_after if state["qty"] > 0 else 0.0
        state["last_t_qty"] = int(state["qty"])

        with cycles.batch():
            cycles.record_trade(
                symbol, side="SELL", qty=qty, price=price, action=action,
                t_before=t_before,
                t_after=t_after if state["qty"] > 0 else 0.0,
                avg_after=state["avg_price"], qty_after=int(state["qty"]),
                avg_before=avg_before,
                source=source, note=note or order.get("desc", ""),
                fill_id=order.get("fill_id"),
                filled_at=order.get("ordered_at") or order.get("filled_at"),
                order_id=order.get("order_id"),
            )
            completed = cycles.record_sell(
                symbol, usd, t_after, state["qty"], state["principal"],
            )
        return state, completed
