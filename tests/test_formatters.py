"""포맷터 출력이 항상 텔레그램이 받아들이는 HTML 인지 검증.

새 화면·항목을 추가했을 때 태그가 깨져 전송이 실패하는 것을 여기서 잡는다.
"""

from __future__ import annotations

import pytest

from render.html import TELEGRAM_MAX_LEN, validate_html
from tg.balance_formatter import format_balance
from tg.plan_formatter import format_plan_block, format_plans
from tg.records_dashboard_formatter import format_records_dashboard
from tg.status_formatter import format_status
from tg.ui import help_block


def _assert_safe(text: str) -> None:
    problems = validate_html(text)
    assert problems == [], f"{problems}\n---\n{text[:800]}"


@pytest.mark.parametrize("dry", [True, False])
def test_status_output_is_valid_html(fake_app, dry):
    fake_app._dry = dry
    text = format_status(fake_app)
    assert "TQQQ" in text
    _assert_safe(text)


def test_status_with_no_active_symbols(fake_app):
    fake_app.runtime._active = []
    text = format_status(fake_app)
    assert "거래 종목 없음" in text
    _assert_safe(text)


def test_status_hides_inactive_symbols(fake_app):
    """거래하지 않는 종목은 화면에 나오지 않아야 한다."""
    fake_app.runtime._active = ["SOXL"]
    text = format_status(fake_app)
    assert "SOXL" in text
    assert "TQQQ" not in text


@pytest.mark.parametrize("dry", [True, False])
def test_plans_output_is_valid_html(fake_app, dry):
    fake_app._dry = dry
    text = format_plans(fake_app, ["TQQQ"], premium=10)
    assert "주문계획" in text
    _assert_safe(text)


def test_plan_block_uses_card_not_blockquote(fake_app):
    """카드를 이어 붙이므로 blockquote 를 쓰면 중첩으로 전송이 실패한다."""
    block = format_plan_block(fake_app, "TQQQ", 10, price=60.0)
    assert "blockquote" not in block
    _assert_safe(block)


def test_plans_with_no_symbols(fake_app):
    text = format_plans(fake_app, [], premium=10)
    assert "거래 종목 없음" in text
    _assert_safe(text)


def test_plans_escape_hostile_order_description(fake_app):
    """주문 설명에 <, & 가 들어와도 HTML 이 깨지지 않는다."""
    original = fake_app.strategy.get_plan_from_state

    def hostile(*args, **kwargs):
        plan = original(*args, **kwargs)
        plan["buy_orders"][0]["desc"] = "<b>주입 & 시도</b>"
        return plan

    fake_app.strategy.get_plan_from_state = hostile
    text = format_plans(fake_app, ["TQQQ"], premium=10)
    assert "&lt;b&gt;" in text
    _assert_safe(text)


@pytest.mark.parametrize("dry", [True, False])
def test_balance_output_is_valid_html(fake_app, dry):
    fake_app._dry = dry
    text = format_balance(fake_app)
    assert "계좌현황" in text
    _assert_safe(text)


@pytest.mark.parametrize("dry", [True, False])
def test_records_dashboard_output_is_valid_html(fake_app, dry):
    fake_app._dry = dry
    text = format_records_dashboard(fake_app)
    assert "대시보드" in text
    _assert_safe(text)


def test_help_block_is_valid_html():
    _assert_safe(help_block())


def test_formatters_stay_within_telegram_limit(fake_app):
    fake_app._dry = False
    for text in (
        format_status(fake_app),
        format_balance(fake_app),
        format_records_dashboard(fake_app),
    ):
        assert len(text) <= TELEGRAM_MAX_LEN
