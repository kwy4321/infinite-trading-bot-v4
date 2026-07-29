"""Google Sheets ledger sync — trades, cycles, status, monthly."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

from config.settings import ROOT
from reporting.dashboard_data import (
    collect_all_trades,
    collect_completed_cycles,
    collect_monthly_rows,
    collect_portfolio_snapshot,
)

if TYPE_CHECKING:
    from app import App

logger = logging.getLogger(__name__)

STATUS_HEADERS = [
    "updated_at", "symbol", "active", "mode", "T", "split_count", "principal",
    "qty", "avg_price", "current_price", "eval_usd", "cycle_no", "cycle_started_at",
    "cycle_pnl_usd", "cycle_pnl_pct", "force_one", "reverse_mode", "take_profit_pct",
]
TRADES_HEADERS = [
    "symbol", "cycle_no", "cycle_status", "date", "datetime", "side", "qty", "price",
    "amount_usd", "action", "t_before", "t_after", "avg_after", "qty_after", "source",
    "order_id", "note",
]
CYCLES_HEADERS = [
    "symbol", "cycle_no", "started_at", "ended_at", "principal", "total_buy_usd",
    "total_sell_usd", "profit_usd", "profit_pct", "max_T", "buy_count", "sell_count",
]
MONTHLY_HEADERS = [
    "year", "month", "scope", "cycles", "profit_usd", "profit_pct_on_buy",
]
DASHBOARD_HEADERS = [
    "updated_at", "dry_run", "paused", "cash_usd", "total_usd", "total_krw",
    "unreal_usd", "unreal_pct", "fx_rate", "realized_usd", "completed_cycles", "active_cycles",
]


def _resolve_json_path(raw: str) -> Path:
    path = Path(raw)
    if path.is_file():
        return path
    candidate = ROOT / raw
    if candidate.is_file():
        return candidate
    raise FileNotFoundError(
        f"Service account JSON not found: {raw} (also tried {candidate})"
    )


def _cell(value: Any) -> str | int | float:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    return value


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

        path = _resolve_json_path(self.settings.google_service_account_json)
        scopes = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive",
        ]
        creds = Credentials.from_service_account_file(str(path), scopes=scopes)
        return gspread.authorize(creds)

    @staticmethod
    def _rows_from_dicts(items: list[dict], headers: list[str]) -> list[list]:
        return [
            headers,
            *[[_cell(item.get(h, "")) for h in headers] for item in items],
        ]

    @staticmethod
    def _write_tab(spreadsheet, title: str, rows: list[list]) -> None:
        try:
            ws = spreadsheet.worksheet(title)
        except Exception:
            cols = max(len(rows[0]) if rows else 1, 1)
            ws = spreadsheet.add_worksheet(
                title=title,
                rows=max(len(rows), 2),
                cols=cols,
            )
        ws.clear()
        if rows:
            ws.update(
                values=rows,
                range_name="A1",
                value_input_option="USER_ENTERED",
            )

    def sync_all(self) -> dict:
        if not self.enabled:
            return {"ok": False, "message": "Google Sheets 비활성 (GOOGLE_SHEETS_ENABLED/ID/JSON 확인)"}

        try:
            snapshot = collect_portfolio_snapshot(self.app, fetch_live_price=False)
            trades = collect_all_trades(self.app)
            cycles = collect_completed_cycles(self.app)
            monthly = collect_monthly_rows(self.app)

            acc = snapshot["account"]
            dashboard_row = [{
                "updated_at": snapshot["updated_at"],
                "dry_run": snapshot["dry_run"],
                "paused": snapshot["paused"],
                "cash_usd": acc.get("cash_usd", 0),
                "total_usd": acc.get("total_usd", 0),
                "total_krw": acc.get("total_krw", 0),
                "unreal_usd": acc.get("unreal_usd", 0),
                "unreal_pct": acc.get("unreal_pct", ""),
                "fx_rate": acc.get("fx_rate", 0),
                "realized_usd": snapshot.get("realized_usd", 0),
                "completed_cycles": snapshot.get("completed_cycles", 0),
                "active_cycles": snapshot.get("active_cycles", 0),
            }]

            client = self._client()
            spreadsheet = client.open_by_key(self.settings.google_spreadsheet_id)
            self._write_tab(
                spreadsheet, "Dashboard",
                self._rows_from_dicts(dashboard_row, DASHBOARD_HEADERS),
            )
            self._write_tab(
                spreadsheet, "Status",
                self._rows_from_dicts(snapshot["symbols"], STATUS_HEADERS),
            )
            self._write_tab(
                spreadsheet, "Trades",
                self._rows_from_dicts(trades, TRADES_HEADERS),
            )
            self._write_tab(
                spreadsheet, "Cycles",
                self._rows_from_dicts(cycles, CYCLES_HEADERS),
            )
            self._write_tab(
                spreadsheet, "Monthly",
                self._rows_from_dicts(monthly, MONTHLY_HEADERS),
            )

            msg = f"Sheets 동기화 완료 — 매매 {len(trades)}건 · 완료회차 {len(cycles)}건"
            logger.info(msg)
            return {
                "ok": True,
                "message": msg,
                "trades": len(trades),
                "cycles": len(cycles),
            }
        except Exception as exc:
            logger.exception("google sheets sync failed")
            return {"ok": False, "message": f"Sheets 동기화 실패: {exc}"}

    def sheets_url(self) -> str:
        if self.settings.google_sheets_url:
            return self.settings.google_sheets_url
        sid = self.settings.google_spreadsheet_id
        if sid:
            return f"https://docs.google.com/spreadsheets/d/{sid}"
        return ""


def sync_ledger(app: "App") -> dict:
    return GoogleSheetsLedger(app).sync_all()
