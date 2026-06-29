"""Telegram command handlers — uses App + JobExecutor, no direct broker orders except manual exec."""

import asyncio
import datetime
import logging
from zoneinfo import ZoneInfo

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from app import App
from jobs.executor import JobExecutor
from strategy.split_handler import apply_split, calc_adjustment, format_preview, parse_ratio
from telegram.dashboard_formatter import format_dashboard
from telegram.keyboards import (
    monthly_keyboard,
    plan_premium_keyboard,
    setting_keyboard,
    split_confirm_keyboard,
    split_count_keyboard,
    split_ratio_keyboard,
    symbol_picker,
)
from telegram.sender import TelegramSender

logger = logging.getLogger(__name__)


class TelegramHandler:
    def __init__(self, app: App, executor: JobExecutor, sender: TelegramSender):
        self.app = app
        self.executor = executor
        self.sender = sender
        self.kst = ZoneInfo("Asia/Seoul")
        self.ny_tz = ZoneInfo("America/New_York")

    def _symbol(self, context: ContextTypes.DEFAULT_TYPE) -> str:
        return context.user_data.get("symbol") or self.app.runtime.default_symbol()

    def _allowed(self, update: Update) -> bool:
        ids = self.app.settings.telegram_allowed_chat_ids
        if not ids:
            return True
        chat = update.effective_chat
        return chat and chat.id in ids

    async def _deny(self, update: Update) -> None:
        if update.message:
            await update.message.reply_text("⛔ 허용되지 않은 채팅입니다.")
        elif update.callback_query:
            await update.callback_query.answer("⛔ 허용되지 않은 채팅", show_alert=True)

    def _pos(self, symbol: str) -> dict:
        return self.app.broker.get_holdings_item(symbol)

    async def cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self._allowed(update):
            return await self._deny(update)
        open_today = self.app.broker.is_us_market_open_today()
        market = "🟢 개장" if open_today else "🔴 휴장"
        paused = self.app.runtime.is_paused()
        dry = self.app.settings.dry_run or not self.app.settings.has_toss
        api = "🧪 DRY_RUN" if dry else "🟢 Toss API"
        msg = (
            "🖥️ <b>라오어 무한매수 4.0</b> (v1.0)\n\n"
            f"봇: {'⏸️ 정지' if paused else '▶️ 가동'} | API: {api}\n"
            f"미증시: {market} | 종목: TQQQ + SOXL\n\n"
            "<b>명령어</b>\n"
            "/dashboard — 전체 현황\n"
            "/status — 종목 상태\n"
            "/plan — 주문 계획\n"
            "/setting — 설정\n"
            "/sync — API 잔고(수량·평단만)\n"
            "/split — 액면분할\n"
            "/cycles /monthly — 회차·월별\n"
            "/cycle_done TQQQ — 수동 졸업\n"
            "/pause /resume — 자동 Job\n"
            "/job1~4 — Job 수동 실행"
        )
        await update.message.reply_text(msg, parse_mode="HTML")

    async def cmd_dashboard(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self._allowed(update):
            return await self._deny(update)
        await update.message.reply_text(format_dashboard(self.app), parse_mode="HTML")

    async def cmd_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self._allowed(update):
            return await self._deny(update)
        parts = update.message.text.split()
        symbol = parts[1].upper() if len(parts) > 1 else self._symbol(context)
        st = self.app.state.load(symbol)
        pos = self._pos(symbol)
        price = pos["current_price"]
        summary = self.app.strategy.summarize(
            symbol, price, st["avg_price"], st["qty"], st["T"],
            st["cash"], st["split_count"],
        )
        self.app.cycles.ensure_current(symbol, st["principal"])
        live = self.app.cycles.calc_unrealized_pnl(symbol, st["qty"], st["avg_price"], price)
        cycle_line = ""
        if live:
            sign = "+" if live["cycle_pnl_usd"] >= 0 else ""
            cycle_line = (
                f"회차 {live['cycle_no']} ({live['started_at']}~)\n"
                f"회차 손익: {sign}${live['cycle_pnl_usd']:,.2f} ({sign}{live['cycle_pnl_pct']:.2f}%)\n"
            )
        profit = 0.0
        if st["avg_price"] > 0 and price > 0:
            profit = (price - st["avg_price"]) / st["avg_price"] * 100
        msg = (
            f"📊 <b>[{symbol}]</b>\n{cycle_line}"
            f"T={st['T']:.4f} ({st['split_count']}분할) | {summary['mode']}\n"
            f"1회매수 ${summary['one_buy_amount']:,.2f} | 별 {summary['star_pct']:+.2f}%\n"
            f"기록: {st['qty']}주 @ ${st['avg_price']:.2f}\n"
            f"API: {pos['qty']}주 @ ${pos['avg_price']:.2f} | 현재 ${price:.2f} ({profit:+.2f}%)\n"
            f"예수금 ${st['cash']:,.2f} (수동)"
        )
        await update.message.reply_text(msg, parse_mode="HTML")

    async def cmd_plan(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self._allowed(update):
            return await self._deny(update)
        await update.message.reply_text(
            "종목 선택:",
            reply_markup=symbol_picker("PLAN_SYM"),
        )

    async def cmd_setting(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self._allowed(update):
            return await self._deny(update)
        symbol = self._symbol(context)
        st = self.app.state.load(symbol)
        msg = (
            f"⚙️ <b>설정 — {symbol}</b>\n"
            f"원금 ${st['principal']:,.0f} | 예수금 ${st['cash']:,.2f} (수동)\n"
            f"분할 {st['split_count']} | 기본 할증 {self.app.runtime.premium_default()}%"
        )
        await update.message.reply_text(msg, reply_markup=setting_keyboard(), parse_mode="HTML")

    async def cmd_sync(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self._allowed(update):
            return await self._deny(update)
        parts = update.message.text.split()
        symbol = parts[1].upper() if len(parts) > 1 else self._symbol(context)
        pos = self._pos(symbol)
        st = self.app.state.sync_holdings(symbol, pos["qty"], pos["avg_price"])
        await update.message.reply_text(
            f"🔄 [{symbol}] API 반영\n"
            f"수량 {st['qty']}주 | 평단 ${st['avg_price']:.2f}\n"
            f"예수금 ${st['cash']:,.2f} (수동, 변경 없음)"
        )

    async def cmd_split(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self._allowed(update):
            return await self._deny(update)
        text = "📐 액면분할 — 종목 선택:"
        markup = symbol_picker("SPLIT_PICK")
        target = update.callback_query.message if update.callback_query else update.message
        await target.reply_text(text, reply_markup=markup)

    async def cmd_cycles(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self._allowed(update):
            return await self._deny(update)
        kb = symbol_picker("CYCLES")
        kb.inline_keyboard.append([InlineKeyboardButton("전체", callback_data="CYCLES:ALL")])
        target = update.callback_query.message if update.callback_query else update.message
        await target.reply_text("📒 회차 기록 — 종목:", reply_markup=kb)

    async def cmd_monthly(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self._allowed(update):
            return await self._deny(update)
        target = update.callback_query.message if update.callback_query else update.message
        await target.reply_text("📅 월별 수익:", reply_markup=monthly_keyboard())

    async def cmd_cycle_done(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self._allowed(update):
            return await self._deny(update)
        parts = update.message.text.split()
        symbol = parts[1].upper() if len(parts) > 1 else self._symbol(context)
        completed = self.app.cycles.complete_cycle(symbol, note="수동 졸업")
        if not completed:
            return await update.message.reply_text(f"⚠️ [{symbol}] 진행 중 회차 없음")
        st = self.app.state.load(symbol)
        st["qty"] = 0
        st["avg_price"] = 0.0
        st["T"] = 0.0
        self.app.state.save(symbol, st)
        await update.message.reply_text(
            self.app.cycles.format_graduation_message(completed, symbol),
            parse_mode="HTML",
        )

    async def cmd_history(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self._allowed(update):
            return await self._deny(update)
        symbol = self._symbol(context)
        sym_data = self.app.cycles.get_symbol_data(symbol)
        completed = sym_data.get("completed", [])
        if not completed:
            return await update.message.reply_text("완료된 회차가 없습니다.")
        lines = [f"📜 <b>[{symbol}] 졸업 명예의 전당</b>\n"]
        for c in reversed(completed[-20:]):
            sign = "+" if c["profit_usd"] >= 0 else ""
            lines.append(
                f"#{c['cycle_no']} {c['ended_at']} {sign}${c['profit_usd']:,.2f} ({sign}{c['profit_pct']:.2f}%)"
            )
        await update.message.reply_text("\n".join(lines), parse_mode="HTML")

    async def cmd_pause(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self._allowed(update):
            return await self._deny(update)
        self.app.runtime.set_paused(True)
        await update.message.reply_text("🛑 자동 Job 일시정지")

    async def cmd_resume(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self._allowed(update):
            return await self._deny(update)
        self.app.runtime.set_paused(False)
        await update.message.reply_text("▶️ 자동 Job 재개")

    async def cmd_job(self, update: Update, context: ContextTypes.DEFAULT_TYPE, name: str):
        if not self._allowed(update):
            return await self._deny(update)
        await update.message.reply_text(f"⏳ {name} 실행 중...")
        if name == "morning_briefing":
            await self.executor.run_morning_briefing()
        else:
            await getattr(self.executor, f"run_{name}")()

    async def handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self._allowed(update):
            return await self._deny(update)
        query = update.callback_query
        await query.answer()
        data = query.data

        if data.startswith("PLAN_SYM:"):
            context.user_data["plan_symbol"] = data.split(":")[1]
            await query.edit_message_text(
                f"[{context.user_data['plan_symbol']}] 할증률 선택:",
                reply_markup=plan_premium_keyboard(),
            )
            return

        if data.startswith("PLAN:"):
            premium = int(data.split(":")[1])
            symbol = context.user_data.get("plan_symbol", self._symbol(context))
            st = self.app.state.load(symbol)
            pos = self._pos(symbol)
            plan = self.app.strategy.get_plan(
                symbol, pos["current_price"], st["avg_price"], st["qty"], st["T"],
                premium, st["cash"], st["split_count"], st["principal"],
            )
            msg = self._format_plan(symbol, st, plan, premium)
            kb = InlineKeyboardMarkup([[
                InlineKeyboardButton("🚀 수동 주문", callback_data=f"EXEC:{symbol}:{premium}"),
            ]])
            await query.edit_message_text(msg, reply_markup=kb, parse_mode="HTML")
            return

        if data.startswith("EXEC:"):
            _, symbol, premium_str = data.split(":")
            await self._execute_manual(query.message.chat_id, symbol, int(premium_str), context)
            await query.edit_message_reply_markup(reply_markup=None)
            return

        if data == "set_ticker":
            await query.edit_message_text("종목:", reply_markup=symbol_picker("select"))
            return

        if data.startswith("select:"):
            sym = data.split(":")[1]
            self.app.runtime.set_default_symbol(sym)
            context.user_data["symbol"] = sym
            await query.edit_message_text(f"✅ 기본 종목 → {sym}")
            return

        if data in ("set_seed", "set_cash"):
            context.user_data["awaiting"] = data
            context.user_data["awaiting_symbol"] = self._symbol(context)
            await query.edit_message_text("숫자를 입력하세요.")
            return

        if data == "set_split":
            sym = self._symbol(context)
            await query.edit_message_text("분할 선택:", reply_markup=split_count_keyboard(sym))
            return

        if data == "set_split_pick":
            sym = self._symbol(context)
            await query.edit_message_text("분할 선택:", reply_markup=split_count_keyboard(sym))
            return

        if data.startswith("SPLIT_COUNT:"):
            _, ticker, count = data.split(":")
            self.app.state.set_split_count(ticker, int(count))
            await query.edit_message_text(f"✅ [{ticker}] {count}분할")
            return

        if data.startswith("SPLIT_PICK:"):
            ticker = data.split(":")[1]
            st = self.app.state.load(ticker)
            await query.edit_message_text(
                f"📐 [{ticker}] {st['qty']}주 @ ${st['avg_price']:.4f}\n비율 선택:",
                reply_markup=split_ratio_keyboard(ticker),
            )
            return

        if data.startswith("SPLIT_CUSTOM:"):
            ticker = data.split(":")[1]
            context.user_data["awaiting"] = f"split_ratio:{ticker}"
            await query.edit_message_text(f"[{ticker}] 비율 입력 (예: 2, 2:1, 0.5)")
            return

        if data.startswith("SPLIT_RATIO:"):
            _, ticker, ratio_str = data.split(":")
            ratio = float(ratio_str)
            st = self.app.state.load(ticker)
            preview = calc_adjustment(st["qty"], st["avg_price"], ratio)
            await query.edit_message_text(
                format_preview(ticker, preview),
                reply_markup=split_confirm_keyboard(ticker, ratio),
            )
            return

        if data.startswith("SPLIT_APPLY:"):
            _, ticker, ratio_str = data.split(":")
            ratio = float(ratio_str)
            st = self.app.state.load(ticker)
            apply_split(st, ratio, note="텔레그램 수동")
            self.app.state.save(ticker, st)
            await query.edit_message_text(
                f"✅ [{ticker}] 반영\n{st['qty']}주 @ ${st['avg_price']:.4f}\nT·예수금 유지"
            )
            return

        if data == "SPLIT_CANCEL":
            await query.edit_message_text("취소됨")
            return

        if data == "open_split":
            await self.cmd_split(update, context)
            return
        if data == "open_cycles":
            await self.cmd_cycles(update, context)
            return
        if data == "open_monthly":
            await self.cmd_monthly(update, context)
            return
        if data == "open_dashboard":
            await query.message.reply_text(format_dashboard(self.app), parse_mode="HTML")
            return

        if data.startswith("CYCLES:"):
            symbol = data.split(":")[1]
            await self._send_cycles(query.message, symbol)
            return

        if data.startswith("MONTHLY:"):
            _, year_str, sym = data.split(":")
            year = int(year_str)
            sym_arg = None if sym == "ALL" else sym
            msg = self.app.cycles.format_monthly_report(year, sym_arg)
            await query.message.reply_text(msg, parse_mode="HTML")
            return

    def _format_plan(self, symbol: str, st: dict, plan: dict, premium: int) -> str:
        msg = (
            f"🎯 <b>[{symbol}]</b> T={st['T']:.4f} | 예수금 ${st['cash']:,.2f}\n"
            f"모드 {plan['mode']} | 1회 ${plan['one_buy_amount']:,.2f} | +{premium}%\n"
            "────────────────\n"
        )
        orders = plan.get("buy_orders", []) + plan.get("sell_orders", [])
        if not orders:
            msg += "주문 없음"
        for o in orders:
            icon = "🔹" if o["side"] == "BUY" else "🔸"
            msg += f"{icon} {o['desc']} → ${o['price']:.2f} x{o['qty']}\n"
        return msg

    async def _send_cycles(self, target, symbol: str):
        if symbol == "ALL":
            parts = []
            for sym in self.app.state.list_symbols():
                st = self.app.state.load(sym)
                pos = self._pos(sym)
                self.app.cycles.ensure_current(sym, st["principal"])
                parts.append(self.app.cycles.format_cycles_report(
                    sym, st["qty"], st["avg_price"], pos["current_price"],
                ))
            msg = "\n\n".join(parts)
        else:
            st = self.app.state.load(symbol)
            pos = self._pos(symbol)
            self.app.cycles.ensure_current(symbol, st["principal"])
            msg = self.app.cycles.format_cycles_report(
                symbol, st["qty"], st["avg_price"], pos["current_price"],
            )
        await target.reply_text(msg, parse_mode="HTML")

    async def _execute_manual(self, chat_id: int, symbol: str, premium: int, context: ContextTypes.DEFAULT_TYPE):
        st = self.app.state.load(symbol)
        pos = self._pos(symbol)
        plan = self.app.strategy.get_plan(
            symbol, pos["current_price"], st["avg_price"], st["qty"], st["T"],
            premium, st["cash"], st["split_count"], st["principal"],
        )
        orders = plan.get("buy_orders", []) + plan.get("sell_orders", [])
        ok = 0
        grad = None
        for order in orders:
            side = order["side"]
            try:
                if self.app.settings.dry_run or not self.app.settings.has_toss:
                    success = True
                else:
                    success = self.app.broker.place_limit_order(
                        symbol, side, order["price"], order["qty"],
                    )
                if success:
                    ok += 1
                    if side == "BUY":
                        st = self.app.fills.apply_buy_fill(st, order, self.app.cycles, symbol)
                    else:
                        st, completed = self.app.fills.apply_sell_fill(
                            st, order, self.app.cycles, symbol,
                        )
                        if completed:
                            grad = self.app.cycles.format_graduation_message(completed, symbol)
                    self.app.state.save(symbol, st)
            except Exception as e:
                logger.exception("Manual order failed")
                await context.bot.send_message(chat_id, f"🚨 주문 실패: {e}")
            await asyncio.sleep(0.3)
        if grad:
            await context.bot.send_message(chat_id, grad, parse_mode="HTML")
        else:
            await context.bot.send_message(chat_id, f"✅ [{symbol}] {ok}/{len(orders)}건")

    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self._allowed(update):
            return await self._deny(update)
        text = update.message.text.strip()
        if text.startswith("/set_t"):
            try:
                parts = text.split()
                new_t = float(parts[1])
                symbol = parts[2].upper() if len(parts) > 2 else self._symbol(context)
                self.app.state.set_T(symbol, new_t)
                await update.message.reply_text(f"✅ [{symbol}] T → {new_t}")
            except (IndexError, ValueError):
                await update.message.reply_text("예: /set_t 5.25 TQQQ")
            return

        awaiting = context.user_data.get("awaiting")
        if not awaiting:
            return

        symbol = context.user_data.get("awaiting_symbol", self._symbol(context))
        if awaiting.startswith("split_ratio:"):
            ticker = awaiting.split(":")[1]
            try:
                ratio = parse_ratio(text)
                st = self.app.state.load(ticker)
                preview = calc_adjustment(st["qty"], st["avg_price"], ratio)
                context.user_data["awaiting"] = None
                await update.message.reply_text(
                    format_preview(ticker, preview),
                    reply_markup=split_confirm_keyboard(ticker, ratio),
                )
            except ValueError as e:
                await update.message.reply_text(f"❌ {e}")
            return

        try:
            val = float(text)
            if awaiting == "set_seed":
                self.app.state.set_principal(symbol, val)
            elif awaiting == "set_cash":
                self.app.state.set_cash(symbol, val)
                context.user_data["awaiting"] = None
                return await update.message.reply_text(f"✅ [{symbol}] 예수금 ${val:,.2f}")
            elif awaiting == "set_split":
                self.app.state.set_split_count(symbol, int(val))
            context.user_data["awaiting"] = None
            await update.message.reply_text("✅ 저장됨")
        except ValueError:
            await update.message.reply_text("숫자만 입력하세요.")
