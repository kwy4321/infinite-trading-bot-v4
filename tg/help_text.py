"""Telegram command help — single source of truth."""

HELP_MESSAGE = """\
🖥️ <b>라오어 무한매수 4.0</b>

<b>📊 현황</b>
/dashboard — 전체 요약 (포지션·회차)
/status — 봇·계좌 (예수금)
/balance — Toss API 계좌 잔고
/plan [종목] — 오늘 T 기준 주문 계획
/sync [종목] — API 수량·평단 → 기록 반영

<b>⚙️ 설정</b>
/setting — 원금·예수금·분할
/split — 액면분할
/set_t &lt;값&gt; [종목] — T 수동 조정

<b>📒 기록</b>
/cycles [종목] — 회차 기록 (종목 생략 시 선택)
/monthly [종목] [연도] — 월별 수익
/history [종목] — 졸업 기록
/cycle_done [종목] — 수동 졸업

<b>🔧 운영</b>
/pause /resume — 자동 Job 정지·재개
/run — Job 수동 실행 (익절·매수 등)
"""
