"""Google Sheets ledger sync — trades, cycles, status, monthly (한글 장부)."""

from __future__ import annotations

import datetime
import logging
from typing import TYPE_CHECKING, Any, Callable

from config.settings import resolve_service_account_path
from core.clock import KST
from render.labels import mode_label
from reporting.dashboard_data import (
    collect_completed_cycles,
    collect_monthly_rows,
    collect_portfolio_snapshot,
    collect_sheet_symbol_status,
    collect_sheet_trades,
    ledger_data_sources,
    prepare_ledger_for_export,
)

if TYPE_CHECKING:
    from app import App

logger = logging.getLogger(__name__)

_GSPREAD_CLIENTS: dict[str, Any] = {}

TAB_SUMMARY = "요약"
TAB_TRADES = "매매내역"
TAB_CYCLES = "완료회차"
TAB_MONTHLY = "월별수익"
REMOVED_TABS = ("종목현황", "Dashboard", "Status", "Trades", "Cycles", "Monthly")

Column = tuple[str, str, str | None]

# 한국 주식 관례 — 이득 빨강, 손실 파랑
COLOR_PROFIT = {"red": 0.88, "green": 0.18, "blue": 0.18}
COLOR_LOSS = {"red": 0.15, "green": 0.40, "blue": 0.88}
SIGNED_FORMATS = frozenset({
    "_fmt_usd_signed", "_fmt_pct", "_fmt_pnl",
    "_fmt_usd_signed_compact", "_fmt_pct_compact",
})

