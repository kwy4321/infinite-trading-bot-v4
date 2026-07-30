"""Google Sheets ledger sync — trades, cycles, status, monthly (한글 장부)."""

from __future__ import annotations

import datetime
import logging
from typing import TYPE_CHECKING, Any, Callable
from zoneinfo import ZoneInfo

from config.settings import resolve_service_account_path
from reporting.dashboard_data import (
    collect_completed_cycles,
    collect_monthly_rows,
    collect_portfolio_snapshot,
    collect_sheet_symbol_status,
    collect_sheet_trades,
    ledger_data_sources,
    prepare_ledger_for_export,
)
from tg.ui import mode_label

if TYPE_CHECKING:
    from app import App

logger = logging.getLogger(__name__)

KST = ZoneInfo("Asia/Seoul")

TAB_SUMMARY = "요약"
TAB_STATUS = "종목현황"
TAB_TRADES = "매매내역"
TAB_CYCLES = "완료회차"
TAB_MONTHLY = "월별수익"
LEGACY_TABS = ("Dashboard", "Status", "Trades", "Cycles", "Monthly")

Column = tuple[str, str, str | None]

# 한국 주식 관례 — 이득 빨강, 손실 파랑
COLOR_PROFIT = {"red": 0.88, "green": 0.18, "blue": 0.18}
COLOR_LOSS = {"red": 0.15, "green": 0.40, "blue": 0.88}
SIGNED_FORMATS = frozenset({"_fmt_usd_signed", "_fmt_pct", "_fmt_pnl"})

STATUS_COLUMNS: list[Column] = [
    ("symbol", "📊 종목", None),
    ("mode_label", "♾️ 전략", None),
    ("avg_price", "💵 평단", "_fmt_usd"),
    ("qty", "📦 보유(주)", None),
    ("purchase_usd", "💰 매입금액", "_fmt_usd"),
    ("T", "🎯 T값", "_fmt_num2"),
    ("take_profit_pct", "🏁 목표%", "_fmt_pct_plain"),
    ("star_price", "⭐ 별값", "_fmt_usd"),
    ("star_pct", "✨ 별%", "_fmt_pct_plain"),
    ("cycle_no", "🔢 회차", None),
    ("cycle_pnl_usd", "📈 회차손익", "_fmt_usd_signed"),
    ("cycle_pnl_pct", "📊 수익률", "_fmt_pct"),
    ("reverse_mode", "🔄 리버스", "_fmt_onoff"),
    ("force_one", "⚡ 강제1회", "_fmt_onoff"),
]

TRADES_COLUMNS: list[Column] = [
    ("seq", "#", None),
    ("date", "📅 날짜", None),
    ("symbol", "📊 종목", None),
    ("t_change", "🎯 T변동", None),
    ("side", "↕️ 매매", "_fmt_side"),
    ("price", "💵 체결가", "_fmt_usd"),
    ("qty", "📦 수량", None),
    ("amount_usd", "💰 총금액", "_fmt_usd"),
    ("pnl_usd", "📈 손익", "_fmt_pnl"),
    ("cycle_no", "🔢 회차", None),
    ("cycle_status", "📌 상태", None),
    ("datetime", "🕐 체결시각", "_fmt_when"),
    ("source", "🔗 출처", "_fmt_source"),
]

CYCLES_COLUMNS: list[Column] = [
    ("symbol", "📊 종목", None),
    ("cycle_no", "🔢 회차", None),
    ("started_at", "🟢 시작", "_fmt_when"),
    ("ended_at", "🔴 종료", "_fmt_when"),
    ("principal", "💰 원금", "_fmt_usd"),
    ("total_buy_usd", "🛒 매수합", "_fmt_usd"),
    ("total_sell_usd", "💵 매도합", "_fmt_usd"),
    ("profit_usd", "📈 실현손익", "_fmt_usd_signed"),
    ("profit_pct", "📊 수익률", "_fmt_pct"),
    ("max_T", "🎯 최고T", "_fmt_num2"),
    ("buy_count", "🛒 매수", None),
    ("sell_count", "💵 매도", None),
]

