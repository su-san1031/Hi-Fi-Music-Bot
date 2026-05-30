# -*- coding: utf-8 -*-
"""
天宮こころ音楽ボット - リファクタリング版
"""
import discord
from discord.ext import commands
from discord import app_commands
import asyncio
import json
import logging
import os
from spotipy import Spotify
from spotipy.oauth2 import SpotifyClientCredentials

# 自作モジュールをインポート
from config import (
    DISCORD_TOKEN, SPOTIFY_CLIENT_ID, SPOTIFY_CLIENT_SECRET,
    COMMAND_PREFIX, LOG_FILE, QUEUE_FILE
)
from utils import QueueManager, setup_logging, safe_interaction_response
from music_player import MusicPlayer

# ログ設定
setup_logging(LOG_FILE)

# Spotifyクライアントの設定
spotify = None
if SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET:
    try:
        spotify = Spotify(auth_manager=SpotifyClientCredentials(
            client_id=SPOTIFY_CLIENT_ID,
            client_secret=SPOTIFY_CLIENT_SECRET
        ))
        logging.info("Spotify機能が有効化されました")
    except Exception as e:
        logging.warning(f"Spotify機能の初期化に失敗: {e}")

# グローバルオブジェクト
queue_manager = QueueManager(QUEUE_FILE)
music_player = MusicPlayer(queue_manager, spotify)

# Botの設定
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix=COMMAND_PREFIX, intents=intents)

