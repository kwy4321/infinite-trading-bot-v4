"""news_summarizer — 프롬프트·파싱 단위 테스트 (API 호출 없음)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from briefing.news_summarizer import (
    _format_index_block,
    _render_analysis,
    _split_sections,
)


def test_split_sections() -> None:
    raw = (
        "[나스닥]\n· 금리 인하 기대\n· 빅테크 실적 호조\n· 변동성 축소\n"
        "[반도체]\n· AI 수요 견조\n· 메모리 가격 반등\n· 장비주 혼조\n"
    )
    split = _split_sections(raw)
    assert split is not None
    nasdaq, semi = split
    assert "금리" in nasdaq
    assert "AI" in semi


def test_render_analysis() -> None:
    raw = (
        "[나스닥]\n· 상승 마감\n· (원인)\n· (전망)\n"
        "[반도체]\n· SOX 강세\n· (원인)\n· (전망)\n"
    )
    text = _render_analysis(raw)
    assert text is not None
    assert "나스닥" in text
    assert "반도체" in text
    assert "주요 뉴스" not in text


def test_format_index_block() -> None:
    block = _format_index_block({
        "indices": [{
            "symbol": "^IXIC",
            "name": "나스닥 종합",
            "ok": True,
            "price": 18000.5,
            "change": 120.3,
            "pct": 0.67,
            "session_label": "7/14(월)",
            "prev_label": "7/11(금)",
        }],
    })
    assert "나스닥 종합" in block
    assert "18,000.50" in block


def main() -> None:
    test_split_sections()
    test_render_analysis()
    test_format_index_block()
    print("test_news_summarizer OK")


if __name__ == "__main__":
    main()
