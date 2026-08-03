"""주문 라벨 — plan/notify 두 스타일이 한 구현을 공유한다."""

from __future__ import annotations

import pytest

from render.labels import short_order_label
from tg.notifications import order_label
from tg.plan_formatter import _short_label


@pytest.mark.parametrize(
    ("desc", "expected"),
    [
        ("별 +10% 매수", "별 +10%"),
        ("평단 매수", "평단"),
        ("큰수매수 첫 진입", "큰수매수"),
        ("하단 방어 -20% 매수", "하단방어 −20%"),
        ("리버스 첫매도 MOC", "리버스 MOC"),
        ("리버스 LOC매도", "리버스 매도"),
        ("리버스 쿼터매수", "리버스 쿼터매수"),
        ("쿼터 매도 1/4", "쿼터 매도"),
    ],
)
def test_shared_labels_agree_between_styles(desc, expected):
    assert short_order_label(desc, style="plan") == expected
    assert short_order_label(desc, style="notify") == expected


def test_take_profit_wording_differs_by_style():
    assert short_order_label("익절 +10%", style="plan") == "익절 매도"
    assert short_order_label("익절 +10%", style="notify") == "익절"


def test_reverse_buy_wording_differs_by_style():
    assert short_order_label("리버스 별 매수", style="plan") == "리버스 별매수"
    assert short_order_label("리버스 별 매수", style="notify") == "리버스 매수"


def test_public_wrappers_delegate():
    assert _short_label("익절 +10%") == "익절 매도"
    assert order_label("익절 +10%") == "익절"


def test_fallback_truncates_by_style():
    long_desc = "알수없는아주긴주문설명입니다정말길어요"
    assert len(_short_label(long_desc)) <= 12
    assert len(order_label(long_desc)) <= 16
