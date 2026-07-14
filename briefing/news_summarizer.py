"""아침 브리핑 — Gemini/OpenAI 나스닥·반도체 시황 분석.

뉴스 헤드라인은 LLM 입력용으로만 쓰고, 텔레그램에는 AI 요약만 노출한다.
"""

from __future__ import annotations

import asyncio
import html
import logging
import xml.etree.ElementTree as ET
from typing import TYPE_CHECKING

import requests

from briefing.index_fetcher import fetch_index_snapshot
from config.settings import Settings
from tg.ui import dim, quote, section

if TYPE_CHECKING:
    from broker.toss_client import TossClient

logger = logging.getLogger(__name__)

_RSS = "https://news.google.com/rss/search"
_HEADERS = {"User-Agent": "Mozilla/5.0 (infinite-trading-bot briefing)"}
_QUERIES = (
    "나스닥 지수",
    "반도체 엔비디아 주가",
)
_MAX_PER_QUERY = 4
_MAX_TOTAL = 8

_MARK_NASDAQ = "[나스닥]"
_MARK_SEMI = "[반도체]"
_PROMPT_TRADING = (
    "당신은 미국 증시 애널리스트입니다. 아래 **지수 마감 데이터**와 참고 헤드라인만 보고 "
    "나스닥 종합지수(^IXIC)와 필라델피아 반도체지수(^SOX)가 {session_label} 미국장에서 "
    "왜 그렇게 움직였는지 한국어로 분석하세요.\n"
    "뉴스 제목을 나열하지 말고, 시황·원인·흐름을 요약하세요.\n"
    "반드시 아래 형식만 출력하세요:\n"
    f"{_MARK_NASDAQ}\n· (한 문장)\n· (한 문장)\n· (한 문장)\n"
    f"{_MARK_SEMI}\n· (한 문장)\n· (한 문장)\n· (한 문장)\n"
    "각 지수마다 불릿 3개. 금리·경제지표·실적·섹터 이슈 등 원인을 명확히. "
    "데이터·헤드라인에 없는 사실은 추측하지 마세요.\n\n"
    "{index_block}"
    "{headline_block}"
)
_PROMPT_HOLIDAY = (
    "당신은 미국 증시 애널리스트입니다.\n"
    "⚠️ {holiday_label} 미국 정규장은 휴장이었습니다. "
    "지수는 전 거래일 {session_label} 마감 기준입니다.\n"
    "오늘 장이 열리지 않았다는 점을 첫 불릿에 명시하고, "
    "헤드라인·지수 데이터에 근거한 시장 배경·전망만 정리하세요. "
    "휴장일에 지수가 등락했다고 쓰지 마세요.\n"
    "뉴스 제목 나열 금지. 반드시 아래 형식만:\n"
    f"{_MARK_NASDAQ}\n· (한 문장)\n· (한 문장)\n· (한 문장)\n"
    f"{_MARK_SEMI}\n· (한 문장)\n· (한 문장)\n· (한 문장)\n\n"
    "{index_block}"
    "{headline_block}"
)


def _has_korean(text: str) -> bool:
    return any("\uac00" <= ch <= "\ud7a3" for ch in text)


def _fetch_headlines() -> list[dict]:
    """LLM 컨텍스트용 — 사용자에게는 노출하지 않음."""
    collected: list[dict] = []
    seen: set[str] = set()
    for query in _QUERIES:
        try:
            resp = requests.get(
                _RSS,
                params={"q": query, "hl": "ko", "gl": "KR", "ceid": "KR:ko"},
                headers=_HEADERS,
                timeout=10,
            )
            resp.raise_for_status()
            root = ET.fromstring(resp.content)
        except Exception as exc:
            logger.warning("뉴스 RSS 실패 %s: %s", query, exc)
            continue
        count = 0
        for item in root.iter("item"):
            title = (item.findtext("title") or "").strip()
            if not title or title in seen or not _has_korean(title):
                continue
            seen.add(title)
            src_el = item.find("source")
            source = (src_el.text or "").strip() if src_el is not None else ""
            collected.append({"title": title, "source": source})
            count += 1
            if count >= _MAX_PER_QUERY or len(collected) >= _MAX_TOTAL:
                break
        if len(collected) >= _MAX_TOTAL:
            break
    return collected


