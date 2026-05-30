# -*- coding: utf-8 -*-
"""
音楽再生機能のクラス
"""
import discord
import yt_dlp
import asyncio
import logging
import time
from spotipy import Spotify
from spotipy.oauth2 import SpotifyClientCredentials
from config import (
    SINGLE_YDL_OPTIONS, YDL_OPTIONS, FFMPEG_OPTIONS,
    DEFAULT_VOLUME, DISCORD_AUDIO_BITRATE, FFMPEG_EXECUTABLE,
    STREAM_URL_TTL_SECONDS
)
from utils import is_playlist_or_mix

class MusicPlayer:
    """音楽再生を管理するクラス"""
    
    def __init__(self, queue_manager, spotify_client=None):
        self.queue_manager = queue_manager
        self.spotify = spotify_client
        self.auto_join = True
        self.volume = DEFAULT_VOLUME
        self.normalize_audio = True
        self._extract_semaphore = asyncio.Semaphore(3)
        self._prefetch_task = None
    
    async def play_next(self, voice_client):
        """次の曲を再生"""
        if not voice_client or not voice_client.is_connected():
            return
            
        song = self.queue_manager.get_next_song()
        if song:
            self.queue_manager.save_queue()
            try:
                song_info = await self._prepare_song(song)
                self.queue_manager.current_song = dict(song_info)
                audio_source = self._create_audio_source(song_info["stream_url"])
                    
                # 再生終了後のコールバック
                def after_playing(error):
                    if error:
                        logging.error(f"再生エラー: {error!r}")
                    coro = self.play_next(voice_client)
                    asyncio.run_coroutine_threadsafe(coro, voice_client.loop)
                
                voice_client.play(audio_source, after=after_playing)
                logging.info(f"再生開始: {song_info['title']}")
                
                self.queue_manager.save_queue()
                self._start_prefetch_next()
                
            except Exception as e:
                logging.exception(f"再生エラー: {e!r}")
                # エラーが発生した場合は次の曲を試す
                await self.play_next(voice_client)
        else:
            # キューが空の場合
            self.queue_manager.current_song = {"title": None, "url": None}
            logging.info("キューが空になりました")

    async def _extract_info(self, url, options=None):
        """yt-dlpの同期処理をイベントループ外で実行"""
        extract_options = options or SINGLE_YDL_OPTIONS
        async with self._extract_semaphore:
            return await asyncio.to_thread(self._extract_info_sync, extract_options, url)

    def _extract_info_sync(self, options, url):
        with yt_dlp.YoutubeDL(options) as ydl:
            return ydl.extract_info(url, download=False)

    def _stream_is_fresh(self, song):
        created_at = song.get("stream_created_at") if isinstance(song, dict) else None
        return bool(
            isinstance(song, dict)
            and song.get("stream_url")
            and created_at
            and (time.time() - float(created_at)) < STREAM_URL_TTL_SECONDS
        )

    def _song_from_info(self, info, title=None, fallback_url=None):
        if not info:
            raise ValueError("動画情報を取得できませんでした")

        entries = info.get("entries")
        if entries:
            first_entry = next((entry for entry in entries if entry), None)
            if not first_entry:
                raise ValueError("検索結果が見つかりませんでした")
            info = first_entry

        stable_url = self._get_stable_video_url(info, fallback=fallback_url)
        stream_url = info.get("url")
        if not stable_url or not stream_url:
            raise ValueError("音声URLを取得できませんでした")

        return {
            "url": stable_url,
            "title": title or info.get("title", "Unknown Title"),
            "stream_url": stream_url,
            "stream_created_at": time.time(),
        }

    async def _prepare_song(self, song):
        if isinstance(song, dict):
            song_info = dict(song)
        else:
            song_info = {"url": song, "title": "Unknown Title"}

        if self._stream_is_fresh(song_info):
            return song_info

        info = await self._extract_info(song_info["url"])
        prepared = self._song_from_info(
            info,
            title=song_info.get("title") if song_info.get("title") != "取得中..." else None,
            fallback_url=song_info["url"],
        )
        return prepared

    def _start_prefetch_next(self):
        if self._prefetch_task and not self._prefetch_task.done():
            return
        self._prefetch_task = asyncio.create_task(self._prefetch_next_song())

    def prefetch_next(self):
        """待機中の次曲を先読み"""
        self._start_prefetch_next()

    async def _prefetch_next_song(self):
        next_song = self.queue_manager.peek_next_song()
        if not next_song or self._stream_is_fresh(next_song):
            return

        try:
            prepared = await self._prepare_song(next_song)
            if self.queue_manager.replace_next_song(next_song, prepared):
                logging.info(f"次曲を先読みしました: {prepared['title']}")
        except Exception as e:
            logging.debug(f"次曲の先読みに失敗: {e!r}")
    
    async def handle_spotify_url(self, url):
        """Spotify URLを処理してYouTube検索クエリを返す"""
        if not self.spotify:
            raise ValueError("Spotify機能が無効です")
            
        try:
            track_info = await asyncio.to_thread(self.spotify.track, url)
            track_name = track_info["name"]
            artist_name = track_info["artists"][0]["name"]
            return f"{track_name} {artist_name}", track_name
        except Exception as e:
            raise ValueError(f"Spotify情報の取得に失敗: {e}")
    
    async def search_youtube(self, query):
        """YouTube検索を実行"""
        try:
            song = await self.search_youtube_song(query)
            return song["url"], song["title"]
        except Exception as e:
            raise ValueError(f"YouTube検索に失敗: {e}")

    async def search_youtube_song(self, query):
        """YouTube検索結果を再生用メタデータ付きで取得"""
        info = await self._extract_info(f"ytsearch1:{query}")
        return self._song_from_info(info)
    
    async def process_url(self, url):
        """URLを処理して再生可能な形式に変換"""
        song = await self.process_url_to_song(url)
        return song["url"], song["title"]

    async def process_url_to_song(self, url):
        """URLを処理してキュー保存用の曲情報に変換"""
        # Spotify URL の処理
        if "open.spotify.com" in url:
            search_query, original_title = await self.handle_spotify_url(url)
            song = await self.search_youtube_song(search_query)
            song["title"] = f"{original_title} (Spotify経由)"
            return song
        
        # プレイリスト・ミックスリストの処理
        elif is_playlist_or_mix(url):
            video_url, title = await self.process_playlist_url(url)
            return await self._prepare_song({"url": video_url, "title": title})
        
        # 通常の単一動画処理
        else:
            try:
                info = await self._extract_info(url)
                return self._song_from_info(info, fallback_url=url)
            except Exception as e:
                raise ValueError(f"動画情報の取得に失敗: {e}")

    def _get_stable_video_url(self, info, fallback=None):
        """Queue a stable page URL instead of an expiring direct media URL."""
        if not info:
            return fallback

        webpage_url = info.get('webpage_url')
        if webpage_url:
            return webpage_url

        video_id = info.get('id')
        extractor = info.get('extractor_key') or info.get('ie_key') or ''
        if video_id and 'Youtube' in extractor:
            return f"https://www.youtube.com/watch?v={video_id}"

        return info.get('url') or fallback

    def _create_audio_source(self, source):
        """Create an Opus source so playback does not require system libopus."""
        options = FFMPEG_OPTIONS.get('options', '-vn')
        volume = max(0.0, min(float(self.volume), 2.0))
        audio_filters = []
        if self.normalize_audio:
            audio_filters.append("dynaudnorm=f=250:g=15:p=0.90:m=8")
        audio_filters.append(f"volume={volume}")
        options = f"{options} -filter:a {','.join(audio_filters)}"

        kwargs = {
            "executable": FFMPEG_EXECUTABLE,
            "options": options,
            "bitrate": DISCORD_AUDIO_BITRATE,
        }

        if isinstance(source, str) and source.startswith(("http://", "https://")):
            kwargs["before_options"] = FFMPEG_OPTIONS.get('before_options')

        return discord.FFmpegOpusAudio(source, **kwargs)
    
    async def process_playlist_url(self, url):
        """プレイリストURLから最初の動画を取得"""
        try:
            playlist_options = YDL_OPTIONS.copy()
            playlist_options['playlistend'] = 1
            
            info = await self._extract_info(url, playlist_options)
            
            if 'entries' in info and info['entries']:
                first_entry = info['entries'][0]
                if first_entry and first_entry.get('id'):
                    video_id = first_entry.get('id')
                    video_url = f"https://www.youtube.com/watch?v={video_id}"
                    title = first_entry.get('title', 'Unknown Title')
                    return video_url, title
            
            # エントリーが無効な場合、URLから直接動画IDを抽出
            single_url = url.split('&list=')[0] if '&list=' in url else url
            info_single = await self._extract_info(single_url)
            song = self._song_from_info(info_single, fallback_url=single_url)
            return song["url"], song["title"]
                    
        except Exception as e:
            # エラーが発生した場合は単一動画として処理
            single_url = url.split('&list=')[0] if '&list=' in url else url
            info_single = await self._extract_info(single_url)
            song = self._song_from_info(info_single, fallback_url=single_url)
            return song["url"], song["title"]
    
    async def process_full_playlist(self, url, max_songs=50):
        """プレイリスト全体を処理（非同期処理で改善）"""
        try:
            # ミックスリスト（RD系）の特別な処理
            is_mix = any(indicator in url for indicator in ['RD', 'RDMM', 'RDAMVM', 'RDCLAK', 'RDTMAK'])
            
            playlist_options = YDL_OPTIONS.copy()
            playlist_options['playlistend'] = max_songs
            
            if is_mix:
                # ミックスリスト用の設定（処理速度向上）
                playlist_options.update({
                    'extract_flat': True,  # 高速化のためTrueに変更
                    'playliststart': 1,
                    'playlistend': max_songs,
                    'ignoreerrors': True,
                    'lazy_playlist': True,  # 遅延読み込み
                    'extractor_args': {
                        'youtube': {
                            'player_client': ['android'],  # androidのみに限定で高速化
                            'skip': ['hls', 'dash']
                        }
                    }
                })
                logging.debug("ミックスリスト検出 - 高速化設定を適用")
            
            # デバッグ情報追加
            logging.debug(f"プレイリスト処理開始 - URL: {url}, max_songs: {max_songs}, is_mix: {is_mix}")
            logging.info(f"プレイリスト処理開始 - URL: {url}, max_songs: {max_songs}, is_mix: {is_mix}")
            
            info = await self._extract_info(url, playlist_options)
            
            # デバッグ情報追加
            logging.debug(f"抽出情報確認 - entries存在: {'entries' in info}")
            if 'entries' in info:
                entries_count = len(info['entries']) if info['entries'] else 0
                logging.debug(f"entries数: {entries_count}")
            
            if 'entries' in info and info['entries']:
                playlist_title = info.get('title', '再生リスト')
                entries_list = [entry for entry in info['entries'] if entry is not None]
                total_entries = len(entries_list)
                
                logging.debug(f"プレイリストタイトル: {playlist_title}, 有効entries数: {total_entries}")
                logging.info(f"プレイリスト詳細 - タイトル: {playlist_title}, 有効数: {total_entries}")
                
                songs = []  # URLs → songs（辞書形式）に変更
                for i, entry in enumerate(entries_list[:max_songs]):
                    if entry:
                        # extract_flat=Trueの場合の処理
                        if isinstance(entry, dict):
                            video_id = entry.get('id') or entry.get('url', '').split('/')[-1]
                            video_title = entry.get('title', f'Unknown Video {i+1}')
                        else:
                            # 文字列の場合
                            video_id = str(entry)
                            video_title = f'Video {i+1}'
                        
                        if video_id:
                            # URLの形式を統一
                            if 'youtube.com/watch' in str(video_id) or 'youtu.be/' in str(video_id):
                                video_url = str(video_id)
                            else:
                                video_url = f"https://www.youtube.com/watch?v={video_id}"
                            
                            # 辞書形式で曲情報を保存
                            song_info = {
                                'url': video_url,
                                'title': video_title
                            }
                            songs.append(song_info)
                            
                            if i < 3:  # 最初の3つのエントリをデバッグ表示（短縮）
                                logging.debug(f"エントリ{i+1}: {video_title[:30]}... - {video_url}")
                        else:
                            logging.debug(f"エントリ{i+1}: IDが見つかりません")
                
                logging.debug(f"最終的な有効曲数: {len(songs)}")
                logging.info(f"プレイリスト処理完了 - 最終曲数: {len(songs)}")
                
                return songs, playlist_title, total_entries
            else:
                error_msg = "再生リストが見つからないか、動画が含まれていません"
                logging.debug(f"エラー - {error_msg}")
                logging.debug(f"info keys: {list(info.keys()) if info else 'None'}")
                raise ValueError(error_msg)
                
        except Exception as e:
            error_msg = f"プレイリストの処理に失敗: {e}"
            logging.debug(f"例外発生 - {error_msg}")
            logging.error(error_msg)
            raise ValueError(error_msg)
    
    def set_volume(self, voice_client, volume):
        """音量を設定"""
        self.volume = volume / 100
        if voice_client and isinstance(voice_client.source, discord.PCMVolumeTransformer):
            voice_client.source.volume = self.volume
            return True
        return voice_client is not None
