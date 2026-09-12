"""Small, read-only SellerSprite MCP client. Session credentials stay in memory."""
import hashlib
import json
import math
import os
import re
import threading
from datetime import datetime, timedelta, timezone
from urllib.request import Request, ProxyHandler, build_opener
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit, parse_qs
import credential_store
import sources

ALLOWED = {'products': 'product_research', 'keywords': 'keyword_miner', 'reviews': 'review'}
HISTORY_TOOLS = ('keepa_info', 'asin_sales_trend')


class Client:
    def __init__(self, key):
        self.key = key
        self.session = None
        self.version = '2025-03-26'
        self.counter = 0
        self.tools = {}
        self.last_http = None
        self.lock = threading.RLock()

    def rpc(self, method, params, notification=False):
        self.counter += 1
        message = {'jsonrpc': '2.0', 'method': method, 'params': params}
        if not notification:
            message['id'] = self.counter
        headers = {'secret-key': self.key, 'Content-Type': 'application/json',
                   'Accept': 'application/json, text/event-stream', 'MCP-Protocol-Version': self.version}
        if self.session:
            headers['Mcp-Session-Id'] = self.session
        req = Request('https://mcp.sellersprite.com/mcp', data=json.dumps(message).encode(), headers=headers)
        try:
            with build_opener(ProxyHandler({}), sources.NoRedirect()).open(req, timeout=45) as response:
                self.last_http = getattr(response, 'status', None)
                if response.headers.get('Mcp-Session-Id'):
                    self.session = response.headers['Mcp-Session-Id']
                if notification:
                    return {}
                if 'text/event-stream' in response.headers.get('Content-Type', ''):
                    total, lines, payload = 0, [], None
                    for raw in response:
                        total += len(raw)
                        if total > 8_000_000:
                            raise sources.SourceError('MCP 响应过大，已停止')
                        line = raw.decode('utf-8').rstrip('\r\n')
                        if line.startswith('data:'):
                            lines.append(line[5:].lstrip())
                        elif not line and lines:
                            candidate = json.loads('\n'.join(lines)); lines = []
                            if candidate.get('id') == message['id']:
                                payload = candidate; break
                    if payload is None:
                        raise sources.SourceError('MCP 未返回对应请求结果')
                else:
                    raw = response.read(8_000_001)
                    if len(raw) > 8_000_000:
                        raise sources.SourceError('MCP 响应过大，已停止')
                    payload = json.loads(raw)
        except HTTPError as error:
            self.last_http = error.code
            hints = {401: '密钥无效', 403: '密钥没有权限或未授权服务', 429: '额度或频率限制'}
            raise sources.SourceError(f'卖家精灵 HTTP {error.code}：{hints.get(error.code, "请求未成功")}，未自动重试', error.code) from None
        except (URLError, TimeoutError, OSError):
            raise sources.SourceError('卖家精灵连接超时或不可达，未自动重试') from None
        if payload.get('error'):
            raise sources.SourceError('MCP 协议请求被拒绝，请核查工具权限和参数', 200)
        return payload.get('result', {})

    def initialize(self):
        with self.lock:
            result = self.rpc('initialize', {'protocolVersion': self.version, 'capabilities': {},
                'clientInfo': {'name': 'fieldwork', 'version': '1.0'}})
            self.version = result.get('protocolVersion', self.version)
            self.rpc('notifications/initialized', {}, notification=True)
            cursor = None
            for _ in range(5):
                listing = self.rpc('tools/list', {'cursor': cursor} if cursor else {})
                self.tools.update({tool['name']: tool for tool in listing.get('tools', [])})
                cursor = listing.get('nextCursor')
                if not cursor:
                    break
            if not self.tools:
                raise sources.SourceError('密钥已连接，但没有可用 MCP 工具，请核查服务授权')

    def call(self, name, arguments):
        with self.lock:
            if name not in self.tools:
                raise sources.SourceError('该密钥未开放所需 MCP 工具')
            result = self.rpc('tools/call', {'name': name, 'arguments': arguments})
            if result.get('isError'):
                raise sources.SourceError('卖家精灵工具返回失败，请检查密钥授权、剩余额度与查询参数', 200)
            data = result.get('structuredContent')
            if not data:
                texts = [x.get('text', '') for x in result.get('content', []) if x.get('type') == 'text']
                try:
                    data = json.loads('\n'.join(texts))
                except ValueError:
                    raise sources.SourceError('卖家精灵未返回可保存的结构化数据', 200) from None
            if not isinstance(data, (dict, list)):
                raise sources.SourceError('卖家精灵返回格式不完整', 200)
            return data


