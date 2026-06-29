#!/usr/bin/env bash
# 서버 최초 1회: clone → venv → .env → systemd 등록
set -euo pipefail

REPO_URL="${1:-}"
INSTALL_DIR="${2:-$HOME/infinite-trading-bot-v4}"
BRANCH="${3:-main}"

usage() {
  echo "Usage: $0 <git-repo-url> [install-dir] [branch]"
  echo "Example: $0 git@github.com:you/infinite-trading-bot-v4.git"
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
pip install -U pip -q
pip install -r requirements.txt -q

mkdir -p data/accounts/default data/backups

if [[ ! -f .env ]]; then
  cp .env.example .env
  echo ""
  echo ">>> .env created. Edit secrets before starting:"
  echo "    nano $INSTALL_DIR/.env"
  echo ""
fi

SERVICE="/etc/systemd/system/infinite-trading-bot.service"
sed -e "s|@INSTALL_DIR@|$INSTALL_DIR|g" -e "s|@RUN_USER@|$RUN_USER|g" \
  deploy/infinite-trading-bot.service.tpl | sudo tee "$SERVICE" >/dev/null

sudo systemctl daemon-reload
sudo systemctl enable infinite-trading-bot

echo ""
echo "Setup complete."
echo "  Install dir : $INSTALL_DIR"
echo "  Service     : infinite-trading-bot"
echo ""
echo "Next:"
echo "  1) nano $INSTALL_DIR/.env"
echo "  2) bash scripts/test_telegram.sh"
echo "  3) sudo systemctl start infinite-trading-bot"
echo "  4) sudo systemctl status infinite-trading-bot"
