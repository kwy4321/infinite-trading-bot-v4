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
from config.settings import SYMBOLS
from tg.ui import (
    DIVIDER,
    badge_bot,
    badge_live,
    badge_on,
    code,
    help_block,
    market_status_label,
    quote,
    row,
    section,
    symbol_card,
    usd,
)
from tg.balance_formatter import format_balance
from tg.plan_formatter import format_plans
from tg.records_formatter import format_graduation_history, format_profit_summary
from tg.dashboard_formatter import format_dashboard
from tg.status_formatter import format_status
from tg.keyboards import (
    plan_action_keyboard,
    premium_keyboard,
    run_job_keyboard,
    setting_keyboard,
    split_confirm_keyboard,
    split_count_keyboard,
    split_ratio_keyboard,
    symbol_picker,
)
from tg.sender import TelegramSender

logger = logging.getLogger(__name__)

JOB_LABELS = {
    "job1": "장마감 LOC (job3와 동일)",
    "job2": "(미사용)",
    "job3": "장마감 LOC (매수·매도)",
    "job4": "오늘 마무리",
    "briefing": "아침 브리핑",
    "morning_briefing": "아침 브리핑",
}


class TelegramHandler:
    def __init__(self, app: App, executor: JobExecutor, sender: TelegramSender):
        self.app = app
        self.executor = executor
        self.sender = sender
        self.kst = ZoneInfo("Asia/Seoul")
        self.ny_tz = ZoneInfo("America/New_York")

    def _symbol(self, context: ContextTypes.DEFAULT_TYPE) -> str:
        return context.user_data.get("symbol") or self.app.runtime.default_symbol()

    def _setting_text(self, symbol: str) -> str:
        st = self.app.state.load(symbol)
        return (
            f"{section('설정', '⚙️')}\n"
            + quote(
                row("📦", "종목", symbol_card(symbol)),
                row("💰", "원금", usd(st["principal"], decimals=0)),
                row("🍰", "분할", code(str(st["split_count"]))),
                row("📈", "큰수매수", code(f"+{self.app.runtime.premium_default()}%")),
                row("⚡", "강제1회", badge_on(st.get("force_one", False))),
            )
        )

    def _setting_keyboard(self, symbol: str):
        st = self.app.state.load(symbol)
        return setting_keyboard(st.get("force_one", False))

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
        try:
            market = market_status_label(self.app.broker.get_us_market_status())
        except Exception:
            market = market_status_label("off_hours")
        paused = self.app.runtime.is_paused()
        dry = self.app.settings.dry_run or not self.app.settings.has_toss
        header = (
            f"🖥️ <b>라오어 무한매수 4.0</b>\n"
            f"{quote(f'{badge_bot(paused)}   ·   {badge_live(dry)}   ·   {market}')}\n"
        )
        await update.message.reply_text(header + help_block(), parse_mode="HTML")

    async def cmd_dashboard(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self._allowed(update):
            return await self._deny(update)
        if not self.app.settings.has_toss and not self.app.settings.dry_run:
            return await update.message.reply_text(
                "⚠️ Toss API 키가 없습니다. .env 의 TOSS_CLIENT_ID/SECRET 확인"
            )
        try:
            await update.message.reply_text(format_dashboard(self.app), parse_mode="HTML")
        except Exception as e:
            logger.exception("dashboard failed")
            await update.message.reply_text(f"🚨 조회 실패: {e}")

    async def cmd_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self._allowed(update):
            return await self._deny(update)
        try:
            await update.message.reply_text(
                format_status(self.app),
                parse_mode="HTML",
            )
        except Exception as e:
            logger.exception("status failed")
            await update.message.reply_text(f"🚨 조회 실패: {e}")

    async def cmd_balance(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self._allowed(update):
            return await self._deny(update)
        if not self.app.settings.has_toss:
            return await update.message.reply_text("⚠️ Toss API 키가 없습니다. .env 의 TOSS_CLIENT_ID/SECRET 확인")
        if self.app.settings.dry_run:
            return await update.message.reply_text(
                "⚠️ DRY_RUN=true — 실제 계좌 조회 안 함.\n"
                "잔고 확인: .env 에서 DRY_RUN=false 후\n"
                "sudo systemctl restart infinite-trading-bot"
            )
        try:
            await update.message.reply_text(format_balance(self.app), parse_mode="HTML")
        except Exception as e:
            logger.exception("Toss balance failed")
            await update.message.reply_text(f"🚨 Toss API 조회 실패: {e}")

    def _plan_symbols(self, context: ContextTypes.DEFAULT_TYPE, parts: list[str]) -> list[str]:
        if len(parts) > 1 and parts[1].upper() in SYMBOLS:
            return [parts[1].upper()]
        return list(self.app.runtime.active_symbols())

    def _render_plans(self, symbols: list[str], premium: int) -> str:
        return format_plans(self.app, symbols, premium)

    async def cmd_plan(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self._allowed(update):
            return await self._deny(update)
        parts = update.message.text.split()
        symbols = self._plan_symbols(context, parts)
        premium = self.app.runtime.premium_default()
        context.user_data["plan_symbols"] = symbols
        try:
            msg = self._render_plans(symbols, premium)
            await update.message.reply_text(
                msg,
                reply_markup=plan_action_keyboard(symbols),
                parse_mode="HTML",
            )
        except Exception as e:
            logger.exception("plan failed")
            await update.message.reply_text(f"🚨 조회 실패: {e}")

    async def cmd_setting(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self._allowed(update):
            return await self._deny(update)
        symbol = self._symbol(context)
        await update.message.reply_text(
            self._setting_text(symbol),
            reply_markup=self._setting_keyboard(symbol),
            parse_mode="HTML",
        )

    async def cmd_split(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self._allowed(update):
            return await self._deny(update)
        text = "📐 액면분할  │  종목 선택"
        markup = symbol_picker("SPLIT_PICK")
        target = update.callback_query.message if update.callback_query else update.message
        await target.reply_text(text, reply_markup=markup)

    async def cmd_cycles(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self._allowed(update):
            return await self._deny(update)
        parts = update.message.text.split()
        if len(parts) > 1:
            symbol = parts[1].upper()
            if symbol in SYMBOLS or symbol == "ALL":
                return await self._send_cycles(update.message, symbol)
        kb = symbol_picker("CYCLES")
        kb.inline_keyboard.append([InlineKeyboardButton("전체", callback_data="CYCLES:ALL")])
        await update.message.reply_text("📒 회차 기록 — 종목:", reply_markup=kb)

    async def cmd_monthly(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self._allowed(update):
            return await self._deny(update)
        parts = update.message.text.split()
        year = datetime.date.today().year
        symbol = None
        for part in parts[1:]:
            token = part.upper()
            if token in SYMBOLS:
                symbol = token
            elif token.isdigit() and len(token) == 4:
                year = int(token)
        msg = format_profit_summary(self.app, year, symbol)
        await update.message.reply_text(msg, parse_mode="HTML")

    async def cmd_run(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self._allowed(update):
            return await self._deny(update)
        await update.message.reply_text(
            f"▶️ <b>수동 실행</b>\n{DIVIDER}\n⏱️ 스케줄 Job을 직접 실행합니다.",
            reply_markup=run_job_keyboard(),
            parse_mode="HTML",
        )

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
        parts = update.message.text.split()
        symbol = parts[1].upper() if len(parts) > 1 else self._symbol(context)
        await update.message.reply_text(
            format_graduation_history(self.app, symbol),
            parse_mode="HTML",
        )

    async def cmd_set_t(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self._allowed(update):
            return await self._deny(update)
        try:
            parts = update.message.text.split()
            new_t = float(parts[1])
            symbol = parts[2].upper() if len(parts) > 2 else self._symbol(context)
            self.app.state.set_T(symbol, new_t)
            await update.message.reply_text(f"✅ [{symbol}] T → {new_t}")
        except (IndexError, ValueError):
            await update.message.reply_text("사용법: /set_t 5.25 TQQQ")

    async def cmd_pause(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self._allowed(update):
            return await self._deny(update)
        self.app.runtime.set_paused(True)
        await update.message.reply_text("⏸️  자동 실행을 멈췄습니다.")

    async def cmd_resume(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self._allowed(update):
            return await self._deny(update)
        self.app.runtime.set_paused(False)
        await update.message.reply_text("⏰  자동 실행을 재개했습니다.")

    async def _run_job(self, chat_id: int, context: ContextTypes.DEFAULT_TYPE, name: str):
        label = JOB_LABELS.get(name, name)
        await context.bot.send_message(chat_id, f"⏳ {label} 실행 중...")
        if name == "briefing":
            await self.executor.run_morning_briefing()
        else:
            await getattr(self.executor, f"run_{name}")()

    async def handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self._allowed(update):
            return await self._deny(update)
        query = update.callback_query
        await query.answer()
        data = query.data

        if data.startswith("EXEC:"):
            symbol = data.split(":")[1]
            premium = self.app.runtime.premium_default()
            await self._execute_manual(query.message.chat_id, symbol, premium, context)
            await query.edit_message_reply_markup(reply_markup=None)
            return

        if data == "set_premium":
            await query.edit_message_text(
                "📈 큰수매수 할증 (현재가 대비):",
                reply_markup=premium_keyboard(),
            )
            return

        if data.startswith("PREMIUM:"):
            pct = int(data.split(":")[1])
            self.app.runtime.set_premium_default(pct)
            sym = self._symbol(context)
            await query.edit_message_text(
                self._setting_text(sym),
                reply_markup=self._setting_keyboard(sym),
                parse_mode="HTML",
            )
            return

        if data == "toggle_force_one":
            sym = self._symbol(context)
            st = self.app.state.load(sym)
            self.app.state.set_force_one(sym, not st.get("force_one", False))
            await query.edit_message_text(
                self._setting_text(sym),
                reply_markup=self._setting_keyboard(sym),
                parse_mode="HTML",
            )
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

        if data == "set_seed":
            context.user_data["awaiting"] = data
            context.user_data["awaiting_symbol"] = self._symbol(context)
            await query.edit_message_text("💰 원금(무한매수 기준금)을 달러로 입력하세요.")
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
                f"✅ [{ticker}] 반영\n{st['qty']}주 @ ${st['avg_price']:.4f}\nT·원금 유지"
            )
            return

        if data == "SPLIT_CANCEL":
            await query.edit_message_text("취소됨")
            return

        if data.startswith("RUN:"):
            job = data.split(":")[1]
            await query.edit_message_reply_markup(reply_markup=None)
            await self._run_job(query.message.chat_id, context, job)
            return

        if data.startswith("CYCLES:"):
            symbol = data.split(":")[1]
            await self._send_cycles(query.message, symbol)
            return

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
            premium, st["principal"], st["split_count"], st.get("force_one", False),
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
            return await self.cmd_set_t(update, context)

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
                context.user_data["awaiting"] = None
                return await update.message.reply_text(f"✅ [{symbol}] 원금 ${val:,.0f}")
            if awaiting == "set_split":
                self.app.state.set_split_count(symbol, int(val))
            context.user_data["awaiting"] = None
            await update.message.reply_text("✅ 저장됨")
        except ValueError:
            await update.message.reply_text("숫자만 입력하세요.")
