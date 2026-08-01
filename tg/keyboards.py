"""Inline keyboard builders."""

from __future__ import annotations

from config.settings import PREMIUM_OPTIONS, SPLIT_OPTIONS, SYMBOLS, TAKE_PROFIT_OPTIONS
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup

# 하단 고정 메뉴 (Reply Keyboard) — 탭하면 명령어 입력 없이 실행
MAIN_HOME = "🏠 메인·현황"
MAIN_PLAN = "📋 주문계획"
MAIN_SETTING = "⚙️ 설정"
MAIN_BALANCE = "💼 잔고"
MAIN_LEDGER = "📊 장부"
MAIN_DASHBOARD = "📈 대시보드"
# 구 하단 메뉴 라벨 (키보드 갱신 전 — 탭 시 메인·현황과 동일 동작)
MAIN_STATUS = "♾️ 현황"
MAIN_HOME_LEGACY = "🏠 메인"
MAIN_CYCLES = MAIN_LEDGER  # 하위 호환


def dashboard_keyboard(settings) -> InlineKeyboardMarkup | None:
    """Streamlit 대시보드 바로가기."""
    url = settings.streamlit_link
    if not url:
        return None
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📈 대시보드 열기", url=url)],
    ])


def ledger_keyboard(settings) -> InlineKeyboardMarkup | None:
    """Streamlit 대시보드 + Google Sheets."""
    rows: list[list[InlineKeyboardButton]] = []
    dash = settings.streamlit_link
    if dash:
        rows.append([InlineKeyboardButton("📊 대시보드 보기", url=dash)])
    url = settings.google_sheets_link
    if url:
        rows.append([InlineKeyboardButton("📗 Google Sheets", url=url)])
    if settings.has_google_sheets or url:
        rows.append([InlineKeyboardButton("🔄 Sheets 동기화", callback_data="LEDGER:sync")])
    return InlineKeyboardMarkup(rows) if rows else None


def main_menu_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [
            [KeyboardButton(MAIN_HOME), KeyboardButton(MAIN_PLAN), KeyboardButton(MAIN_SETTING)],
            [KeyboardButton(MAIN_BALANCE), KeyboardButton(MAIN_LEDGER), KeyboardButton(MAIN_DASHBOARD)],
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


def setting_keyboard(force_one: bool = False, *, dry: bool = True) -> InlineKeyboardMarkup:
    force_label = "⚡ 강제1회 OFF" if force_one else "⚡ 강제1회 ON"
    live_label = "💹 실거래 켜기" if dry else "🧪 DRY 모드"
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📡 거래 종목", callback_data="set_symbols")],
        [InlineKeyboardButton("💰 원금", callback_data="set_seed")],
        [InlineKeyboardButton("🍰 분할", callback_data="set_split")],
        [InlineKeyboardButton("📈 큰수매수", callback_data="set_premium")],
        [InlineKeyboardButton("🎯 목표수익률", callback_data="set_takeprofit")],
        [InlineKeyboardButton("🔑 API 토큰", callback_data="set_token")],
        [InlineKeyboardButton(live_label, callback_data="toggle_force_live")],
        [InlineKeyboardButton("🔍 환경확인", callback_data="ENV:check")],
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


def token_keyboard(from_settings: bool = False) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton("🔄 상태 확인", callback_data="TOKEN:refresh")]]
    if from_settings:
        rows.append([InlineKeyboardButton("⬅️ 설정으로", callback_data="back_setting")])
    return InlineKeyboardMarkup(rows)


def run_job_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📈 익절", callback_data="RUN:job1"),
         InlineKeyboardButton("🌙 프리장 LOC", callback_data="RUN:job3")],
        [InlineKeyboardButton("📊 일일리포트", callback_data="RUN:job4"),
         InlineKeyboardButton("🌅 아침브리핑", callback_data="RUN:briefing")],
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
