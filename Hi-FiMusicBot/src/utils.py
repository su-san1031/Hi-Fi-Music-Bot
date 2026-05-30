# -*- coding: utf-8 -*-
"""
音楽ボットのユーティリティ関数
"""
import json
import os
import logging
from collections import deque

class QueueManager:
    """キューの管理を行うクラス"""
    
    def __init__(self, queue_file="queue.json"):
        self.queue_file = queue_file
        self.queue = deque()  # URLとタイトルの辞書を格納
        self.current_song = {"title": None, "url": None}
        self.loop_mode = False
    
    def save_queue(self):
        """キューをファイルに保存"""
        try:
            with open(self.queue_file, "w", encoding="utf-8") as f:
                json.dump(list(self.queue), f, ensure_ascii=False, indent=2)
        except Exception as e:
            logging.error(f"キューの保存に失敗: {e}")
    
    def load_queue(self):
        """ファイルからキューを読み込み"""
        try:
            if os.path.exists(self.queue_file):
                with open(self.queue_file, "r", encoding="utf-8") as f:
                    queue_data = json.load(f)
                    # 旧形式（文字列）と新形式（辞書）の互換性を保つ
                    converted_queue = []
                    for item in queue_data:
                        if isinstance(item, str):
                            # 旧形式の場合、URLのみなのでタイトルは未設定
                            converted_queue.append({"url": item, "title": "取得中..."})
                        else:
                            # 新形式の場合、そのまま使用
                            converted_queue.append(item)
                    self.queue = deque(converted_queue)
                logging.info(f"キューを復元しました: {len(self.queue)}曲")
        except Exception as e:
            logging.error(f"キューの読み込みに失敗: {e}")
            self.queue = deque()
    
    def add_song(self, url, title="取得中...", **metadata):
        """キューに曲を追加"""
        song_info = {"url": url, "title": title or "取得中..."}
        song_info.update(metadata)
        self.queue.append(song_info)
        self.save_queue()

    def add_song_info(self, song_info):
        """辞書形式の曲情報をキューに追加"""
        self.queue.append(song_info)
        self.save_queue()
    
    def add_songs(self, song_list):
        """キューに複数の曲を追加（URLとタイトルのペアのリスト）"""
        logging.info(f"add_songs呼び出し - 追加予定曲数: {len(song_list)}")
        
        before_count = len(self.queue)
        
        # song_listが文字列のリスト（旧形式）の場合の互換性を保つ
        for item in song_list:
            if isinstance(item, str):
                self.queue.append({"url": item, "title": "取得中..."})
            else:
                self.queue.append(item)
        
        after_count = len(self.queue)
        
        logging.info(f"キューサイズ変化 - 追加前: {before_count}, 追加後: {after_count}")
        
        self.save_queue()
    
    def get_next_song(self):
        """次の曲を取得"""
        if self.queue:
            return self.queue.popleft()
        elif self.loop_mode and self.current_song["url"]:
            return dict(self.current_song)
        return None

    def peek_next_song(self):
        """次の曲を取り出さずに取得"""
        return self.queue[0] if self.queue else None

    def replace_next_song(self, expected_song, replacement_song):
        """先頭曲が変わっていなければ差し替え"""
        if self.queue and (self.queue[0] is expected_song or self.queue[0] == expected_song):
            self.queue[0] = replacement_song
            self.save_queue()
            return True
        return False
    
    def clear_queue(self):
        """キューをクリア"""
        self.queue.clear()
        self.save_queue()

    def reset_queue(self):
        """再起動・退出時用にキュー状態を完全にリセット"""
        self.queue.clear()
        self.current_song = {"title": None, "url": None}
        self.save_queue()
    
    def shuffle_queue(self):
        """キューをシャッフル"""
        import random
        random.shuffle(self.queue)
        self.save_queue()
    
    def remove_song(self, index):
        """指定インデックスの曲を削除"""
        if 0 <= index < len(self.queue):
            queue_list = list(self.queue)
            removed_song = queue_list.pop(index)
            self.queue = deque(queue_list)
            self.save_queue()
            return removed_song
        return None
    
    def remove_range(self, start_index, end_index):
        """指定範囲の曲を削除"""
        if 0 <= start_index <= end_index < len(self.queue):
            queue_list = list(self.queue)
            removed_count = end_index - start_index + 1
            del queue_list[start_index:end_index + 1]
            self.queue = deque(queue_list)
            self.save_queue()
            return removed_count
        return 0
    
    def skip_to(self, index):
        """指定インデックスまでスキップ"""
        skip_count = 0
        while skip_count < index and self.queue:
            self.queue.popleft()
            skip_count += 1
        self.save_queue()
        return skip_count

def is_playlist_or_mix(url):
    """URLが再生リストまたはミックスリストかどうかを判定"""
    playlist_indicators = [
        'list=', 'playlist', 'RD', 'RDMM', 'RDAMVM', 
        'RDCLAK', 'RDTMAK', 'WL', 'LL', 'UU', 'PL', 'FL',
    ]
    return any(indicator in url for indicator in playlist_indicators)

def setup_logging(log_file="bot_error.log"):
    """ログ設定を初期化"""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[
            logging.FileHandler(log_file, encoding="utf-8"),
            logging.StreamHandler()
        ]
    )

def safe_interaction_response(func):
    """インタラクション応答の安全なデコレータ"""
    async def wrapper(*args, **kwargs):
        try:
            return await func(*args, **kwargs)
        except Exception as e:
            logging.error(f"Interaction error in {func.__name__}: {e}")
            # エラーが発生した場合は何もしない（ログのみ）
    return wrapper
