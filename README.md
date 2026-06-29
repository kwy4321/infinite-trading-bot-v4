# Infinite Trading Bot v4

라오어 무한매수 4.0 — Telegram 제어 + Toss Open API (DRY_RUN 지원)

## 구조

- `main.py` — Telegram polling + 스케줄러
- `config/settings.py` — `.env` 로드
- `scripts/server_setup.sh` — 서버 최초 설치
- `scripts/deploy.sh` — pull + 재시작 (push 시 GitHub Actions가 SSH로 실행)
- `scripts/test_telegram.sh` — 서버에서 텔레그램 연결 테스트

## 1. GitHub에 올리기 (로컬 PC)

1. [Git for Windows](https://git-scm.com/download/win) 설치
2. GitHub에서 **Private** 저장소 생성 (예: `infinite-trading-bot-v4`)
3. PowerShell:

```powershell
cd "E:\개인자료\자동매매 구축\infinite_trading_bot_v4_complete-v2"
powershell -ExecutionPolicy Bypass -File .\scripts\init_github.ps1
```

`.env`는 `.gitignore`에 있어 **GitHub에 올라가지 않습니다.** (토큰/시크릿 안전)

## 2. 서버 최초 설치

SSH로 서버 접속 후:

```bash
git clone git@github.com:YOUR_USER/infinite-trading-bot-v4.git ~/infinite-trading-bot-v4
cd ~/infinite-trading-bot-v4
bash scripts/server_setup.sh git@github.com:YOUR_USER/infinite-trading-bot-v4.git
```

`.env` 편집:

```bash
nano ~/infinite-trading-bot-v4/.env
# TELEGRAM_BOT_TOKEN, TELEGRAM_ALLOWED_CHAT_IDS, TOSS_* 등 입력
# DRY_RUN=true 로 먼저 테스트 권장
```

텔레그램 테스트:

```bash
bash scripts/test_telegram.sh
```

봇 실행:

```bash
sudo systemctl start infinite-trading-bot
sudo systemctl status infinite-trading-bot
journalctl -u infinite-trading-bot -f
```

## 3. 자동 배포 (GitHub Actions → 서버)

`main` 브랜치에 push하면 서버에서 `git pull` + systemd 재시작.

### GitHub Secrets (Repository → Settings → Secrets)

| Secret | 예시 |
|--------|------|
| `SSH_HOST` | 서버 IP 또는 도메인 |
| `SSH_USER` | `ubuntu` |
| `SSH_PRIVATE_KEY` | 서버 SSH 개인키 전체 (PEM) |
| `SSH_PORT` | `22` (기본값, 생략 가능) |
| `DEPLOY_PATH` | `/home/ubuntu/infinite-trading-bot-v4` |

### 서버 SSH 키 (GitHub Actions용)

서버에서:

```bash
ssh-keygen -t ed25519 -f ~/.ssh/github_deploy -N ""
cat ~/.ssh/github_deploy.pub >> ~/.ssh/authorized_keys
cat ~/.ssh/github_deploy   # → GitHub Secret SSH_PRIVATE_KEY 에 붙여넣기
```

수동 배포 테스트: GitHub → Actions → **Deploy to Server** → **Run workflow**

## 4. 로컬 Windows (선택)

보안 정책으로 Telegram API가 막힌 PC에서는 로컬 테스트 대신 **서버에서** `test_telegram.sh` 사용.

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\setup_and_run.ps1
```

## 환경 변수 (.env.example 참고)

| 변수 | 설명 |
|------|------|
| `TELEGRAM_BOT_TOKEN` | BotFather 토큰 |
| `TELEGRAM_ALLOWED_CHAT_IDS` | 허용 chat ID (쉼표 구분) |
| `TOSS_CLIENT_ID` / `TOSS_CLIENT_SECRET` | Toss Open API |
| `DRY_RUN` | `true`면 실주문 없음 |

## 텔레그램 명령어

| 구분 | 명령 | 설명 |
|------|------|------|
| 현황 | `/dashboard` | 전체 요약 (포지션·회차) |
| | `/status [종목]` | 전략·T·잔고 상세 |
| | `/balance` | Toss API 계좌 잔고 (`DRY_RUN=false`) |
| | `/plan [종목]` | 오늘 T 기준 주문 계획 |
| | `/sync [종목]` | API 수량·평단 → 기록 반영 |
| 설정 | `/setting` | 원금·예수금·분할 |
| | `/split` | 액면분할 |
| | `/set_t <값> [종목]` | T 수동 조정 |
| 기록 | `/cycles [종목]` | 회차 기록 |
| | `/monthly [종목] [연도]` | 월별 수익 |
| | `/history [종목]` | 졸업 기록 |
| | `/cycle_done [종목]` | 수동 졸업 |
| 운영 | `/pause` `/resume` | 자동 Job 정지·재개 |
| | `/run` | Job 수동 실행 |
