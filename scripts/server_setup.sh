#!/usr/bin/env bash
# 서버 최초 1회: clone → venv → .env → systemd (GCP e2-micro 최적화)
set -euo pipefail

REPO_URL="${1:-}"
INSTALL_DIR="${2:-$HOME/infinite-trading-bot-v4}"
BRANCH="${3:-main}"

usage() {
  echo "Usage: $0 <git-repo-url> [install-dir] [branch]"
  echo "Example: $0 https://github.com/kwy4321/infinite-trading-bot-v4.git"
  exit 1
}

[[ -n "$REPO_URL" ]] || usage

RUN_USER="$(id -un)"

if [[ -d "$INSTALL_DIR/.git" ]]; then
  echo "Already cloned: $INSTALL_DIR"
  cd "$INSTALL_DIR"
  git fetch origin "$BRANCH"
  git checkout "$BRANCH"
  git pull origin "$BRANCH"
else
  git clone -b "$BRANCH" "$REPO_URL" "$INSTALL_DIR"
  cd "$INSTALL_DIR"
fi

if [[ ! -d .venv ]]; then
  python3 -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate
pip install --no-cache-dir -U pip -q
pip install --no-cache-dir -r requirements.txt -q

mkdir -p data/accounts/default data/backups

if [[ ! -f .env ]]; then
  cp .env.example .env
  echo ""
  echo ">>> .env created. Edit secrets before starting:"
  echo "    nano $INSTALL_DIR/.env"
  echo ""
fi

# journal 로그 용량 제한 (디스크 절약)
if [[ ! -f /etc/systemd/journald.conf.d/bot-limit.conf ]]; then
  sudo mkdir -p /etc/systemd/journald.conf.d
  sudo tee /etc/systemd/journald.conf.d/bot-limit.conf >/dev/null <<'EOF'
[Journal]
SystemMaxUse=50M
MaxRetentionSec=7day
EOF
  sudo systemctl restart systemd-journald || true
fi

# e2-micro 1GB RAM — swap 1G (없을 때만)
if ! sudo swapon --show 2>/dev/null | grep -q '/swapfile'; then
  if [[ ! -f /swapfile ]]; then
    echo "Creating 1G swap (GCP free tier)..."
    sudo fallocate -l 1G /swapfile 2>/dev/null || sudo dd if=/dev/zero of=/swapfile bs=1M count=1024 status=none
    sudo chmod 600 /swapfile
    sudo mkswap /swapfile
  fi
  sudo swapon /swapfile 2>/dev/null || true
  if ! grep -q '/swapfile' /etc/fstab 2>/dev/null; then
    echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab >/dev/null
  fi
fi

SERVICE="/etc/systemd/system/infinite-trading-bot.service"
sed -e "s|@INSTALL_DIR@|$INSTALL_DIR|g" -e "s|@RUN_USER@|$RUN_USER|g" \
  deploy/infinite-trading-bot.service.tpl | sudo tee "$SERVICE" >/dev/null

sudo systemctl daemon-reload
sudo systemctl enable infinite-trading-bot

echo ""
echo "Setup complete (lightweight mode for GCP free tier)."
echo "  Install dir : $INSTALL_DIR"
echo "  venv        : $INSTALL_DIR/.venv"
echo "  Service     : infinite-trading-bot"
echo ""
echo "Next:"
echo "  1) nano $INSTALL_DIR/.env"
echo "  2) bash scripts/test_telegram.sh"
echo "  3) sudo systemctl start infinite-trading-bot"
echo "  4) sudo systemctl status infinite-trading-bot"
