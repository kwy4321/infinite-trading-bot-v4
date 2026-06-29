"""Job execution orchestrator."""

import asyncio
import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from app import App
from strategy.order_planner import JobPhase, filter_orders_for_phase

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

    async def run_for_symbol(self, symbol: str, phase: JobPhase, premium: int = 10) -> str:
        st = self.app.state.load(symbol)
        api = self.app.broker.get_holdings_item(symbol)
        price = api["current_price"] or self.app.broker.get_price(symbol)
        plan = self.app.strategy.get_plan(
            symbol, price, st["avg_price"], st["qty"], st["T"],
            premium, st["cash"], st["split_count"], st["principal"],
        )
        filtered = filter_orders_for_phase(plan, phase)
        orders = filtered["buy_orders"] + filtered["sell_orders"]
        if not orders:
            return f"[{symbol}] {phase.value}: 주문 없음"

        ok = 0
        grad_msg = None
        for order in orders:
            side = order["side"]
            for attempt in range(self._retry):
                try:
                    if self.app.settings.dry_run or not self.app.settings.has_toss:
                        success = True
                    else:
                        success = self.app.broker.place_limit_order(
                            symbol, side, order["price"], order["qty"]
                        )
                    if success:
                        ok += 1
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

    async def run_phase(self, phase: JobPhase, premium: int = 10) -> None:
        if not self.app.broker.is_us_market_open_today() and phase != JobPhase.JOB4_REPORT:
            await self._notify("📅 오늘 미국 휴장 — Job 스킵")
            return
        lines = []
        for sym in self._active_symbols():
            lines.append(await self.run_for_symbol(sym, phase, premium))
        if lines:
            await self._notify("\n".join(lines))

    async def run_morning_briefing(self) -> None:
        from briefing.morning_briefing import build_briefing
        text = await build_briefing(self.app)
        await self._notify(text, html=True)

    async def run_backup(self) -> None:
        from jobs.backup_job import run_backup
        path = run_backup(self.app.paths.data_root)
        await self._notify(f"📦 백업 완료: {path.name}")

    async def run_job1(self, **_):
        await self.run_phase(JobPhase.JOB1_TAKE_PROFIT)

    async def run_job2(self, **_):
        await self.run_phase(JobPhase.JOB2_SETTLE)

    async def run_job3(self, premium: int = 10, **_):
        await self.run_phase(JobPhase.JOB3_BUY, premium)

    async def run_job4(self, **_):
        await self.run_phase(JobPhase.JOB4_REPORT)
        await self.run_backup()
        now = datetime.now(KST).strftime("%Y-%m-%d %H:%M")
        await self._notify(f"📊 Job4 완료 ({now})")

    async def force_job(self, name: str, premium: int = 10) -> None:
        mapping = {
            "job1": self.run_job1,
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
