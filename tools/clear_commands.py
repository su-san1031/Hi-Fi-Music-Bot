#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
スラッシュコマンドをクリアするスクリプト
重複したコマンドを削除します
"""
import discord
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from config import DISCORD_TOKEN

if not DISCORD_TOKEN:
    print("❌ config.jsonのdiscord_tokenが見つかりません")
    exit(1)

# Clientの設定
intents = discord.Intents.default()
intents.message_content = True

class CommandCleaner(discord.Client):
    def __init__(self):
        super().__init__(intents=intents)
        
    async def on_ready(self):
        print(f'ログイン: {self.user.name}')
        
        try:
            # グローバルコマンドをクリア
            print("グローバルコマンドをクリア中...")
            await self.http.bulk_upsert_global_commands(self.application_id, [])
            print("✅ グローバルコマンドをクリアしました")
            
            # 各ギルドのコマンドもクリア
            guild_count = 0
            for guild in self.guilds:
                print(f"ギルド '{guild.name}' のコマンドをクリア中...")
                await self.http.bulk_upsert_guild_commands(self.application_id, guild.id, [])
                guild_count += 1
            
            print(f"✅ {guild_count} 個のギルドのコマンドをクリアしました")
            print("コマンドクリア完了！")
            
        except Exception as e:
            print(f"❌ エラー: {e}")
        finally:
            await self.close()

async def main():
    client = CommandCleaner()
    try:
        await client.start(DISCORD_TOKEN)
    except Exception as e:
        print(f"❌ 接続エラー: {e}")

if __name__ == "__main__":
    asyncio.run(main())
