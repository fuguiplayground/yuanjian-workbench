"""Private team distribution entry point. Never print or persist connection keys."""
import json
from pathlib import Path
import sys

import sellersprite
import server


def load_team_connection(root):
    path = Path(root) / '.team' / 'sellersprite.json'
    if not path.exists():
        return False
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
        if not isinstance(data, dict) or set(data) != {'key'} or not isinstance(data['key'], str) or not data['key'].strip():
            raise ValueError('Invalid team connection')
        sellersprite.set_team_connection(data['key'])
    except (OSError, UnicodeError, ValueError, TypeError):
        print('团队卖家精灵连接未能读取，可在「数据源与能力」重新连接。', flush=True)
        return False
    return True


def main():
    if load_team_connection(Path(__file__).resolve().parent):
        print('已载入团队卖家精灵连接，查询会共用团队额度。', flush=True)
    server.main()


if __name__ == '__main__':
    main()
