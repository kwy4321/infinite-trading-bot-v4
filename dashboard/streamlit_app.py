"""Streamlit dashboard — 현황·장부 (read-only)."""

from __future__ import annotations

import datetime
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd
import streamlit as st

from app import App
from config.settings import SYMBOLS, get_settings
from reporting.dashboard_data import (
    collect_all_trades,
    collect_completed_cycles,
    collect_monthly_rows,
    collect_portfolio_snapshot,
    collect_symbol_status,
)


@st.cache_resource
def get_app() -> App:
    return App.create()


def _check_auth(settings) -> bool:
    pwd = (settings.streamlit_password or "").strip()
    if not pwd:
        return True
    if st.session_state.get("authed"):
        return True
    with st.form("login"):
        st.subheader("로그인")
        entered = st.text_input("비밀번호", type="password")
        if st.form_submit_button("입장"):
            if entered == pwd:
                st.session_state["authed"] = True
                st.rerun()
            else:
                st.error("비밀번호가 올바르지 않습니다.")
    return False


def main() -> None:
    settings = get_settings()
    st.set_page_config(
        page_title="라오어 무한매수 4.0",
        page_icon="♾️",
        layout="wide",
    )
    if not _check_auth(settings):
        st.stop()

    app = get_app()
    st.title("♾️ 라오어 무한매수 4.0 — 현황 대시보드")

    if st.button("🔄 새로고침"):
        st.cache_resource.clear()
        st.rerun()

    snapshot = collect_portfolio_snapshot(app)
    acc = snapshot["account"]
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("총자산 (USD)", f"${acc.get('total_usd', 0):,.2f}")
    c2.metric("평가손익", f"${acc.get('unreal_usd', 0):+,.2f}")
    c3.metric("실현수익", f"${snapshot.get('realized_usd', 0):+,.2f}")
    c4.metric("진행 회차", str(snapshot.get("active_cycles", 0)))

    st.caption(
        f"갱신: {snapshot['updated_at']} · "
        f"{'🧪 DRY' if snapshot['dry_run'] else '🟢 LIVE'} · "
        f"{'⏸️ 정지' if snapshot['paused'] else '▶️ 운영'}"
    )

    if settings.has_google_sheets:
        sheets_url = settings.google_sheets_url or (
            f"https://docs.google.com/spreadsheets/d/{settings.google_spreadsheet_id}"
        )
        st.link_button("📗 Google Sheets 장부 열기", sheets_url)

    st.divider()
    st.subheader("종목 현황")
    status_df = pd.DataFrame(snapshot["symbols"])
    if not status_df.empty:
        show_cols = [
            "symbol", "mode_label", "T", "split_count", "qty", "avg_price",
            "current_price", "cycle_no", "cycle_pnl_usd", "cycle_pnl_pct",
            "reverse_mode", "force_one",
        ]
        st.dataframe(status_df[[c for c in show_cols if c in status_df.columns]], use_container_width=True)

    tab_trades, tab_cycles, tab_monthly = st.tabs(["매매 내역", "완료 회차", "월별 수익"])
    with tab_trades:
        trades = collect_all_trades(app)
        if trades:
            tdf = pd.DataFrame(trades)
            sym_filter = st.multiselect("종목", SYMBOLS, default=list(SYMBOLS))
            if sym_filter:
                tdf = tdf[tdf["symbol"].isin(sym_filter)]
            st.dataframe(tdf, use_container_width=True, height=420)
        else:
            st.info("매매 내역이 없습니다.")

    with tab_cycles:
        cycles = collect_completed_cycles(app)
        if cycles:
            st.dataframe(pd.DataFrame(cycles), use_container_width=True)
        else:
            st.info("완료된 회차가 없습니다.")

    with tab_monthly:
        year = st.number_input("연도", min_value=2020, max_value=2100, value=datetime.date.today().year)
        monthly = collect_monthly_rows(app, int(year))
        if monthly:
            mdf = pd.DataFrame(monthly)
            st.dataframe(mdf, use_container_width=True)
        else:
            st.info("해당 연도 월별 기록이 없습니다.")

    with st.expander("종목 상세"):
        sym = st.selectbox("종목 선택", SYMBOLS)
        detail = collect_symbol_status(app, sym)
        st.json(detail)


if __name__ == "__main__":
    main()
