"""Entry point — thin wiring: App, scheduler, Telegram polling."""

import datetime
import logging
from zoneinfo import ZoneInfo

from telegram.ext import ApplicationBuilder, CallbackQueryHandler, CommandHandler, MessageHandler, filters

from app import App
from jobs.executor import JobExecutor
from strategy.order_planner import CLOSE_LEAD_SECONDS
from tg.handler import TelegramHandler
from tg.sender import TelegramSender

logger = logging.getLogger(__name__)
KST = ZoneInfo("Asia/Seoul")
NY = ZoneInfo("America/New_York")


def _is_us_summer() -> bool:
    ny = datetime.datetime.now(NY)
    return ny.dst() != datetime.timedelta(0)


def _lead_time(close_hour: int, close_minute: int) -> datetime.time:
    """미국 장 마감(KST) 직전 CLOSE_LEAD_SECONDS."""
    base = datetime.datetime(2000, 1, 1, close_hour, close_minute, 0)
    early = base - datetime.timedelta(seconds=CLOSE_LEAD_SECONDS)
    return early.time().replace(tzinfo=KST)


def _register_jobs(app_tg, executor: JobExecutor):
    """Register KST daily jobs — LOC orders at US close only; plan at US open."""

    async def job3_summer(ctx):
        if not _is_us_summer():
            return
        await executor.run_job3()

    async def job3_winter(ctx):
        if _is_us_summer():
            return
        await executor.run_job3()

    async def job4(ctx):
        await executor.run_job4()

    async def briefing(ctx):
        await executor.run_morning_briefing()

    async def plan_open_summer(ctx):
        if not _is_us_summer():
            return
        await executor.run_market_open_plan()

    async def plan_open_winter(ctx):
        if _is_us_summer():
            return
        await executor.run_market_open_plan()

    chat_ids = list(app_tg.bot_data.get("chat_ids") or [])
    chat_id = chat_ids[0] if chat_ids else None

    jq = app_tg.job_queue
    if executor.app.settings.briefing_enabled:
        jq.run_daily(briefing, time=datetime.time(7, 0, tzinfo=KST), chat_id=chat_id, name="briefing")
    # 종가 LOC — 한국 새벽(미국 16:00 ET 직전)만
    jq.run_daily(job3_summer, time=_lead_time(5, 0), chat_id=chat_id, name="job3_summer")
    jq.run_daily(job3_winter, time=_lead_time(6, 0), chat_id=chat_id, name="job3_winter")
    jq.run_daily(job4, time=datetime.time(6, 15, tzinfo=KST), chat_id=chat_id, name="job4")
    # 저녁: 주문계획 알림만 (주문 없음)
    jq.run_daily(plan_open_summer, time=datetime.time(22, 30, tzinfo=KST), chat_id=chat_id, name="plan_open_summer")
    jq.run_daily(plan_open_winter, time=datetime.time(23, 30, tzinfo=KST), chat_id=chat_id, name="plan_open_winter")


def main():
    application_app = App.create()
    log_level = getattr(logging, application_app.settings.log_level, logging.WARNING)
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

    dry = application_app.settings.dry_run or not application_app.settings.has_toss
    mode = "DRY_RUN" if dry else "LIVE"
    logger.info("🚀 라오어 무한매수 4.0 v1.0 시작 (%s)", mode)
    tg.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
