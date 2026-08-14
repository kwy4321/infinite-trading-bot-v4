"""Google Sheets ledger sync — trades, cycles, status, monthly (한글 장부)."""

from __future__ import annotations

import datetime
import logging
import time
from dataclasses import dataclass
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


def _freeze_request(sheet_id: int, header_rows: int) -> dict:
    return {
        "updateSheetProperties": {
            "properties": {
                "sheetId": sheet_id,
                "gridProperties": {"frozenRowCount": max(header_rows, 0)},
            },
            "fields": "gridProperties.frozenRowCount",
        },
    }


@dataclass
class _TabPlan:
    """탭 1개의 최종 값·서식 — 네트워크 호출 전에 로컬에서 모두 만든다."""

    title: str
    values: list[list]
    columns: list[Column] | None = None
    section_at: list[int] | None = None
    header_rows: int = 1

    @property
    def ncol(self) -> int:
        return max((len(r) for r in self.values), default=1)

    @property
    def nrows(self) -> int:
        return len(self.values)


def _sheet_index(metadata: dict) -> dict[str, dict]:
    """탭 이름 → {id, rows, cols, rules}. 메타데이터 1회 조회로 전부 해결한다."""
    index: dict[str, dict] = {}
    for sheet in metadata.get("sheets") or []:
        props = sheet.get("properties") or {}
        title = props.get("title")
        if not title:
            continue
        grid = props.get("gridProperties") or {}
        index[str(title)] = {
            "id": props.get("sheetId"),
            "rows": int(grid.get("rowCount") or 0),
            "cols": int(grid.get("columnCount") or 0),
            "rules": len(sheet.get("conditionalFormats") or []),
        }
    return index


def _structure_requests(
    index: dict[str, dict], plans: list[_TabPlan], removed: tuple[str, ...],
) -> list[dict]:
    """탭 생성·삭제·그리드 확장 — 값 쓰기 전에 한 번의 batch_update 로 처리."""
    requests: list[dict] = []
    for title in removed:
        info = index.get(title)
        if info and info.get("id") is not None:
            requests.append({"deleteSheet": {"sheetId": info["id"]}})

    for plan in plans:
        need_rows = max(plan.nrows + 5, 10)
        need_cols = max(plan.ncol, 2)
        info = index.get(plan.title)
        if info is None:
            requests.append({
                "addSheet": {
                    "properties": {
                        "title": plan.title,
                        "gridProperties": {
                            "rowCount": need_rows,
                            "columnCount": need_cols,
                        },
                    },
                },
            })
            continue
        if info["rows"] < need_rows or info["cols"] < need_cols:
            requests.append({
                "updateSheetProperties": {
                    "properties": {
                        "sheetId": info["id"],
                        "gridProperties": {
                            "rowCount": max(info["rows"], need_rows),
                            "columnCount": max(info["cols"], need_cols),
                        },
                    },
                    "fields": "gridProperties.rowCount,gridProperties.columnCount",
                },
            })
    return requests


def _index_added_sheets(index: dict[str, dict], replies: list | None) -> None:
    """addSheet 응답의 새 sheetId 반영 — 추가 조회 없이 서식까지 이어서 보낸다."""
    for reply in replies or []:
        props = ((reply or {}).get("addSheet") or {}).get("properties") or {}
        title = props.get("title")
        if not title:
            continue
        grid = props.get("gridProperties") or {}
        index[str(title)] = {
            "id": props.get("sheetId"),
            "rows": int(grid.get("rowCount") or 0),
            "cols": int(grid.get("columnCount") or 0),
            "rules": 0,
        }


def _tab_format_requests(plan: _TabPlan, sheet_id: int, rule_count: int) -> list[dict]:
    """탭 1개의 서식 요청 — 모든 탭 분을 모아 batch_update 한 번에 보낸다."""
    requests = _delete_conditional_format_requests(sheet_id, rule_count)
    reset = _reset_body_text_format_request(
        sheet_id, start_row=plan.header_rows, end_row=plan.nrows, ncol=plan.ncol,
    )
    if reset:
        requests.append(reset)

    if plan.section_at is not None:
        requests.extend(
            _summary_layout_requests(
                sheet_id, nrows=plan.nrows, section_at=plan.section_at,
            ),
        )
        requests.extend(
            _summary_conditional_format_requests(sheet_id, nrows=plan.nrows),
        )
        return requests

    requests.append(
        _header_format_request(sheet_id, header_rows=plan.header_rows, ncol=plan.ncol),
    )
    requests.append(_freeze_request(sheet_id, plan.header_rows))
    if plan.columns:
        requests.extend(
            _signed_conditional_format_requests(
                sheet_id, plan.columns,
                header_rows=plan.header_rows, nrows=plan.nrows,
            ),
        )
    return requests


