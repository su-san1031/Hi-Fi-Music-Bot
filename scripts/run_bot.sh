#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

if [ ! -x ".venv/bin/python" ]; then
  echo ".venv がありません。先にセットアップしてください。"
  exit 1
fi

exec .venv/bin/python src/Hi-FiMusicBot.py
