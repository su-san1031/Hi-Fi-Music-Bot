# Hi-FiMusicBot

YouTubeとSpotifyに対応したDiscord音楽Botです。
Windows11/Linuxで動作確認済みです
※Windowsの仕様上動作が安定しない事があります

## 機能

- YouTube動画の再生
- YouTubeプレイリスト/ミックスリストの再生
- Spotify楽曲の検索と再生
- キュー管理
- ループ再生
- 自動ボイスチャンネル参加
- 動画ごとの音量差を一定にできる
- 高レスポンス/高音質再生

## 開発環境

- Windows11
- Ubuntu Server 26.04 LTS
- Python 3.13
  
## 必要なもの

- Python 3.10以上
- Discord Bot Token
- Spotify連携を使う場合は Spotify Client ID / Client Secret

ffmpegは自動取得されます。通常は別途インストール不要です。

## フォルダー構成

- `run_bot.bat`: Windows用の簡単起動ファイル
- `config.example.json`: 設定ファイルの見本
- `config.json`: 自分用の設定ファイル
- `src/`: Bot本体
- `scripts/`: Linux向けの起動・停止スクリプト
- `tools/`: 補助ツール

## Windowsでの使い方

1. Python 3.10以上をインストールします。
2. `run_bot.bat` をダブルクリックします。
3. 初回起動時に `config.json` が自動作成されます。
4. `config.json` をメモ帳などで開きます。
5. `discord_token` にDiscord Bot Tokenを貼り付けます。
6. もう一度 `run_bot.bat` をダブルクリックします。

`config.json` の例:

```json
{
  "discord_token": "ここにDiscord Bot Tokenを貼り付け",
  "spotify_client_id": "",
  "spotify_client_secret": "",
  "discord_audio_bitrate": 192,
  "stream_url_ttl_seconds": 1200,
  "ffmpeg_executable": ""
}
```

Spotify連携を使わない場合、`spotify_client_id` と `spotify_client_secret` は空欄で構いません。

## Discord Bot Tokenの取得方法

1. Discord Developer Portalを開きます。
2. `New Application` でアプリを作成します。
3. `Bot` タブでBotを作成します。
4. `Reset Token` または `Copy Token` からトークンを取得します。
5. 取得したトークンを `config.json` の `discord_token` に貼り付けます。

Botをサーバーへ招待するときは、OAuth2 URL Generatorで以下を選択してください。

- Scopes: `bot`, `applications.commands`
- Bot Permissions: `View Channels`, `Send Messages`, `Connect`, `Speak`, `Use Voice Activity`

## Spotify連携の設定

SpotifyのURLや曲名検索を使いたい場合だけ設定してください。

1. Spotify Developer Dashboardを開きます。
2. `Create app` でアプリを作成します。
3. `Settings` からClient IDを確認します。
4. `View client secret` からClient Secretを取得します。
5. `config.json` の `spotify_client_id` と `spotify_client_secret` に貼り付けます。

## 手動で起動する場合

```bash
python -m venv .venv
```

Windows:

```bat
.venv\Scripts\activate
pip install -r requirements.txt
python src/Hi-FiMusicBot.py
```

Linux:

```bash
source .venv/bin/activate
pip install -r requirements.txt
python src/Hi-FiMusicBot.py
```

Linuxでは以下のスクリプトも使えます。

```bash
./scripts/start_bot.sh
./scripts/stop_bot.sh
```

## コマンド一覧

- `/connect`: ボイスチャンネルに参加
- `/add <URL or 検索キーワード>`: 曲をキューに追加
- `/playlist <URL>`: プレイリストをキューに追加
- `/skip`: 次の曲へスキップ
- `/pause`: 一時停止
- `/resume`: 再開
- `/stop`: 停止
- `/current`: 現在再生中の曲を表示
- `/queue`: キューを表示
- `/shuffle`: キューをシャッフル
- `/clear`: キューを空にする
- `/remove <番号>`: 指定した曲をキューから削除
- `/loop`: ループ再生を切り替え
- `/autojoin`: 自動参加を切り替え
- `/help`: ヘルプを表示
