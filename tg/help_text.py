"""Telegram command help — single source of truth."""

HELP_MESSAGE = """\
<b>📊 현황</b>
/status — 진행상황 (봇·회차·T·전략)
/balance — 계좌현황 (예수금·보유·평단·평가)
/plan — 오늘의 주문계획

<b>⚙️ 설정</b>
/setting — 원금·예수금·분할
/sync [종목] — API 수량·평단 반영
/split — 액면분할
/set_t &lt;값&gt; [종목] — T 수동 조정

<b>📒 기록</b>
/history [종목] — 종료 기록 (졸업일·회차·수익)
/monthly [종목] [연도] — 수익현황 (월별 수익률)

<b>🔧 운영</b>
/pause /resume — 자동 실행 멈춤·재개
/run — Job 수동 실행
/cycle_done [종목] — 수동 졸업
"""
