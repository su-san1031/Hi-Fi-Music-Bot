#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

if [ -f bot.pid ] && ps -p "$(cat bot.pid)" >/dev/null 2>&1; then
  echo "Bot is already running: PID $(cat bot.pid)"
  exit 0
fi

if [ ! -x ".venv/bin/python" ]; then
  echo ".venv is missing. Create it and install requirements first."
  exit 1
fi

: > bot_stdout.log
setsid -f bash -c 'echo $$ > bot.pid; exec .venv/bin/python src/Hi-FiMusicBot.py >> bot_stdout.log 2>&1'
sleep 1
echo "Bot started: PID $(cat bot.pid)"
