#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

if [ ! -f bot.pid ]; then
  echo "bot.pid not found."
  exit 0
fi

pid="$(cat bot.pid)"
if ps -p "$pid" >/dev/null 2>&1; then
  kill "$pid"
  echo "Bot stopped: PID $pid"
else
  echo "Bot is not running: PID $pid"
fi
