"""Entry point — thin wiring: App, scheduler, Telegram polling."""

from __future__ import annotations

import datetime
import logging
from zoneinfo import ZoneInfo

from telegram.ext import ApplicationBuilder, CallbackQueryHandler, CommandHandler, MessageHandler, filters

from app import App
from jobs.executor import JobExecutor
from jobs.regular_open_scheduler import register_regular_open_jobs
from tg.handler import TelegramHandler
from tg.sender import TelegramSender

logger = logging.getLogger(__name__)
KST = ZoneInfo("Asia/Seoul")


def _register_jobs(app_tg, executor: JobExecutor):
    """Register KST daily jobs — LOC(CLS) at US regular open; sync after close."""

    async def job4(ctx):
        await executor.run_job4()

    async def briefing(ctx):
        await executor.run_morning_briefing()

    chat_ids = list(app_tg.bot_data.get("chat_ids") or [])
    chat_id = chat_ids[0] if chat_ids else None

    jq = app_tg.job_queue
    if executor.app.settings.briefing_enabled:
        jq.run_daily(briefing, time=datetime.time(7, 0, tzinfo=KST), chat_id=chat_id, name="briefing")
    jq.run_daily(job4, time=datetime.time(6, 15, tzinfo=KST), chat_id=chat_id, name="job4")
    register_regular_open_jobs(jq, executor, chat_id=chat_id)


def main():
    application_app = App.create()
    dry = application_app.settings.dry_run or not application_app.settings.has_toss
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
    sender = TelegramSender(bot=None, chat_ids=chat_ids)
    executor = JobExecutor(application_app, sender=sender)
    handler = TelegramHandler(application_app, executor, sender)

    tg = ApplicationBuilder().token(token).build()
    tg.bot_data["chat_ids"] = chat_ids
    sender.set_bot(tg.bot)

    tg.add_handler(CommandHandler("start", handler.cmd_start))
    tg.add_handler(CommandHandler("help", handler.cmd_start))
    tg.add_handler(CommandHandler("dashboard", handler.cmd_dashboard))
    tg.add_handler(CommandHandler("status", handler.cmd_status))
    tg.add_handler(CommandHandler("balance", handler.cmd_balance))
    tg.add_handler(CommandHandler("plan", handler.cmd_plan))
    tg.add_handler(CommandHandler("setting", handler.cmd_setting))
    tg.add_handler(CommandHandler("set_t", handler.cmd_set_t))
    tg.add_handler(CommandHandler("history", handler.cmd_history))
    tg.add_handler(CommandHandler("split", handler.cmd_split))
    tg.add_handler(CommandHandler("cycles", handler.cmd_cycles))
    tg.add_handler(CommandHandler("monthly", handler.cmd_monthly))
    tg.add_handler(CommandHandler("cycle_done", handler.cmd_cycle_done))
    tg.add_handler(CommandHandler("sync", handler.cmd_sync))
    tg.add_handler(CommandHandler("pause", handler.cmd_pause))
    tg.add_handler(CommandHandler("resume", handler.cmd_resume))
    tg.add_handler(CommandHandler("run", handler.cmd_run))
    tg.add_handler(CommandHandler("token", handler.cmd_token))
    tg.add_handler(CallbackQueryHandler(handler.handle_callback))
    tg.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handler.handle_message))

    _register_jobs(tg, executor)

    mode = "DRY_RUN" if dry else "LIVE"
    logger.info("🚀 라오어 무한매수 4.0 v1.0 시작 (%s)", mode)
    tg.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
