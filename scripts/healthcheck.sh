#!/usr/bin/env bash
# Exit 0 if main.py imports cleanly
cd "$(dirname "$0")/.."
python -c "from app import App; App.create(); print('ok')"
