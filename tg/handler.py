"""Telegram command handlers — uses App + JobExecutor, no direct broker orders except manual exec."""

from __future__ import annotations

import asyncio
import datetime
import logging
from zoneinfo import ZoneInfo

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from app import App
from broker.toss_client import TossClient
from jobs.executor import JobExecutor
from strategy.fill_reconciler import FillReconciler
from strategy.split_handler import apply_split, calc_adjustment, format_preview, parse_ratio
from config.settings import SYMBOLS
from tg.home_formatter import format_home
from tg.balance_formatter import format_balance
from tg.plan_formatter import format_plans
from tg.records_formatter import format_graduation_history, format_profit_summary
from tg.dashboard_formatter import format_dashboard
from tg.status_formatter import format_status
from tg.token_formatter import format_toss_token_brief, format_toss_token_detail
from tg.keyboards import (
    plan_action_keyboard,
    premium_keyboard,
    run_job_keyboard,
    setting_keyboard,
    split_confirm_keyboard,
    split_count_keyboard,
    split_ratio_keyboard,
    symbol_picker,
    take_profit_keyboard,
    token_keyboard,
    trading_symbols_keyboard,
    main_menu_keyboard,
    MAIN_HOME,
    MAIN_PLAN,
    MAIN_SETTING,
    MAIN_STATUS,
    MAIN_BALANCE,
    MAIN_CYCLES,
)
from tg.sender import TelegramSender
from tg.ui import DIVIDER, badge_on, code, quote, row, section, usd

logger = logging.getLogger(__name__)

