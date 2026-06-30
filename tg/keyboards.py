"""Inline keyboard builders."""

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from config.settings import PREMIUM_OPTIONS, SPLIT_OPTIONS, SYMBOLS


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


def plan_action_keyboard(symbols: list[str]) -> InlineKeyboardMarkup:
    exec_row = [
        InlineKeyboardButton(f"🚀 {sym}", callback_data=f"EXEC:{sym}")
        for sym in symbols
    ]
    return InlineKeyboardMarkup([exec_row] if exec_row else [])


def symbol_picker(prefix: str) -> InlineKeyboardMarkup:
    row = [InlineKeyboardButton(s, callback_data=f"{prefix}:{s}") for s in SYMBOLS]
    return InlineKeyboardMarkup([row])


def setting_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔀 종목", callback_data="set_ticker")],
        [InlineKeyboardButton("💰 원금", callback_data="set_seed")],
        [InlineKeyboardButton("💵 예수금", callback_data="set_cash")],
        [InlineKeyboardButton("🍰 분할", callback_data="set_split")],
        [InlineKeyboardButton("📈 큰수매수", callback_data="set_premium")],
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
