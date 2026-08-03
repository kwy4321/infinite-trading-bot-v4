"""텔레그램 HTML 안전성 — /plan 무응답 사건의 회귀 방지."""

from __future__ import annotations

from render.html import (
    TELEGRAM_MAX_LEN,
    bold,
    card,
    code,
    dim,
    esc,
    quote,
    quote_exp,
    split_html,
    strip_tags,
    validate_html,
)


def test_esc_escapes_html_specials():
    assert esc("a<b>&c") == "a&lt;b&gt;&amp;c"
    assert esc(None) == ""
    assert esc(12) == "12"


def test_primitives_escape_their_input():
    for fn in (bold, code, dim):
        assert "<script>" not in fn("<script>")
        assert "&lt;script&gt;" in fn("<script>")


def test_quote_flattens_nested_blockquote():
    """중첩 blockquote 는 텔레그램이 거부한다 — quote() 가 알아서 제거해야 한다."""
    inner = quote("inner")
    outer = quote("head", inner, "tail")
    assert outer.count("<blockquote>") == 1
    assert outer.count("</blockquote>") == 1
    assert validate_html(outer) == []


def test_quote_exp_also_flattens():
    out = quote_exp(quote("x"))
    assert out.count("blockquote") == 2  # 여는 태그 + 닫는 태그
    assert validate_html(out) == []


def test_card_has_no_blockquote():
    """카드를 여러 개 이어 붙이는 화면(주문계획)은 blockquote 를 쓰지 않는다."""
    assert "blockquote" not in card("a", "b")


def test_validate_html_detects_problems():
    assert validate_html("<b>ok</b>") == []
    assert validate_html("<b>missing close") != []
    assert validate_html("<div>bad tag</div>") != []
    assert validate_html("<blockquote><blockquote>x</blockquote></blockquote>") != []


def test_strip_tags_returns_plain_text():
    assert strip_tags("<b>hi</b> <i>there</i>") == "hi there"
    assert strip_tags("a &amp; b") == "a & b"


def test_split_html_keeps_short_text_intact():
    assert split_html("short") == ["short"]


def test_split_html_respects_limit_and_balances_tags():
    body = "\n".join(f"<b>line {i}</b> filler text" for i in range(600))
    chunks = split_html(body, limit=1000)
    assert len(chunks) > 1
    for chunk in chunks:
        assert len(chunk) <= 1000
        assert validate_html(chunk) == [], chunk[-200:]


def test_split_html_reopens_unclosed_tag_across_chunks():
    body = "<b>" + ("x" * 300) + "</b>"
    chunks = split_html(body, limit=100)
    assert all(validate_html(c) == [] for c in chunks)
    assert "".join(strip_tags(c) for c in chunks).replace("\n", "") == "x" * 300


def test_telegram_limit_is_platform_value():
    assert TELEGRAM_MAX_LEN == 4096
