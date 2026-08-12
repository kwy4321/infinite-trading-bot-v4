"""Google Sheets sync — format batching / conditional rules (perf guards)."""

from integrations.google_sheets import (
    CYCLES_COLUMNS,
    TRADES_COLUMNS,
    _delete_conditional_format_requests,
    _sheet_rule_counts,
    _signed_conditional_format_requests,
)


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


def test_sheet_rule_counts_by_title():
    meta = {
        "sheets": [
            {
                "properties": {"title": "매매내역", "sheetId": 10},
                "conditionalFormats": [{}, {}],
            },
            {"properties": {"title": "요약", "sheetId": 11}, "conditionalFormats": []},
        ],
    }
    assert _sheet_rule_counts(meta) == {"매매내역": 2, "요약": 0}
