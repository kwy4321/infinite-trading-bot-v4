"""Gemini 시황 요약 — 재시도·폴백."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from briefing.news_summarizer import _summarize_gemini


def _resp(status: int, *, text: str = "", json_data: dict | None = None):
    mock = MagicMock()
    mock.status_code = status
    mock.text = text
    mock.json.return_value = json_data or {}
    return mock


def test_gemini_retries_503_then_succeeds():
    ok = _resp(200, json_data={
        "candidates": [{"content": {"parts": [{"text": "[나스닥]\n· ok\n· ok\n· ok\n[반도체]\n· ok\n· ok\n· ok"}]}}],
    })
    with patch("briefing.news_summarizer.requests.post", side_effect=[
        _resp(503, text="overloaded"),
        ok,
    ]) as post:
        with patch("briefing.news_summarizer.time.sleep"):
            text, err = _summarize_gemini("AIza-test-key", "", "prompt")
    assert text
    assert err == ""
    assert post.call_count == 2


def test_gemini_falls_back_to_next_model_on_503():
    ok = _resp(200, json_data={
        "candidates": [{"content": {"parts": [{"text": "summary"}]}}],
    })
    with patch("briefing.news_summarizer.requests.post", side_effect=[
        _resp(503, text="overloaded"),
        _resp(503, text="overloaded"),
        _resp(503, text="overloaded"),
        ok,
    ]) as post:
        with patch("briefing.news_summarizer.time.sleep"):
            text, err = _summarize_gemini("AIza-test-key", "", "prompt")
    assert text == "summary"
    assert err == ""
    assert post.call_count == 4


def test_gemini_transient_error_message():
    with patch(
        "briefing.news_summarizer.requests.post",
        return_value=_resp(503, text="unavailable"),
    ):
        with patch("briefing.news_summarizer.time.sleep"):
            text, err = _summarize_gemini("AIza-test-key", "gemini-2.5-flash", "prompt")
    assert text is None
    assert "HTTP 503" in err
    assert "키 문제 아님" in err
