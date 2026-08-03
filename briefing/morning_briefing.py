"""Morning briefing assembler."""

import asyncio

from app import App
from briefing.index_fetcher import fetch_index_summary
from briefing.market_context import get_briefing_market_context
from briefing.news_summarizer import summarize_market_analysis
from briefing.strategy_briefing import format_strategy_briefing
from core.clock import now_kst
from render.html import bold
from services.trading_context import is_dry


async def build_briefing(app: App) -> str:
    now = now_kst().strftime("%Y-%m-%d %H:%M")
    settings = app.settings
    broker = app.broker if not is_dry(app) else None
    # 휴장 조회·전략 카드는 브로커 HTTP 를 타므로 이벤트 루프 밖에서 실행한다.
    ctx = await asyncio.to_thread(get_briefing_market_context, broker)
    lines = [f"🌅 {bold('아침 브리핑')} ({now} KST)\n"]
    if ctx["us_holiday"]:
        lines.append(
            f"{bold(ctx['holiday_label'])} 미국 증시 {bold('휴장')} — "
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
        await asyncio.to_thread(
            format_strategy_briefing,
            app,
            ctx["session_date"],
            session_label=ctx["session_label"],
        )
    )
    return "\n".join(lines)