MONTHLY_COLUMNS: list[Column] = [
    ("year", "📅 연도", None),
    ("month", "📆 월", None),
    ("scope", "📊 구분", None),
    ("cycles", "🔢 회차", None),
    ("profit_usd", "📈 실현손익", "_fmt_usd_signed"),
    ("profit_pct_on_buy", "📊 수익률", "_fmt_pct"),
]


def _to_float(v: Any) -> float | None:
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _fmt_usd(v: Any) -> str:
    try:
        return f"💵 ${float(v):,.2f}"
    except (TypeError, ValueError):
        return str(v or "")


def _fmt_usd_signed(v: Any) -> str:
    try:
        n = float(v)
        if n > 0:
            return f"📈 +${n:,.2f}"
        if n < 0:
            return f"📉 ${n:,.2f}"
        return "➖ $0.00"
    except (TypeError, ValueError):
        return str(v or "")


def _fmt_pct(v: Any) -> str:
    try:
        n = float(v)
        if n > 0:
            return f"📈 +{n:.2f}%"
        if n < 0:
            return f"📉 {n:.2f}%"
        return "➖ 0.00%"
    except (TypeError, ValueError):
        return str(v or "")


def _fmt_pct_plain(v: Any) -> str:
    try:
        return f"🏁 {float(v):g}%"
    except (TypeError, ValueError):
        return str(v or "")


def _fmt_num2(v: Any) -> str:
    try:
        return f"🎯 {float(v):.2f}"
    except (TypeError, ValueError):
        return str(v or "")


def _fmt_side(v: Any) -> str:
    s = str(v or "").upper()
    return {"BUY": "🔴 매수", "SELL": "🔵 매도"}.get(s, s or "")


def _fmt_yesno(v: Any) -> str:
    return "예" if v in (True, "true", "True", 1, "1") else "아니오"


def _fmt_onoff(v: Any) -> str:
    return "✅ ON" if v in (True, "true", "True", 1, "1") else "⬜ OFF"


def _fmt_pnl(v: Any) -> str:
    if v is None or v == "":
        return "—"
    return _fmt_usd_signed(v)


def _fmt_source(v: Any) -> str:
    s = str(v or "").lower()
    return {
        "broker": "🏦 토스증권",
        "sync": "🔄 동기화",
        "fill_log": "📋 체결로그",
    }.get(s, s or "—")


def _fmt_when(v: Any) -> str:
    raw = str(v or "").strip()
    if not raw:
        return ""
    try:
        dt = datetime.datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=datetime.timezone.utc)
        return dt.astimezone(KST).strftime("%Y-%m-%d %H:%M")
    except ValueError:
        return raw[:16] if len(raw) > 10 else raw


_FORMATTERS: dict[str, Callable[[Any], Any]] = {
    "_fmt_usd": _fmt_usd,
    "_fmt_usd_signed": _fmt_usd_signed,
    "_fmt_pct": _fmt_pct,
    "_fmt_pct_plain": _fmt_pct_plain,
    "_fmt_num2": _fmt_num2,
    "_fmt_side": _fmt_side,
    "_fmt_yesno": _fmt_yesno,
    "_fmt_onoff": _fmt_onoff,
    "_fmt_pnl": _fmt_pnl,
    "_fmt_source": _fmt_source,
    "_fmt_when": _fmt_when,
}


def _cell(value: Any) -> str | int | float:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "예" if value else "아니오"
    return value


def _format_value(value: Any, fmt_name: str | None) -> Any:
    if fmt_name:
        return _FORMATTERS[fmt_name](value)
    return _cell(value)


