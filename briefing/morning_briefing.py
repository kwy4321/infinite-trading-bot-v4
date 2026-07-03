"""Morning briefing assembler."""

import datetime
from zoneinfo import ZoneInfo

from app import App
from briefing.index_fetcher import fetch_index_summary
from briefing.market_context import get_briefing_market_context
from briefing.news_summarizer import summarize_news


async def build_briefing(app: App) -> str:
    kst = ZoneInfo("Asia/Seoul")
    now = datetime.datetime.now(kst).strftime("%Y-%m-%d %H:%M")
    broker = app.broker if not app.settings.dry_run else None
    ctx = get_briefing_market_context(broker)
    lines = [f"🌅 <b>아침 브리핑</b> ({now} KST)\n"]
    if ctx["us_holiday"]:
        lines.append(
            f"🇺🇸 <b>{ctx['holiday_label']}</b> 미국 증시 <b>휴장</b> — "
            f"지수는 직전 마감일 기준입니다.\n"
        )
    lines.append(await fetch_index_summary(broker))
    lines.append("")
    lines.append(await summarize_news(app.settings, market_ctx=ctx))
    return "\n".join(lines)