class MusicBot:
    """音楽ボットのメインクラス"""
    
    def __init__(self, bot_instance, music_player_instance, queue_manager_instance):
        self.bot = bot_instance
        self.music_player = music_player_instance
        self.queue_manager = queue_manager_instance
        self.setup_events()
        self.setup_commands()
    
    def setup_events(self):
        """イベントハンドラーを設定"""
        
        @self.bot.event
        async def on_ready():
            logging.info(f'Logged in as {self.bot.user.name}')
            print(f'Logged in as {self.bot.user.name}')
            
            try:
                # コマンドを同期（クリアはしない - 既に正しく定義されている）
                synced = await self.bot.tree.sync()
                print(f"Synced {len(synced)} command(s).")
                logging.info(f"Slash commands synced: {len(synced)}")
                
                # 登録されたコマンドを表示（重複チェック）
                command_names = [command.name for command in synced]
                duplicates = [name for name in set(command_names) if command_names.count(name) > 1]
                
                if duplicates:
                    print(f"⚠️ 重複しているコマンド: {duplicates}")
                    logging.warning(f"Duplicate commands detected: {duplicates}")
                else:
                    print("✅ コマンドの重複なし")
                
                for command in synced:
                    print(f"- /{command.name}: {command.description}")
                    
            except Exception as e:
                print(f"Failed to sync commands: {e}")
                logging.error(f"Command sync failed: {e}")
                
            print("Bot is ready and all commands are synced!")
        
        @self.bot.event
        async def on_command_error(ctx, error):
            if isinstance(error, commands.CommandNotFound):
                await ctx.send("❌ そのコマンドは見つからないにゃ〜。Slash Command（`/`で始まる）を使ってにゃ！\n`/amyahelp` でコマンド一覧を確認できるよ〜♪")
            else:
                logging.error(f"Command error: {error}")
                await ctx.send(f"⚠️ エラーが発生したにゃ: {str(error)}")
        
        @self.bot.event
        async def on_voice_state_update(member, before, after):
            # Bot自身がVCから切断/退出したらキューをリセット
            if self.bot.user and member.id == self.bot.user.id:
                if before.channel and not after.channel:
                    self.queue_manager.reset_queue()
                    logging.info("Botのボイス切断によりキューをリセットしました")
                return

            if member.bot:
                return
            
            # 自動参加処理
            if after.channel and not before.channel and self.music_player.auto_join:
                voice_client = discord.utils.get(self.bot.voice_clients, guild=member.guild)
                if not voice_client:
                    try:
                        # 安全な自動接続処理
                        new_voice_client = await after.channel.connect(timeout=15.0, reconnect=True)
                        logging.info(f"ボイスチャンネル {after.channel.name} に自動参加しました")
                    except discord.errors.ConnectionClosed as e:
                        if e.code == 4006:
                            # Session invalid の場合は少し待ってから再試行
                            logging.warning("自動参加でSession invalid (4006) - 再試行します")
                            try:
                                await asyncio.sleep(3)
                                new_voice_client = await after.channel.connect(timeout=15.0, reconnect=True)
                                logging.info(f"ボイスチャンネル {after.channel.name} に自動参加しました（再試行成功）")
                            except Exception as retry_e:
                                logging.error(f"自動参加の再試行に失敗: {retry_e}")
                        else:
                            logging.error(f"自動参加に失敗 (コード{e.code}): {e}")
                    except Exception as e:
                        logging.error(f"自動参加に失敗: {e}")
            
            # 自動退出処理
            voice_client = discord.utils.get(self.bot.voice_clients, guild=member.guild)
            if voice_client and voice_client.channel:
                channel_members = voice_client.channel.members
                if len([m for m in channel_members if not m.bot]) == 0:
                    self.queue_manager.reset_queue()
                    await voice_client.disconnect()
                    logging.info(f"ボイスチャンネル {voice_client.channel.name} から退出しました。キューをリセットしました")
    
    def setup_commands(self):
        """スラッシュコマンドを設定"""
        
        # === 基本操作コマンド ===
        @self.bot.tree.command(name="connect", description="🎵 ボイスチャンネルに参加します")
        async def connect(interaction: discord.Interaction):
            try:
                if interaction.user.voice:
                    channel = interaction.user.voice.channel
                    
                    # 既存の接続があれば切断
                    if interaction.guild.voice_client:
                        await interaction.guild.voice_client.disconnect()
                        await asyncio.sleep(1)  # 切断完了を待つ
                    
                    await interaction.response.defer()
                    
                    # 再試行ロジック付きで接続
                    voice_client = None
                    max_retries = 3
                    
                    for attempt in range(max_retries):
                        try:
                            logging.info(f"ボイス接続試行 {attempt + 1}/{max_retries}")
                            voice_client = await channel.connect(timeout=20.0, reconnect=True)
                            break
                        except discord.errors.ConnectionClosed as e:
                            if e.code == 4006:  # Session invalid
                                logging.warning(f"Session invalid (4006) - 試行 {attempt + 1}")
                                await asyncio.sleep(2 ** attempt)  # 指数バックオフ
                                continue
                            else:
                                raise e
                        except Exception as e:
                            logging.error(f"接続試行 {attempt + 1} 失敗: {e}")
                            if attempt == max_retries - 1:
                                raise e
                            await asyncio.sleep(2)
                    
                    if voice_client:
                        # 保存されたキューがあるかチェック
                        queue_length = len(self.queue_manager.queue)
                        
                        if queue_length > 0 and not voice_client.is_playing():
                            # キューがある場合は自動的に再生開始
                            await self.music_player.play_next(voice_client)
                            current_title = self.queue_manager.current_song.get("title", "Unknown Title")
                            
                            await interaction.followup.send(
                                f"🎵 **{channel.name}** に参加しました！\n"
                                f"🔄 保存されたキューを復元\n"
                                f"🎵 **{current_title}** を再生開始\n"
                                f"📋 待機中: {queue_length-1} 曲"
                            )
                        else:
                            await interaction.followup.send(f"🎵 **{channel.name}** に参加しました！")
                    else:
                        await interaction.followup.send("❌ ボイスチャンネルへの接続に失敗しました", ephemeral=True)
                else:
                    await interaction.response.send_message("❌ 先にボイスチャンネルに参加してください", ephemeral=True)
            except Exception as e:
                logging.error(f"Connect command error: {e}")
                try:
                    if interaction.response.is_done():
                        await interaction.followup.send("❌ 接続に失敗しました", ephemeral=True)
                    else:
                        await interaction.response.send_message("❌ 接続に失敗しました", ephemeral=True)
                except:
                    pass
        
        # === 音楽再生コマンド ===
        @self.bot.tree.command(name="add", description="🎶 曲をキューに追加します")
        @app_commands.describe(url="YouTubeのURL、検索キーワード、またはSpotifyのURL")
        async def add(interaction: discord.Interaction, url: str):
            try:
                if not interaction.guild.voice_client:
                    if interaction.user.voice:
                        # より安全な接続処理
                        try:
                            await interaction.user.voice.channel.connect(timeout=15.0, reconnect=True)
                        except discord.errors.ConnectionClosed as e:
                            if e.code == 4006:
                                # Session invalid の場合は少し待ってから再試行
                                await asyncio.sleep(2)
                                await interaction.user.voice.channel.connect(timeout=15.0, reconnect=True)
                            else:
                                raise e
                    else:
                        await interaction.response.send_message("❌ 先にボイスチャンネルに参加してください", ephemeral=True)
                        return

                await interaction.response.defer()
                
                try:
                    # URLかキーワードかを判定
                    if "http" in url:
                        song_info = await self.music_player.process_url_to_song(url)
                    else:
                        # 検索キーワードとして処理
                        song_info = await self.music_player.search_youtube_song(url)
                    
                    # タイトル付きで曲を追加
                    self.queue_manager.add_song_info(song_info)
                    queue_position = len(self.queue_manager.queue)
                    
                    await interaction.followup.send(f"✅ **{song_info['title']}** をキューに追加しました\n📍 待機位置: {queue_position}番目")
                    
                    if not interaction.guild.voice_client.is_playing():
                        await self.music_player.play_next(interaction.guild.voice_client)
                    else:
                        self.music_player.prefetch_next()
                        
                except ValueError as e:
                    await interaction.followup.send(f"❌ {str(e)}", ephemeral=True)
                    
            except Exception as e:
                logging.error(f"Add command error: {e}")
                if not interaction.response.is_done():
                    await interaction.response.send_message(f"❌ エラーが発生しました: {str(e)}", ephemeral=True)
        
        @self.bot.tree.command(name="playlist", description="📜 プレイリスト全体をキューに追加します")
        @app_commands.describe(url="プレイリストのURL", count="追加する最大曲数 (デフォルト: 50)")
        async def playlist(interaction: discord.Interaction, url: str, count: int = 50):
            try:
                if not interaction.guild.voice_client:
                    if interaction.user.voice:
                        await interaction.user.voice.channel.connect()
                    else:
                        await interaction.response.send_message("❌ 先にボイスチャンネルに参加してください", ephemeral=True)
                        return

                await interaction.response.defer()
                
                # 処理中メッセージを送信
                status_msg = await interaction.followup.send("🔄 プレイリストを処理中...")
                
                try:
                    logging.debug(f"プレイリストコマンド実行 - URL: {url}, count: {count}")
                    logging.info(f"プレイリストコマンド実行 - URL: {url}, count: {count}")
                    
                    # タイムアウト付きでプレイリスト処理
                    try:
                        songs, playlist_title, total_entries = await asyncio.wait_for(
                            self.music_player.process_full_playlist(url, count),
                            timeout=120.0  # 2分でタイムアウト
                        )
                    except asyncio.TimeoutError:
                        await status_msg.edit(content="❌ プレイリスト処理がタイムアウトしました。曲数を減らして再試行してください。")
                        return
                    
                    logging.debug(f"プレイリスト処理結果 - 取得曲数: {len(songs)}, タイトル: {playlist_title}")
                    
                    if songs:
                        # 進捗表示更新
                        await status_msg.edit(content="🎵 キューに追加中...")
                        
                        queue_before = len(self.queue_manager.queue)
                        self.queue_manager.add_songs(songs)  # songsは辞書のリスト
                        queue_after = len(self.queue_manager.queue)
                        
                        logging.debug(f"キュー状態 - 追加前: {queue_before}, 追加後: {queue_after}")
                        
                        # 完了メッセージ
                        await status_msg.edit(
                            content=f"✅ **{playlist_title}** から {len(songs)} 曲を追加しました！\n"
                                   f"📊 総曲数: {total_entries} 曲\n"
                                   f"📋 現在のキュー: {queue_after} 曲"
                        )
                        
                        if not interaction.guild.voice_client.is_playing():
                            logging.debug("再生開始処理実行")
                            await self.music_player.play_next(interaction.guild.voice_client)
                        else:
                            self.music_player.prefetch_next()
                    else:
                        await status_msg.edit(content="❌ 追加できる曲が見つかりませんでした")
                        
                except ValueError as e:
                    logging.debug(f"プレイリスト処理でエラー: {e}")
                    await status_msg.edit(content=f"❌ {str(e)}")
                    
            except Exception as e:
                logging.error(f"Playlist command error: {e}")
                logging.debug(f"プレイリストコマンドで例外: {e}")
                try:
                    if 'status_msg' in locals():
                        await status_msg.edit(content=f"❌ エラーが発生しました: {str(e)}")
                    elif not interaction.response.is_done():
                        await interaction.response.send_message(f"❌ エラーが発生しました: {str(e)}", ephemeral=True)
                except:
                    pass
        
        # === 再生制御コマンド ===
        @self.bot.tree.command(name="skip", description="⏭️ 現在の曲をスキップします")
        async def skip(interaction: discord.Interaction):
            try:
                if interaction.guild.voice_client and interaction.guild.voice_client.is_playing():
                    interaction.guild.voice_client.stop()
                    await interaction.response.send_message("⏭️ スキップしました！")
                else:
                    await interaction.response.send_message("❌ 再生中の曲がありません", ephemeral=True)
            except Exception as e:
                logging.error(f"Skip command error: {e}")
                await interaction.response.send_message("❌ スキップに失敗しました", ephemeral=True)
        
        @self.bot.tree.command(name="pause", description="⏸️ 再生を一時停止します")
        async def pause(interaction: discord.Interaction):
            try:
                if interaction.guild.voice_client and interaction.guild.voice_client.is_playing():
                    interaction.guild.voice_client.pause()
                    await interaction.response.send_message("⏸️ 一時停止しました")
                else:
                    await interaction.response.send_message("❌ 再生中の曲がありません", ephemeral=True)
            except Exception as e:
                logging.error(f"Pause command error: {e}")
                await interaction.response.send_message("❌ 一時停止に失敗しました", ephemeral=True)
        
        @self.bot.tree.command(name="resume", description="▶️ 再生を再開します")
        async def resume(interaction: discord.Interaction):
            try:
                if interaction.guild.voice_client and interaction.guild.voice_client.is_paused():
                    interaction.guild.voice_client.resume()
                    await interaction.response.send_message("▶️ 再生を再開しました")
                else:
                    await interaction.response.send_message("❌ 一時停止中の曲がありません", ephemeral=True)
            except Exception as e:
                logging.error(f"Resume command error: {e}")
                await interaction.response.send_message("❌ 再開に失敗しました", ephemeral=True)
        
        @self.bot.tree.command(name="stop", description="⏹️ 再生を停止してキューをクリアします")
        async def stop(interaction: discord.Interaction):
            try:
                if interaction.guild.voice_client:
                    interaction.guild.voice_client.stop()
                    self.queue_manager.clear_queue()
                    await interaction.response.send_message("⏹️ 停止してキューをクリアしました")
                else:
                    await interaction.response.send_message("❌ 再生中の曲がありません", ephemeral=True)
            except Exception as e:
                logging.error(f"Stop command error: {e}")
                await interaction.response.send_message("❌ 停止に失敗しました", ephemeral=True)
        
        # === 情報表示コマンド ===
        @self.bot.tree.command(name="current", description="🎵 現在再生中の曲を表示します")
        async def current(interaction: discord.Interaction):
            try:
                current_title = self.queue_manager.current_song["title"]
                current_url = self.queue_manager.current_song["url"]
                queue_length = len(self.queue_manager.queue)
                
                if current_title:
                    embed = discord.Embed(
                        title="🎵 現在再生中",
                        description=f"**{current_title}**",
                        color=0x00ff00
                    )
                    embed.add_field(name="📋 待機中", value=f"{queue_length} 曲", inline=True)
                    embed.add_field(name="🔁 ループ", value="有効" if self.queue_manager.loop_mode else "無効", inline=True)
                    if current_url and len(current_url) < 1024:
                        embed.add_field(name="🔗 URL", value=current_url, inline=False)
                    
                    await interaction.response.send_message(embed=embed)
                else:
                    await interaction.response.send_message(f"❌ 再生中の曲がありません\n📋 待機中: {queue_length} 曲")
            except Exception as e:
                logging.error(f"Current command error: {e}")
                await interaction.response.send_message("❌ 情報取得に失敗しました", ephemeral=True)
        
        @self.bot.tree.command(name="queue", description="📋 再生キューを表示します")
        async def queue(interaction: discord.Interaction):
            try:
                queue_length = len(self.queue_manager.queue)
                
                if self.queue_manager.queue:
                    embed = discord.Embed(
                        title="📋 再生キュー",
                        description=f"合計 {queue_length} 曲",
                        color=0x0099ff
                    )
                    
                    queue_list = list(self.queue_manager.queue)
                    display_count = min(10, len(queue_list))
                    
                    for i in range(display_count):
                        song = queue_list[i]
                        
                        # 新しい辞書形式の場合
                        if isinstance(song, dict):
                            title = song.get('title', 'Unknown Title')
                            # タイトルが長すぎる場合は省略
                            if len(title) > 60:
                                title = title[:57] + "..."
                        else:
                            # 旧形式（URL文字列）の場合の後方互換性
                            if "youtube.com/watch?v=" in song:
                                video_id = song.split("v=")[1].split("&")[0]
                                title = f"YouTube動画 ({video_id[:8]}...)"
                            else:
                                title = song[:60] + "..." if len(song) > 60 else song
                        
                        embed.add_field(
                            name=f"{i+1}. 曲",
                            value=f"🎵 {title}",
                            inline=False
                        )
                    
                    if len(queue_list) > 10:
                        embed.add_field(
                            name="...",
                            value=f"他 {len(queue_list) - 10} 曲",
                            inline=False
                        )
                    
                    await interaction.response.send_message(embed=embed)
                else:
                    await interaction.response.send_message("� キューは空です")
            except Exception as e:
                logging.error(f"Queue command error: {e}")
                await interaction.response.send_message("❌ キュー表示に失敗しました", ephemeral=True)
        
        # === キュー操作コマンド ===
        @self.bot.tree.command(name="shuffle", description="🔀 キューをシャッフルします")
        async def shuffle(interaction: discord.Interaction):
            try:
                queue_length = len(self.queue_manager.queue)
                
                if self.queue_manager.queue:
                    self.queue_manager.shuffle_queue()
                    await interaction.response.send_message(f"🔀 {queue_length} 曲をシャッフルしました！")
                else:
                    await interaction.response.send_message("📭 シャッフルする曲がありません", ephemeral=True)
            except Exception as e:
                logging.error(f"Shuffle command error: {e}")
                await interaction.response.send_message("❌ シャッフルに失敗しました", ephemeral=True)
        
        @self.bot.tree.command(name="clear", description="🗑️ キューをクリアします")
        async def clear(interaction: discord.Interaction):
            try:
                queue_length = len(self.queue_manager.queue)
                if queue_length > 0:
                    self.queue_manager.clear_queue()
                    await interaction.response.send_message(f"�️ {queue_length} 曲をキューから削除しました")
                else:
                    await interaction.response.send_message("📭 キューは既に空です", ephemeral=True)
            except Exception as e:
                logging.error(f"Clear command error: {e}")
                await interaction.response.send_message("❌ クリアに失敗しました", ephemeral=True)
        
        @self.bot.tree.command(name="remove", description="🗑️ キューから指定した曲を削除します")
        @app_commands.describe(position="削除したい曲の番号（1から開始）")
        async def remove(interaction: discord.Interaction, position: int):
            try:
                if not self.queue_manager.queue:
                    await interaction.response.send_message("📭 キューは空です", ephemeral=True)
                    return
                
                if position < 1 or position > len(self.queue_manager.queue):
                    await interaction.response.send_message(f"❌ 番号は1〜{len(self.queue_manager.queue)}の範囲で指定してください", ephemeral=True)
                    return
                
                removed_url = self.queue_manager.remove_song(position - 1)
                if removed_url:
                    await interaction.response.send_message(f"🗑️ {position} 番目の曲を削除しました")
                else:
                    await interaction.response.send_message("❌ 削除に失敗しました", ephemeral=True)
                    
            except Exception as e:
                logging.error(f"Remove command error: {e}")
                await interaction.response.send_message("❌ 削除に失敗しました", ephemeral=True)
        
        @self.bot.tree.command(name="loop", description="🔁 ループ再生を切り替えます")
        async def loop(interaction: discord.Interaction):
            try:
                self.queue_manager.loop_mode = not self.queue_manager.loop_mode
                status = "有効" if self.queue_manager.loop_mode else "無効"
                emoji = "🔁" if self.queue_manager.loop_mode else "➡️"
                await interaction.response.send_message(f"{emoji} ループ再生: **{status}**")
            except Exception as e:
                logging.error(f"Loop command error: {e}")
                await interaction.response.send_message("❌ ループ設定に失敗しました", ephemeral=True)
        
        @self.bot.tree.command(name="autojoin", description="🤖 自動参加機能を切り替えます")
        async def autojoin(interaction: discord.Interaction):
            try:
                self.music_player.auto_join = not self.music_player.auto_join
                status = "有効" if self.music_player.auto_join else "無効"
                emoji = "🤖" if self.music_player.auto_join else "😴"
                await interaction.response.send_message(f"{emoji} 自動参加: **{status}**")
            except Exception as e:
                logging.error(f"Autojoin command error: {e}")
                await interaction.response.send_message("❌ 自動参加設定に失敗しました", ephemeral=True)
        
        # === ヘルプコマンド ===
        @self.bot.tree.command(name="help", description="❓ コマンド一覧を表示します")
        async def help(interaction: discord.Interaction):
            embed = discord.Embed(
                title="🎵 音楽ボット コマンド一覧",
                description="天宮こころ音楽ボットの使い方",
                color=0xff69b4
            )
            
            embed.add_field(
                name="🎵 基本操作",
                value="`/connect` - ボイスチャンネルに参加",
                inline=False
            )
            
            embed.add_field(
                name="🎶 音楽追加",
                value="`/add <URL/キーワード>` - 曲を追加\n"
                      "`/playlist <URL>` - プレイリストを追加",
                inline=False
            )
            
            embed.add_field(
                name="⏯️ 再生制御",
                value="`/skip` - スキップ\n"
                      "`/pause` - 一時停止\n"
                      "`/resume` - 再開\n"
                      "`/stop` - 停止",
                inline=False
            )
            
            embed.add_field(
                name="📋 情報表示",
                value="`/current` - 現在再生中\n"
                      "`/queue` - キュー表示",
                inline=False
            )
            
            embed.add_field(
                name="🔧 キュー操作",
                value="`/shuffle` - シャッフル\n"
                      "`/clear` - キュークリア\n"
                      "`/remove <番号>` - 曲削除",
                inline=False
            )
            
            embed.add_field(
                name="⚙️ 設定",
                value="`/loop` - ループ切り替え\n"
                      "`/autojoin` - 自動参加切り替え",
                inline=False
            )
            
            auto_join_status = "有効" if self.music_player.auto_join else "無効"
            loop_status = "有効" if self.queue_manager.loop_mode else "無効"
            queue_count = len(self.queue_manager.queue)
            
            embed.add_field(
                name="📊 現在の状態",
                value=f"自動参加: {auto_join_status}\n"
                      f"ループ: {loop_status}\n"
                      f"音量ならし: 常時有効\n"
                      f"キュー: {queue_count} 曲",
                inline=False
            )
            
            await interaction.response.send_message(embed=embed)

# ボットのインスタンスを作成
music_bot = MusicBot(bot, music_player, queue_manager)

async def main():
    """メイン関数"""
    try:
        # 既存のプロセスをチェック（Windows用）
        import psutil
        current_pid = os.getpid()
        bot_processes = []
        
        for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
            if proc.info['name'] == 'python.exe' and proc.info['pid'] != current_pid:
                cmdline = proc.info.get('cmdline', [])
                if any('Hi-FiMusicBot.py' in arg for arg in cmdline):
                    bot_processes.append(proc.info['pid'])
        
        if bot_processes:
            print(f"⚠️ 警告: 他のボットプロセスが実行中です (PID: {bot_processes})")
            print("   重複を避けるため、他のプロセスを終了してから再度実行してください。")
            return
        
        queue_manager.reset_queue()
        logging.info("Bot起動時にキューをリセットしました")
        print("Starting bot...")
        await bot.start(DISCORD_TOKEN)
    except KeyboardInterrupt:
        print("Bot stopped by user.")
        await bot.close()
    except Exception as e:
        print(f"Bot startup error: {e}")
        logging.error(f"Bot startup error: {e}")

if __name__ == "__main__":
    import psutil  # プロセス管理用
    asyncio.run(main())