def _format_index_block(snapshot: dict) -> str:
    lines = ["[지수 마감 데이터]"]
    for item in snapshot.get("indices") or []:
        name = item.get("name") or item.get("symbol") or "—"
        if not item.get("ok"):
            lines.append(f"- {name}: 데이터 없음")
            continue
        sign = "+" if float(item.get("change") or 0) >= 0 else ""
        lines.append(
            f"- {name} ({item.get('symbol', '')}): "
            f"{float(item['price']):,.2f} ({sign}{float(item['pct']):.2f}%, "
            f"{sign}{float(item['change']):,.2f}) · "
            f"{item.get('prev_label', '')}→{item.get('session_label', '')}"
        )
    return "\n".join(lines) + "\n\n"


def _format_headline_block(items: list[dict]) -> str:
    if not items:
        return ""
    rows = [f"- {item['title']} ({item['source']})" for item in items]
    return "[참고 헤드라인]\n" + "\n".join(rows) + "\n\n"


def _summarize_openai(api_key: str, model: str, prompt: str) -> str | None:
    try:
        resp = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": model or "gpt-4o-mini",
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.3,
            },
            timeout=45,
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"].strip()
    except Exception as exc:
        logger.warning("OpenAI 요약 실패: %s", exc)
        return None


def _summarize_gemini(api_key: str, model: str, prompt: str) -> str | None:
    model = model or "gemini-2.5-flash"
    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"{model}:generateContent?key={api_key}"
    )
    try:
        resp = requests.post(
            url,
            json={"contents": [{"parts": [{"text": prompt}]}]},
            timeout=45,
        )
        resp.raise_for_status()
        parts = resp.json()["candidates"][0]["content"]["parts"]
        return "".join(p.get("text", "") for p in parts).strip()
    except Exception as exc:
        logger.warning("Gemini 요약 실패: %s", exc)
        return None


def _split_sections(text: str) -> tuple[str, str] | None:
    cleaned = text.replace("**", "").replace("`", "")
    n_idx = cleaned.find(_MARK_NASDAQ)
    s_idx = cleaned.find(_MARK_SEMI)
    if n_idx == -1 or s_idx == -1 or s_idx <= n_idx:
        return None
    nasdaq = cleaned[n_idx + len(_MARK_NASDAQ):s_idx].strip()
    semi = cleaned[s_idx + len(_MARK_SEMI):].strip()
    if not nasdaq or not semi:
        return None
    return nasdaq, semi


def _render_analysis(summary: str) -> str | None:
    split = _split_sections(summary)
    if split:
        nasdaq, semi = split
        return "\n\n".join([
            f"{section('나스닥 종합 · AI 시황', '📊')}\n{quote(html.escape(nasdaq))}",
            f"{section('필라델피아 반도체 · AI 시황', '🔌')}\n{quote(html.escape(semi))}",
        ])
    cleaned = html.escape(summary.replace("**", "").replace("`", "").strip())
    if cleaned:
        return f"{section('미국 증시 · AI 시황', '💡')}\n{quote(cleaned)}"
    return None


def _build_sync(
    settings: Settings,
    broker: "TossClient | None" = None,
    market_ctx: dict | None = None,
) -> str:
    api_key = settings.summarizer_api_key
    if not api_key:
        return dim("💡 SUMMARIZER_API_KEY 설정 시 나스닥·반도체 AI 시황 요약이 포함됩니다.")

    snapshot = fetch_index_snapshot(broker)
    ctx = market_ctx or snapshot
    index_block = _format_index_block(snapshot)
    headlines = _fetch_headlines()
    headline_block = _format_headline_block(headlines)

    if ctx.get("us_holiday"):
        prompt = _PROMPT_HOLIDAY.format(
            holiday_label=ctx.get("holiday_label") or "해당일",
            session_label=ctx.get("session_label") or "전 거래일",
            index_block=index_block,
            headline_block=headline_block,
        )
    else:
        prompt = _PROMPT_TRADING.format(
            session_label=ctx.get("session_label") or "전일",
            index_block=index_block,
            headline_block=headline_block,
        )

    provider = (settings.summarizer_provider or "gemini").lower()
    if provider == "gemini":
        summary = _summarize_gemini(api_key, settings.summarizer_model, prompt)
    else:
        summary = _summarize_openai(api_key, settings.summarizer_model, prompt)

    if summary:
        rendered = _render_analysis(summary)
        if rendered:
            return rendered

    return dim("AI 시황 요약을 불러오지 못했습니다. 잠시 후 다시 시도해 주세요.")


async def summarize_market_analysis(
    settings: Settings,
    broker: "TossClient | None" = None,
    *,
    market_ctx: dict | None = None,
) -> str:
    return await asyncio.to_thread(_build_sync, settings, broker, market_ctx)


# 하위 호환
async def summarize_news(
    settings: Settings, *, market_ctx: dict | None = None,
) -> str:
    return await summarize_market_analysis(settings, None, market_ctx=market_ctx)
