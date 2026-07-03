"""Job execution orchestrator."""

import asyncio
import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from app import App
from broker.toss_client import TossClient
from strategy.order_planner import (
    JobPhase,
    filter_orders_for_phase,
    gate_orders_by_close_price,
)
from strategy.fill_reconciler import FillReconciler

logger = logging.getLogger(__name__)
KST = ZoneInfo("Asia/Seoul")


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

    async def run_for_symbol(self, symbol: str, phase: JobPhase, premium: int | None = None) -> str:
        if premium is None:
            premium = self.app.runtime.premium_default()
        st = self.app.state.load(symbol)
        api = self.app.broker.get_holdings_item(symbol)
        price = api["current_price"] or self.app.broker.get_price(symbol)
        plan = self.app.strategy.get_plan(
            symbol, price, st["avg_price"], st["qty"], st["T"],
            premium, st["principal"], st["split_count"], st.get("force_one", False),
            take_profit_pct=st.get("take_profit_pct"),
        )
        filtered = filter_orders_for_phase(plan, phase)

        # 장 마감 30초 전 종가 근사가(price)로 LOC 흉내 — 조건 맞는 주문만 통과
        is_dry = self.app.settings.dry_run or not self.app.settings.has_toss
        gated = gate_orders_by_close_price(filtered, 0.0 if is_dry else price)
        orders = gated["buy_orders"] + gated["sell_orders"]
        if not orders:
            return f"[{symbol}] {phase.value}: 주문 없음"

        ok = 0
        grad_msg = None
        for order in orders:
            side = order["side"]
            # 시장가로 체결되므로 기록은 종가 근사가(price)로 남긴다
            if not is_dry and price > 0:
                order = {**order, "price": round(price, 2)}
            for attempt in range(self._retry):
                try:
                    if is_dry:
                        success = True
                        order_id = None
                    else:
                        order_id = self.app.broker.place_market_order(
                            symbol, side, order["qty"]
                        )
                        success = bool(order_id)
                    if success:
                        ok += 1
                        if order_id:
                            FillReconciler.track_order(st, symbol, order_id, side, order["qty"])
                        if side == "BUY":
                            st = self.app.fills.apply_buy_fill(
                                st, order, self.app.cycles, symbol
                            )
                        else:
                            st, completed = self.app.fills.apply_sell_fill(
                                st, order, self.app.cycles, symbol
                            )
                            if completed:
                                grad_msg = self.app.cycles.format_graduation_message(completed, symbol)
                        self.app.state.save(symbol, st)
                        break
                except Exception as e:
                    logger.exception("Order failed %s attempt %s", symbol, attempt + 1)
                    if attempt == self._retry - 1:
                        await self._notify(f"🚨 [{symbol}] 주문 실패: {e}")
                await asyncio.sleep(0.3)

        msg = f"✅ [{symbol}] {phase.value} {ok}/{len(orders)}건"
        if grad_msg:
            await self._notify(grad_msg, html=True)
        return msg

    def _target_us_date_for_phase(self, phase: JobPhase) -> str:
        now = datetime.now(KST)
        if phase in (JobPhase.JOB3_LOC_CLOSE, JobPhase.JOB1_LOC_CLOSE):
            return TossClient.target_us_date_for_morning_job(now)
        return TossClient.target_us_date_for_ny_job(now)

    def _phase_label(self, phase: JobPhase) -> str:
        return {
            JobPhase.JOB1_LOC_CLOSE: "LOC",
            JobPhase.JOB3_LOC_CLOSE: "LOC",
            JobPhase.JOB2_SETTLE: "체결정리",
        }.get(phase, phase.value)

    async def run_phase(self, phase: JobPhase, premium: int | None = None) -> None:
        if premium is None:
            premium = self.app.runtime.premium_default()

        if self.app.runtime.is_paused():
            await self._notify("⏸️ 자동매매가 정지 상태예요. /resume 로 재개하세요.")
            return

        if phase != JobPhase.JOB4_REPORT:
            target = self._target_us_date_for_phase(phase)
            try:
                open_, us_date = self.app.broker.check_us_regular_session(target)
            except Exception as e:
                logger.exception("market open check failed")
                await self._notify(f"🚨 장 개장 확인 실패: {e}")
                return
            if not open_:
                label = self._phase_label(phase)
                hint = ""
                if phase in (JobPhase.JOB3_LOC_CLOSE, JobPhase.JOB1_LOC_CLOSE):
                    hint = "\n(한국 새벽 Job — 오늘 밤 열릴 미국 정규장 기준)"
                await self._notify(
                    f"📅 <b>{us_date}</b> 미국 정규장 휴장 — {label} Job 스킵 (주문 없음){hint}",
                    html=True,
                )
                return

        symbols = self._active_symbols()
        if not symbols:
            await self._notify("⚠️ 거래 종목이 없어요. /setting → 📡 거래 종목에서 켜주세요.")
            return

        lines = []
        for sym in symbols:
            try:
                lines.append(await self.run_for_symbol(sym, phase, premium))
            except Exception as e:
                logger.exception("run_for_symbol failed %s", sym)
                lines.append(f"🚨 [{sym}] 실행 실패: {e}")
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
        header = "🔔 <b>미국 장 시작</b> — 오늘의 주문계획이에요.\n\n"
        await self._notify(header + text, html=True)

    def sync_cycle_from_broker(self, symbol: str, premium: int | None = None) -> dict:
        """토스 실계좌·체결 내역으로 T·회차·평단·주수 동기화."""
        if premium is None:
            premium = self.app.runtime.premium_default()

        reconcile = {"applied": [], "t_before": 0.0, "t_after": 0.0}
        if self.app.reconciler and not (self.app.settings.dry_run or not self.app.settings.has_toss):
            try:
                reconcile = self.app.reconciler.reconcile_symbol(symbol, premium)
            except Exception:
                logger.exception("fill reconcile failed %s", symbol)

        st = self.app.state.load(symbol)
        item = self.app.broker.get_holdings_item(symbol)
        qty = int(item.get("qty", 0) or 0)
        avg = float(item.get("avg_price", 0.0) or 0.0)
        price = float(item.get("current_price", 0.0) or 0.0)
        invested = round(qty * avg, 2)
        eval_usd = round(qty * price, 2) if price > 0 else invested

        if qty <= 0:
            return {
                "symbol": symbol, "qty": 0, "avg": 0.0, "price": price,
                "invested": 0.0, "eval": 0.0, "T": 0.0,
                "reconciled": reconcile.get("applied", []),
                "t_before": reconcile.get("t_before", 0.0),
                "t_after": reconcile.get("t_after", 0.0),
            }

        st["qty"] = qty
        st["avg_price"] = round(avg, 4)
        st["last_t_qty"] = qty
        self.app.state.save(symbol, st)

        t_val = float(st.get("T", 0.0))
        self.app.cycles.ensure_current(symbol, st["principal"])
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
        }

    async def run_cycle_sync(self, notify: bool = True) -> None:
        """활성 종목의 회차 기록을 토스 실계좌 기준으로 동기화."""
        is_dry = self.app.settings.dry_run or not self.app.settings.has_toss
        if is_dry:
            if notify:
                await self._notify("🧪 DRY_RUN — 실계좌 회차 동기화는 LIVE에서만 됩니다.")
            return
        symbols = self._active_symbols() or list(self.app.state.list_symbols())
        premium = self.app.runtime.premium_default()
        lines = ["🔄 <b>회차 동기화</b> <i>(체결·실계좌 기준)</i>"]
        for sym in symbols:
            try:
                r = self.sync_cycle_from_broker(sym, premium)
            except Exception as e:
                logger.exception("cycle sync failed %s", sym)
                lines.append(f"🚨 [{sym}] 동기화 실패: {e}")
                continue
            if r["qty"] <= 0:
                lines.append(f"◆ <b>{sym}</b> — 보유 없음")
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
        await self.run_phase(JobPhase.JOB3_LOC_CLOSE, premium)

    async def run_job2(self, **_):
        await self._notify("job2는 사용하지 않아요. 장 마감 LOC는 /job3 입니다.")

    async def run_job3(self, premium: int | None = None, **_):
        await self.run_phase(JobPhase.JOB3_LOC_CLOSE, premium)

    async def run_job4(self, **_):
        await self.run_phase(JobPhase.JOB4_REPORT)
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
            "job3": lambda **kw: self.run_job3(premium=premium),
            "job4": self.run_job4,
            "briefing": self.run_morning_briefing,
        }
        fn = mapping.get(name.lower())
        if fn:
            await fn()
        else:
            await self._notify(f"알 수 없는 Job: {name}")
