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

STATUS_COLUMNS: list[Column] = [
    ("symbol", "종목", None),
    ("active", "거래종목", "_fmt_yesno"),
    ("mode_label", "전략모드", None),
    ("T", "T값", "_fmt_num2"),
    ("split_count", "분할", None),
    ("principal", "원금($)", "_fmt_usd"),
    ("qty", "보유수량", None),
    ("avg_price", "평단($)", "_fmt_usd"),
    ("current_price", "현재가($)", "_fmt_usd"),
    ("eval_usd", "평가($)", "_fmt_usd"),
    ("cycle_no", "회차", None),
    ("cycle_started_at", "회차시작", "_fmt_when"),
    ("cycle_pnl_usd", "회차손익($)", "_fmt_usd_signed"),
    ("cycle_pnl_pct", "회차수익률", "_fmt_pct"),
    ("take_profit_pct", "목표수익률", "_fmt_pct_plain"),
    ("reverse_mode", "리버스", "_fmt_onoff"),
    ("force_one", "강제1회", "_fmt_onoff"),
]

TRADES_COLUMNS: list[Column] = [
    ("seq", "연번", None),
    ("date", "날짜", None),
    ("symbol", "종목", None),
    ("t_change", "T값 변동", None),
    ("side", "매매", "_fmt_side"),
    ("price", "체결가($)", "_fmt_usd"),
    ("qty", "수량(주)", None),
    ("amount_usd", "총금액($)", "_fmt_usd"),
    ("pnl_usd", "손익($)", "_fmt_pnl"),
    ("cycle_no", "회차", None),
    ("cycle_status", "회차상태", None),
    ("datetime", "체결시각", "_fmt_when"),
    ("source", "출처", "_fmt_source"),
]

CYCLES_COLUMNS: list[Column] = [
    ("symbol", "종목", None),
    ("cycle_no", "회차", None),
    ("started_at", "시작", "_fmt_when"),
    ("ended_at", "종료", "_fmt_when"),
    ("principal", "원금($)", "_fmt_usd"),
    ("total_buy_usd", "매수합($)", "_fmt_usd"),
    ("total_sell_usd", "매도합($)", "_fmt_usd"),
    ("profit_usd", "실현손익($)", "_fmt_usd_signed"),
    ("profit_pct", "수익률", "_fmt_pct"),
    ("max_T", "최고T", "_fmt_num2"),
    ("buy_count", "매수횟수", None),
    ("sell_count", "매도횟수", None),
]

MONTHLY_COLUMNS: list[Column] = [
    ("year", "연도", None),
    ("month", "월", None),
    ("scope", "구분", None),
    ("cycles", "완료회차", None),
    ("profit_usd", "실현손익($)", "_fmt_usd_signed"),
    ("profit_pct_on_buy", "수익률(매수대비)", "_fmt_pct"),
]


def _fmt_usd(v: Any) -> str:
    try:
        return f"${float(v):,.2f}"
    except (TypeError, ValueError):
        return str(v or "")


def _fmt_usd_signed(v: Any) -> str:
    try:
        n = float(v)
        sign = "+" if n > 0 else ""
        return f"{sign}${n:,.2f}"
    except (TypeError, ValueError):
        return str(v or "")


def _fmt_pct(v: Any) -> str:
    try:
        n = float(v)
        sign = "+" if n > 0 else ""
        return f"{sign}{n:.2f}%"
    except (TypeError, ValueError):
        return str(v or "")


def _fmt_pct_plain(v: Any) -> str:
    try:
        return f"{float(v):g}%"
    except (TypeError, ValueError):
        return str(v or "")


def _fmt_num2(v: Any) -> str:
    try:
        return f"{float(v):.2f}"
    except (TypeError, ValueError):
        return str(v or "")


def _fmt_side(v: Any) -> str:
    s = str(v or "").upper()
    return {"BUY": "매수", "SELL": "매도"}.get(s, s or "")


def _fmt_yesno(v: Any) -> str:
    return "예" if v in (True, "true", "True", 1, "1") else "아니오"


