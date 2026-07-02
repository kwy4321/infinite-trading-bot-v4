"""Inline keyboard builders."""

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from config.settings import PREMIUM_OPTIONS, SPLIT_OPTIONS, SYMBOLS, TAKE_PROFIT_OPTIONS


def premium_keyboard() -> InlineKeyboardMarkup:
    rows = []
    row = []
    for n in PREMIUM_OPTIONS:
        row.append(InlineKeyboardButton(f"+{n}%", callback_data=f"PREMIUM:{n}"))
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    return InlineKeyboardMarkup(rows)


def take_profit_keyboard() -> InlineKeyboardMarkup:
    rows = []
    row = []
    for n in TAKE_PROFIT_OPTIONS:
        row.append(InlineKeyboardButton(f"+{n}%", callback_data=f"TAKEPROFIT:{n}"))
        if len(row) == 3:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    return InlineKeyboardMarkup(rows)


def plan_action_keyboard(symbols: list[str]) -> InlineKeyboardMarkup:
    exec_row = [
        InlineKeyboardButton(f"🚀 {sym}", callback_data=f"EXEC:{sym}")
        for sym in symbols
    ]
    return InlineKeyboardMarkup([exec_row] if exec_row else [])


def symbol_picker(prefix: str) -> InlineKeyboardMarkup:
    row = [InlineKeyboardButton(s, callback_data=f"{prefix}:{s}") for s in SYMBOLS]
    return InlineKeyboardMarkup([row])


def setting_keyboard(force_one: bool = False) -> InlineKeyboardMarkup:
    force_label = "⚡ 강제1회 OFF" if force_one else "⚡ 강제1회 ON"
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔀 종목", callback_data="set_ticker")],
        [InlineKeyboardButton("📡 자동매매 종목", callback_data="set_active")],
        [InlineKeyboardButton("💰 원금", callback_data="set_seed")],
        [InlineKeyboardButton("🍰 분할", callback_data="set_split")],
        [InlineKeyboardButton("📈 큰수매수", callback_data="set_premium")],
        [InlineKeyboardButton("🎯 목표수익률", callback_data="set_takeprofit")],
        [InlineKeyboardButton(force_label, callback_data="toggle_force_one")],
    ])


def active_symbols_keyboard(active: list[str]) -> InlineKeyboardMarkup:
    """자동매매 대상 종목 ON/OFF 토글. 🟢=켜짐, ⚪=꺼짐."""
    active_up = {s.upper() for s in active}
    row = [
        InlineKeyboardButton(
            f"{'🟢' if s in active_up else '⚪'} {s}",
            callback_data=f"TOGGLE_ACTIVE:{s}",
        )
        for s in SYMBOLS
    ]
    return InlineKeyboardMarkup([
        row,
        [InlineKeyboardButton("⬅️ 설정으로", callback_data="back_setting")],
    ])


def run_job_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📈 익절", callback_data="RUN:job1"),
         InlineKeyboardButton("🔄 체결정리", callback_data="RUN:job2")],
        [InlineKeyboardButton("🛒 매수", callback_data="RUN:job3"),
         InlineKeyboardButton("📊 일일리포트", callback_data="RUN:job4")],
        [InlineKeyboardButton("🌅 아침브리핑", callback_data="RUN:briefing")],
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
