"""KST 기준 자동 LOC 접수 스케줄 — 구현은 core.clock 에 있다 (하위 호환 재노출)."""

from __future__ import annotations

from core.clock import KST, LOC_SUBMIT_HHMM, loc_auto_submit_kst

__all__ = ["KST", "LOC_SUBMIT_HHMM", "loc_auto_submit_kst", "regular_open_kst"]


def regular_open_kst(us_date: str):
    """하위 호환 별칭."""
    return loc_auto_submit_kst(us_date)