def _rows_table(items: list[dict], columns: list[Column]) -> tuple[list[list], list[list[float | None]]]:
    headers = [label for _, label, _ in columns]
    body: list[list] = []
    sign_grid: list[list[float | None]] = []
    for item in items:
        row_item = dict(item)
        if "mode" in item and "mode_label" not in row_item:
            row_item["mode_label"] = mode_label(str(item.get("mode", "")), brief=True)
        row: list = []
        signs: list[float | None] = []
        for key, _, fmt in columns:
            raw = row_item.get(key)
            if fmt in SIGNED_FORMATS:
                signs.append(_to_float(raw))
            else:
                signs.append(None)
            row.append(_format_value(raw, fmt))
        body.append(row)
        sign_grid.append(signs)
    return [headers, *body], sign_grid


def _rows_summary(app: "App", snapshot: dict) -> list[list]:
    updated = _fmt_when(snapshot.get("updated_at", ""))
    dry = snapshot.get("dry_run")
    mode = "🧪 DRY_RUN (모의)" if dry else "💹 LIVE (실거래)"
    bot = "⏸️ 정지" if snapshot.get("paused") else "▶️ 가동"
    premium = app.runtime.premium_default()

    rows: list[list] = [
        ["📒 라오어 무한매수 4.0 — 장부 요약", ""],
        ["🕐 마지막 동기화", updated],
        ["⚙️ 운영 모드", mode],
        ["🤖 봇 상태", bot],
    ]

    active = app.runtime.active_symbols()
    if not active:
        rows.extend([["", ""], ["⚠️ 거래 종목 없음", "텔레그램 ⚙️설정에서 종목 선택"]])
        return rows

    for sym in active:
        st = app.state.load(sym)
        qty = int(st.get("qty") or 0)
        avg = float(st.get("avg_price") or 0)
        purchase = round(avg * qty, 2) if qty and avg else 0
        t_val = float(st.get("T", 0))
        plan_price = avg or float(st.get("current_price") or 0)
        plan = app.strategy.get_plan_from_state(sym, plan_price, st, premium)
        star_price = float(plan.get("star_price") or 0)
        star_pct = float(plan.get("star_pct") or 0)
        tp = float(plan.get("take_profit_pct") or app.strategy.resolve_take_profit(sym, st.get("take_profit_pct")))

        star_txt = f"⭐ ${star_price:,.2f} (+{star_pct:g}%)" if star_price > 0 else "—"

        rows.extend([
            ["", ""],
            [f"📊 {sym}", ""],
            ["💼 평단가", _fmt_usd(avg) if avg else "—"],
            ["📦 보유수량", f"{qty}주"],
            ["💰 매입금액", _fmt_usd(purchase) if purchase else "—"],
            ["🎯 T값", f"{t_val:.2f}"],
            ["🏁 목표수익률", f"{tp:g}%"],
            ["⭐ 별값", star_txt],
        ])
    return rows


