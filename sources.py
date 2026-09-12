"""TikHub read-only adapters. Credentials and opaque cursors never enter project files."""
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import credential_store
from datetime import datetime, timezone
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit, urlunsplit
from urllib.request import Request, ProxyHandler, HTTPRedirectHandler, build_opener

LABELS = {'tiktok': 'TikTok', 'xhs': '小红书', 'reddit': 'Reddit'}
_session_connection = None
BASE_URLS = ('https://api.tikhub.dev', 'https://api.tikhub.io')
ENDPOINTS = {
    'tiktok': {'keywords': '/api/v1/tiktok/web/fetch_search_keyword_suggest',
               'translate': '/api/v1/tiktok/app/v3/fetch_content_translate',
               'posts': '/api/v1/tiktok/app/v3/fetch_video_search_result',
               'reviews': '/api/v1/tiktok/web/fetch_post_comment'},
    'xhs': {'keywords': '/api/v1/xiaohongshu/web_v3/fetch_search_suggest',
            'posts': '/api/v1/xiaohongshu/app_v2/search_notes',
            'reviews': '/api/v1/xiaohongshu/app_v2/get_note_comments'},
    'reddit': {'keywords': '/api/v1/reddit/app/fetch_search_typeahead',
               'posts': '/api/v1/reddit/app/fetch_dynamic_search',
               'reviews': '/api/v1/reddit/app/fetch_post_comments'}}


class SourceError(ValueError):
    def __init__(self, message, status=None):
        super().__init__(message)
        self.status = status


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise HTTPError(req.full_url, code, '数据源不接受重定向', headers, None)


def config():
    path = Path.home() / '.config' / 'fieldwork' / 'config.json'
    return json.loads(path.read_text()) if path.exists() else {}


def credential():
    record = _session_connection or credential_store.read('tikhub')
    if record:
        return record['key']
    if os.environ.get('TIKHUB_API_KEY'):
        return os.environ['TIKHUB_API_KEY']
    c = config()
    if sys.platform == 'darwin' and c.get('tikhub_keychain_account') and c.get('tikhub_keychain_service'):
        try:
            result = subprocess.run(['/usr/bin/security', 'find-generic-password', '-s',
                c['tikhub_keychain_service'], '-a', c['tikhub_keychain_account'], '-w'],
                capture_output=True, text=True, timeout=10)
            if result.returncode == 0 and result.stdout.strip():
                return result.stdout.strip()
        except (OSError, subprocess.TimeoutExpired):
            pass
    raise SourceError('请在「数据源与能力」粘贴 TikHub API Key 并连接。')


def api_base():
    record = _session_connection or credential_store.read('tikhub') or {}
    base = record.get('base_url') or config().get('tikhub_base_url', BASE_URLS[0])
    if base not in BASE_URLS:
        raise SourceError('数据源地址不在允许列表')
    return base


def connect(key='', base_url='', persist=False):
    global _session_connection
    key = str(key or credential()).strip()
    base_url = base_url or api_base()
    if base_url not in BASE_URLS:
        raise SourceError('请选择 TikHub 官方服务地址')
    if not 10 <= len(key) <= 1500 or not key.isascii() or any(c.isspace() for c in key) or '://' in key:
        raise SourceError('请输入 TikHub API Key，不是网页地址或账号密码')
    req = Request(base_url + '/api/v1/tikhub/user/get_user_info',
                  headers={'Authorization': 'Bearer ' + key, 'User-Agent': 'Fieldwork/1.0'})
    try:
        with build_opener(ProxyHandler({}), NoRedirect()).open(req, timeout=40) as response:
            payload = json.loads(response.read(1_000_001))
            if response.status != 200 or not isinstance(payload, dict) or payload.get('code') not in (0, 200) or \
               not isinstance(payload.get('api_key_data'), dict) or not isinstance(payload.get('user_data'), dict):
                raise SourceError('TikHub 凭据验证未通过，未保存')
    except HTTPError as error:
        error.close()
        raise SourceError(f'TikHub 验证 HTTP {error.code}，未保存；请检查密钥和账号状态', error.code) from None
    except (URLError, TimeoutError, OSError):
        raise SourceError('TikHub 验证连接失败或超时，未保存') from None
    except (ValueError, UnicodeError):
        raise SourceError('TikHub 验证响应无效，未保存') from None
    record = {'key': key, 'base_url': base_url}
    if persist:
        credential_store.save('tikhub', record)
    _session_connection = record
    return {**connection_status(), 'verified': True, 'http': 200}