_client = None
_team_key = None


def parse_connection(value):
    key = str(value or '').strip()
    if '://' in key:
        try:
            url = urlsplit(key)
            fields = parse_qs(url.query, keep_blank_values=True)
            valid = (url.scheme == 'https' and url.hostname == 'mcp.sellersprite.com'
                     and url.port in (None, 443) and url.path.rstrip('/') == '/mcp'
                     and not url.username and not url.password and not url.fragment
                     and set(fields) == {'secret-key'} and len(fields['secret-key']) == 1)
        except ValueError:
            valid = False
        if not valid:
            raise ValueError('请粘贴卖家精灵官方「复制 MCP 链接」的完整链接，或只粘贴密钥')
        key = fields['secret-key'][0]
    if not 10 <= len(key) <= 1000 or not key.isascii() or any(c.isspace() for c in key):
        raise ValueError('请输入完整的卖家精灵 MCP 链接或密钥')
    return key


def set_team_connection(key):
    """Load a private team package connection into memory without connecting."""
    global _team_key
    _team_key = parse_connection(key)


def connect(key='', persist=False):
    global _client
    if not key:
        key = (_client.key if _client else '') or (credential_store.read('sellersprite') or {}).get('key') or os.environ.get('SELLERSPRITE_SECRET_KEY') or _team_key
    key = parse_connection(key)
    client = Client(key)
    client.initialize()
    if persist:
        credential_store.save('sellersprite', {'key': key})
    _client = client
    return status()


def status():
    record = credential_store.read('sellersprite')
    saved = record is not None
    active_key = (_client.key if _client else '') or (record or {}).get('key') or os.environ.get('SELLERSPRITE_SECRET_KEY') or _team_key
    team = bool(_team_key) and active_key == _team_key
    return {'connected': _client is not None, 'tool_count': len(_client.tools) if _client else 0,
            'configured': _client is not None or saved or bool(os.environ.get('SELLERSPRITE_SECRET_KEY')) or bool(_team_key),
            'team_connection': team, 'shared_quota': team,
            'saved': saved, 'secure_storage': credential_store.backend(),
            'supported': {k: v in _client.tools for k, v in ALLOWED.items()} if _client else {},
            'storage': ('使用团队包连接，成员共用卖家精灵查询额度' + ('；首次查询时连接' if _client is None else '')) if team else
                       '已保存在本机；重启后首次查询自动连接' if saved else '仅当前服务内存；停止服务后需重新连接'}


def query(kind, keyword='', asin=''):
    global _client
    if _client is None:
        connect()
    name = ALLOWED[kind]
    if name not in _client.tools:
        raise sources.SourceError('该密钥未开放所需 MCP 工具')
    args = {'marketplace': 'US', 'page': 1, 'size': 10}
    args.update({'asin': asin} if kind == 'reviews' else {'keyword': keyword})
    if kind == 'products':
        args['matchType'] = 1
    elif kind == 'keywords':
        args['includeKeywords'] = [keyword]
    if 'request' in _client.tools[name].get('inputSchema', {}).get('properties', {}):
        args = {'request': args}
    return _client.call(name, args)


