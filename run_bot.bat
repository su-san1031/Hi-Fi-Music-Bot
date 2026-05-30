@echo off
echo Discord音楽Botを起動中...
cd /d "%~dp0"

REM 必要なパッケージがインストールされているかチェック
echo 依存関係をチェック中...
py -m pip install -r requirements.txt

echo Botを起動します...
py src\Hi-FiMusicBot.py
pause