def connection_status():
    saved = credential_store.read('tikhub') is not None
    public = {'saved': saved, 'secure_storage': credential_store.backend(),
              'verified': _session_connection is not None}
    try:
        credential()
        return {**public, 'configured': True, 'provider': 'TikHub', 'platforms': LABELS, 'base_url': api_base(),
                'note': '凭据可读取；每次采集仍以实际接口响应为准。'}
    except (SourceError, ValueError, OSError):
        return {**public, 'configured': False, 'provider': 'TikHub', 'platforms': LABELS, 'base_url': BASE_URLS[0],
                'note': '本机尚未配置 TikHub 凭据。'}


def request(platform, kind, params):
    base = api_base()
    translate = kind == 'translate'
    req = Request(base + ENDPOINTS[platform][kind] + ('' if translate else '?' + urlencode(params)),
                  data=json.dumps(params).encode() if translate else None,
                  headers={'Authorization': 'Bearer ' + credential(), 'User-Agent': 'Fieldwork/1.0', 'Content-Type': 'application/json'})
    try:
        with build_opener(ProxyHandler({}), NoRedirect()).open(req, timeout=40) as response:
            if response.status != 200:
                raise SourceError('数据源返回异常状态', response.status)
            payload = json.load(response)
    except HTTPError as error:
        hints = {401: '凭据无效', 402: '余额不足', 403: '接口拒绝访问', 429: '请求过于频繁'}
        raise SourceError(f'HTTP {error.code}：{hints.get(error.code, "数据源请求失败")}；未自动重试', error.code) from None
    except (URLError, TimeoutError, OSError):
        raise SourceError('连接失败或超时；本页计费状态未知，未自动重试') from None
    except (ValueError, UnicodeError):
        raise SourceError('数据源未返回有效 JSON；未自动重试') from None
    if not isinstance(payload, dict) or payload.get('code') not in (None, 0, 200):
        raise SourceError('数据源业务状态异常，未写入结果', 200)
    data = payload.get('data')
    if not isinstance(data, dict) or data.get('success') is False or data.get('status_code') not in (None, 0):
        raise SourceError('平台返回失败或结果结构异常', 200)
    return payload


def needs_translation(platform, query):
    return platform != 'xhs' and bool(re.search(r'[\u3400-\u9fff]', query))


def translate_query(query):
    payload = request('tiktok', 'translate', {'trg_lang': 'en', 'src_content': query})
    rows = payload['data'].get('translated_content_list') or []
    translated = rows[0].get('translated_content') if rows else None
    if not isinstance(translated, str) or not translated.strip() or needs_translation('tiktok', translated):
        raise SourceError('未得到有效英文译词，请输入英文或切换小红书', 200)
    return text(translated, 300)


def safe_url(value):
    p = urlsplit(str(value or ''))
    return urlunsplit((p.scheme, p.netloc, p.path, '', '')) if p.scheme in ('http', 'https') and p.hostname and not p.username else ''


def text(value, limit=12000):
    # Public content may contain contact details. Store a minimal redacted excerpt.
    s = str(value or '')[:limit]
    s = re.sub(r'[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}', '[邮箱已脱敏]', s)
    s = re.sub(r'(?<!\d)(?:\+?86[- ]?)?1[3-9]\d{9}(?!\d)', '[手机号已脱敏]', s)
    s = re.sub(r'(?<!\w)@[\w.\-]+', '[用户提及]', s)
    s = re.sub(r'https?://[^\s<>]+', lambda m: safe_url(m.group()), s)
    return s.strip()