def parse(kind, payload, keyword, collected_at, product_id=''):
    data = payload
    if isinstance(data, dict) and data.get('code') not in (None, 'OK', 0, 200):
        raise sources.SourceError('卖家精灵业务请求失败，未保存数据', 200)
    if isinstance(data, dict) and 'data' in data:
        data = data['data']
    items = data if isinstance(data, list) else data.get('items') if isinstance(data, dict) else None
    if not isinstance(items, list):
        raise sources.SourceError('卖家精灵结果结构需要核对，未保存数据', 200)
    rows = []
    for r in items:
        common = {'source': '卖家精灵 MCP', 'platform': 'amazon', 'market_scope': 'Amazon 美国站',
                  'provenance': 'live', 'query': keyword, 'collected_at': collected_at}
        if kind == 'products':
            asin = str(r.get('asin') or '')
            if not asin or not r.get('title'):
                continue
            units = r.get('units')
            rows.append({**common, 'id': asin, 'title': sources.text(r['title'], 500), 'price': r.get('price'),
                'currency': 'USD', 'rating': r.get('rating'), 'review_count': r.get('ratings'), 'brand': sources.text(r.get('brand'), 100),
                'source_url': 'https://www.amazon.com/dp/' + asin, 'image': sources.safe_url(r.get('imageUrl') or r.get('image')),
                'features': [], 'sales_raw': str(units) + ' 件（父体月销量，第三方估算）' if units is not None else '',
                'sales_period': str(r.get('month') or '供应商未注明月份'), 'sales_kind': '父体月销量（第三方估算）'})
        elif kind == 'keywords':
            word = sources.text(r.get('keyword'), 300)
            if not word:
                continue
            rows.append({**common, 'id': 'ss-kw-' + hashlib.sha256(word.encode()).hexdigest()[:20], 'text': word,
                'translation': sources.text(r.get('keywordCn'), 300), 'seed': keyword, 'data_type': 'market',
                'search_volume': r.get('searches'), 'search_period': str(r.get('month') or ''), 'source_url': ''})
        else:
            body = sources.text(r.get('content'))
            if not body:
                continue
            date = sources.timestamp(r.get('date'))
            digest = hashlib.sha256((product_id + body + date).encode()).hexdigest()[:20]
            rows.append({**common, 'id': 'ss-review-' + digest, 'product_id': product_id, 'body': body,
                         'rating': r.get('star'), 'date': date, 'review_type': 'product',
                         'source_url': f'https://www.amazon.com/product-reviews/{product_id}'})
    if items and not rows:
        raise sources.SourceError('返回记录缺少关键字段，未保存数据', 200)
    return rows


def history_asin(value):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Z0-9]{10}', value):
        raise ValueError('请输入有效的 10 位 Amazon ASIN')
    return value


def query_history(tool, asin, collected_at):
    """Exactly one read-only data query; no automatic retry or polling."""
    global _client
    if tool not in HISTORY_TOOLS:
        raise ValueError('不支持的商品历史查询')
    history_asin(asin)
    if _client is None:
        connect()
    args = {'marketplace': 'US', 'asin': asin}
    if tool == 'keepa_info':
        end = datetime.fromisoformat(collected_at)
        args.update(startTimestamp=int((end - timedelta(days=90)).timestamp() * 1000),
                    endTimestamp=int(end.timestamp() * 1000), dailyLatest=True,
                    returnFields='asin,dataAsin,parentAsin,price,bsr,reviews,rating')
    else:
        args['returnFields'] = 'asin,salesTrendPoints'
    with _client.lock:
        payload = _client.call(tool, args)
        return payload, _client.last_http


def _history_date(value):
    if not isinstance(value, str):
        raise ValueError('历史时间无效')
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        raise ValueError('历史时间缺少时区')
    return parsed.astimezone(timezone.utc)


def _history_value(value, kind):
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value):
        raise ValueError('历史指标必须是有效数值')
    if value == -1:
        return None
    if value < 0 or (kind == 'rating' and value > 5):
        raise ValueError('历史指标超出范围')
    if kind in ('bsr', 'ratings_count', 'units'):
        if int(value) != value:
            raise ValueError('历史计数必须是整数')
        return None if kind == 'bsr' and value == 0 else int(value)
    return float(value)