class GoogleSheetsLedger:
    def __init__(self, app: "App"):
        self.app = app
        self.settings = app.settings

    @property
    def enabled(self) -> bool:
        return self.settings.has_google_sheets

    def _client(self):
        import gspread
        from google.oauth2.service_account import Credentials

        path = resolve_service_account_path(self.settings.google_service_account_json)
        if path is None:
            raise FileNotFoundError("Google service account JSON not found")
        scopes = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive",
        ]
        creds = Credentials.from_service_account_file(str(path), scopes=scopes)
        return gspread.authorize(creds)

    @staticmethod
    def _get_or_add_worksheet(spreadsheet, title: str, rows: int, cols: int):
        import gspread

        try:
            return spreadsheet.worksheet(title)
        except gspread.WorksheetNotFound:
            return spreadsheet.add_worksheet(title=title, rows=max(rows, 10), cols=max(cols, 2))

    @staticmethod
    def _style_worksheet(ws, *, header_rows: int = 1, ncol: int = 1) -> None:
        try:
            from gspread.utils import rowcol_to_a1

            end = rowcol_to_a1(header_rows, max(ncol, 1))
            ws.format(
                f"A1:{end}",
                {
                    "textFormat": {"bold": True, "fontSize": 10},
                    "backgroundColor": {"red": 0.85, "green": 0.92, "blue": 0.98},
                    "horizontalAlignment": "CENTER",
                },
            )
            ws.freeze(rows=header_rows)
        except Exception:
            logger.debug("sheet format skipped", exc_info=True)

    @staticmethod
    def _apply_signed_colors(
        spreadsheet,
        ws,
        sign_grid: list[list[float | None]],
        columns: list[Column],
        *,
        header_rows: int = 1,
    ) -> None:
        """손익·수익률 — 이득 빨강, 손실 파랑."""
        if not sign_grid:
            return
        try:
            sheet_id = ws.id
            requests = []
            for r_idx, signs in enumerate(sign_grid):
                for c_idx, (sign, (_, _, fmt)) in enumerate(zip(signs, columns)):
                    if fmt not in SIGNED_FORMATS or sign is None or sign == 0:
                        continue
                    color = COLOR_PROFIT if sign > 0 else COLOR_LOSS
                    row_i = header_rows + r_idx
                    requests.append({
                        "repeatCell": {
                            "range": {
                                "sheetId": sheet_id,
                                "startRowIndex": row_i,
                                "endRowIndex": row_i + 1,
                                "startColumnIndex": c_idx,
                                "endColumnIndex": c_idx + 1,
                            },
                            "cell": {
                                "userEnteredFormat": {
                                    "textFormat": {
                                        "foregroundColor": color,
                                        "bold": True,
                                    },
                                },
                            },
                            "fields": "userEnteredFormat.textFormat",
                        },
                    })
            if requests:
                spreadsheet.batch_update({"requests": requests})
        except Exception:
            logger.debug("signed colors skipped", exc_info=True)

    @staticmethod
    def _apply_summary_layout(spreadsheet, ws, nrows: int) -> None:
        """요약 시트 — 열 너비·줄바꿈·섹션 강조."""
        try:
            sheet_id = ws.id
            spreadsheet.batch_update({
                "requests": [
                    {
                        "updateDimensionProperties": {
                            "range": {
                                "sheetId": sheet_id,
                                "dimension": "COLUMNS",
                                "startIndex": 0,
                                "endIndex": 1,
                            },
                            "properties": {"pixelSize": 220},
                            "fields": "pixelSize",
                        },
                    },
                    {
                        "updateDimensionProperties": {
                            "range": {
                                "sheetId": sheet_id,
                                "dimension": "COLUMNS",
                                "startIndex": 1,
                                "endIndex": 2,
                            },
                            "properties": {"pixelSize": 340},
                            "fields": "pixelSize",
                        },
                    },
                ],
            })
            ws.format(
                f"A1:B{max(nrows, 1)}",
                {"wrapStrategy": "WRAP", "verticalAlignment": "TOP"},
            )
            ws.format(
                "A1",
                {
                    "textFormat": {"bold": True, "fontSize": 14},
                    "backgroundColor": {"red": 0.92, "green": 0.94, "blue": 0.98},
                },
            )
            ws.freeze(rows=1)
        except Exception:
            logger.debug("summary layout skipped", exc_info=True)

    def _write_table_tab(
        self,
        spreadsheet,
        title: str,
        items: list[dict],
        columns: list[Column],
    ) -> None:
        if not items:
            self._write_tab(spreadsheet, title, [["⚠️ 데이터 없음", ""]])
            return
        rows, sign_grid = _rows_table(items, columns)
        ncol = max(len(r) for r in rows)
        ws = self._get_or_add_worksheet(spreadsheet, title, len(rows) + 5, ncol)
        ws.clear()
        ws.update(values=rows, range_name="A1", value_input_option="USER_ENTERED")
        self._style_worksheet(ws, header_rows=1, ncol=ncol)
        self._apply_signed_colors(spreadsheet, ws, sign_grid, columns)

    def _write_tab(
        self,
        spreadsheet,
        title: str,
        rows: list[list],
        *,
        header_rows: int = 1,
        summary_title: bool = False,
    ) -> None:
        if not rows:
            rows = [["(데이터 없음)", ""]]
        ncol = max(len(r) for r in rows)
        ws = self._get_or_add_worksheet(spreadsheet, title, len(rows) + 5, ncol)
        ws.clear()
        ws.update(values=rows, range_name="A1", value_input_option="USER_ENTERED")
        if summary_title:
            self._apply_summary_layout(spreadsheet, ws, len(rows))
        elif header_rows:
            self._style_worksheet(ws, header_rows=header_rows, ncol=ncol)

    @staticmethod
    def _remove_legacy_tabs(spreadsheet) -> None:
        for name in LEGACY_TABS:
            try:
                ws = spreadsheet.worksheet(name)
                spreadsheet.del_worksheet(ws)
            except Exception:
                pass

    def sync_all(self, *, rebuild_broker: bool = True) -> dict:
        if not self.enabled:
            return {"ok": False, "message": "Google Sheets 비활성 (GOOGLE_SHEETS_ENABLED/ID/JSON 확인)"}

        try:
            prep = prepare_ledger_for_export(self.app, rebuild_broker=rebuild_broker)
            snapshot = collect_portfolio_snapshot(self.app, fetch_live_price=False)
            trades = collect_sheet_trades(self.app)
            cycles = collect_completed_cycles(self.app)
            monthly = collect_monthly_rows(self.app)
            sources = ledger_data_sources(self.app)

            status_rows = collect_sheet_symbol_status(self.app)

            client = self._client()
            sid = self.settings.resolved_spreadsheet_id
            if not sid:
                return {"ok": False, "message": "GOOGLE_SPREADSHEET_ID 또는 GOOGLE_SHEETS_URL 확인"}
            spreadsheet = client.open_by_key(sid)

            self._write_tab(
                spreadsheet, TAB_SUMMARY, _rows_summary(self.app, snapshot),
                summary_title=True,
            )
            if status_rows:
                self._write_table_tab(spreadsheet, TAB_STATUS, status_rows, STATUS_COLUMNS)
            else:
                self._write_tab(spreadsheet, TAB_STATUS, [["⚠️ 거래 중인 종목 없음", ""]])
            self._write_table_tab(spreadsheet, TAB_TRADES, trades, TRADES_COLUMNS)
            self._write_table_tab(spreadsheet, TAB_CYCLES, cycles, CYCLES_COLUMNS)
            self._write_table_tab(spreadsheet, TAB_MONTHLY, monthly, MONTHLY_COLUMNS)
            self._remove_legacy_tabs(spreadsheet)

            msg = f"Sheets 동기화 완료 — 매매 {len(trades)}건 · 완료회차 {len(cycles)}건"
            if len(trades) == 0 and len(cycles) == 0:
                msg += (
                    f" (장부 0건 — {sources['data_dir']} 확인 · "
                    f"fill_log={sum(s['fill_log'] for s in sources['symbols'].values())} · "
                    "/sync 후 /sheets_sync)"
                )
            elif prep.get("broker_symbols"):
                msg += f" · 토스체결 {','.join(prep['broker_symbols'])} 반영"
            logger.info(msg)
            return {
                "ok": True,
                "message": msg,
                "trades": len(trades),
                "cycles": len(cycles),
                "prep": prep,
                "sources": sources,
            }
        except Exception as exc:
            logger.exception("google sheets sync failed")
            return {"ok": False, "message": f"Sheets 동기화 실패: {exc}"}

    def sheets_url(self) -> str:
        return self.settings.google_sheets_link


def sync_ledger(app: "App", *, rebuild_broker: bool = True) -> dict:
    return GoogleSheetsLedger(app).sync_all(rebuild_broker=rebuild_broker)