def timestamp(value):
    if isinstance(value, (float, int)):
        try:
            return datetime.fromtimestamp(value / 1000 if value > 100000000000 else value, timezone.utc).isoformat()
        except (ValueError, OverflowError, OSError):
            return ''
    return str(value or '')[:100]


def metric(value, signed=False):
    if isinstance(value, bool) or value in (None, ''):
        return None
    try:
        n = float(value)
        return int(n) if (signed or n >= 0) and n.is_integer() else None
    except (TypeError, ValueError, OverflowError):
        return None


def base_row(platform, query, collected_at):
    return {'platform': platform, 'source': LABELS[platform] + ' · TikHub',
            'query': text(query, 300), 'collected_at': collected_at, 'provenance': 'live',
            'market_scope': '中文平台讨论，非美国买家样本' if platform == 'xhs' else
                'US 搜索区域；用户实际地域未确认' if platform == 'tiktok' else '全站搜索；用户实际地域未确认'}


def params_for(platform, kind, query, post=None, cursor=None):
    if kind == 'keywords':
        return {'query' if platform == 'reddit' else 'keyword': query}
    if kind == 'posts':
        p = ({'keyword': query, 'count': 20, 'offset': 0, 'region': 'US'} if platform == 'tiktok' else
             {'keyword': query, 'page': 1, 'sort_type': 'general', 'note_type': '不限', 'time_filter': '不限'} if platform == 'xhs' else
             {'query': query, 'search_type': 'post', 'sort': 'RELEVANCE', 'time_range': 'all', 'need_format': 'true'})
    else:
        p = ({'aweme_id': post['external_id'], 'cursor': 0, 'count': 20} if platform == 'tiktok' else
             {'note_id': post['external_id'], 'sort_strategy': 'latest_v2'} if platform == 'xhs' else
             {'post_id': post['external_id'], 'sort_type': 'CONFIDENCE', 'need_format': 'true'})
    return {**p, **(cursor or {})}


