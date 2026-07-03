"""토스 체결·실계좌와 봇 state(T·회차)를 맞춘다."""

from __future__ import annotations

import datetime
import logging
import math
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app import App

logger = logging.getLogger(__name__)


class FillReconciler:
    """매매 체결을 관찰해 T·회차 기록을 자동 반영."""

    def __init__(self, app: "App"):
        self.app = app

    def reconcile_symbol(self, symbol: str, premium: int | None = None) -> dict:
        """Returns {applied: [fill entries], t_before, t_after, qty_before, qty_after}."""
        if premium is None:
            premium = self.app.runtime.premium_default()

        st = self.app.state.load(symbol)
        t_before = float(st.get("T", 0.0))
        qty_before = int(st.get("qty", 0))
        applied: list[dict] = []

        if self.app.settings.dry_run or not self.app.settings.has_toss:
            return {
                "applied": applied,
                "t_before": t_before,
                "t_after": t_before,
                "qty_before": qty_before,
                "qty_after": qty_before,
            }

        broker = self.app.broker.get_holdings_item(symbol)
        broker_qty = int(broker.get("qty", 0) or 0)
        broker_avg = float(broker.get("avg_price", 0.0) or 0.0)
        broker_price = float(broker.get("current_price", 0.0) or 0.0)

        applied.extend(self._process_tracked_orders(symbol, st, premium))
        applied.extend(self._process_open_orders(symbol, st, premium))
        invest_applied = self._reconcile_invested_gap(
            symbol, st, broker_qty, broker_avg, broker_price, premium,
        )
        applied.extend(invest_applied)
        if invest_applied:
            st = self.app.state.load(symbol)
        applied.extend(self._reconcile_qty_delta(
            symbol, st, broker_qty, broker_avg, broker_price, premium,
            skip_buys=bool(invest_applied),
        ))

        if applied:
            self.app.state.save(symbol, st)
        elif broker_qty > 0 and "last_t_qty" not in st:
            st["last_t_qty"] = broker_qty
            self.app.state.save(symbol, st)

        st = self.app.state.load(symbol)
        self._refresh_fill_dates_from_closed_orders(symbol, broker_qty)
        st = self.app.state.load(symbol)
        return {
            "applied": applied,
            "t_before": t_before,
            "t_after": float(st.get("T", 0.0)),
            "qty_before": qty_before,
            "qty_after": int(st.get("qty", 0)),
        }

    def _process_tracked_orders(self, symbol: str, st: dict, premium: int) -> list[dict]:
        applied = []
        remaining = []
        for entry in st.get("tracked_orders", []):
            if entry.get("symbol", "").upper() != symbol.upper():
                remaining.append(entry)
                continue
            order_id = entry.get("order_id")
            if not order_id:
                continue
            try:
                order = self.app.broker.get_order(order_id)
            except Exception:
                logger.exception("get_order failed %s", order_id)
                remaining.append(entry)
                continue
            fills = self._extract_order_fills(order, symbol)
            for fill in fills:
                if self._is_processed(st, fill["id"]):
                    continue
                applied.append(self._apply_fill(symbol, st, fill, premium))
            status = (order.get("status") or "").upper()
            if status in ("PENDING", "PARTIAL_FILLED", "PENDING_CANCEL", "PENDING_REPLACE"):
                remaining.append(entry)
        st["tracked_orders"] = remaining
        return applied

    def _process_open_orders(self, symbol: str, st: dict, premium: int) -> list[dict]:
        applied = []
        try:
            orders = self.app.broker.get_open_orders(symbol)
        except Exception:
            logger.exception("get_open_orders failed %s", symbol)
            return applied
        for order in orders:
            fills = self._extract_order_fills(order, symbol)
            for fill in fills:
                if self._is_processed(st, fill["id"]):
                    continue
                applied.append(self._apply_fill(symbol, st, fill, premium))
        return applied

    def _reconcile_invested_gap(
        self,
        symbol: str,
        st: dict,
        broker_qty: int,
        broker_avg: float,
        broker_price: float,
        premium: int,
    ) -> list[dict]:
        """수동 매수 등 — cycles 투입금 vs 실계좌 투입금 차이로 미반영 체결 추정."""
        if broker_qty <= 0 or broker_avg <= 0:
            return []

        cur = self.app.cycles.get_symbol_data(symbol).get("current") or {}
        recorded_buy = float(cur.get("total_buy_usd", 0.0))
        actual_invested = round(broker_qty * broker_avg, 2)
        gap_usd = round(actual_invested - recorded_buy, 2)
        if gap_usd < 1.0:
            return []

        price = broker_price or broker_avg
        est_qty = max(1, int(round(gap_usd / price)))
        if est_qty > broker_qty:
            est_qty = broker_qty

        action, _, note = self._infer_buy_action(st, symbol, est_qty, price, premium)
        fill = {
            "id": f"invest-gap:{symbol}:{datetime.date.today().isoformat()}:{est_qty}",
            "order_id": None,
            "side": "BUY",
            "qty": est_qty,
            "price": round(price, 2),
            "action": action,
            "source": "sync",
            "note": note or "실계좌 투입금 차이 — 미반영 매수 추정",
            "filled_at": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
        }
        if self._is_processed(st, fill["id"]):
            return []
        return [self._apply_fill(symbol, st, fill, premium)]

    def _reconcile_qty_delta(
        self,
        symbol: str,
        st: dict,
        broker_qty: int,
        broker_avg: float,
        broker_price: float,
        premium: int,
        skip_buys: bool = False,
    ) -> list[dict]:
        """state 주수 vs 실계좌 주수 차이로 미반영 체결 추정."""
        state_qty = int(st.get("qty", 0))
        last_t_qty = int(st.get("last_t_qty", state_qty))
        tracked_qty = last_t_qty
        delta = broker_qty - max(state_qty, tracked_qty)
        if delta > 0 and skip_buys:
            delta = 0
        if delta == 0:
            sell_delta = min(state_qty, tracked_qty) - broker_qty
            if sell_delta <= 0:
                return []
            price = broker_price or broker_avg or float(st.get("avg_price", 0.0))
            action, _, note = self._infer_sell_action(st, symbol, sell_delta, price, premium)
            fill = {
                "id": f"qty-delta:sell:{symbol}:{datetime.date.today().isoformat()}:{sell_delta}",
                "order_id": None,
                "side": "SELL",
                "qty": sell_delta,
                "price": round(price, 2),
                "action": action,
                "source": "sync",
                "note": note or "실계좌 주수 감소 — 미반영 매도 추정",
                "filled_at": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
            }
            if self._is_processed(st, fill["id"]):
                return []
            return [self._apply_fill(symbol, st, fill, premium)]

        applied = []
        remaining = delta
        price = broker_price or broker_avg or float(st.get("avg_price", 0.0))
        while remaining > 0:
            chunk = remaining
            action, use_price, note = self._infer_buy_action(st, symbol, chunk, price, premium)
            fill = {
                "id": f"qty-delta:buy:{symbol}:{datetime.date.today().isoformat()}:{chunk}:{len(applied)}",
                "order_id": None,
                "side": "BUY",
                "qty": chunk,
                "price": round(use_price, 2),
                "action": action,
                "source": "sync",
                "note": note or "실계좌 주수 증가 — 미반영 매수 추정",
                "filled_at": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
            }
            if self._is_processed(st, fill["id"]):
                break
            applied.append(self._apply_fill(symbol, st, fill, premium))
            remaining -= chunk
            if chunk <= 0:
                break
        return applied

    def _extract_order_fills(self, order: dict, symbol: str) -> list[dict]:
        sym = str(order.get("symbol") or "").upper()
        if sym and sym != symbol.upper():
            return []
        execution = order.get("execution") or {}
        filled_qty = int(float(
            execution.get("filledQuantity")
            or execution.get("filled_quantity")
            or order.get("filled_quantity")
            or 0
        ))
        if filled_qty <= 0:
            return []
        avg_price = float(
            execution.get("averageFilledPrice")
            or execution.get("average_filled_price")
            or order.get("average_filled_price")
            or order.get("price")
            or 0
        )
        order_id = str(order.get("orderId") or order.get("order_id") or "")
        order_date = (
            order.get("orderedAt") or order.get("ordered_at")
            or execution.get("filledAt") or execution.get("filled_at")
            or order.get("filled_at") or ""
        )
        side = (order.get("side") or "").upper()
        fill_id = f"{order_id}:{filled_qty}:{order_date or 'na'}"
        return [{
            "id": fill_id,
            "order_id": order_id,
            "side": side,
            "qty": filled_qty,
            "price": round(avg_price, 2),
            "action": None,
            "source": "broker",
            "note": f"토스 체결 ({order.get('status', '')})",
            "ordered_at": order_date,
            "filled_at": order_date,
        }]

    def _apply_fill(self, symbol: str, st: dict, fill: dict, premium: int) -> dict:
        t_before = float(st.get("T", 0.0))
        side = fill["side"]
        order = {
            "qty": int(fill["qty"]),
            "price": float(fill["price"]),
            "side": side,
        }
        if fill.get("id"):
            order["fill_id"] = fill["id"]
        if fill.get("filled_at"):
            order["filled_at"] = fill["filled_at"]
        if fill.get("ordered_at"):
            order["ordered_at"] = fill["ordered_at"]
        src = fill.get("source", "sync")
        note = fill.get("note", "")
        if side == "BUY":
            if not fill.get("action"):
                action, price, note = self._infer_buy_action(
                    st, symbol, order["qty"], order["price"], premium,
                )
                order["action"] = action
                order["price"] = price
                fill.setdefault("note", note)
            else:
                order["action"] = fill["action"]
            st = self.app.fills.apply_buy_fill(
                st, order, self.app.cycles, symbol, source=src, note=note,
            )
        else:
            if not fill.get("action"):
                action, price, note = self._infer_sell_action(
                    st, symbol, order["qty"], order["price"], premium,
                )
                order["action"] = action
                order["price"] = price
                fill.setdefault("note", note)
            else:
                order["action"] = fill["action"]
            st, _completed = self.app.fills.apply_sell_fill(
                st, order, self.app.cycles, symbol, source=src, note=note,
            )

        t_after = float(st.get("T", 0.0))
        entry = {
            **fill,
            "symbol": symbol.upper(),
            "side": side,
            "action": order.get("action"),
            "t_before": t_before,
            "t_after": t_after,
            "avg_after": float(st.get("avg_price", 0.0)),
            "qty_after": int(st.get("qty", 0)),
            "ordered_at": fill.get("ordered_at") or fill.get("filled_at"),
            "at": fill.get("ordered_at") or fill.get("filled_at") or datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
        }
        if fill.get("order_id"):
            entry["order_id"] = fill["order_id"]
        self._append_fill_log(st, entry)
        st["last_t_qty"] = int(st.get("qty", 0))
        self.app.state.save(symbol, st)
        return entry

    def _infer_buy_action(
        self, st: dict, symbol: str, qty: int, price: float, premium: int,
    ) -> tuple[str, float, str]:
        plan = self.app.strategy.get_plan(
            symbol,
            price,
            float(st.get("avg_price", 0.0)),
            int(st.get("qty", 0)),
            float(st.get("T", 0.0)),
            premium,
            float(st.get("principal", 0.0)),
            int(st.get("split_count", 40)),
            st.get("force_one", False),
            take_profit_pct=st.get("take_profit_pct"),
        )
        best = None
        for o in plan.get("buy_orders", []):
            if int(o.get("qty", 0)) != qty:
                continue
            diff = abs(float(o.get("price", 0)) - price)
            if best is None or diff < best[0]:
                best = (diff, o)
        if best:
            o = best[1]
            return o.get("action", "BUY_FULL"), float(o["price"]), o.get("desc", "주문계획 매칭")

        t_val = float(st.get("T", 0.0))
        one_buy = float(plan.get("one_buy_amount", 0.0))
        if t_val < 1 and qty == 1:
            return "BUY_FULL", price, "수동/외부 매수 (첫 진입 추정)"
        if one_buy > 0 and price > 0:
            half_qty = max(1, math.floor(one_buy / 2 / price))
            full_qty = max(1, math.floor(one_buy / price))
            if qty <= half_qty:
                return "BUY_HALF", price, "수동/외부 매수 (절반매수 추정)"
            if qty <= full_qty:
                return "BUY_FULL", price, "수동/외부 매수 (풀매수 추정)"
        return "BUY_FULL", price, "수동/외부 매수 (풀매수 추정)"

    def _infer_sell_action(
        self, st: dict, symbol: str, qty: int, price: float, premium: int,
    ) -> tuple[str | None, float, str]:
        plan = self.app.strategy.get_plan(
            symbol,
            price,
            float(st.get("avg_price", 0.0)),
            int(st.get("qty", 0)),
            float(st.get("T", 0.0)),
            premium,
            float(st.get("principal", 0.0)),
            int(st.get("split_count", 40)),
            st.get("force_one", False),
            take_profit_pct=st.get("take_profit_pct"),
        )
        best = None
        for o in plan.get("sell_orders", []):
            if int(o.get("qty", 0)) != qty:
                continue
            diff = abs(float(o.get("price", 0)) - price)
            if best is None or diff < best[0]:
                best = (diff, o)
        if best:
            o = best[1]
            return o.get("action"), float(o["price"]), o.get("desc", "주문계획 매칭")

        held = int(st.get("qty", 0))
        qtr = max(1, math.floor(held / 4)) if held > 0 else 1
        if qty <= qtr:
            return "SELL_QUARTER", price, "수동/외부 매도 (쿼터 추정)"
        return None, price, "수동/외부 매도 (익절 추정)"

    def _refresh_fill_dates_from_closed_orders(
        self, symbol: str, target_qty: int | None = None,
    ) -> int:
        """토스 CLOSED 주문 orderedAt으로 fill_log·trades 재구성."""
        try:
            fills = self.app.broker.list_broker_fills(symbol, days=90, max_orders=200)
        except Exception:
            logger.exception("refresh fill dates failed %s", symbol)
            return 0
        if not fills:
            logger.warning("no broker fills for %s", symbol)
            return 0
        st = self.app.state.load(symbol)
        qty = int(target_qty if target_qty is not None else st.get("qty", 0))
        if qty <= 0:
            try:
                broker = self.app.broker.get_holdings_item(symbol)
                qty = int(broker.get("qty", 0) or 0)
            except Exception:
                pass
        if qty <= 0:
            return 0
        log = st.get("fill_log", [])
        self.app.cycles.apply_broker_fill_dates(log, fills)
        self.app.state.save(symbol, st)
        self.app.cycles.ensure_current(symbol, float(st.get("principal", 0.0)))
        n = self.app.cycles.rebuild_trades_from_broker(symbol, fills, log, qty)
        if n:
            logger.info(
                "rebuilt %s trades for %s from %d broker fills (qty=%d)",
                n, symbol, len(fills), qty,
            )
        return n

    @staticmethod
    def _is_processed(st: dict, fill_id: str) -> bool:
        return any(e.get("id") == fill_id for e in st.get("fill_log", []))

    @staticmethod
    def _append_fill_log(st: dict, entry: dict) -> None:
        log = st.setdefault("fill_log", [])
        log.append(entry)
        limit = 100
        if len(log) > limit:
            st["fill_log"] = log[-limit:]

    @staticmethod
    def track_order(st: dict, symbol: str, order_id: str, side: str, qty: int) -> None:
        if not order_id:
            return
        tracked = st.setdefault("tracked_orders", [])
        tracked.append({
            "order_id": str(order_id),
            "symbol": symbol.upper(),
            "side": side.upper(),
            "qty": int(qty),
            "at": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
        })
        if len(tracked) > 50:
            st["tracked_orders"] = tracked[-50:]