STATUS_COLUMNS: list[Column] = [
    ("symbol", "종목", None),
    ("mode_label", "전략", None),
    ("avg_price", "평단", "_fmt_usd_compact"),
    ("qty", "보유", None),
    ("purchase_usd", "매입금액", "_fmt_usd_compact"),
    ("T", "T", "_fmt_num_compact"),
    ("take_profit_pct", "목표%", "_fmt_pct_compact_plain"),
    ("star_price", "별값", "_fmt_usd_compact"),
    ("star_pct", "별%", "_fmt_pct_compact_plain"),
    ("cycle_no", "회차", None),
    ("cycle_pnl_usd", "회차손익", "_fmt_usd_signed_compact"),
    ("cycle_pnl_pct", "수익률", "_fmt_pct_compact"),
    ("reverse_mode", "리버스", "_fmt_onoff_compact"),
    ("force_one", "강제1회", "_fmt_onoff_compact"),
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


def _fmt_usd_compact(v: Any) -> str:
    try:
        return f"${float(v):,.2f}"
    except (TypeError, ValueError):
        return str(v or "")


def _fmt_usd_signed_compact(v: Any) -> str:
    try:
        n = float(v)
        if n > 0:
            return f"+${n:,.2f}"
        if n < 0:
            return f"-${abs(n):,.2f}"
        return "$0.00"
    except (TypeError, ValueError):
        return str(v or "")


def _fmt_pct_compact(v: Any) -> str:
    try:
        n = float(v)
        if n > 0:
            return f"+{n:.2f}%"
        if n < 0:
            return f"{n:.2f}%"
        return "0.00%"
    except (TypeError, ValueError):
        return str(v or "")


def _fmt_pct_compact_plain(v: Any) -> str:
    try:
        return f"{float(v):g}%"
    except (TypeError, ValueError):
        return str(v or "")


def _fmt_num_compact(v: Any) -> str:
    try:
        return f"{float(v):.2f}"
    except (TypeError, ValueError):
        return str(v or "")


def _fmt_onoff_compact(v: Any) -> str:
    return "ON" if v in (True, "true", "True", 1, "1") else "OFF"


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
    "_fmt_usd_compact": _fmt_usd_compact,
    "_fmt_usd_signed_compact": _fmt_usd_signed_compact,
    "_fmt_pct_compact": _fmt_pct_compact,
    "_fmt_pct_compact_plain": _fmt_pct_compact_plain,
    "_fmt_num_compact": _fmt_num_compact,
    "_fmt_onoff_compact": _fmt_onoff_compact,
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


def _pad_rows(rows: list[list], ncol: int) -> list[list]:
    return [list(r) + [""] * (ncol - len(r)) for r in rows]


def _authorize_gspread(settings) -> Any:
    """서비스 계정 gspread 클라이언트 — 경로별 1회 생성 후 재사용."""
    import gspread
    from google.oauth2.service_account import Credentials

    path = resolve_service_account_path(settings.google_service_account_json)
    if path is None:
        raise FileNotFoundError("Google service account JSON not found")
    key = str(path.resolve())
    cached = _GSPREAD_CLIENTS.get(key)
    if cached is not None:
        return cached
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    creds = Credentials.from_service_account_file(str(path), scopes=scopes)
    _GSPREAD_CLIENTS[key] = gspread.authorize(creds)
    return _GSPREAD_CLIENTS[key]


def _compact_signed_fmt(fmt: str | None) -> bool:
    return bool(fmt and fmt.endswith("_compact"))


def _sheet_rule_counts(metadata: dict) -> dict[str, int]:
    counts: dict[str, int] = {}
    for sheet in metadata.get("sheets") or []:
        props = sheet.get("properties") or {}
        title = props.get("title")
        if title:
            counts[str(title)] = len(sheet.get("conditionalFormats") or [])
    return counts


def _delete_conditional_format_requests(sheet_id: int, rule_count: int) -> list[dict]:
    return [
        {"deleteConditionalFormatRule": {"sheetId": sheet_id, "index": idx}}
        for idx in range(rule_count - 1, -1, -1)
    ]


def _header_format_request(sheet_id: int, *, header_rows: int, ncol: int) -> dict:
    return {
        "repeatCell": {
            "range": {
                "sheetId": sheet_id,
                "startRowIndex": 0,
                "endRowIndex": header_rows,
                "startColumnIndex": 0,
                "endColumnIndex": max(ncol, 1),
            },
            "cell": {
                "userEnteredFormat": {
                    "textFormat": {"bold": True, "fontSize": 10},
                    "backgroundColor": {"red": 0.85, "green": 0.92, "blue": 0.98},
                    "horizontalAlignment": "CENTER",
                },
            },
            "fields": (
                "userEnteredFormat.textFormat,"
                "userEnteredFormat.backgroundColor,"
                "userEnteredFormat.horizontalAlignment"
            ),
        },
    }


def _reset_body_text_format_request(
    sheet_id: int, *, start_row: int, end_row: int, ncol: int,
) -> dict | None:
    if end_row <= start_row:
        return None
    return {
        "repeatCell": {
            "range": {
                "sheetId": sheet_id,
                "startRowIndex": start_row,
                "endRowIndex": end_row,
                "startColumnIndex": 0,
                "endColumnIndex": max(ncol, 1),
            },
            "cell": {
                "userEnteredFormat": {
                    "textFormat": {
                        "foregroundColor": {"red": 0.0, "green": 0.0, "blue": 0.0},
                        "bold": False,
                    },
                },
            },
            "fields": "userEnteredFormat.textFormat",
        },
    }


def _signed_conditional_format_requests(
    sheet_id: int,
    columns: list[Column],
    *,
    header_rows: int,
    nrows: int,
) -> list[dict]:
    """손익·수익률 열 — 셀별 repeatCell 대신 열 단위 조건부 서식 (2규칙/열)."""
    from gspread.utils import rowcol_to_a1

    requests: list[dict] = []
    body_rows = max(nrows - header_rows, 0)
    if body_rows <= 0:
        return requests

    for c_idx, (_, _, fmt) in enumerate(columns):
        if fmt not in SIGNED_FORMATS:
            continue
        col = rowcol_to_a1(1, c_idx + 1)[:-1]
        anchor = f"{col}{header_rows + 1}"
        if _compact_signed_fmt(fmt):
            patterns = (("^\\+", COLOR_PROFIT), ("^\\-", COLOR_LOSS))
        else:
            patterns = (("^📈", COLOR_PROFIT), ("^📉", COLOR_LOSS))
        for pattern, color in patterns:
            requests.append({
                "addConditionalFormatRule": {
                    "rule": {
                        "ranges": [{
                            "sheetId": sheet_id,
                            "startRowIndex": header_rows,
                            "endRowIndex": nrows,
                            "startColumnIndex": c_idx,
                            "endColumnIndex": c_idx + 1,
                        }],
                        "booleanRule": {
                            "condition": {
                                "type": "CUSTOM_FORMULA",
                                "values": [{
                                    "userEnteredValue": f'=REGEXMATCH({anchor},"{pattern}")',
                                }],
                            },
                            "format": {
                                "textFormat": {
                                    "foregroundColor": color,
                                    "bold": True,
                                },
                            },
                        },
                    },
                    "index": 0,
                },
            })
    return requests


def _summary_conditional_format_requests(sheet_id: int, *, nrows: int) -> list[dict]:
    """요약 시트 B열 — +/- compact 값만 색상."""
    if nrows <= 1:
        return []
    requests: list[dict] = []
    for pattern, color in (("^\\+", COLOR_PROFIT), ("^\\-", COLOR_LOSS)):
        requests.append({
            "addConditionalFormatRule": {
                "rule": {
                    "ranges": [{
                        "sheetId": sheet_id,
                        "startRowIndex": 1,
                        "endRowIndex": nrows,
                        "startColumnIndex": 1,
                        "endColumnIndex": 2,
                    }],
                    "booleanRule": {
                        "condition": {
                            "type": "CUSTOM_FORMULA",
                            "values": [{
                                "userEnteredValue": f'=REGEXMATCH(B2,"{pattern}")',
                            }],
                        },
                        "format": {
                            "textFormat": {
                                "foregroundColor": color,
                                "bold": True,
                            },
                        },
                    },
                },
                "index": 0,
            },
        })
    return requests


def _summary_layout_requests(
    sheet_id: int, *, nrows: int, section_at: list[int],
) -> list[dict]:
    requests: list[dict] = [
        {
            "updateDimensionProperties": {
                "range": {
                    "sheetId": sheet_id,
                    "dimension": "COLUMNS",
                    "startIndex": 0,
                    "endIndex": 1,
                },
                "properties": {"pixelSize": 88},
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
                "properties": {"pixelSize": 168},
                "fields": "pixelSize",
            },
        },
        {
            "repeatCell": {
                "range": {
                    "sheetId": sheet_id,
                    "startRowIndex": 0,
                    "endRowIndex": max(nrows, 1),
                    "startColumnIndex": 0,
                    "endColumnIndex": 2,
                },
                "cell": {
                    "userEnteredFormat": {
                        "wrapStrategy": "WRAP",
                        "verticalAlignment": "MIDDLE",
                        "textFormat": {"fontSize": 10},
                    },
                },
                "fields": (
                    "userEnteredFormat.wrapStrategy,"
                    "userEnteredFormat.verticalAlignment,"
                    "userEnteredFormat.textFormat.fontSize"
                ),
            },
        },
        {
            "repeatCell": {
                "range": {
                    "sheetId": sheet_id,
                    "startRowIndex": 0,
                    "endRowIndex": 1,
                    "startColumnIndex": 0,
                    "endColumnIndex": 2,
                },
                "cell": {
                    "userEnteredFormat": {
                        "textFormat": {"bold": True, "fontSize": 12},
                        "backgroundColor": {"red": 0.93, "green": 0.94, "blue": 0.97},
                    },
                },
                "fields": "userEnteredFormat.textFormat,userEnteredFormat.backgroundColor",
            },
        },
        {
            "repeatCell": {
                "range": {
                    "sheetId": sheet_id,
                    "startRowIndex": 2,
                    "endRowIndex": 5,
                    "startColumnIndex": 0,
                    "endColumnIndex": 1,
                },
                "cell": {
                    "userEnteredFormat": {
                        "textFormat": {"bold": True, "fontSize": 10},
                    },
                },
                "fields": "userEnteredFormat.textFormat",
            },
        },
        {
            "updateSheetProperties": {
                "properties": {
                    "sheetId": sheet_id,
                    "gridProperties": {"frozenRowCount": 1},
                },
                "fields": "gridProperties.frozenRowCount",
            },
        },
    ]
    for idx in section_at:
        requests.append({
            "repeatCell": {
                "range": {
                    "sheetId": sheet_id,
                    "startRowIndex": idx,
                    "endRowIndex": idx + 1,
                    "startColumnIndex": 0,
                    "endColumnIndex": 2,
                },
                "cell": {
                    "userEnteredFormat": {
                        "textFormat": {"bold": True, "fontSize": 11},
                        "backgroundColor": {"red": 0.85, "green": 0.92, "blue": 0.98},
                    },
                },
                "fields": "userEnteredFormat.textFormat,userEnteredFormat.backgroundColor",
            },
        })
    return requests


def _build_summary_rows(
    app: "App",
    snapshot: dict,
    status_rows: list[dict],
) -> tuple[list[list], list[tuple[int, float | None]], list[int]]:
    """요약 시트 — 2열 세로 (모바일). (rows, signed_row_idx, section_header_rows)."""
    updated = _fmt_when(snapshot.get("updated_at", ""))
    dry = snapshot.get("dry_run")
    mode = "DRY_RUN" if dry else "LIVE"
    bot = "정지" if snapshot.get("paused") else "가동"

    rows: list[list] = [
        ["라오어 무한매수 4.0 — 장부 요약", ""],
        ["", ""],
        ["동기화", updated],
        ["모드", mode],
        ["봇", bot],
        ["", ""],
    ]
    sign_at: list[tuple[int, float | None]] = []
    section_at: list[int] = []

    if not status_rows:
        rows.append(["거래 중인 종목 없음", ""])
        return rows, sign_at, section_at

    for item in status_rows:
        row_item = dict(item)
        if "mode" in item and "mode_label" not in row_item:
            row_item["mode_label"] = mode_label(str(item.get("mode", "")), brief=True)

        sym = str(row_item.get("symbol") or "")
        section_at.append(len(rows))
        rows.append([sym, ""])

        for key, label, fmt in STATUS_COLUMNS:
            if key == "symbol":
                continue
            raw = row_item.get(key)
            rows.append([label, _format_value(raw, fmt)])
            if fmt in SIGNED_FORMATS:
                sign_at.append((len(rows) - 1, _to_float(raw)))

        rows.append(["", ""])

    return rows, sign_at, section_at


class GoogleSheetsLedger:
    def __init__(self, app: "App"):
        self.app = app
        self.settings = app.settings

    @property
    def enabled(self) -> bool:
        return self.settings.has_google_sheets

    def _client(self):
        return _authorize_gspread(self.settings)

    @staticmethod
    def _get_or_add_worksheet(spreadsheet, title: str, rows: int, cols: int):
        import gspread

        try:
            return spreadsheet.worksheet(title)
        except gspread.WorksheetNotFound:
            return spreadsheet.add_worksheet(title=title, rows=max(rows, 10), cols=max(cols, 2))

    def _apply_sheet_formats(
        self,
        spreadsheet,
        ws,
        requests: list[dict],
        *,
        rule_count: int = 0,
    ) -> None:
        if not requests and rule_count <= 0:
            return
        batch = _delete_conditional_format_requests(ws.id, rule_count) + requests
        try:
            spreadsheet.batch_update({"requests": batch})
        except Exception:
            logger.debug("sheet format batch skipped", exc_info=True)

    def _write_summary_tab(
        self,
        spreadsheet,
        snapshot: dict,
        status_rows: list[dict],
        *,
        rule_count: int = 0,
    ) -> None:
        rows, _sign_at, section_at = _build_summary_rows(
            self.app, snapshot, status_rows,
        )
        ws = self._get_or_add_worksheet(spreadsheet, TAB_SUMMARY, len(rows) + 5, 2)
        ws.clear()
        ws.update(values=rows, range_name="A1", value_input_option="USER_ENTERED")
        reset = _reset_body_text_format_request(
            ws.id, start_row=1, end_row=len(rows), ncol=2,
        )
        format_requests = _summary_layout_requests(
            ws.id, nrows=len(rows), section_at=section_at,
        )
        format_requests.extend(_summary_conditional_format_requests(ws.id, nrows=len(rows)))
        if reset:
            format_requests.insert(0, reset)
        self._apply_sheet_formats(spreadsheet, ws, format_requests, rule_count=rule_count)

    def _write_table_tab(
        self,
        spreadsheet,
        title: str,
        items: list[dict],
        columns: list[Column],
        *,
        rule_count: int = 0,
    ) -> None:
        if not items:
            self._write_tab(spreadsheet, title, [["⚠️ 데이터 없음", ""]], rule_count=rule_count)
            return
        rows, _sign_grid = _rows_table(items, columns)
        ncol = max(len(r) for r in rows)
        ws = self._get_or_add_worksheet(spreadsheet, title, len(rows) + 5, ncol)
        ws.clear()
        ws.update(values=rows, range_name="A1", value_input_option="USER_ENTERED")
        reset = _reset_body_text_format_request(
            ws.id, start_row=1, end_row=len(rows), ncol=ncol,
        )
        format_requests = [
            _header_format_request(ws.id, header_rows=1, ncol=ncol),
            {
                "updateSheetProperties": {
                    "properties": {
                        "sheetId": ws.id,
                        "gridProperties": {"frozenRowCount": 1},
                    },
                    "fields": "gridProperties.frozenRowCount",
                },
            },
        ]
        format_requests.extend(
            _signed_conditional_format_requests(
                ws.id, columns, header_rows=1, nrows=len(rows),
            ),
        )
        if reset:
            format_requests.insert(0, reset)
        self._apply_sheet_formats(spreadsheet, ws, format_requests, rule_count=rule_count)

    def _write_tab(
        self,
        spreadsheet,
        title: str,
        rows: list[list],
        *,
        header_rows: int = 1,
        rule_count: int = 0,
    ) -> None:
        if not rows:
            rows = [["(데이터 없음)", ""]]
        ncol = max(len(r) for r in rows)
        ws = self._get_or_add_worksheet(spreadsheet, title, len(rows) + 5, ncol)
        ws.clear()
        ws.update(values=rows, range_name="A1", value_input_option="USER_ENTERED")
        if not header_rows:
            return
        self._apply_sheet_formats(
            spreadsheet,
            ws,
            [_header_format_request(ws.id, header_rows=header_rows, ncol=ncol)],
            rule_count=rule_count,
        )

    @staticmethod
    def _remove_extra_tabs(spreadsheet) -> None:
        for name in REMOVED_TABS:
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
            metadata = spreadsheet.fetch_sheet_metadata()
            rule_counts = _sheet_rule_counts(metadata)

            self._write_summary_tab(
                spreadsheet, snapshot, status_rows,
                rule_count=rule_counts.get(TAB_SUMMARY, 0),
            )
            self._write_table_tab(
                spreadsheet, TAB_TRADES, trades, TRADES_COLUMNS,
                rule_count=rule_counts.get(TAB_TRADES, 0),
            )
            self._write_table_tab(
                spreadsheet, TAB_CYCLES, cycles, CYCLES_COLUMNS,
                rule_count=rule_counts.get(TAB_CYCLES, 0),
            )
            self._write_table_tab(
                spreadsheet, TAB_MONTHLY, monthly, MONTHLY_COLUMNS,
                rule_count=rule_counts.get(TAB_MONTHLY, 0),
            )
            self._remove_extra_tabs(spreadsheet)

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