def parse(platform, kind, payload, query, collected_at, post=None):
    d = payload['data']
    common = base_row(platform, query, collected_at)
    rows, next_cursor, skipped = [], None, 0
    if kind == 'keywords':
        if platform == 'tiktok':
            # A verified successful response omits data when it has no suggestions.
            items = d.get('data', []) if d.get('status_code') == 0 else d['data']
            words = [r.get('word') for r in items]
        elif platform == 'xhs':
            words = [r.get('text') for r in d['data']['sug_items']]
        else:
            children = d['search']['dynamic']['components']['main']
            words = []
            for group in children:
                for item in group.get('children', []):
                    p = item.get('presentation', {})
                    if isinstance(p.get('suggestion'), str) and isinstance(p.get('query'), str):
                        words.append(p['suggestion'].replace('%query%', p['query']))
        for word in words:
            word = text(word, 300)
            if word:
                digest = hashlib.sha256((query + '|' + word).encode()).hexdigest()[:20]
                rows.append({**common, 'id': platform + '-kw-' + digest, 'text': word, 'seed': query,
                             'data_type': 'suggestion', 'source_url': '', 'intent': '未分类'})
        return rows, None, skipped
    if kind == 'posts':
        if platform == 'tiktok':
            if not any(key in d for key in ('search_item_list', 'aweme_list')):
                raise ValueError('TikTok 内容结构不完整')
            raw = [r['aweme_info'] for r in d.get('search_item_list', []) if r.get('aweme_info')] or d.get('aweme_list', [])
            if d.get('has_more') and d.get('cursor') is not None:
                next_cursor = {'offset': d['cursor']}
        elif platform == 'xhs':
            raw = [r['note'] for r in d['data']['items'] if r.get('note')]
            if d.get('next_page') and raw:
                next_cursor = {k: d[k] for k in ('search_id', 'search_session_id') if d.get(k)}
                next_cursor['page'] = d['next_page']
        else:
            main = d['search']['dynamic']['components']['main']
            raw = [c['post'] for edge in main['edges'] for c in edge['node'].get('children', []) if c.get('post')]
            if main.get('pageInfo', {}).get('hasNextPage') and main['pageInfo'].get('endCursor'):
                next_cursor = {'after': main['pageInfo']['endCursor']}
        for r in raw:
            id_ = str(r.get('aweme_id') if platform == 'tiktok' else r.get('id') or '')
            if not id_ or id_ == 'None':
                skipped += 1
                continue
            if platform == 'tiktok':
                title, body = r.get('desc'), r.get('desc')
                stats = r.get('statistics', {})
                likes, count, created = stats.get('digg_count'), stats.get('comment_count'), r.get('create_time')
                url = f'https://www.tiktok.com/@_/video/{id_}'
            elif platform == 'xhs':
                title, body = r.get('title') or r.get('desc'), r.get('desc')
                likes, count, created = r.get('liked_count'), r.get('comments_count'), r.get('timestamp')
                url = f'https://www.xiaohongshu.com/explore/{id_}'
            else:
                title, body = r.get('postTitle'), r.get('content', {}).get('markdown')
                likes, count, created = r.get('score'), r.get('commentCount'), r.get('createdAt')
                url = 'https://www.reddit.com' + r['permalink'] if r.get('permalink', '').startswith('/') else r.get('url')
            rows.append({**common, 'id': platform + '-' + id_, 'external_id': id_,
                         'title': text(title, 500) or '无标题内容', 'body': text(body),
                         'source_url': safe_url(url), 'likes': metric(likes, platform == 'reddit'), 'comment_count': metric(count),
                         'posted_at': timestamp(created)})
    else:
        if platform == 'tiktok':
            if 'comments' not in d:
                raise ValueError('TikTok 评论结构不完整')
            raw = d.get('comments') or []
            if d.get('has_more') and d.get('cursor') is not None:
                next_cursor = {'cursor': d['cursor']}
        elif platform == 'xhs':
            b = d['data']; raw = []
            for r in b['comments']:
                raw.append(r)
                raw.extend(r.get('sub_comments') or [])
            if b.get('has_more') and b.get('cursor'):
                next_cursor = {'cursor': b['cursor']}
                try:
                    ctx = json.loads(b['cursor'])
                    next_cursor.update({k: ctx[k] for k in ('index', 'pageArea') if k in ctx})
                except (ValueError, TypeError):
                    pass
        else:
            forest = d['postInfoById']['commentForest']
            raw = []
            def visit(trees):
                nonlocal next_cursor
                for tree in trees:
                    if tree.get('node'):
                        raw.append(tree['node'])
                    if tree.get('more', {}).get('cursor') and not tree['more'].get('isTooDeepForCount'):
                        next_cursor = {'after': tree['more']['cursor']}
                    if isinstance(tree.get('children'), list):
                        visit(tree['children'])
            visit(forest['trees'])
        for r in raw:
            id_ = r.get('cid') if platform == 'tiktok' else r.get('id')
            body = r.get('text') if platform == 'tiktok' else r.get('content') if platform == 'xhs' else r.get('content', {}).get('markdown')
            if not id_ or not body or r.get('isRemoved') or r.get('isAdminTakedown'):
                skipped += 1
                continue
            date = r.get('create_time') if platform == 'tiktok' else r.get('time') if platform == 'xhs' else r.get('createdAt')
            url = 'https://www.reddit.com' + r['permalink'] if platform == 'reddit' and r.get('permalink', '').startswith('/') else post['source_url']
            rows.append({**common, 'id': platform + '-c-' + str(id_), 'post_id': post['id'], 'product_id': '',
                         'body': text(body), 'date': timestamp(date), 'review_type': 'social',
                         'source_url': safe_url(url), 'rating': None,
                         'like_count': metric(r.get('digg_count') if platform == 'tiktok' else r.get('like_count') if platform == 'xhs' else r.get('score'), platform == 'reddit')})
    return rows, next_cursor, skipped