def parse_history(tool, payload, asin, collected_at):
    """Keep only chart values and public ASIN references, never the raw response."""
    if tool not in HISTORY_TOOLS:
        raise ValueError('不支持的商品历史查询')
    history_asin(asin)
    if not isinstance(payload, dict) or payload.get('code') not in (None, 'OK', 0, 200):
        raise sources.SourceError('商品历史查询业务状态失败', 200)
    data = payload.get('data', payload)
    if not isinstance(data, dict):
        raise sources.SourceError('商品历史返回结构无效', 200)
    end = _history_date(collected_at)
    result = {'requested_asin': asin, 'source_url': 'https://www.amazon.com/dp/' + asin, 'skipped_points': 0}
    if tool == 'keepa_info':
        result.update(returned_asin=history_asin(data.get('asin')),
                      data_asin=history_asin(data.get('dataAsin') or data.get('asin')),
                      parent_asin=history_asin(data['parentAsin']) if data.get('parentAsin') else '')
        start = end - timedelta(days=90)
        result.update(range={'start': start.isoformat(), 'end': end.isoformat()}, series={})
        mapping = {'price': 'price', 'bsr': 'bsr', 'ratings_count': 'reviews', 'rating': 'rating'}
        if not any(name in data for name in mapping.values()):
            raise sources.SourceError('商品历史缺少已核验的趋势字段', 200)
        for field, name in mapping.items():
            rows = data.get(name) if data.get(name) is not None else []
            if not isinstance(rows, list) or len(rows) > 10000:
                raise sources.SourceError('商品历史点数或格式异常', 200)
            points = {}
            for point in rows:
                try:
                    if not isinstance(point, dict) or isinstance(point.get('timePoint'), bool) or \
                       not isinstance(point.get('timePoint'), (int, float)) or 'value' not in point:
                        raise ValueError('历史点结构无效')
                    at = datetime.fromtimestamp(point['timePoint'] / 1000, timezone.utc)
                    if not start <= at <= end:
                        raise ValueError('历史点超出查询日期')
                    value = _history_value(point['value'], field)
                    if at.isoformat() in points:
                        result['skipped_points'] += 1
                    points[at.isoformat()] = value
                except (ValueError, TypeError, OverflowError, OSError):
                    result['skipped_points'] += 1
            result['series'][field] = [{'at': at, 'value': points[at]} for at in sorted(points)]
    else:
        detail = data.get('asin')
        if not isinstance(detail, dict) or not isinstance(data.get('salesTrendPoints'), list):
            raise sources.SourceError('月销量历史返回结构无效', 200)
        result.update(returned_asin=history_asin(detail.get('asin')),
                      parent_asin=history_asin(detail['parent']) if detail.get('parent') else '')
        rows = data['salesTrendPoints']
        if len(rows) > 500:
            raise sources.SourceError('月销量历史点数超过上限', 200)
        months = {}
        for row in rows:
            try:
                month = row.get('month')
                if not isinstance(month, str) or not re.fullmatch(r'20\d{2}-(0[1-9]|1[0-2])', month) or month > end.strftime('%Y-%m'):
                    raise ValueError('月销量日期无效')
                point = {'month': month}
                for field, source, kind in (
                    ('price', 'price', 'price'), ('average_price', 'averagePrice', 'price'),
                    ('parent_units', 'parentUnitSales', 'units'), ('child_units', 'childUnitSales', 'units'),
                    ('parent_revenue', 'parentSalesRevenue', 'price'), ('child_revenue', 'childSalesRevenue', 'price')):
                    point[field] = _history_value(row.get(source), kind)
                if month in months:
                    result['skipped_points'] += 1
                months[month] = point
            except (ValueError, TypeError, AttributeError, OverflowError):
                result['skipped_points'] += 1
        result['months'] = [months[month] for month in sorted(months)]
    return result


