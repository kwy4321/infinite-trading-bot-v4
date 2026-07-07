"""Job execution orchestrator."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from app import App
from broker.toss_client import TossClient
from strategy.order_planner import (
    CLOSE_LEAD_SECONDS,
    JobPhase,
    filter_orders_for_phase,
    gate_orders_by_close_price,
)
from strategy.fill_reconciler import FillReconciler
from strategy.session_fill import (
    has_us_session_fill_from_broker,
    has_us_session_fill_in_state,
)
from tg.notifications import (
    format_market_close_report,
    format_market_close_start,
    format_market_open,
    format_order_filled,
    format_order_not_filled,
    format_order_submitted,
    order_label,
)
from tg.ui import dim

logger = logging.getLogger(__name__)
KST = ZoneInfo("Asia/Seoul")
NY = ZoneInfo("America/New_York")
_LOC_PHASES = (JobPhase.JOB1_LOC_CLOSE, JobPhase.JOB3_LOC_CLOSE)


class JobExecutor:
    def __init__(self, app: App, sender=None):
        self.app = app
        self.sender = sender
        self._retry = 3

    async def _notify(self, text: str, html: bool = False):
        if self.sender:
            await self.sender.send(text, parse_mode="HTML" if html else None)

    def _active_symbols(self) -> list:
        if self.app.runtime.is_paused():
            return []
        return self.app.runtime.active_symbols()

    def _is_dry(self) -> bool:
        return self.app.settings.dry_run or not self.app.settings.has_toss

    async def _already_traded_for_us_session(
        self, symbol: str, us_date: str, *, st: dict | None = None,
    ) -> bool:
        """해당 미국 거래일(ET)에 이미 체결됐으면 True — 종가 LOC 중복 방지."""
        if st is None:
            st = self.app.state.load(symbol)
        if has_us_session_fill_in_state(st, symbol, us_date, self.app.cycles):
            return True
        if not self._is_dry():
            try:
                return await asyncio.to_thread(
                    has_us_session_fill_from_broker,
                    self.app.broker, symbol, us_date,
                )
            except Exception:
                logger.exception("broker session fill check failed %s", symbol)
        return False

    @staticmethod
    def _in_close_order_window(kst_now: datetime | None = None) -> bool:
        """자동 주문 허용 — 미국 종가 직전 ±3분만 (재시작·수동 오주문 방지)."""
        now = kst_now or datetime.now(KST)
        is_summer = now.astimezone(NY).dst() != timedelta(0)
        close_h, close_m = (5, 0) if is_summer else (6, 0)
        scheduled = datetime(
            now.year, now.month, now.day, close_h, close_m, 0, tzinfo=KST,
        ) - timedelta(seconds=CLOSE_LEAD_SECONDS)
        margin = timedelta(minutes=3)
        return scheduled - margin <= now <= scheduled + margin

    async def _execute_one_order(
        self,
        symbol: str,
        order: dict,
        ref_price: float,
        st: dict,
        *,
        use_market: bool = False,
        use_loc: bool = False,
        notify: bool = True,
        wait_fill: bool = True,
    ) -> tuple[bool, bool, dict, str | None, str]:
        """Returns (submitted, filled, state, graduation_message, order_id)."""
        is_dry = self._is_dry()
        side = order["side"]
        qty = int(order["qty"])
        label = order_label(order.get("desc", ""))
        limit_price = float(order.get("price", 0))

        for attempt in range(self._retry):
            try:
                if is_dry:
                    placed = {"order_id": ""}
                elif use_loc:
                    placed = await asyncio.to_thread(
                        self.app.broker.place_loc_order, symbol, side, limit_price, qty,
                    )
                elif use_market:
                    placed = await asyncio.to_thread(
                        self.app.broker.place_market_order, symbol, side, qty,
                    )
                else:
                    placed = await asyncio.to_thread(
                        self.app.broker.place_limit_order,
                        symbol, side, limit_price, qty,
                    )

                oid = str(placed.get("order_id") or "")
                if notify:
                    await self._notify(
                        format_order_submitted(
                            symbol, side, qty, label, order_id=oid, dry=is_dry,
                            loc=use_loc and not is_dry,
                        ),
                        html=True,
                    )

                if is_dry:
                    fill_price = ref_price if ref_price > 0 else limit_price
                    filled_qty = qty
                    status = "FILLED"
                    fill_time = datetime.now(KST).isoformat(timespec="seconds")
                else:
                    if oid:
                        FillReconciler.track_order(st, symbol, oid, side, qty)
                    if not wait_fill:
                        self.app.state.save(symbol, st)
                        return True, False, st, None, oid
                    fill_timeout = 120.0 if use_loc else 90.0
                    detail = await asyncio.to_thread(
                        self.app.broker.wait_for_fill, oid, fill_timeout,
                    )
                    filled_qty = int(float(detail.get("filled_quantity") or 0))
                    fill_price = float(
                        detail.get("average_filled_price") or ref_price or limit_price or 0
                    )
                    status = str(detail.get("status") or "")
                    fill_time = (
                        detail.get("filled_at")
                        or detail.get("ordered_at")
                        or datetime.now(KST).isoformat(timespec="seconds")
                    )

                grad = None
                if filled_qty > 0:
                    fill_id = (
                        FillReconciler.make_fill_id(oid, filled_qty, side)
                        if oid else ""
                    )
                    if oid and FillReconciler._is_processed(
                        st, fill_id,
                        order_id=oid, qty=filled_qty, side=side,
                    ):
                        FillReconciler.untrack_order(st, oid)
                        self.app.state.save(symbol, st)
                        return True, True, st, None, oid

                    t_before = float(st.get("T", 0.0))
                    filled_order = {
                        **order,
                        "price": round(fill_price, 2),
                        "qty": filled_qty,
                        "ordered_at": fill_time,
                        "filled_at": fill_time,
                        "order_id": oid or None,
                        "fill_id": fill_id or None,
                    }
                    if notify:
                        await self._notify(
                            format_order_filled(
                                symbol, side, filled_qty, fill_price, label, dry=is_dry,
                            ),
                            html=True,
                        )
                    if side == "BUY":
                        st = self.app.fills.apply_buy_fill(
                            st, filled_order, self.app.cycles, symbol,
                        )
                    else:
                        st, completed = self.app.fills.apply_sell_fill(
                            st, filled_order, self.app.cycles, symbol,
                        )
                        if completed:
                            grad = self.app.cycles.format_graduation_message(
                                completed, symbol,
                            )
                    if oid and not is_dry:
                        if fill_id and not FillReconciler._is_processed(
                            st, fill_id,
                            order_id=oid, qty=filled_qty, side=side,
                        ):
                            FillReconciler._append_fill_log(st, {
                                "id": fill_id,
                                "order_id": oid,
                                "symbol": symbol.upper(),
                                "side": side,
                                "qty": filled_qty,
                                "price": round(fill_price, 2),
                                "ordered_at": fill_time,
                                "filled_at": fill_time,
                                "at": fill_time,
                                "source": "bot",
                                "t_before": t_before,
                                "t_after": float(st.get("T", 0.0)),
                                "qty_after": int(st.get("qty", 0)),
                                "avg_after": float(st.get("avg_price", 0.0)),
                            })
                        FillReconciler.untrack_order(st, oid)
                    return True, True, st, grad, oid

                if notify:
                    await self._notify(
                        format_order_not_filled(symbol, side, label, status),
                        html=True,
                    )
                if oid and not is_dry:
                    FillReconciler.untrack_order(st, oid)
                return True, False, st, None, oid
            except Exception as e:
                logger.exception("Order failed %s attempt %s", symbol, attempt + 1)
                if attempt == self._retry - 1:
                    await self._notify(f"🚨 [{symbol}] 주문 실패: {e}")
            await asyncio.sleep(0.3)
        return False, False, st, None, ""

    async def _wait_loc_fill(
        self,
        symbol: str,
        order: dict,
        oid: str,
        ref_price: float,
        st: dict,
        *,
        notify: bool = True,
    ) -> tuple[bool, dict, str | None]:
        """LOC 접수 후 종가 경매 체결 대기."""
        side = order["side"]
        qty = int(order["qty"])
        label = order_label(order.get("desc", ""))
        limit_price = float(order.get("price", 0))

        detail = await asyncio.to_thread(
            self.app.broker.wait_for_fill, oid, 120.0,
        )
        filled_qty = int(float(detail.get("filled_quantity") or 0))
        fill_price = float(
            detail.get("average_filled_price") or ref_price or limit_price or 0
        )
        status = str(detail.get("status") or "")
        fill_time = (
            detail.get("filled_at")
            or detail.get("ordered_at")
            or datetime.now(KST).isoformat(timespec="seconds")
        )

        grad = None
        if filled_qty > 0:
            fill_id = FillReconciler.make_fill_id(oid, filled_qty, side)
            if FillReconciler._is_processed(
                st, fill_id, order_id=oid, qty=filled_qty, side=side,
            ):
                FillReconciler.untrack_order(st, oid)
                return True, st, None

            t_before = float(st.get("T", 0.0))
            filled_order = {
                **order,
                "price": round(fill_price, 2),
                "qty": filled_qty,
                "ordered_at": fill_time,
                "filled_at": fill_time,
                "order_id": oid,
                "fill_id": fill_id,
            }
            if notify:
                await self._notify(
                    format_order_filled(
                        symbol, side, filled_qty, fill_price, label,
                    ),
                    html=True,
                )
            if side == "BUY":
                st = self.app.fills.apply_buy_fill(
                    st, filled_order, self.app.cycles, symbol,
                )
            else:
                st, completed = self.app.fills.apply_sell_fill(
                    st, filled_order, self.app.cycles, symbol,
                )
                if completed:
                    grad = self.app.cycles.format_graduation_message(
                        completed, symbol,
                    )
            if not FillReconciler._is_processed(
                st, fill_id, order_id=oid, qty=filled_qty, side=side,
            ):
                FillReconciler._append_fill_log(st, {
                    "id": fill_id,
                    "order_id": oid,
                    "symbol": symbol.upper(),
                    "side": side,
                    "qty": filled_qty,
                    "price": round(fill_price, 2),
                    "ordered_at": fill_time,
                    "filled_at": fill_time,
                    "at": fill_time,
                    "source": "bot",
                    "t_before": t_before,
                    "t_after": float(st.get("T", 0.0)),
                    "qty_after": int(st.get("qty", 0)),
                    "avg_after": float(st.get("avg_price", 0.0)),
                })
            FillReconciler.untrack_order(st, oid)
            return True, st, grad

        if notify:
            await self._notify(
                format_order_not_filled(symbol, side, label, status),
                html=True,
            )
        FillReconciler.untrack_order(st, oid)
        return False, st, None

    async def execute_orders(
        self,
        symbol: str,
        orders: list[dict],
        ref_price: float,
        *,
        use_market: bool = False,
        use_loc: bool = False,
        notify_per_order: bool = True,
        wait_fill: bool = True,
    ) -> dict:
        """주문 실행. notify_per_order=False면 배치 시 건별 알림 생략."""
        st = self.app.state.load(symbol)
        submitted = filled = 0
        grad_msg = None
        is_dry = self._is_dry()
        loc_two_phase = use_loc and wait_fill and not is_dry

        pending_loc: list[tuple[dict, str]] = []
        for order in orders:
            work = dict(order)
            if not is_dry and ref_price > 0 and use_market:
                work["price"] = round(ref_price, 2)
            sub_ok, fill_ok, st, grad, oid = await self._execute_one_order(
                symbol, work, ref_price, st,
                use_market=use_market,
                use_loc=use_loc,
                notify=notify_per_order,
                wait_fill=wait_fill and not loc_two_phase,
            )
            if sub_ok:
                submitted += 1
            if loc_two_phase and sub_ok and oid:
                pending_loc.append((work, oid))
            elif fill_ok:
                filled += 1
            if grad:
                grad_msg = grad

        if loc_two_phase:
            for work, oid in pending_loc:
                fill_ok, st, grad = await self._wait_loc_fill(
                    symbol, work, oid, ref_price, st,
                    notify=notify_per_order,
                )
                if fill_ok:
                    filled += 1
                if grad:
                    grad_msg = grad

        self.app.state.save(symbol, st)
        if grad_msg:
            await self._notify(grad_msg, html=True)

        total = len(orders)
        line = f"✅ [{symbol}] 접수 {submitted}/{total} · 체결 {filled}/{total}"
        return {
            "submitted": submitted,
            "filled": filled,
            "total": total,
            "line": line,
            "grad_msg": grad_msg,
        }

    async def run_for_symbol(
        self,
        symbol: str,
        phase: JobPhase,
        premium: int | None = None,
        *,
        notify_per_order: bool = True,
        force: bool = False,
    ) -> dict:
        if premium is None:
            premium = self.app.runtime.premium_default()
        st = self.app.state.load(symbol)
        if phase in _LOC_PHASES and not force:
            us_date = self._target_us_date_for_phase(phase)
            if await self._already_traded_for_us_session(symbol, us_date, st=st):
                return {
                    "submitted": 0,
                    "filled": 0,
                    "total": 0,
                    "skipped": True,
                    "line": (
                        f"⏭️ [{symbol}] {us_date} 미국 거래일 — "
                        f"이미 체결됨, 종가 주문 스킵"
                    ),
                    "grad_msg": None,
                }
        api = self.app.broker.get_holdings_item(symbol)
        price = api["current_price"] or self.app.broker.get_price(symbol)
        plan = self.app.strategy.get_plan(
            symbol, price, st["avg_price"], st["qty"], st["T"],
            premium, st["principal"], st["split_count"], st.get("force_one", False),
            take_profit_pct=st.get("take_profit_pct"),
        )
        filtered = filter_orders_for_phase(plan, phase)
        is_dry = self._is_dry()
        if phase in _LOC_PHASES:
            if is_dry:
                gated = gate_orders_by_close_price(filtered, price)
                orders = gated["buy_orders"] + gated["sell_orders"]
            else:
                orders = filtered["buy_orders"] + filtered["sell_orders"]
        else:
            orders = []
        if not orders:
            return {
                "submitted": 0, "filled": 0, "total": 0,
                "line": f"[{symbol}] {phase.value}: 주문 없음",
                "grad_msg": None,
            }
        result = await self.execute_orders(
            symbol, orders, price,
            use_loc=True,
            notify_per_order=notify_per_order,
            wait_fill=True,
        )
        result["line"] = (
            f"✅ [{symbol}] {phase.value} "
            f"접수 {result['submitted']}/{result['total']} · "
            f"체결 {result['filled']}/{result['total']}"
        )
        return result

    def _target_us_date_for_phase(self, phase: JobPhase) -> str:
        now = datetime.now(KST)
        if phase in _LOC_PHASES:
            return TossClient.target_us_date_for_ny_job(now)
        if phase == JobPhase.JOB4_REPORT:
            return TossClient.target_us_date_for_morning_job(now)
        return TossClient.target_us_date_for_ny_job(now)

    def _phase_label(self, phase: JobPhase) -> str:
        return {
            JobPhase.JOB1_LOC_CLOSE: "종가 LOC",
            JobPhase.JOB3_LOC_CLOSE: "종가 LOC",
            JobPhase.JOB2_SETTLE: "체결정리",
        }.get(phase, phase.value)

    async def run_phase(
        self, phase: JobPhase, premium: int | None = None, *, force: bool = False,
    ) -> None:
        if premium is None:
            premium = self.app.runtime.premium_default()

        if self.app.runtime.is_paused():
            await self._notify("⏸️ 자동매매가 정지 상태예요. /resume 로 재개하세요.")
            return

        if phase in _LOC_PHASES and not force and not self._in_close_order_window():
            logger.info("LOC run_phase skipped — outside US close window (no morning orders)")
            return

        if phase != JobPhase.JOB4_REPORT:
            target = self._target_us_date_for_phase(phase)
            try:
                open_, us_date, cal_ok = self.app.broker.check_us_regular_session(target)
            except Exception as e:
                logger.exception("market open check failed")
                await self._notify(f"🚨 장 개장 확인 실패: {e}")
                return
            label = self._phase_label(phase)
            if not cal_ok:
                await self._notify(
                    f"⚠️ 미국 휴장 확인 실패 — {label} 주문 스킵\n"
                    f"{dim('토스 캘린더 API 오류. 잠시 후 /sync 또는 재시도하세요.')}",
                    html=True,
                )
                return
            if not open_:
                hint = ""
                if phase in _LOC_PHASES:
                    hint = "\n(한국 새벽 — 미국 정규장 종가 직전)"
                await self._notify(
                    f"📅 <b>{us_date}</b> 미국 정규장 휴장 — {label} Job 스킵 (주문 없음){hint}",
                    html=True,
                )
                return

        symbols = self._active_symbols()
        if not symbols:
            await self._notify("⚠️ 거래 종목이 없어요. /setting → 📡 거래 종목에서 켜주세요.")
            return

        is_loc = phase in _LOC_PHASES
        if is_loc:
            now = datetime.now(KST).strftime("%H:%M:%S")
            await self._notify(
                format_market_close_start(now, len(symbols)), html=True,
            )

        lines = []
        total_sub = total_fill = total_orders = 0
        for sym in symbols:
            try:
                result = await self.run_for_symbol(
                    sym, phase, premium,
                    notify_per_order=not is_loc,
                    force=force,
                )
                lines.append(result["line"])
                total_sub += result["submitted"]
                total_fill += result["filled"]
                total_orders += result["total"]
            except Exception as e:
                logger.exception("run_for_symbol failed %s", sym)
                lines.append(f"🚨 [{sym}] 실행 실패: {e}")

        if is_loc:
            target = self._target_us_date_for_phase(phase)
            self.app.runtime.mark_job3_run(target)
            now = datetime.now(KST).strftime("%H:%M:%S")
            await self._notify(
                format_market_close_report(
                    now, lines, total_sub, total_orders, total_fill,
                ),
                html=True,
            )
        elif lines:
            await self._notify("\n".join(lines))

    async def run_morning_briefing(self) -> None:
        try:
            from briefing.morning_briefing import build_briefing
            text = await build_briefing(self.app)
            await self._notify(text, html=True)
        except Exception as e:
            logger.exception("morning briefing failed")
            await self._notify(f"🚨 아침 브리핑 생성 실패: {e}")

    async def run_market_open_plan(self) -> None:
        """미국 장 시작 시각에 오늘의 주문계획을 자동 전송 (개장일·가동 상태에만)."""
        if self.app.runtime.is_paused():
            return
        try:
            if not self.app.broker.is_us_market_open_today():
                return
        except Exception:
            logger.exception("market open check failed (plan broadcast)")
            return
        symbols = self._active_symbols()
        if not symbols:
            await self._notify("⚠️ 거래 종목이 없어요. /setting → 📡 거래 종목에서 켜주세요.")
            return
        from tg.plan_formatter import format_plans
        premium = self.app.runtime.premium_default()
        try:
            text = format_plans(self.app, symbols, premium)
        except Exception as e:
            logger.exception("plan broadcast build failed")
            await self._notify(f"🚨 주문계획 자동 전송 실패: {e}")
            return
        now = datetime.now(KST).strftime("%H:%M")
        await self._notify(format_market_open(now), html=True)
        await self._notify(text, html=True)

    def sync_cycle_from_broker(self, symbol: str, premium: int | None = None) -> dict:
        """토스 실계좌·체결 내역으로 T·회차·평단·주수 동기화."""
        if premium is None:
            premium = self.app.runtime.premium_default()

        reconcile = {
            "applied": [], "t_before": 0.0, "t_after": 0.0,
            "holdings": {}, "warnings": [],
        }
        is_live = self.app.reconciler and not (
            self.app.settings.dry_run or not self.app.settings.has_toss
        )
        if is_live:
            try:
                reconcile = self.app.reconciler.reconcile_symbol(symbol, premium)
            except Exception:
                logger.exception("fill reconcile failed %s", symbol)
                reconcile = {
                    "applied": [], "warnings": ["체결 reconcile 실패 — T 미반영 가능"],
                    "t_before": 0.0, "t_after": 0.0, "holdings": {},
                }

        item = reconcile.get("holdings") or {}
        if not item:
            item = self.app.broker.get_holdings_item(symbol)
        qty = int(item.get("qty", 0) or 0)
        avg = float(item.get("avg_price", 0.0) or 0.0)
        price = float(item.get("current_price", 0.0) or 0.0)
        invested = round(qty * avg, 2)
        eval_usd = round(qty * price, 2) if price > 0 else invested

        st = self.app.state.load(symbol)
        if qty <= 0:
            if not is_live:
                self.app.cycles.sync_trades_from_fill_log(
                    symbol, st.get("fill_log", []), float(st.get("principal", 0.0)),
                )
                self.app.cycles.dedupe_symbol_trades(symbol)
            return {
                "symbol": symbol, "qty": 0, "avg": 0.0, "price": price,
                "invested": 0.0, "eval": 0.0, "T": 0.0,
                "reconciled": reconcile.get("applied", []),
                "t_before": reconcile.get("t_before", 0.0),
                "t_after": reconcile.get("t_after", 0.0),
                "warnings": reconcile.get("warnings", []),
            }

        st["qty"] = qty
        st["avg_price"] = round(avg, 4)
        st["last_t_qty"] = qty
        self.app.state.save(symbol, st)

        if not is_live:
            self.app.cycles.sync_trades_from_fill_log(
                symbol, st.get("fill_log", []), float(st.get("principal", 0.0)),
            )
            self.app.cycles.dedupe_symbol_trades(symbol)

        t_val = float(st.get("T", 0.0))
        self.app.cycles.record_snapshot(
            symbol, t_val=t_val, avg_price=avg, qty=qty,
            current_price=price, eval_usd=eval_usd, invested_usd=invested,
            principal=st["principal"],
        )
        return {
            "symbol": symbol, "qty": qty, "avg": avg, "price": price,
            "invested": invested, "eval": eval_usd, "T": t_val,
            "reconciled": reconcile.get("applied", []),
            "t_before": reconcile.get("t_before", t_val),
            "t_after": t_val,
            "warnings": reconcile.get("warnings", []),
        }

    async def run_cycle_sync(
        self, notify: bool = True, symbols: list[str] | None = None,
    ) -> None:
        """회차 기록을 토스 실계좌 기준으로 동기화 (symbols 미지정 시 활성 종목)."""
        is_dry = self.app.settings.dry_run or not self.app.settings.has_toss
        if is_dry:
            if notify:
                await self._notify("🧪 DRY_RUN — 실계좌 회차 동기화는 LIVE에서만 됩니다.")
            return
        targets = symbols or self._active_symbols() or list(self.app.state.list_symbols())
        premium = self.app.runtime.premium_default()
        lines = ["🔄 <b>회차 동기화</b> <i>(체결·실계좌 기준)</i>"]
        for sym in targets:
            try:
                r = await asyncio.wait_for(
                    asyncio.to_thread(self.sync_cycle_from_broker, sym, premium),
                    timeout=120.0,
                )
            except asyncio.TimeoutError:
                logger.error("cycle sync timed out %s", sym)
                lines.append(f"⚠️ [{sym}] 동기화 시간 초과 (120초) — 나중에 /sync 재시도")
                continue
            except Exception as e:
                logger.exception("cycle sync failed %s", sym)
                lines.append(f"🚨 [{sym}] 동기화 실패: {e}")
                continue
            if r["qty"] <= 0:
                lines.append(f"◆ <b>{sym}</b> — 보유 없음")
                for w in r.get("warnings") or []:
                    lines.append(f"⚠️ <b>{sym}</b> {w}")
                continue
            t_line = f"🎯 T <b>{r['T']:g}</b>"
            if r.get("reconciled"):
                tb, ta = r.get("t_before", r["T"]), r.get("t_after", r["T"])
                if ta != tb:
                    t_line = f"🎯 T <b>{tb:g}</b> → <b>{ta:g}</b>"
            lines.append(
                f"◆ <b>{sym}</b>\n"
                f"{t_line} · 평단 <b>${r['avg']:,.2f}</b> · <b>{r['qty']}</b>주\n"
                f"💵 평가금액 <b>${r['eval']:,.2f}</b> <i>(투입 ${r['invested']:,.2f})</i>"
            )
            for fill in r.get("reconciled", []):
                sym = r["symbol"]
                fill.setdefault("symbol", sym)
                if fill.get("avg_after") is None:
                    fill["avg_after"] = r["avg"]
                if fill.get("qty_after") is None:
                    fill["qty_after"] = r["qty"]
                lines.append(self.app.cycles.format_trade_line(sym, fill).strip())
            for w in r.get("warnings") or []:
                lines.append(f"⚠️ <b>{sym}</b> {w}")
        if notify:
            await self._notify("\n".join(lines), html=True)

    async def run_backup(self) -> None:
        if not self.app.settings.backup_enabled:
            return
        from jobs.backup_job import run_backup
        path = run_backup(self.app.paths.data_root, keep=self.app.settings.backup_keep)
        if path:
            await self._notify(f"📦 백업: {path.name}")

    async def run_job1(self, premium: int | None = None, **_):
        await self.run_job3(premium)

    async def run_job2(self, **_):
        await self._notify("job2는 사용하지 않아요. 종가 LOC 주문은 /job3 입니다.")

    async def run_job3(self, premium: int | None = None, *, scheduled: bool = True, **_):
        if not self._in_close_order_window():
            logger.info("job3 skipped — outside US close window")
            return
        target = self._target_us_date_for_phase(JobPhase.JOB3_LOC_CLOSE)
        if scheduled and self.app.runtime.last_job3_us_date() == target:
            logger.info("job3 skipped — already ran for US date %s", target)
            return
        if scheduled and not self.app.runtime.is_paused():
            symbols = self._active_symbols()
            skipped = []
            for sym in symbols:
                if await self._already_traded_for_us_session(sym, target):
                    skipped.append(sym)
            if symbols and len(skipped) == len(symbols):
                logger.info(
                    "job3 skipped — all symbols already filled for US date %s",
                    target,
                )
                await self._notify(
                    f"⏭️ <b>종가 LOC 스킵</b>\n"
                    f"📅 미국 거래일 <b>{target}</b> — 이미 체결됨\n"
                    f"{dim('(저녁 주문계획과 별개 · 체결된 날은 새벽 주문 없음)')}\n"
                    + "\n".join(f"· {s}" for s in skipped),
                    html=True,
                )
                self.app.runtime.mark_job3_run(target)
                return
        await self.run_phase(JobPhase.JOB3_LOC_CLOSE, premium)

    async def run_job4(self, **_):
        await self.run_cycle_sync(notify=True)
        await self.run_backup()
        now = datetime.now(KST).strftime("%Y-%m-%d %H:%M")
        await self._notify(f"📊 오늘 마무리 완료 ({now})")

    async def force_job(self, name: str, premium: int | None = None) -> None:
        if premium is None:
            premium = self.app.runtime.premium_default()
        mapping = {
            "job1": lambda **kw: self.run_job1(premium=premium),
            "job2": self.run_job2,
            "job3": lambda **kw: self.run_job3(premium=premium, scheduled=False),
            "job4": self.run_job4,
            "briefing": self.run_morning_briefing,
        }
        fn = mapping.get(name.lower())
        if fn:
            await fn()
        else:
            await self._notify(f"알 수 없는 Job: {name}")
