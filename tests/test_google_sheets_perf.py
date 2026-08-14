"""Google Sheets sync — 왕복 호출 수·조건부 서식 (속도 회귀 방지)."""

from __future__ import annotations

import pytest

from integrations.google_sheets import (
    CYCLES_COLUMNS,
    MONTHLY_COLUMNS,
    REMOVED_TABS,
    TAB_CYCLES,
    TAB_MONTHLY,
    TAB_SUMMARY,
    TAB_TRADES,
    TRADES_COLUMNS,
    GoogleSheetsLedger,
    _delete_conditional_format_requests,
    _index_added_sheets,
    _sheet_index,
    _signed_conditional_format_requests,
    _structure_requests,
    _table_plan,
    _TabPlan,
)

TARGET_TABS = (TAB_SUMMARY, TAB_TRADES, TAB_CYCLES, TAB_MONTHLY)


class FakeSpreadsheet:
    """gspread Spreadsheet 최소 흉내 — 호출 1건 = API 왕복 1회."""

    def __init__(self, titles=TARGET_TABS, rows=20000, cols=26, rules=0):
        self.calls: list[str] = []
        self.batches: list[dict] = []
        self._meta = {
            "sheets": [
                {
                    "properties": {
                        "title": t,
                        "sheetId": 100 + i,
                        "gridProperties": {"rowCount": rows, "columnCount": cols},
                    },
                    "conditionalFormats": [{} for _ in range(rules)],
                }
                for i, t in enumerate(titles)
            ],
        }

    def fetch_sheet_metadata(self):
        self.calls.append("fetch_sheet_metadata")
        return self._meta

    def batch_update(self, body):
        self.calls.append("batch_update")
        self.batches.append(body)
        replies = []
        for req in body.get("requests", []):
            if "addSheet" in req:
                props = dict(req["addSheet"]["properties"])
                props.setdefault("sheetId", 900 + len(replies))
                replies.append({"addSheet": {"properties": props}})
            else:
                replies.append({})
        return {"replies": replies}

    def values_batch_clear(self, body):
        self.calls.append("values_batch_clear")
        self.last_clear = body

    def values_batch_update(self, body):
        self.calls.append("values_batch_update")
        self.last_values = body

    def worksheet(self, title):
        raise AssertionError("worksheet() 는 왕복 1회를 더 쓰므로 쓰면 안 된다")


def _plans(n_trades: int = 3) -> list[_TabPlan]:
    trades = [
        {
            "seq": i, "symbol": "TQQQ", "side": "SELL", "price": 10.0,
            "qty": 1, "amount_usd": 10.0, "pnl_usd": -1.0 * i,
        }
        for i in range(1, n_trades + 1)
    ]
    return [
        _TabPlan(title=TAB_SUMMARY, values=[["요약", ""], ["모드", "LIVE"]], section_at=[]),
        _table_plan(TAB_TRADES, trades, TRADES_COLUMNS),
        _table_plan(TAB_CYCLES, [], CYCLES_COLUMNS),
        _table_plan(TAB_MONTHLY, [], MONTHLY_COLUMNS),
    ]


@pytest.mark.parametrize("n_trades", [3, 5000])
def test_push_uses_constant_api_calls_regardless_of_row_count(n_trades):
    """데이터가 늘어도 왕복 횟수는 그대로 — 페이로드만 커진다."""
    sheet = FakeSpreadsheet()
    calls = GoogleSheetsLedger._push_plans(sheet, _plans(n_trades))

    assert calls <= 4
    assert sheet.calls == [
        "fetch_sheet_metadata",
        "values_batch_clear",
        "values_batch_update",
        "batch_update",
    ]


def test_push_writes_every_tab_in_one_values_call():
    sheet = FakeSpreadsheet()
    GoogleSheetsLedger._push_plans(sheet, _plans())

    ranges = [d["range"] for d in sheet.last_values["data"]]
    assert ranges == [f"'{t}'!A1" for t in TARGET_TABS]
    assert sheet.last_values["valueInputOption"] == "USER_ENTERED"
    assert sheet.last_clear["ranges"] == [f"'{t}'" for t in TARGET_TABS]


