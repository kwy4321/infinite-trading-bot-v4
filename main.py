"""Entry point — thin wiring: App, scheduler, Telegram polling."""

import datetime
import logging
from zoneinfo import ZoneInfo

from telegram.ext import ApplicationBuilder, CallbackQueryHandler, CommandHandler, MessageHandler, filters

from app import App
from jobs.executor import JobExecutor
from telegram.handler import TelegramHandler
from telegram.sender import TelegramSender

logger = logging.getLogger(__name__)
KST = ZoneInfo("Asia/Seoul")
NY = ZoneInfo("America/New_York")


def _is_us_summer() -> bool:
    ny = datetime.datetime.now(NY)
    return ny.dst() != datetime.timedelta(0)


def _register_jobs(app_tg, executor: JobExecutor):
    """Register KST daily jobs with summer/winter skip (same pattern as v0)."""

    async def job1(ctx):
        h = datetime.datetime.now(KST).hour
        if _is_us_summer() and h != 17:
            return
        if not _is_us_summer() and h != 18:
            return
        await executor.run_job1()

    async def job2(ctx):
        h = datetime.datetime.now(KST).hour
        if _is_us_summer() and h != 23:
            return
        if not _is_us_summer() and h not in (0, 23):
            return
        await executor.run_job2()

    async def job3(ctx):
        await executor.run_job3(premium=10)

    async def job4(ctx):
        await executor.run_job4()

    async def briefing(ctx):
        await executor.run_morning_briefing()

    chat_ids = list(app_tg.bot_data.get("chat_ids") or [])
    chat_id = chat_ids[0] if chat_ids else None

    jq = app_tg.job_queue
    jq.run_daily(briefing, time=datetime.time(7, 0, tzinfo=KST), chat_id=chat_id, name="briefing")
    jq.run_daily(job1, time=datetime.time(17, 0, tzinfo=KST), chat_id=chat_id, name="job1_summer")
    jq.run_daily(job1, time=datetime.time(18, 0, tzinfo=KST), chat_id=chat_id, name="job1_winter")
    jq.run_daily(job2, time=datetime.time(23, 0, tzinfo=KST), chat_id=chat_id, name="job2_summer")
    jq.run_daily(job2, time=datetime.time(0, 0, tzinfo=KST), chat_id=chat_id, name="job2_winter")
    jq.run_daily(job3, time=datetime.time(5, 30, tzinfo=KST), chat_id=chat_id, name="job3")
    jq.run_daily(job4, time=datetime.time(6, 15, tzinfo=KST), chat_id=chat_id, name="job4")


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )

    application_app = App.create()
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
    tg.add_handler(CommandHandler("dashboard", handler.cmd_dashboard))
    tg.add_handler(CommandHandler("status", handler.cmd_status))
    tg.add_handler(CommandHandler("plan", handler.cmd_plan))
    tg.add_handler(CommandHandler("setting", handler.cmd_setting))
    tg.add_handler(CommandHandler("history", handler.cmd_history))
    tg.add_handler(CommandHandler("sync", handler.cmd_sync))
    tg.add_handler(CommandHandler("split", handler.cmd_split))
    tg.add_handler(CommandHandler("cycles", handler.cmd_cycles))
    tg.add_handler(CommandHandler("monthly", handler.cmd_monthly))
    tg.add_handler(CommandHandler("cycle_done", handler.cmd_cycle_done))
    tg.add_handler(CommandHandler("pause", handler.cmd_pause))
    tg.add_handler(CommandHandler("resume", handler.cmd_resume))
    tg.add_handler(CommandHandler("job1", lambda u, c: handler.cmd_job(u, c, "job1")))
    tg.add_handler(CommandHandler("job2", lambda u, c: handler.cmd_job(u, c, "job2")))
    tg.add_handler(CommandHandler("job3", lambda u, c: handler.cmd_job(u, c, "job3")))
    tg.add_handler(CommandHandler("job4", lambda u, c: handler.cmd_job(u, c, "job4")))
    tg.add_handler(CommandHandler("briefing", lambda u, c: handler.cmd_job(u, c, "morning_briefing")))
    tg.add_handler(CallbackQueryHandler(handler.handle_callback))
    tg.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handler.handle_message))

    _register_jobs(tg, executor)

    dry = application_app.settings.dry_run or not application_app.settings.has_toss
    mode = "DRY_RUN" if dry else "LIVE"
    logger.info("🚀 라오어 무한매수 4.0 v1.0 시작 (%s)", mode)
    tg.run_polling()


if __name__ == "__main__":
    main()
