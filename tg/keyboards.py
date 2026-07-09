"""Inline keyboard builders."""

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup

from config.settings import PREMIUM_OPTIONS, SPLIT_OPTIONS, SYMBOLS, TAKE_PROFIT_OPTIONS

# 하단 고정 메뉴 (Reply Keyboard) — 탭하면 명령어 입력 없이 실행
MAIN_HOME = "🏠 메인"
MAIN_PLAN = "📋 주문계획"
MAIN_SETTING = "⚙️ 설정"
MAIN_STATUS = "♾️ 현황"
MAIN_BALANCE = "💼 잔고"
MAIN_CYCLES = "📒 회차내역"


def main_menu_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [
            [KeyboardButton(MAIN_HOME), KeyboardButton(MAIN_PLAN), KeyboardButton(MAIN_SETTING)],
            [KeyboardButton(MAIN_STATUS), KeyboardButton(MAIN_BALANCE), KeyboardButton(MAIN_CYCLES)],
        ],
        resize_keyboard=True,
        is_persistent=True,
    )


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
        [InlineKeyboardButton("📡 거래 종목", callback_data="set_symbols")],
        [InlineKeyboardButton("💰 원금", callback_data="set_seed")],
        [InlineKeyboardButton("🍰 분할", callback_data="set_split")],
        [InlineKeyboardButton("큰수매수", callback_data="set_premium")],
        [InlineKeyboardButton("목표수익률", callback_data="set_takeprofit")],
        [InlineKeyboardButton("🔑 API 토큰", callback_data="set_token")],
        [InlineKeyboardButton(force_label, callback_data="toggle_force_one")],
    ])


def trading_symbols_keyboard(active: list[str], editing: str) -> InlineKeyboardMarkup:
    """거래 종목 선택 — 🟢=켜짐, ⚪=꺼짐, ✏️=설정 편집 중."""
    active_up = {s.upper() for s in active}
    editing = editing.upper()
    row = []
    for s in SYMBOLS:
        if s in active_up:
            label = f"🟢 {s}" + (" ✏️" if s == editing else "")
        else:
            label = f"⚪ {s}"
        row.append(InlineKeyboardButton(label, callback_data=f"TRADE:{s}"))
    return InlineKeyboardMarkup([
        row,
        [InlineKeyboardButton("⬅️ 설정으로", callback_data="back_setting")],
    ])


def active_symbols_keyboard(active: list[str]) -> InlineKeyboardMarkup:
    """@deprecated — trading_symbols_keyboard 사용."""
    return trading_symbols_keyboard(active, active[0] if active else SYMBOLS[0])


def token_keyboard(from_settings: bool = False) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton("🔄 갱신하기", callback_data="TOKEN:refresh")]]
    if from_settings:
        rows.append([InlineKeyboardButton("⬅️ 설정으로", callback_data="back_setting")])
    return InlineKeyboardMarkup(rows)


def run_job_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("익절", callback_data="RUN:job1"),
         InlineKeyboardButton("체결정리", callback_data="RUN:job2")],
        [InlineKeyboardButton("프리장 LOC", callback_data="RUN:job3"),
         InlineKeyboardButton("일일리포트", callback_data="RUN:job4")],
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