def _fmt_onoff(v: Any) -> str:
    return "ON" if v in (True, "true", "True", 1, "1") else "OFF"


def _fmt_pnl(v: Any) -> str:
    if v is None or v == "":
        return "—"
    return _fmt_usd_signed(v)


def _fmt_source(v: Any) -> str:
    s = str(v or "").lower()
    return {"broker": "토스증권", "sync": "동기화", "fill_log": "체결로그"}.get(s, s or "—")


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


def _rows_table(items: list[dict], columns: list[Column]) -> list[list]:
    headers = [label for _, label, _ in columns]
    body = []
    for item in items:
        row_item = dict(item)
        if "mode" in item and "mode_label" not in row_item:
            row_item["mode_label"] = mode_label(str(item.get("mode", "")), brief=True)
        body.append([
            _format_value(row_item.get(key), fmt)
            for key, _, fmt in columns
        ])
    return [headers, *body]


def _rows_summary(snapshot: dict) -> list[list]:
    acc = snapshot.get("account") or {}
    updated = _fmt_when(snapshot.get("updated_at", ""))
    dry = snapshot.get("dry_run")
    mode = "DRY_RUN (모의)" if dry else "LIVE (실거래)"
    bot = "⏸ 정지" if snapshot.get("paused") else "▶️ 가동"

    rows: list[list] = [
        ["라오어 무한매수 4.0 — 장부 요약", ""],
        ["", ""],
        ["항목", "값"],
        ["마지막 동기화", updated],
        ["운영 모드", mode],
        ["봇 상태", bot],
        ["", ""],
        ["── 계좌 ──", ""],
        ["달러 예수금", _fmt_usd(acc.get("cash_usd", 0))],
        ["총 자산(USD)", _fmt_usd(acc.get("total_usd", 0))],
        ["총 자산(KRW)", f"₩{float(acc.get('total_krw') or 0):,.0f}"],
        ["평가손익", _fmt_usd_signed(acc.get("unreal_usd", 0))],
        ["평가수익률", _fmt_pct(acc.get("unreal_pct")) if acc.get("unreal_pct") not in (None, "") else ""],
        ["환율", f"{float(acc.get('fx_rate') or 0):,.2f} KRW/USD" if acc.get("fx_rate") else ""],
        ["", ""],
        ["── 누적 ──", ""],
        ["실현수익(완료회차)", _fmt_usd_signed(snapshot.get("realized_usd", 0))],
        ["완료 회차 수", snapshot.get("completed_cycles", 0)],
        ["진행 중 회차", snapshot.get("active_cycles", 0)],
    ]
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
        if summary_title and len(rows) >= 3:
            try:
                ws.format("A1", {"textFormat": {"bold": True, "fontSize": 14}})
                ws.format("A3:B3", {
                    "textFormat": {"bold": True},
                    "backgroundColor": {"red": 0.85, "green": 0.92, "blue": 0.98},
                })
                ws.freeze(rows=3)
            except Exception:
                pass
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

            status_rows = []
            for sym in snapshot.get("symbols") or []:
                row = dict(sym)
                row["mode_label"] = mode_label(str(sym.get("mode", "")), brief=True)
                status_rows.append(row)

            client = self._client()
            sid = self.settings.resolved_spreadsheet_id
            if not sid:
                return {"ok": False, "message": "GOOGLE_SPREADSHEET_ID 또는 GOOGLE_SHEETS_URL 확인"}
            spreadsheet = client.open_by_key(sid)

            self._write_tab(
                spreadsheet, TAB_SUMMARY, _rows_summary(snapshot),
                summary_title=True,
            )
            self._write_tab(
                spreadsheet, TAB_STATUS, _rows_table(status_rows, STATUS_COLUMNS),
            )
            self._write_tab(
                spreadsheet, TAB_TRADES, _rows_table(trades, TRADES_COLUMNS),
            )
            self._write_tab(
                spreadsheet, TAB_CYCLES, _rows_table(cycles, CYCLES_COLUMNS),
            )
            self._write_tab(
                spreadsheet, TAB_MONTHLY, _rows_table(monthly, MONTHLY_COLUMNS),
            )
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
