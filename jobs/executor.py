"""Job execution orchestrator."""

import asyncio
import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from app import App
from strategy.order_planner import (
    JobPhase,
    filter_orders_for_phase,
    gate_orders_by_close_price,
)

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
                    else:
                        success = self.app.broker.place_market_order(
                            symbol, side, order["qty"]
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

    async def run_phase(self, phase: JobPhase, premium: int | None = None) -> None:
        if premium is None:
            premium = self.app.runtime.premium_default()

        if self.app.runtime.is_paused():
            await self._notify("⏸️ 자동매매가 정지 상태예요. /resume 로 재개하세요.")
            return

        try:
            market_open = self.app.broker.is_us_market_open_today()
        except Exception as e:
            logger.exception("market open check failed")
            await self._notify(f"🚨 장 개장 확인 실패: {e}")
            return
        if not market_open and phase != JobPhase.JOB4_REPORT:
            await self._notify("📅 오늘은 미국 휴장이라 자동 실행을 건너뛰었어요.")
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

    def sync_cycle_from_broker(self, symbol: str) -> dict:
        """토스 실계좌로 평단가·주수·평가금액을 가져와 현재 회차에 기록.

        T(진행 회차)는 토스가 주지 않는 값이라, 봇이 매수마다 누적 관리하는
        state["T"](풀매수 +1, 절반매수 +0.5)를 그대로 쓴다. 실계좌의 평단/주수는
        진실로 삼아 동기화한다.
        """
        st = self.app.state.load(symbol)
        item = self.app.broker.get_holdings_item(symbol)
        qty = int(item.get("qty", 0) or 0)
        avg = float(item.get("avg_price", 0.0) or 0.0)
        price = float(item.get("current_price", 0.0) or 0.0)
        invested = round(qty * avg, 2)
        eval_usd = round(qty * price, 2) if price > 0 else invested

        if qty <= 0:
            return {"symbol": symbol, "qty": 0, "avg": 0.0, "price": price,
                    "invested": 0.0, "eval": 0.0, "T": 0.0}

        # 평단·주수만 실계좌 기준으로 동기화 (T는 건드리지 않음)
        st["qty"] = qty
        st["avg_price"] = round(avg, 4)
        self.app.state.save(symbol, st)

        t_val = float(st.get("T", 0.0))
        self.app.cycles.ensure_current(symbol, st["principal"])
        self.app.cycles.record_snapshot(
            symbol, t_val=t_val, avg_price=avg, qty=qty,
            current_price=price, eval_usd=eval_usd, invested_usd=invested,
            principal=st["principal"],
        )
        return {"symbol": symbol, "qty": qty, "avg": avg, "price": price,
                "invested": invested, "eval": eval_usd, "T": t_val}

    async def run_cycle_sync(self, notify: bool = True) -> None:
        """활성 종목의 회차 기록을 토스 실계좌 기준으로 동기화."""
        is_dry = self.app.settings.dry_run or not self.app.settings.has_toss
        if is_dry:
            if notify:
                await self._notify("🧪 DRY_RUN — 실계좌 회차 동기화는 LIVE에서만 됩니다.")
            return
        symbols = self._active_symbols() or list(self.app.state.list_symbols())
        lines = ["🔄 <b>회차 동기화</b> <i>(토스 실계좌 기준)</i>"]
        for sym in symbols:
            try:
                r = self.sync_cycle_from_broker(sym)
            except Exception as e:
                logger.exception("cycle sync failed %s", sym)
                lines.append(f"🚨 [{sym}] 동기화 실패: {e}")
                continue
            if r["qty"] <= 0:
                lines.append(f"◆ <b>{sym}</b> — 보유 없음")
                continue
            lines.append(
                f"◆ <b>{sym}</b>\n"
                f"🎯 T <b>{r['T']:g}</b> · 평단 <b>${r['avg']:,.2f}</b> · <b>{r['qty']}</b>주\n"
                f"💵 평가금액 <b>${r['eval']:,.2f}</b> <i>(투입 ${r['invested']:,.2f})</i>"
            )
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
