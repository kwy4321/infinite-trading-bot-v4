"""Morning briefing assembler."""

import datetime
from zoneinfo import ZoneInfo

from app import App
from briefing.index_fetcher import fetch_index_summary
from briefing.market_context import get_briefing_market_context
from briefing.news_summarizer import summarize_market_analysis
from briefing.strategy_briefing import format_strategy_briefing


from config.settings import reload_settings
from tg.format_helpers import is_dry


async def build_briefing(app: App) -> str:
    kst = ZoneInfo("Asia/Seoul")
    now = datetime.datetime.now(kst).strftime("%Y-%m-%d %H:%M")
    settings = reload_settings()
    app.settings = settings
    broker = app.broker if not is_dry(app) else None
    ctx = get_briefing_market_context(broker)
    lines = [f"🌅 <b>아침 브리핑</b> ({now} KST)\n"]
    if ctx["us_holiday"]:
        lines.append(
            f"<b>{ctx['holiday_label']}</b> 미국 증시 <b>휴장</b> — "
            f"지수는 직전 마감일 기준입니다.\n"
        )
    lines.append(await fetch_index_summary(broker))
    analysis = await summarize_market_analysis(
        settings, broker, market_ctx=ctx,
    )
    if analysis:
        lines.append("")
        lines.append(analysis)
    lines.append("")
    lines.append(
        format_strategy_briefing(
            app,
            ctx["session_date"],
            session_label=ctx["session_label"],
        )
    )
    return "\n".join(lines)