def restore_watch_history(records, products):
    """Validate exported chart data by rebuilding only the public source schema."""
    if not isinstance(records, list) or len(records) > 500:
        raise ValueError('商品历史记录格式或数量无效')
    product_ids = {p['id'] for p in products if p.get('platform') == 'amazon'}
    restored = []
    seen = set()
    for record in records:
        if not isinstance(record, dict) or not re.fullmatch(r'[a-f0-9]{16}', str(record.get('id', ''))) or record['id'] in seen:
            raise ValueError('商品历史编号无效或重复')
        seen.add(record['id'])
        asin = history_asin(record.get('product_id'))
        if asin not in product_ids or record.get('marketplace') != 'US' or record.get('request_limit') != 2:
            raise ValueError('商品历史与 Amazon 美国站商品不匹配')
        created = _history_date(record.get('created_at')).isoformat()
        finished = _history_date(record['finished_at']).isoformat() if record.get('finished_at') else ''
        if finished and finished < created:
            raise ValueError('商品历史结束时间无效')
        requests = record.get('requests')
        results = record.get('results')
        if isinstance(requests, bool) or not isinstance(requests, int) or not 0 <= requests <= 2 or \
           not isinstance(results, list) or len(results) > requests:
            raise ValueError('商品历史查询次数无效')
        item = {'id': record['id'], 'product_id': asin, 'marketplace': 'US', 'source': '卖家精灵 MCP',
                'mode': 'manual', 'created_at': created, 'finished_at': finished,
                'requests': requests, 'request_limit': 2, 'results': []}
        for index, result in enumerate(results):
            tool = result.get('tool')
            if tool != HISTORY_TOOLS[index] or result.get('status') not in ('success', 'failed'):
                raise ValueError('商品历史查询来源或状态无效')
            http = result.get('http')
            if http is not None and (isinstance(http, bool) or not isinstance(http, int) or not 100 <= http <= 599):
                raise ValueError('商品历史 HTTP 状态无效')
            clean = {'tool': tool, 'status': result['status'], 'http': http,
                     'error': sources.text(result.get('error'), 300), 'data': None}
            if clean['status'] == 'success':
                if http is not None and not 200 <= http < 300:
                    raise ValueError('成功的商品历史不能带失败 HTTP 状态')
                value = result.get('data')
                if not isinstance(value, dict) or value.get('requested_asin') != asin:
                    raise ValueError('商品历史引用的 ASIN 不一致')
                history_asin(value.get('returned_asin'))
                if tool == 'keepa_info':
                    raw = {'asin': value['returned_asin'], 'dataAsin': value.get('data_asin'), 'parentAsin': value.get('parent_asin')}
                    expected_range = {'start': (_history_date(created) - timedelta(days=90)).isoformat(), 'end': created}
                    if value.get('range') != expected_range or not isinstance(value.get('series'), dict):
                        raise ValueError('商品历史查询日期范围无效')
                    for field, original in (('price', 'price'), ('bsr', 'bsr'), ('ratings_count', 'reviews'), ('rating', 'rating')):
                        rows = value['series'].get(field)
                        if not isinstance(rows, list):
                            raise ValueError('商品历史趋势格式无效')
                        raw[original] = [{'timePoint': int(_history_date(p['at']).timestamp() * 1000), 'value': p['value']} for p in rows]
                else:
                    months = value.get('months')
                    if not isinstance(months, list):
                        raise ValueError('月销量趋势格式无效')
                    raw = {'asin': {'asin': value['returned_asin'], 'parent': value.get('parent_asin')}, 'salesTrendPoints': []}
                    for point in months:
                        raw['salesTrendPoints'].append({'month': point['month'], **{source: point[field] for field, source in (
                            ('price', 'price'), ('average_price', 'averagePrice'), ('parent_units', 'parentUnitSales'),
                            ('child_units', 'childUnitSales'), ('parent_revenue', 'parentSalesRevenue'), ('child_revenue', 'childSalesRevenue'))}})
                clean['data'] = parse_history(tool, raw, asin, created)
                skipped = value.get('skipped_points', 0)
                if clean['data']['skipped_points'] or isinstance(skipped, bool) or not isinstance(skipped, int) or skipped < 0:
                    raise ValueError('商品历史包含无效或重复数据点')
                clean['data']['skipped_points'] = skipped
                clean['error'] = ''
            elif result.get('data') is not None or not clean['error']:
                raise ValueError('失败的商品历史不能包含成功数据')
            item['results'].append(clean)
        status = record.get('status')
        successes = sum(x['status'] == 'success' for x in item['results'])
        if status in ('running', 'interrupted'):
            item['status'] = 'interrupted'
        else:
            expected = 'success' if successes == 2 else 'partial' if successes else 'failed'
            if status != expected or requests != 2 or len(results) != 2 or not finished:
                raise ValueError('商品历史完成状态与结果不一致')
            item['status'] = status
        restored.append(item)
    return restored