JOB_LABELS = {
    "job1": "본장 LOC (job3와 동일)",
    "job2": "(미사용)",
    "job3": "본장 LOC (매수·매도 CLS 접수)",
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

    def _effective_take_profit(self, symbol: str, st: dict) -> float:
        return self.app.strategy.resolve_take_profit(symbol, st.get("take_profit_pct"))

    def _setting_text(self, symbol: str) -> str:
        st = self.app.state.load(symbol)
        active = self.app.runtime.active_symbols()
        active_str = ", ".join(active) if active else "없음"
        tp = self._effective_take_profit(symbol, st)
        edit_hint = f" · {symbol} 편집" if symbol in active else ""
        return (
            f"{section('설정', '⚙️')}\n"
            + quote(
                row("📡", "거래 종목", code(active_str + edit_hint)),
                row("💰", "원금", usd(st["principal"], decimals=0)),
                row("🍰", "분할", code(str(st["split_count"]))),
                row("📈", "큰수매수", code(f"T=0 +{self.app.runtime.premium_default()}%")),
                row("🎯", "목표수익률", code(f"+{tp:g}%")),
                row("⚡", "강제1회", badge_on(st.get("force_one", False))),
            )
        )

    def _symbols_picker_text(self, editing: str) -> str:
        return (
            "📡 <b>거래 종목</b>\n"
            "탭하여 켜기(🟢)/끄기(⚪) · ✏️ 표시 종목의 원금·분할을 편집해요.\n"
            "켜진 종목만 주문계획·자동매매에 반영돼요."
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

    async def _fetch_token_status(self, refresh: bool = False) -> dict:
        auth = self.app.broker.auth
        if refresh:
            return await asyncio.to_thread(auth.force_refresh)
        return await asyncio.to_thread(auth.get_status)

    async def cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self._allowed(update):
            return await self._deny(update)
        try:
            dry = self.app.settings.dry_run or not self.app.settings.has_toss
            token_line = format_toss_token_brief(self.app)
            if not dry and self.app.settings.has_toss:
                try:
                    status = await self._fetch_token_status(refresh=False)
                    token_line = format_toss_token_brief(self.app, status)
                except Exception:
                    logger.exception("token brief check failed")
                    token_line = "🔑 토스 토큰  🔴 사용 불가"
            await update.message.reply_text(
                format_home(self.app, token_line),
                reply_markup=main_menu_keyboard(),
                parse_mode="HTML",
            )
        except Exception as e:
            logger.exception("cmd_start failed")
            await update.message.reply_text(f"🚨 /start 실패: {e}")

    async def cmd_token(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self._allowed(update):
            return await self._deny(update)
        dry = self.app.settings.dry_run or not self.app.settings.has_toss
        try:
            status = None if dry or not self.app.settings.has_toss else await self._fetch_token_status()
            text = format_toss_token_detail(self.app, status)
            markup = token_keyboard() if not dry and self.app.settings.has_toss else None
            await update.message.reply_text(text, reply_markup=markup, parse_mode="HTML")
        except Exception as e:
            logger.exception("cmd_token failed")
            await update.message.reply_text(f"🚨 토큰 조회 실패: {e}")

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
        active = self.app.runtime.active_symbols()
        if active:
            return list(active)
        return [self._symbol(context)]

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
            markup = plan_action_keyboard(symbols) if symbols else None
            await update.message.reply_text(
                msg,
                reply_markup=markup,
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

    async def cmd_cycles_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """하단 메뉴 — 동기화 후 거래 중인 종목의 현재 회차·매매 내역."""
        if not self._allowed(update):
            return await self._deny(update)
        active = self.app.runtime.active_symbols()
        if not active:
            return await update.message.reply_text(
                "⚠️ 거래 종목이 없어요. ⚙️ 설정 → 📡 거래 종목에서 켜주세요.",
            )
        if len(active) == 1:
            return await self._sync_then_send_cycles(update.message, active[0])
        symbols_csv = ",".join(active)
        return await self._sync_then_send_cycles(update.message, symbols_csv)

    async def cmd_cycles(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self._allowed(update):
            return await self._deny(update)
        parts = update.message.text.split()
        if len(parts) > 1:
            symbol = parts[1].upper()
            if symbol in SYMBOLS or symbol == "ALL":
                return await self._sync_then_send_cycles(update.message, symbol)
        rows = [
            [InlineKeyboardButton(s, callback_data=f"CYCLES:{s}") for s in SYMBOLS],
            [InlineKeyboardButton("전체", callback_data="CYCLES:ALL")],
        ]
        kb = InlineKeyboardMarkup(rows)
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

    async def cmd_sync(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self._allowed(update):
            return await self._deny(update)
        if not self.app.settings.has_toss or self.app.settings.dry_run:
            return await update.message.reply_text(
                "⚠️ LIVE 모드에서만 실계좌 동기화가 됩니다. (.env: DRY_RUN=false + Toss 키)"
            )
        await update.message.reply_text("🔄 토스 체결·실계좌에서 T·회차 동기화 중...")
        await self.executor.run_cycle_sync(notify=True)

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
        elif name == "job3":
            await self.executor.run_job3(scheduled=False)
        else:
            await getattr(self.executor, f"run_{name}")()

    async def handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self._allowed(update):
            return await self._deny(update)
        query = update.callback_query
        data = query.data

        if data.startswith("TRADE:") or data.startswith("TOGGLE_ACTIVE:"):
            sym = data.split(":")[1]
            active, editing, alert = self.app.runtime.select_trading_symbol(sym)
            await query.answer(alert or "✓", show_alert=bool(alert))
            context.user_data["symbol"] = editing
            await query.edit_message_text(
                self._symbols_picker_text(editing),
                reply_markup=trading_symbols_keyboard(active, editing),
                parse_mode="HTML",
            )
            return

        await query.answer()

        if data.startswith("EXEC:"):
            symbol = data.split(":")[1]
            premium = self.app.runtime.premium_default()
            await self._execute_manual(query.message.chat_id, symbol, premium, context)
            await query.edit_message_reply_markup(reply_markup=None)
            return

        if data == "set_premium":
            await query.edit_message_text(
                "📈 큰수매수 할증 (T=0 첫 매수만, 현재가 대비):",
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

        if data == "set_takeprofit":
            await query.edit_message_text(
                "🎯 목표 수익률 (평단가 대비 익절 LOC 기준):",
                reply_markup=take_profit_keyboard(),
            )
            return

        if data.startswith("TAKEPROFIT:"):
            pct = int(data.split(":")[1])
            sym = self._symbol(context)
            self.app.state.set_take_profit(sym, pct)
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

        if data == "set_symbols":
            active = self.app.runtime.active_symbols()
            editing = self._symbol(context)
            await query.edit_message_text(
                self._symbols_picker_text(editing),
                reply_markup=trading_symbols_keyboard(active, editing),
                parse_mode="HTML",
            )
            return

        if data == "back_setting":
            sym = self._symbol(context)
            await query.edit_message_text(
                self._setting_text(sym),
                reply_markup=self._setting_keyboard(sym),
                parse_mode="HTML",
            )
            return

        if data == "set_token":
            dry = self.app.settings.dry_run or not self.app.settings.has_toss
            try:
                status = None if dry or not self.app.settings.has_toss else await self._fetch_token_status()
                text = format_toss_token_detail(self.app, status)
                markup = token_keyboard(from_settings=True) if not dry and self.app.settings.has_toss else InlineKeyboardMarkup([
                    [InlineKeyboardButton("⬅️ 설정으로", callback_data="back_setting")],
                ])
                await query.edit_message_text(text, reply_markup=markup, parse_mode="HTML")
            except Exception as e:
                logger.exception("set_token failed")
                await query.edit_message_text(f"🚨 토큰 조회 실패: {e}")
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

        if data == "TOKEN:refresh":
            if self.app.settings.dry_run or not self.app.settings.has_toss:
                await query.edit_message_text("⚠️ LIVE 모드에서만 토큰 갱신이 됩니다.")
                return
            await query.edit_message_text("⏳ 토큰 갱신 중…")
            try:
                status = await self._fetch_token_status(refresh=True)
                text = format_toss_token_detail(self.app, status)
                await query.edit_message_text(
                    text,
                    reply_markup=token_keyboard(from_settings=True),
                    parse_mode="HTML",
                )
            except Exception as e:
                logger.exception("token refresh failed")
                await query.edit_message_text(f"🚨 토큰 갱신 실패: {e}")
            return

        if data.startswith("CYCLES:"):
            symbol = data.split(":")[1]
            await self._sync_then_send_cycles(query.message, symbol)
            return

    async def _sync_then_send_cycles(self, target, symbol: str):
        """실계좌 동기화(/sync) 후 회차 내역 표시."""
        is_live = not (self.app.settings.dry_run or not self.app.settings.has_toss)
        sync_symbols = self._cycle_symbol_list(symbol)
        if is_live:
            await target.reply_text("🔄 토스 체결·실계좌에서 T·회차 동기화 중...")
            try:
                await self.executor.run_cycle_sync(notify=False, symbols=sync_symbols)
            except Exception:
                logger.exception("cycle sync before report failed")
        await self._send_cycles(target, symbol, already_synced=is_live)

    @staticmethod
    def _cycle_symbol_list(symbol: str) -> list[str]:
        if symbol == "ALL":
            return list(SYMBOLS)
        if "," in symbol:
            return [
                s.strip().upper() for s in symbol.split(",")
                if s.strip().upper() in SYMBOLS
            ]
        return [symbol.upper()]

    async def _send_cycles(self, target, symbol: str, *, already_synced: bool = False):
        try:
            symbols = self._cycle_symbol_list(symbol)
            is_live = not (self.app.settings.dry_run or not self.app.settings.has_toss)
            premium = self.app.runtime.premium_default()
            parts = []
            for sym in symbols:
                st = self.app.state.load(sym)
                if is_live and already_synced:
                    try:
                        pos = self.app.broker.get_holdings_item(sym)
                        price = float(pos.get("current_price") or st.get("avg_price") or 0)
                    except Exception:
                        logger.exception("holdings fetch failed %s", sym)
                        price = float(st.get("avg_price") or 0)
                    parts.append(self.app.cycles.format_cycles_report(
                        sym, st["qty"], st["avg_price"], price,
                        fill_log=st.get("fill_log", []),
                    ))
                    continue
                if is_live and not already_synced:
                    try:
                        await asyncio.to_thread(
                            self.executor.sync_cycle_from_broker, sym, premium,
                        )
                    except Exception:
                        logger.exception("cycle refresh failed %s", sym)
                st = self.app.state.load(sym)
                broker_fills = None
                if is_live:
                    pos = self.app.broker.get_holdings_item(sym)
                    price = float(pos.get("current_price") or st.get("avg_price") or 0)
                    qty = int(st.get("qty", 0) or pos.get("qty", 0) or 0)
                    order_ids = FillReconciler.collect_known_order_ids(
                        self.app, sym, st=st,
                    )
                    broker_fills = self.app.broker.list_broker_fills(
                        sym, days=90, max_orders=200, extra_order_ids=order_ids,
                    )
                    if broker_fills and qty > 0:
                        self.app.cycles.rebuild_trades_from_broker(
                            sym, broker_fills, st.get("fill_log", []), qty,
                        )
                else:
                    try:
                        price = self._pos(sym)["current_price"]
                    except Exception:
                        logger.exception("holdings fetch failed %s", sym)
                        price = float(st.get("avg_price") or 0)
                if not is_live:
                    self.app.cycles.ensure_current(sym, st["principal"])
                    self.app.cycles.sync_trades_from_fill_log(
                        sym, st.get("fill_log", []), float(st.get("principal", 0.0)),
                    )
                    self.app.cycles.dedupe_symbol_trades(sym)
                    st = self.app.state.load(sym)
                parts.append(self.app.cycles.format_cycles_report(
                    sym, st["qty"], st["avg_price"], price,
                    fill_log=st.get("fill_log", []),
                    broker_fills=broker_fills,
                ))
            await target.reply_text("\n\n".join(parts), parse_mode="HTML")
        except Exception as e:
            logger.exception("cycles report failed")
            await target.reply_text(f"🚨 회차 조회 실패: {e}")

    async def _execute_manual(self, chat_id: int, symbol: str, premium: int, context: ContextTypes.DEFAULT_TYPE):
        st = self.app.state.load(symbol)
        pos = self._pos(symbol)
        plan = self.app.strategy.get_plan(
            symbol, pos["current_price"], st["avg_price"], st["qty"], st["T"],
            premium, st["principal"], st["split_count"], st.get("force_one", False),
            take_profit_pct=st.get("take_profit_pct"),
        )
        orders = plan.get("buy_orders", []) + plan.get("sell_orders", [])
        if not orders:
            await context.bot.send_message(chat_id, f"[{symbol}] 주문 없음")
            return
        is_live = self.app.settings.has_toss and not self.app.settings.dry_run
        if is_live and not self.app.broker.is_us_loc_session_now():
            await context.bot.send_message(
                chat_id,
                "⏭️ 지금은 미국 프리마켓·정규장 시간이 아니에요. "
                "LOC(CLS)는 프리장(18:05 KST) 또는 장중에 접수할 수 있어요.",
            )
            return
        target = TossClient.target_us_date_for_evening_loc()
        if await self.executor._already_traded_for_us_session(symbol, target, st=st):
            await context.bot.send_message(
                chat_id,
                f"⏭️ [{symbol}] {target} — 본장 시작 전 LOC 이미 접수됨. 스킵합니다.",
            )
            return
        ref = float(pos["current_price"] or 0)
        plan["holdings_qty"] = int(st.get("qty") or 0)
        from strategy.order_planner import prepare_loc_submit_orders
        filtered = {
            "buy_orders": plan.get("buy_orders", []),
            "sell_orders": plan.get("sell_orders", []),
        }
        if is_live:
            await asyncio.to_thread(
                self.app.broker.cancel_open_cls_orders, symbol,
            )
            orders = prepare_loc_submit_orders(filtered, plan)
            wait_fill = False
        else:
            from strategy.order_planner import prepare_loc_orders
            orders = prepare_loc_orders(filtered, ref)
            wait_fill = True
        if not orders:
            await context.bot.send_message(chat_id, f"[{symbol}] 접수할 LOC 주문 없음")
            return
        try:
            result = await self.executor.execute_orders(
                symbol, orders, ref, use_loc=True,
                notify_per_order=True, wait_fill=wait_fill,
            )
        except Exception as e:
            logger.exception("Manual order failed")
            await context.bot.send_message(chat_id, f"🚨 주문 실패: {e}")
            return
        if not result.get("grad_msg"):
            await context.bot.send_message(chat_id, result["line"])

    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self._allowed(update):
            return await self._deny(update)
        text = update.message.text.strip()

        menu_routes = {
            MAIN_HOME: self.cmd_start,
            MAIN_PLAN: self.cmd_plan,
            MAIN_SETTING: self.cmd_setting,
            MAIN_STATUS: self.cmd_status,
            "📈 현황": self.cmd_status,  # 구 하단 메뉴 (키보드 갱신 전)
            MAIN_BALANCE: self.cmd_balance,
            MAIN_CYCLES: self.cmd_cycles_menu,
        }
        if text in menu_routes:
            context.user_data.pop("awaiting", None)
            context.user_data.pop("awaiting_symbol", None)
            return await menu_routes[text](update, context)

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
