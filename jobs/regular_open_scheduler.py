"""미국 본장 개장 시각에 LOC 1회 스케줄 — 폴링 없음."""

from __future__ import annotations

import datetime
import logging
from zoneinfo import ZoneInfo

from broker.toss_client import TossClient
from strategy.market_schedule import regular_open_kst

logger = logging.getLogger(__name__)
KST = ZoneInfo("Asia/Seoul")
JOB_NAME = "regular_open_loc"


def _clear_named_jobs(jq, name: str) -> None:
    for job in list(jq.jobs()):
        if job.name == name:
            job.schedule_removal()


def schedule_regular_open_loc(jq, executor, *, chat_id=None) -> None:
    """당일 본장 개장(KST) 시각에 run_once 1회 등록."""
    _clear_named_jobs(jq, JOB_NAME)

    target = TossClient.target_us_date_for_evening_loc()
    open_kst = regular_open_kst(target)

    now = datetime.datetime.now(KST)
    if executor.app.runtime.last_job3_us_date() == target:
        logger.info("regular_open_loc — %s 이미 접수됨, 스케줄 생략", target)
        return
    if open_kst <= now:
        logger.info(
            "regular_open_loc — 개장 %s 지남 (현재 %s), 스케줄 생략",
            open_kst.strftime("%H:%M"),
            now.strftime("%H:%M"),
        )
        return

    async def regular_open_loc(_ctx):
        await executor.run_market_open_plan()

    jq.run_once(regular_open_loc, when=open_kst, chat_id=chat_id, name=JOB_NAME)
    logger.info(
        "regular_open_loc — %s KST 예약 (미국 거래일 %s)",
        open_kst.strftime("%Y-%m-%d %H:%M"),
        target,
    )


def register_regular_open_jobs(jq, executor, *, chat_id=None) -> None:
    """시작 시 + 매일 06:15에 당일 개장 시각 재등록."""

    async def reschedule(_ctx):
        schedule_regular_open_loc(jq, executor, chat_id=chat_id)

    jq.run_daily(
        reschedule,
        time=datetime.time(6, 15, tzinfo=KST),
        chat_id=chat_id,
        name="regular_open_reschedule",
    )
    schedule_regular_open_loc(jq, executor, chat_id=chat_id)
