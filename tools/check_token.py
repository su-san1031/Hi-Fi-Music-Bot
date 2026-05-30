import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from config import DISCORD_TOKEN

token = DISCORD_TOKEN

print(f'Token length: {len(token) if token else 0}')
print(f'Token format valid: {token and len(token) > 50 and "." in token}')

# トークンの構造チェック
if token:
    parts = token.split('.')
    print(f'Token parts: {len(parts)}')
    if len(parts) >= 3:
        print(f'Part 1 length: {len(parts[0])}')
        print(f'Part 2 length: {len(parts[1])}')
        print(f'Part 3 length: {len(parts[2])}')
