"""Telegram command handlers — uses App + JobExecutor, no direct broker orders except manual exec."""

from __future__ import annotations

import asyncio
import datetime
import html
import logging
from zoneinfo import ZoneInfo

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from app import App
from broker.toss_client import TossClient
from jobs.executor import JobExecutor
from strategy.split_handler import apply_split, calc_adjustment, format_preview, parse_ratio
from config.settings import SYMBOLS, google_sheets_issues
from tg.build_info import git_rev
from tg.envcheck_formatter import format_env_check
from tg.home_formatter import format_home_status
from tg.balance_formatter import format_balance
from tg.plan_formatter import format_plans
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
    ledger_keyboard,
    MAIN_HOME,
    MAIN_HOME_LEGACY,
    MAIN_PLAN,
    MAIN_SETTING,
    MAIN_STATUS,
    MAIN_BALANCE,
    MAIN_LEDGER,
    MAIN_CYCLES,
)
from tg.sender import TelegramSender
from tg.format_helpers import dry_mode_reason, is_dry, sync_broker_dry_run
from tg.ui import DIVIDER, badge_live, badge_on, code, dim, quote, row, section, usd

logger = logging.getLogger(__name__)

JOB_LABELS = {
    "job1": "프리장 LOC (job3와 동일)",
    "job2": "(미사용)",
    "job3": "프리장 LOC (매수·매도 CLS 접수)",
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

    def _main_menu_markup(self):
        return main_menu_keyboard()

    async def _refresh_main_menu(self, update: Update) -> None:
        """텔레그램은 새 ReplyKeyboard를 받을 때까지 예전 하단 버튼을 유지한다."""
        if not update.message:
            return
        try:
            msg = await update.message.reply_text(
                "\u200b",
                reply_markup=self._main_menu_markup(),
                disable_notification=True,
            )
            await msg.delete()
        except Exception:
            logger.debug("main menu keyboard refresh failed", exc_info=True)

    def _reverse_status_line(self, st: dict) -> str:
        st = dict(st)
        self.app.strategy.sync_reverse_flags(st)
        split = int(st.get("split_count", 40))
        if st.get("reverse_exited"):
            return "⚪ 종료 (회복 대기)"
        if st.get("reverse_mode"):
            return "🟢 ON · T 자동"
        return f"⚪ OFF · T>{split - 1} 시 자동"

    def _setting_text(self, symbol: str) -> str:
        st = self.app.state.load(symbol)
        active = self.app.runtime.active_symbols()
        active_str = ", ".join(active) if active else "없음"
        tp = self._effective_take_profit(symbol, st)
        edit_hint = f" · {symbol} 편집" if symbol in active else ""
        dry = is_dry(self.app)
        dry_hint = dry_mode_reason(self.app)
        trade_mode = badge_live(dry)
        if dry_hint:
            trade_mode += f" ({dry_hint})"
        return (
            f"{section('설정', '⚙️')}\n"
            + quote(
                row("💹", "거래 모드", code(trade_mode)),
                row("📡", "거래 종목", code(active_str + edit_hint)),
                row("💰", "원금", usd(st["principal"], decimals=0)),
                row("🍰", "분할", code(str(st["split_count"]))),
                row("📈", "큰수매수", code(f"T=0 +{self.app.runtime.premium_default()}%")),
                row("🎯", "목표수익률", code(f"+{tp:g}%")),
                row("🔄", "리버스", code(self._reverse_status_line(st))),
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
        return setting_keyboard(
            st.get("force_one", False),
            dry=is_dry(self.app),
        )

    def _allowed(self, update: Update) -> bool:
        ids = self.app.settings.telegram_allowed_chat_ids
        chat = update.effective_chat
        if chat:
            self.app.runtime.remember_notify_chat(chat.id)
        if not ids:
            return True
        return chat and chat.id in ids

    async def _deny(self, update: Update) -> None:
        if update.message:
            await update.message.reply_text("⛔ 허용되지 않은 채팅입니다.")
        elif update.callback_query:
            await update.callback_query.answer("⛔ 허용되지 않은 채팅", show_alert=True)

    def _pos(self, symbol: str) -> dict:
        return self.app.broker.get_holdings_item(symbol)

    async def _show_token_detail(self, query, status: dict | None, *, from_settings: bool = False) -> None:
        text = format_toss_token_detail(self.app, status)
        if self.app.settings.has_toss:
            markup = token_keyboard(from_settings=from_settings)
        elif from_settings:
            markup = InlineKeyboardMarkup([
                [InlineKeyboardButton("⬅️ 설정으로", callback_data="back_setting")],
            ])
        else:
            markup = None
        try:
            await query.edit_message_text(text, reply_markup=markup, parse_mode="HTML")
        except Exception:
            logger.exception("token detail HTML edit failed")
            plain = html.unescape(text.replace("<blockquote>", "").replace("</blockquote>", ""))
            for tag in ("<b>", "</b>", "<i>", "</i>", "<code>", "</code>"):
                plain = plain.replace(tag, "")
            await query.edit_message_text(plain[:4000], reply_markup=markup)

    async def _fetch_token_status(self) -> dict:
        """캐시 확인 → 없거나 만료면 1회 발급 (유효하면 재발급 안 함)."""
        self._refresh_env()
        auth = self.app.broker.auth
        auth.sync_credentials(
            self.app.settings.toss_client_id,
            self.app.settings.toss_client_secret,
        )
        return await asyncio.to_thread(auth.ensure_token_status)

    async def _resolve_token_line(self) -> str:
        token_line = format_toss_token_brief(self.app)
        if self.app.settings.has_toss:
            try:
                status = await self._fetch_token_status()
                token_line = format_toss_token_brief(self.app, status)
            except Exception:
                logger.exception("token brief check failed")
                token_line = "🔑 토스 토큰  🔴 사용 불가"
        return token_line

    async def cmd_home(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self._allowed(update):
            return await self._deny(update)
        try:
            token_line = await self._resolve_token_line()
            await update.message.reply_text(
                format_home_status(self.app, token_line),
                reply_markup=self._main_menu_markup(),
                parse_mode="HTML",
            )
        except Exception as e:
            logger.exception("home failed")
            await update.message.reply_text(f"🚨 조회 실패: {e}")

    async def cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        return await self.cmd_home(update, context)

    async def cmd_token(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self._allowed(update):
            return await self._deny(update)
        try:
            status = None if not self.app.settings.has_toss else await self._fetch_token_status()
            text = format_toss_token_detail(self.app, status)
            markup = token_keyboard() if self.app.settings.has_toss else None
            await update.message.reply_text(text, reply_markup=markup, parse_mode="HTML")
        except Exception as e:
            logger.exception("cmd_token failed")
            await update.message.reply_text(f"🚨 토큰 조회 실패: {e}")

    async def _sync_ledger(self, *, rebuild_broker: bool = True) -> dict | None:
        if not self.app.settings.has_google_sheets:
            return None
        try:
            from integrations.google_sheets import sync_ledger
            return await asyncio.wait_for(
                asyncio.to_thread(sync_ledger, self.app, rebuild_broker=rebuild_broker),
                timeout=120.0,
            )
        except asyncio.TimeoutError:
            logger.exception("google sheets sync timeout")
            return {"ok": False, "message": "Sheets 동기화 시간 초과 (120초)"}
        except Exception as exc:
            logger.exception("google sheets sync failed")
            return {"ok": False, "message": f"Sheets 동기화 실패: {exc}"}

    @staticmethod
    def _format_sheets_result(result: dict | None, *, brief: bool = False) -> str:
        if not result:
            return "🚨 Google Sheets 동기화 실패"
        if result.get("ok"):
            if brief:
                rev = git_rev()
                return f"✅ Google Sheets 동기화 완료 ({rev})"
            msg = result.get("message") or "Sheets 동기화 완료"
            return f"✅ {msg}"
        msg = result.get("message") or "Sheets 동기화 실패"
        if brief:
            return f"🚨 {msg}"
        lines = [f"🚨 {msg}"]
        prep = result.get("prep") or {}
        if prep.get("errors"):
            lines.append(f"⚠️ {prep['errors'][0]}")
        return "\n".join(lines)

    def _refresh_env(self) -> None:
        """장부 명령 시 .env 재로드 — VM에 .env 동기화 후 재시작 없이 반영."""
        self.app.reload_settings()

    _LEDGER_SYNCING = "🔄 Google Sheets 동기화 중…"

    async def _complete_ledger_sync_ui(self, msg, markup) -> None:
        try:
            result = await self._sync_ledger(rebuild_broker=True)
            status = self._format_sheets_result(result, brief=True)
        except Exception as exc:
            logger.exception("ledger sync failed")
            status = f"🚨 Google Sheets 동기화 실패: {exc}"
        try:
            await msg.edit_text(status, reply_markup=markup)
        except Exception:
            logger.debug("ledger status edit failed, send new message", exc_info=True)
            await msg.reply_text(status, reply_markup=markup)

    async def _reply_ledger(self, target, *, sync: bool = True) -> None:
        self._refresh_env()
        markup = ledger_keyboard(self.app.settings)
        if not markup:
            issues = google_sheets_issues(self.app.settings)
            detail = " · ".join(issues) if issues else "Google Sheets 미설정"
            await target.reply_text(f"🚨 {detail}")
            return
        if sync and self.app.settings.has_google_sheets:
            progress = await target.reply_text(self._LEDGER_SYNCING)
            await self._complete_ledger_sync_ui(progress, markup)
            return
        await target.reply_text("📊", reply_markup=markup)

    async def cmd_myid(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """채팅 ID 확인 — .env TELEGRAM_ALLOWED_CHAT_IDS 설정용 (허용 검사 없음)."""
        chat = update.effective_chat
        user = update.effective_user
        if not chat or not update.message:
            return
        lines = [f"chat_id: {chat.id}"]
        if user:
            lines.append(f"user_id: {user.id}")
        allowed = self.app.settings.telegram_allowed_chat_ids
        if allowed:
            ok = "✅ 허용됨" if chat.id in allowed else "❌ .env에 이 chat_id 추가 필요"
            lines.append(f"허용 목록: {', '.join(str(x) for x in allowed)}")
            lines.append(ok)
        else:
            lines.append("허용 목록: (비어 있음 — 모든 채팅 허용)")
        await update.message.reply_text("\n".join(lines))

    async def cmd_version(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self._allowed(update):
            return await self._deny(update)
        from tg.build_info import ledger_ui_label
        await update.message.reply_text(
            f"봇 빌드: {git_rev()}\n장부 UI: {ledger_ui_label()}\n명령: /envcheck 환경설정 확인",
        )

    async def cmd_ledger(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """장부 — Google Sheets 바로가기."""
        if not self._allowed(update):
            return await self._deny(update)
        try:
            await self._refresh_main_menu(update)
            await self._reply_ledger(update.message)
        except Exception as e:
            logger.exception("ledger menu failed")
            await update.message.reply_text(f"🚨 장부 안내 실패: {e}")

    async def cmd_dashboard(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        return await self.cmd_ledger(update, context)

    async def cmd_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        return await self.cmd_home(update, context)

    async def cmd_balance(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self._allowed(update):
            return await self._deny(update)
        if not self.app.settings.has_toss:
            return await update.message.reply_text("⚠️ Toss API 키가 없습니다. .env 의 TOSS_CLIENT_ID/SECRET 확인")
        if is_dry(self.app):
            return await update.message.reply_text(
                "⚠️ DRY 모드 — 실제 계좌 조회 안 함.\n"
                "⚙️ 설정 → 💹 실거래 켜기 로 LIVE 전환하거나\n"
                ".env DRY_RUN=false 후 봇 재시작",
                reply_markup=self._main_menu_markup(),
            )
        try:
            await update.message.reply_text(
                format_balance(self.app),
                reply_markup=self._main_menu_markup(),
                parse_mode="HTML",
            )
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

    def _build_plan_reply(self, symbols: list[str], premium: int):
        msg = self._render_plans(symbols, premium)
        markup = plan_action_keyboard(symbols) if symbols else None
        return msg, markup

    async def cmd_plan(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self._allowed(update):
            return await self._deny(update)
        parts = update.message.text.split()
        symbols = self._plan_symbols(context, parts)
        premium = self.app.runtime.premium_default()
        context.user_data["plan_symbols"] = symbols
        status = await update.message.reply_text(
            "📋 주문계획 조회 중...",
            reply_markup=self._main_menu_markup(),
        )
        try:
            msg, markup = await asyncio.wait_for(
                asyncio.to_thread(self._build_plan_reply, symbols, premium),
                timeout=45.0,
            )
            await status.edit_text(msg, reply_markup=markup, parse_mode="HTML")
        except asyncio.TimeoutError:
            logger.warning("plan query timeout symbols=%s", symbols)
            await status.edit_text(
                "🚨 주문계획 조회 시간 초과\n"
                "Toss API 응답 지연 — 잠시 후 다시 시도하거나 /status 로 확인하세요.",
            )
        except Exception as e:
            logger.exception("plan failed")
            await status.edit_text(f"🚨 조회 실패: {e}")

    async def cmd_setting(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self._allowed(update):
            return await self._deny(update)
        context.user_data.pop("awaiting", None)
        context.user_data.pop("awaiting_symbol", None)
        try:
            symbol = self._symbol(context)
            await update.message.reply_text(
                self._setting_text(symbol),
                reply_markup=self._setting_keyboard(symbol),
                parse_mode="HTML",
            )
        except Exception as e:
            logger.exception("cmd_setting failed")
            await update.message.reply_text(f"🚨 설정 화면 실패: {e}")

    async def cmd_cancel(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self._allowed(update):
            return await self._deny(update)
        context.user_data.pop("awaiting", None)
        context.user_data.pop("awaiting_symbol", None)
        await update.message.reply_text(
            "✅ 입력 취소됨 — ⚙️ 설정 또는 /setting",
            reply_markup=self._main_menu_markup(),
        )

    async def cmd_split(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self._allowed(update):
            return await self._deny(update)
        text = "📐 액면분할  │  종목 선택"
        markup = symbol_picker("SPLIT_PICK")
        target = update.callback_query.message if update.callback_query else update.message
        await target.reply_text(text, reply_markup=markup)

    async def cmd_cycles(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        return await self.cmd_ledger(update, context)

    async def cmd_monthly(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        return await self.cmd_ledger(update, context)

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
        return await self.cmd_ledger(update, context)

    async def cmd_sheets_sync(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self._allowed(update):
            return await self._deny(update)
        self._refresh_env()
        if not self.app.settings.has_google_sheets:
            issues = google_sheets_issues(self.app.settings)
            detail = "\n".join(f"· {x}" for x in issues) if issues else ""
            msg = "🚨 Google Sheets 미설정"
            if detail:
                msg += "\n" + detail
            return await update.message.reply_text(msg)
        markup = ledger_keyboard(self.app.settings)
        progress = await update.message.reply_text(self._LEDGER_SYNCING)
        await self._complete_ledger_sync_ui(progress, markup)

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
        self._refresh_env()
        if is_dry(self.app):
            return await update.message.reply_text(
                "⚠️ LIVE 모드에서만 실계좌 동기화가 됩니다.\n"
                "⚙️ 설정 → 💹 실거래 켜기"
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

    async def cmd_briefing(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self._allowed(update):
            return await self._deny(update)
        chat_id = update.effective_chat.id
        await update.message.reply_text("⏳ 아침 브리핑 생성 중...")
        await self.executor.run_morning_briefing(scheduled=False, chat_id=chat_id)

    async def cmd_envcheck(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self._allowed(update):
            return await self._deny(update)
        try:
            self._refresh_env()
            await update.message.reply_text(
                format_env_check(self.app.settings), parse_mode="HTML",
            )
        except Exception as e:
            logger.exception("envcheck failed")
            await update.message.reply_text(f"🚨 환경 확인 실패: {e}")

    async def _run_job(self, chat_id: int, context: ContextTypes.DEFAULT_TYPE, name: str):
        label = JOB_LABELS.get(name, name)
        await context.bot.send_message(chat_id, f"⏳ {label} 실행 중...")
        if name == "briefing":
            await self.executor.run_morning_briefing(scheduled=False, chat_id=chat_id)
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

        if data == "ENV:check":
            sym = self._symbol(context)
            try:
                self._refresh_env()
                text = format_env_check(self.app.settings)
            except Exception as e:
                logger.exception("envcheck callback failed")
                text = f"🚨 환경 확인 실패: {html.escape(str(e))}"
            try:
                await query.edit_message_text(
                    text,
                    reply_markup=self._setting_keyboard(sym),
                    parse_mode="HTML",
                )
            except Exception:
                logger.exception("envcheck edit failed — send new message")
                await query.message.reply_text(
                    text,
                    reply_markup=self._setting_keyboard(sym),
                    parse_mode="HTML",
                )
            return

        if data == "toggle_force_live":
            if not self.app.settings.has_toss:
                await query.answer(
                    "토스 API 키(TOSS_CLIENT_ID/SECRET)가 없어 실거래를 켤 수 없어요.",
                    show_alert=True,
                )
                return
            self._refresh_env()
            enable = is_dry(self.app)
            self.app.runtime.set_force_live(enable)
            sync_broker_dry_run(self.app)
            sym = self._symbol(context)
            await query.edit_message_text(
                self._setting_text(sym),
                reply_markup=self._setting_keyboard(sym),
                parse_mode="HTML",
            )
            mode = "실거래(LIVE)" if enable else "DRY(시뮬)"
            await query.answer(f"거래 모드 → {mode}")
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
            try:
                status = None if not self.app.settings.has_toss else await self._fetch_token_status()
                await self._show_token_detail(query, status, from_settings=True)
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
            self._refresh_env()
            if not self.app.settings.has_toss:
                await query.edit_message_text("⚠️ TOSS_CLIENT_ID / TOSS_CLIENT_SECRET 이 .env 에 없습니다.")
                return
            await query.edit_message_text("⏳ 토큰 확인 중…")
            try:
                status = await self._fetch_token_status()
                await self._show_token_detail(query, status, from_settings=True)
            except Exception as e:
                logger.exception("token check failed")
                await query.edit_message_text(f"🚨 토큰 확인 실패: {e}")
            return

        if data == "LEDGER:sync":
            if not self.app.settings.has_google_sheets:
                await query.answer("Google Sheets 미설정", show_alert=True)
                return
            await query.answer()
            markup = ledger_keyboard(self.app.settings)
            await query.edit_message_text(self._LEDGER_SYNCING, reply_markup=None)
            await self._complete_ledger_sync_ui(query.message, markup)
            return

        if data.startswith("CYCLES:"):
            await self._reply_ledger(query.message)
            return

    async def _execute_manual(self, chat_id: int, symbol: str, premium: int, context: ContextTypes.DEFAULT_TYPE):
        st = self.app.state.load(symbol)
        pos = self._pos(symbol)
        from tg.format_helpers import resolve_available_cash
        cash = resolve_available_cash(self.app, symbol, st)
        plan = self.app.strategy.get_plan_from_state(
            symbol, pos["current_price"], st, premium, available_cash=cash,
        )
        self.app.state.save(symbol, st)
        orders = plan.get("buy_orders", []) + plan.get("sell_orders", [])
        if not orders:
            await context.bot.send_message(chat_id, f"[{symbol}] 주문 없음")
            return
        is_live = self.app.settings.has_toss and not is_dry(self.app)
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
                f"⏭️ [{symbol}] {target} — 18:05 이전 LOC 이미 접수됨. 스킵합니다.",
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
            MAIN_HOME: self.cmd_home,
            MAIN_HOME_LEGACY: self.cmd_home,
            MAIN_PLAN: self.cmd_plan,
            "📋 주문 계획": self.cmd_plan,
            MAIN_SETTING: self.cmd_setting,
            "설정": self.cmd_setting,
            MAIN_STATUS: self.cmd_home,
            "📈 현황": self.cmd_home,
            MAIN_BALANCE: self.cmd_balance,
            MAIN_LEDGER: self.cmd_ledger,
            MAIN_CYCLES: self.cmd_ledger,
            "📒 회차내역": self.cmd_ledger,
        }
        low = text.lower()
        if text in menu_routes or low in ("setting", "settings"):
            context.user_data.pop("awaiting", None)
            context.user_data.pop("awaiting_symbol", None)
            await self._refresh_main_menu(update)
            if low in ("setting", "settings"):
                return await self.cmd_setting(update, context)
            return await menu_routes[text](update, context)

        if low in (
            "/envcheck", "envcheck", "/check_env", "check_env",
            "/env", "환경확인", "환경체크", "/환경확인", "/환경체크",
        ):
            return await self.cmd_envcheck(update, context)

        if low in ("/setting", "/settings", "/설정") or text == "설정":
            return await self.cmd_setting(update, context)

        if text in ("/version", "버전"):
            return await self.cmd_version(update, context)

        if text.startswith("/set_t"):
            return await self.cmd_set_t(update, context)

        awaiting = context.user_data.get("awaiting")
        if not awaiting:
            if text.startswith("/"):
                await update.message.reply_text(
                    "알 수 없는 명령입니다.\n"
                    "· /start — 메인\n"
                    "· /setting 또는 ⚙️ 설정\n"
                    "· /envcheck — 환경 확인"
                )
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
