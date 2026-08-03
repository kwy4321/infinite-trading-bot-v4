"""도메인 서비스 계층 — app(broker/state/cycles)을 읽어 화면·주문에 쓰일 값을 만든다.

표현 계층(tg/dashboard/briefing)이 브로커 API 를 직접 호출하지 않고
여기를 거치게 해서, 조회 로직 중복과 이벤트 루프 블로킹을 한 곳에서 통제한다.
"""
