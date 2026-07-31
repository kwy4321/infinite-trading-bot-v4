"""Entry point — thin wiring: App, scheduler, Telegram polling."""

from __future__ import annotations

import datetime
import logging
from zoneinfo import ZoneInfo

from telegram.ext import ApplicationBuilder, CallbackQueryHandler, CommandHandler, MessageHandler, filters
from telegram import BotCommand

from app import App
from jobs.executor import JobExecutor
from tg.bot_lock import acquire_bot_lock
from tg.build_info import git_rev
from tg.handler import TelegramHandler
from tg.keyboards import main_menu_keyboard
from tg.sender import TelegramSender

logger = logging.getLogger(__name__)
KST = ZoneInfo("Asia/Seoul")
PLAN_PREMARKET_KST = datetime.time(18, 0, tzinfo=KST)
LOC_PREMARKET_KST = datetime.time(18, 5, tzinfo=KST)


def _register_jobs(app_tg, executor: JobExecutor):
    """Register KST daily jobs — plan 18:00, CLS submit 18:05, sync after close."""

    async def job4(ctx):
        await executor.run_job4()

    async def briefing(ctx):
        await executor.run_morning_briefing()

    async def premarket_plan(ctx):
        await executor.run_market_open_plan()

    async def premarket_loc(ctx):
        await executor.run_premarket_loc_submit()

    chat_ids = list(app_tg.bot_data.get("chat_ids") or [])
    chat_id = chat_ids[0] if chat_ids else None

    jq = app_tg.job_queue
    jq.run_daily(briefing, time=datetime.time(7, 0, tzinfo=KST), chat_id=chat_id, name="briefing")
    if not executor.app.settings.briefing_enabled:
        logger.warning(
            "BRIEFING_ENABLED=false — 07:00 job은 Sheets 동기화만 실행 (.env true 권장)"
        )
    jq.run_daily(job4, time=datetime.time(6, 15, tzinfo=KST), chat_id=chat_id, name="job4")
    jq.run_daily(premarket_plan, time=PLAN_PREMARKET_KST, chat_id=chat_id, name="premarket_plan")
    jq.run_daily(premarket_loc, time=LOC_PREMARKET_KST, chat_id=chat_id, name="premarket_loc")


def main():
    _lock = acquire_bot_lock()
    application_app = App.create()
    from tg.format_helpers import is_dry
    dry = is_dry(application_app)
    logger.info(
        "Trading mode=%s | toss=%s | sheets=%s | briefing=%s | summarizer=%s",
        "DRY" if dry else "LIVE",
        application_app.settings.has_toss,
        application_app.settings.has_google_sheets,
        application_app.settings.briefing_enabled,
        bool(application_app.settings.summarizer_api_key),
    )
    default_level = "INFO" if not dry else application_app.settings.log_level
    log_level = getattr(logging, default_level, logging.INFO)
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )

    token = application_app.settings.telegram_bot_token
    if not token:
        logger.error("TELEGRAM_BOT_TOKEN 이 .env 에 없습니다.")
        return

    chat_ids = list(application_app.settings.telegram_allowed_chat_ids)
    for cid in chat_ids:
        application_app.runtime.remember_notify_chat(cid)
    sender = TelegramSender(
        bot=None, chat_ids=chat_ids, runtime=application_app.runtime,
    )
    executor = JobExecutor(application_app, sender=sender)
    handler = TelegramHandler(application_app, executor, sender)

    async def _post_init(app):
        me = await app.bot.get_me()
        wh = await app.bot.get_webhook_info()
        logger.info(
            "Telegram @%s | webhook=%s | allowed_chats=%s",
            me.username,
            wh.url or "(none)",
            chat_ids or "(all)",
        )
        if wh.url:
            await app.bot.delete_webhook(drop_pending_updates=True)
            logger.info("webhook deleted — polling mode")
        rev = git_rev()
        try:
            await app.bot.set_my_commands([
                BotCommand("start", "메인·현황"),
                BotCommand("setting", "설정"),
                BotCommand("envcheck", "환경설정 확인"),
                BotCommand("briefing", "아침 브리핑"),
                BotCommand("plan", "주문계획"),
                BotCommand("version", "빌드 버전"),
                BotCommand("myid", "내 chat ID"),
                BotCommand("cancel", "입력 취소"),
            ])
        except Exception as exc:
            logger.warning("set_my_commands failed: %s", exc)
        for cid in chat_ids:
            try:
                await app.bot.send_message(
                    chat_id=cid,
                    text=f"🟢 봇 가동 ({rev}) — /start",
                    reply_markup=main_menu_keyboard(),
                )
            except Exception as exc:
                logger.error("startup ping chat_id=%s failed: %s", cid, exc)

    async def _on_error(update, context):
        logger.exception("telegram error: %s", context.error)

    tg = ApplicationBuilder().token(token).post_init(_post_init).build()
    tg.add_error_handler(_on_error)
    tg.bot_data["chat_ids"] = chat_ids
    sender.set_bot(tg.bot)

    tg.add_handler(CommandHandler("myid", handler.cmd_myid))
    tg.add_handler(CommandHandler("start", handler.cmd_start))
    tg.add_handler(CommandHandler("help", handler.cmd_start))
    tg.add_handler(CommandHandler("cancel", handler.cmd_cancel))
    tg.add_handler(CommandHandler("version", handler.cmd_version))
    tg.add_handler(CommandHandler("dashboard", handler.cmd_dashboard))
    tg.add_handler(CommandHandler("status", handler.cmd_status))
    tg.add_handler(CommandHandler("balance", handler.cmd_balance))
    tg.add_handler(CommandHandler("plan", handler.cmd_plan))
    tg.add_handler(CommandHandler(["setting", "settings"], handler.cmd_setting))
    tg.add_handler(CommandHandler("set_t", handler.cmd_set_t))
    tg.add_handler(CommandHandler("history", handler.cmd_history))
    tg.add_handler(CommandHandler("split", handler.cmd_split))
    tg.add_handler(CommandHandler("cycles", handler.cmd_cycles))
    tg.add_handler(CommandHandler("monthly", handler.cmd_monthly))
    tg.add_handler(CommandHandler("cycle_done", handler.cmd_cycle_done))
    tg.add_handler(CommandHandler("sync", handler.cmd_sync))
    tg.add_handler(CommandHandler("sheets_sync", handler.cmd_sheets_sync))
    tg.add_handler(CommandHandler("pause", handler.cmd_pause))
    tg.add_handler(CommandHandler("resume", handler.cmd_resume))
    tg.add_handler(CommandHandler("run", handler.cmd_run))
    tg.add_handler(CommandHandler("briefing", handler.cmd_briefing))
    tg.add_handler(CommandHandler(["envcheck", "check_env", "env"], handler.cmd_envcheck))
    tg.add_handler(CommandHandler("token", handler.cmd_token))
    tg.add_handler(CallbackQueryHandler(handler.handle_callback))
    tg.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handler.handle_message))

    _register_jobs(tg, executor)

    mode = "DRY_RUN" if dry else "LIVE"
    rev = git_rev()
    logger.info("🚀 라오어 무한매수 4.0 v1.0 시작 (%s, %s)", mode, rev)
    tg.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception:
        logging.basicConfig(level=logging.ERROR)
        logging.exception("봇 시작 실패 — VM: bash scripts/bot.sh logs")
        raise SystemExit(1)
