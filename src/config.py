# -*- coding: utf-8 -*-
"""
音楽ボットの設定ファイル
"""
import json
import os
import shutil
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent
CONFIG_FILE = PROJECT_DIR / "config.json"
CONFIG_EXAMPLE_FILE = PROJECT_DIR / "config.example.json"

DEFAULT_CONFIG = {
    "discord_token": "",
    "spotify_client_id": "",
    "spotify_client_secret": "",
    "discord_audio_bitrate": 192,
    "stream_url_ttl_seconds": 1200,
    "ffmpeg_executable": "",
}


def _create_config_file():
    if CONFIG_EXAMPLE_FILE.exists():
        shutil.copyfile(CONFIG_EXAMPLE_FILE, CONFIG_FILE)
    else:
        CONFIG_FILE.write_text(
            json.dumps(DEFAULT_CONFIG, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    print("⚠️  config.jsonを作成しました。")
    print("   config.jsonを開いて discord_token を設定してから、もう一度起動してください。")


def _load_config():
    created = False
    if not CONFIG_FILE.exists():
        _create_config_file()
        created = True

    try:
        data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise ValueError(f"config.jsonの書式が正しくありません: {e}") from e

    if not isinstance(data, dict):
        raise ValueError("config.jsonの内容はJSONオブジェクトで指定してください。")

    return {**DEFAULT_CONFIG, **data}, created


CONFIG, CONFIG_CREATED = _load_config()


def _get_setting(config_key, env_key):
    env_value = os.getenv(env_key)
    if env_value not in (None, ""):
        return env_value
    return CONFIG.get(config_key, DEFAULT_CONFIG.get(config_key))


def _get_str(config_key, env_key):
    value = _get_setting(config_key, env_key)
    if value is None:
        return None
    value = str(value).strip()
    return value or None


def _get_int(config_key, env_key, default):
    value = _get_setting(config_key, env_key)
    if value in (None, ""):
        return default

    try:
        return int(value)
    except (TypeError, ValueError) as e:
        raise ValueError(f"config.jsonの {config_key} は整数で指定してください。") from e


# 認証情報
DISCORD_TOKEN = _get_str("discord_token", "DISCORD_TOKEN")
SPOTIFY_CLIENT_ID = _get_str("spotify_client_id", "SPOTIFY_CLIENT_ID")
SPOTIFY_CLIENT_SECRET = _get_str("spotify_client_secret", "SPOTIFY_CLIENT_SECRET")

# 認証情報の存在チェック
if not DISCORD_TOKEN:
    raise ValueError("DISCORD_TOKENが設定されていません。config.jsonの discord_token を確認してください。")

if not SPOTIFY_CLIENT_ID or not SPOTIFY_CLIENT_SECRET:
    print("⚠️  警告: Spotify認証情報が設定されていません。")
    print("   Spotify機能を使用するにはconfig.jsonに認証情報を設定してください。")

# YouTube-DL設定
YDL_OPTIONS = {
    'format': 'bestaudio[ext=opus]/bestaudio/best',
    'noplaylist': False,  # Falseに変更（文字列ではなくブール値）
    'extract_flat': True,  # 高速化のためTrueに変更（プレイリスト用）
    'ignoreerrors': True,
    'no_warnings': True,
    'quiet': True,
    'noprogress': True,
    'concurrent-fragments': 1,  # 同時接続数を減らして安定化
    'retries': 3,  # リトライ数を減らして高速化
    'fragment-retries': 2,
    'socket_timeout': 30,  # ソケットタイムアウト追加
    'extractor_args': {
        'youtube': {
            'skip': ['hls', 'dash'],  # HLSやDASHをスキップ
            'player_client': ['android']  # androidクライアントのみ使用
        }
    },
    'playliststart': 1,  # プレイリストの開始位置
}

SINGLE_YDL_OPTIONS = {
    'format': 'bestaudio[ext=opus]/bestaudio/best',
    'noplaylist': True,  # 単一曲用はTrue
    'extract_flat': False,  # 単一曲は詳細情報が必要
    'concurrent-fragments': 2,
    'retries': 5,
    'fragment-retries': 3,
    'ignoreerrors': True,
    'no_warnings': True,
    'quiet': True,
    'noprogress': True,
}

def _resolve_ffmpeg_executable():
    """ffmpeg executable path, falling back to imageio-ffmpeg in local venvs."""
    config_path = _get_str("ffmpeg_executable", "FFMPEG_EXECUTABLE")
    if config_path:
        return config_path

    system_path = shutil.which("ffmpeg")
    if system_path:
        return system_path

    try:
        from static_ffmpeg.run import get_or_fetch_platform_executables_else_raise
        ffmpeg_path, _ = get_or_fetch_platform_executables_else_raise()
        return ffmpeg_path
    except Exception as e:
        print(f"⚠️  static-ffmpegの初期化に失敗: {e}")

    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception as e:
        print(f"⚠️  ffmpegが見つかりません: {e}")
        print("   requirements.txt の imageio-ffmpeg をインストールしてください。")
        return "ffmpeg"


FFMPEG_EXECUTABLE = _resolve_ffmpeg_executable()

FFMPEG_OPTIONS = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn',
}

# ファイル設定
QUEUE_FILE = str(PROJECT_DIR / "queue.json")
LOG_FILE = str(PROJECT_DIR / "bot_error.log")

# ボット設定
COMMAND_PREFIX = '/'
DEFAULT_VOLUME = 0.08
DISCORD_AUDIO_BITRATE = _get_int("discord_audio_bitrate", "DISCORD_AUDIO_BITRATE", 192)
STREAM_URL_TTL_SECONDS = _get_int("stream_url_ttl_seconds", "STREAM_URL_TTL_SECONDS", 20 * 60)
MAX_PLAYLIST_SONGS = 50
