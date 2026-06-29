"""Inline keyboard builders."""

import datetime

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from config.settings import SPLIT_OPTIONS, SYMBOLS


def plan_premium_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("5%", callback_data="PLAN:5"),
         InlineKeyboardButton("10%", callback_data="PLAN:10")],
        [InlineKeyboardButton("15%", callback_data="PLAN:15"),
         InlineKeyboardButton("20%", callback_data="PLAN:20")],
    ])


def symbol_picker(prefix: str) -> InlineKeyboardMarkup:
    row = [InlineKeyboardButton(s, callback_data=f"{prefix}:{s}") for s in SYMBOLS]
    return InlineKeyboardMarkup([row])


def setting_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔀 종목", callback_data="set_ticker"),
         InlineKeyboardButton("💰 원금", callback_data="set_seed")],
        [InlineKeyboardButton("💵 예수금", callback_data="set_cash"),
         InlineKeyboardButton("🍰 분할", callback_data="set_split")],
        [InlineKeyboardButton("📐 액면분할", callback_data="open_split"),
         InlineKeyboardButton("📒 회차", callback_data="open_cycles")],
        [InlineKeyboardButton("📅 월별", callback_data="open_monthly"),
         InlineKeyboardButton("📊 대시보드", callback_data="open_dashboard")],
    ])


def split_ratio_keyboard(ticker: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("2:1", callback_data=f"SPLIT_RATIO:{ticker}:2"),
         InlineKeyboardButton("3:1", callback_data=f"SPLIT_RATIO:{ticker}:3")],
        [InlineKeyboardButton("1:2", callback_data=f"SPLIT_RATIO:{ticker}:0.5"),
         InlineKeyboardButton("✏️ 직접", callback_data=f"SPLIT_CUSTOM:{ticker}")],
    ])


def split_confirm_keyboard(ticker: str, ratio: float) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ 적용", callback_data=f"SPLIT_APPLY:{ticker}:{ratio}"),
        InlineKeyboardButton("❌ 취소", callback_data="SPLIT_CANCEL"),
    ]])


def monthly_keyboard(year: int = None) -> InlineKeyboardMarkup:
    year = year or datetime.date.today().year
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("TQQQ", callback_data=f"MONTHLY:{year}:TQQQ"),
         InlineKeyboardButton("SOXL", callback_data=f"MONTHLY:{year}:SOXL")],
        [InlineKeyboardButton("전체", callback_data=f"MONTHLY:{year}:ALL"),
         InlineKeyboardButton(f"{year - 1}년", callback_data=f"MONTHLY:{year - 1}:ALL")],
    ])


def split_count_keyboard(ticker: str) -> InlineKeyboardMarkup:
    rows = []
    row = []
    for n in SPLIT_OPTIONS:
        row.append(InlineKeyboardButton(str(n), callback_data=f"SPLIT_COUNT:{ticker}:{n}"))
        if len(row) == 3:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    return InlineKeyboardMarkup(rows)