def test_push_creates_missing_tabs_and_drops_legacy_tabs():
    sheet = FakeSpreadsheet(titles=(TAB_SUMMARY, "종목현황"))
    calls = GoogleSheetsLedger._push_plans(sheet, _plans())

    # metadata + 구조(생성·삭제) + clear + values + 서식
    assert calls == 5
    assert sheet.calls.count("batch_update") == 2

    kinds = [next(iter(r)) for r in sheet.batches[0]["requests"]]
    assert kinds.count("deleteSheet") == 1  # 종목현황
    assert kinds.count("addSheet") == 3  # 매매내역·완료회차·월별수익


def test_structure_requests_add_delete_and_grow():
    index = _sheet_index(FakeSpreadsheet(titles=(TAB_TRADES, "Dashboard"), rows=5, cols=2)._meta)
    plans = _plans()
    reqs = _structure_requests(index, plans, REMOVED_TABS)

    kinds = [next(iter(r)) for r in reqs]
    assert "deleteSheet" in kinds  # Dashboard 는 REMOVED_TABS
    assert kinds.count("addSheet") == 3  # 요약·완료회차·월별수익
    assert "updateSheetProperties" in kinds  # 매매내역 그리드 확장


def test_index_added_sheets_registers_new_ids():
    index: dict[str, dict] = {}
    _index_added_sheets(index, [{
        "addSheet": {
            "properties": {
                "title": TAB_TRADES,
                "sheetId": 77,
                "gridProperties": {"rowCount": 20, "columnCount": 13},
            },
        },
    }])
    assert index[TAB_TRADES] == {"id": 77, "rows": 20, "cols": 13, "rules": 0}


def test_signed_conditional_rules_scale_with_columns_not_rows():
    """1000행이어도 repeatCell 수백 개가 아니라 열당 2규칙만."""
    reqs = _signed_conditional_format_requests(
        99, TRADES_COLUMNS, header_rows=1, nrows=1001,
    )
    signed_cols = sum(1 for *_, fmt in TRADES_COLUMNS if fmt in {
        "_fmt_usd_signed", "_fmt_pct", "_fmt_pnl",
        "_fmt_usd_signed_compact", "_fmt_pct_compact",
    })
    assert len(reqs) == signed_cols * 2
    assert all("addConditionalFormatRule" in r for r in reqs)
    assert not any("repeatCell" in r for r in reqs)


def test_cycles_tab_few_conditional_rules():
    reqs = _signed_conditional_format_requests(
        1, CYCLES_COLUMNS, header_rows=1, nrows=50,
    )
    assert len(reqs) == 4  # profit_usd + profit_pct × 2 rules each


def test_delete_conditional_rules_reverse_order():
    reqs = _delete_conditional_format_requests(7, 3)
    assert reqs == [
        {"deleteConditionalFormatRule": {"sheetId": 7, "index": 2}},
        {"deleteConditionalFormatRule": {"sheetId": 7, "index": 1}},
        {"deleteConditionalFormatRule": {"sheetId": 7, "index": 0}},
    ]


def test_sheet_index_reads_ids_grid_and_rules():
    index = _sheet_index(FakeSpreadsheet(titles=(TAB_TRADES,), rows=42, cols=13, rules=2)._meta)
    assert index[TAB_TRADES] == {"id": 100, "rows": 42, "cols": 13, "rules": 2}


def test_stale_conditional_rules_are_dropped_before_reapply():
    sheet = FakeSpreadsheet(rules=2)
    GoogleSheetsLedger._push_plans(sheet, _plans())

    deletes = [r for r in sheet.batches[-1]["requests"] if "deleteConditionalFormatRule" in r]
    assert len(deletes) == 2 * len(TARGET_TABS)