def _table_plan(title: str, items: list[dict], columns: list[Column]) -> _TabPlan:
    if not items:
        return _TabPlan(title=title, values=[["⚠️ 데이터 없음", ""]])
    rows, _sign_grid = _rows_table(items, columns)
    ncol = max(len(r) for r in rows)
    return _TabPlan(title=title, values=_pad_rows(rows, ncol), columns=columns)


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

    def _build_plans(
        self,
        snapshot: dict,
        status_rows: list[dict],
        trades: list[dict],
        cycles: list[dict],
        monthly: list[dict],
    ) -> list[_TabPlan]:
        summary_rows, _sign_at, section_at = _build_summary_rows(
            self.app, snapshot, status_rows,
        )
        return [
            _TabPlan(
                title=TAB_SUMMARY,
                values=_pad_rows(summary_rows, 2),
                section_at=section_at,
            ),
            _table_plan(TAB_TRADES, trades, TRADES_COLUMNS),
            _table_plan(TAB_CYCLES, cycles, CYCLES_COLUMNS),
            _table_plan(TAB_MONTHLY, monthly, MONTHLY_COLUMNS),
        ]

    @staticmethod
    def _push_plans(spreadsheet, plans: list[_TabPlan]) -> int:
        """탭 전체를 배치로 반영. 반환값은 소비한 API 왕복 횟수."""
        calls = 1
        index = _sheet_index(spreadsheet.fetch_sheet_metadata())

        structure = _structure_requests(index, plans, REMOVED_TABS)
        if structure:
            replies = (spreadsheet.batch_update({"requests": structure}) or {}).get("replies")
            _index_added_sheets(index, replies)
            for title in REMOVED_TABS:
                index.pop(title, None)
            calls += 1

        spreadsheet.values_batch_clear(
            body={"ranges": [f"'{p.title}'" for p in plans]},
        )
        spreadsheet.values_batch_update(body={
            "valueInputOption": "USER_ENTERED",
            "data": [
                {"range": f"'{p.title}'!A1", "values": p.values}
                for p in plans
            ],
        })
        calls += 2

        format_requests: list[dict] = []
        for plan in plans:
            info = index.get(plan.title) or {}
            sheet_id = info.get("id")
            if sheet_id is None:
                continue
            format_requests.extend(
                _tab_format_requests(plan, sheet_id, int(info.get("rules") or 0)),
            )
        if format_requests:
            spreadsheet.batch_update({"requests": format_requests})
            calls += 1
        return calls

    def sync_all(self, *, rebuild_broker: bool = True) -> dict:
        if not self.enabled:
            return {"ok": False, "message": "Google Sheets 비활성 (GOOGLE_SHEETS_ENABLED/ID/JSON 확인)"}

        try:
            started = time.monotonic()
            prep = prepare_ledger_for_export(self.app, rebuild_broker=rebuild_broker)
            after_prep = time.monotonic()

            snapshot = collect_portfolio_snapshot(self.app, fetch_live_price=False)
            trades = collect_sheet_trades(self.app)
            cycles = collect_completed_cycles(self.app)
            monthly = collect_monthly_rows(self.app)
            sources = ledger_data_sources(self.app)
            status_rows = collect_sheet_symbol_status(self.app)
            plans = self._build_plans(snapshot, status_rows, trades, cycles, monthly)
            after_collect = time.monotonic()

            sid = self.settings.resolved_spreadsheet_id
            if not sid:
                return {"ok": False, "message": "GOOGLE_SPREADSHEET_ID 또는 GOOGLE_SHEETS_URL 확인"}
            spreadsheet = self._client().open_by_key(sid)
            api_calls = self._push_plans(spreadsheet, plans)
            after_push = time.monotonic()

            timing = {
                "prep_sec": round(after_prep - started, 2),
                "collect_sec": round(after_collect - after_prep, 2),
                "sheets_sec": round(after_push - after_collect, 2),
                "total_sec": round(after_push - started, 2),
                "api_calls": api_calls,
            }

            msg = f"Sheets 동기화 완료 — 매매 {len(trades)}건 · 완료회차 {len(cycles)}건"
            if len(trades) == 0 and len(cycles) == 0:
                msg += (
                    f" (장부 0건 — {sources['data_dir']} 확인 · "
                    f"fill_log={sum(s['fill_log'] for s in sources['symbols'].values())} · "
                    "/sync 후 /sheets_sync)"
                )
            elif prep.get("broker_symbols"):
                msg += f" · 토스체결 {','.join(prep['broker_symbols'])} 반영"
            msg += f" · {timing['total_sec']}초"

            logger.info(
                "%s (준비 %.2fs · 수집 %.2fs · 시트 %.2fs · API %d회)",
                msg, timing["prep_sec"], timing["collect_sec"],
                timing["sheets_sec"], api_calls,
            )
            return {
                "ok": True,
                "message": msg,
                "trades": len(trades),
                "cycles": len(cycles),
                "prep": prep,
                "sources": sources,
                "timing": timing,
            }
        except Exception as exc:
            logger.exception("google sheets sync failed")
            return {"ok": False, "message": f"Sheets 동기화 실패: {exc}"}

    def sheets_url(self) -> str:
        return self.settings.google_sheets_link


def sync_ledger(app: "App", *, rebuild_broker: bool = True) -> dict:
    return GoogleSheetsLedger(app).sync_all(rebuild_broker=rebuild_broker)
