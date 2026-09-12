#!/usr/bin/env python3
"""本地工作台。运行 python3 server.py，无第三方依赖。"""
import argparse
import copy
import csv
import errno
import hashlib
import io
import json
import math
import os
from pathlib import Path
import re
import socket
import threading
import uuid
from datetime import datetime, timezone
from http.client import HTTPException
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs
from urllib.request import build_opener, ProxyHandler
from urllib.error import HTTPError
import sources
import sellersprite
from business_flow import normalize_workspace
import device_setup
from collection_jobs import CollectionJobs
from ai_jobs import AIJobs, normalize_ai_report

ROOT = Path(__file__).resolve().parent
BUILD_ID = hashlib.sha256(b''.join((ROOT / name).read_bytes() for name in (
    'business_flow.py', 'server.py', 'sources.py', 'sellersprite.py', 'device_setup.py',
    'credential_store.py', 'collection_jobs.py', 'keyword_expansion.py', 'ai_jobs.py', 'ai_modules.py', 'codex_runner.py',
    'prompts/sanjin.json', 'skills/consumer-motivation-insight/analysis.md'))).hexdigest()
LOCK = threading.RLock()
KINDS = ('keywords', 'products', 'posts', 'reviews')


def now():
    return datetime.now(timezone.utc).isoformat()


def uid():
    return uuid.uuid4().hex[:16]


def clean_url(value):
    value = str(value or '').strip()
    parsed = urlparse(value)
    if parsed.scheme in ('https', 'http') and parsed.hostname and not parsed.username:
        # 共享项目不保留查询签名、追踪参数或 fragment。
        return f'{parsed.scheme}://{parsed.netloc}{parsed.path}'
    return ''


def string(value, maximum=12000):
    return str(value or '').strip()[:maximum]


def boolean(value):
    return value is True or str(value).lower() in ('true', '1')


def number(value, maximum=None, minimum=0):
    if value is None or value == '':
        return None
    if isinstance(value, bool):
        raise ValueError('数值不能是布尔值')
    result = float(value)
    if not math.isfinite(result) or result < minimum or (maximum is not None and result > maximum):
        raise ValueError('数值超出允许范围')
    return result


def count_value(value):
    result = number(value)
    if result is None or not result.is_integer():
        raise ValueError('计数字段必须是非负整数')
    return int(result)


def normalize(kind, row, provenance='import'):
    base = {'id': string(row.get('id'), 100) or uid(), 'provenance': provenance,
            'source': string(row.get('source'), 200) or '用户导入',
            'source_url': clean_url(row.get('source_url')),
            'collected_at': string(row.get('collected_at'), 100) or now()}
    base.update(platform=string(row.get('platform'), 30), query=string(row.get('query'), 300),
                original_query=string(row.get('original_query'), 300),
                market_scope=string(row.get('market_scope'), 200))
    if kind == 'keywords':
        text = string(row.get('text'), 300)
        if not text:
            raise ValueError('缺少关键词 text')
        base.update(text=text, translation=string(row.get('translation'), 300),
                    intent=string(row.get('intent'), 100) or '未分类',
                    scene=string(row.get('scene'), 200), seed=string(row.get('seed'), 300),
                    favorite=boolean(row.get('favorite', False)),
                    data_type=row.get('data_type') if row.get('data_type') in ('ai', 'market') else 'suggestion',
                    search_volume=number(row.get('search_volume')), search_period=string(row.get('search_period'), 100))
        if 'round' in row:
            round_ = count_value(row['round'])
            if not 1 <= round_ <= 6 or row.get('expansion') not in ('seed', 'az', 'prefix', 'suffix', 'suggestion'):
                raise ValueError('关键词采集轮次或扩词方式无效')
            base.update(round=round_, parent_query=string(row.get('parent_query'), 300), expansion=row['expansion'])
    elif kind == 'products':
        if not row.get('id'):
            raise ValueError('商品必须包含唯一 id，例如 ASIN')
        title = string(row.get('title'), 500)
        if not title:
            raise ValueError('缺少商品 title')
        features = row.get('features', [])
        if isinstance(features, str):
            features = [s.strip() for s in features.split('|') if s.strip()]
        if not isinstance(features, list):
            raise ValueError('features 应为数组或以 | 分隔的文字')
        count = number(row.get('review_count'))
        if count is not None and not count.is_integer():
            raise ValueError('评论数量应为整数')
        base.update(title=title, price=number(row.get('price')), currency=string(row.get('currency'), 10),
                    rating=number(row.get('rating'), 5), review_count=int(count) if count is not None else None,
                    sales_raw=string(row.get('sales_raw'), 250), sales_period=string(row.get('sales_period'), 100) or '周期未知',
                    sales_kind=string(row.get('sales_kind'), 100) or '未注明',
                    features=[string(f, 500) for f in features[:20]], image=clean_url(row.get('image')),
                    brand=string(row.get('brand'), 100), candidate=boolean(row.get('candidate', False)),
                    watched=boolean(row.get('watched', False)))
    elif kind == 'posts':
        if not row.get('id') or not row.get('title') or row.get('platform') not in sources.LABELS:
            raise ValueError('内容必须包含 id、title 和有效 platform')
        base.update(title=string(row['title'], 500), body=string(row.get('body')),
                    translation=string(row.get('translation')),
                    external_id=string(row.get('external_id'), 100), posted_at=string(row.get('posted_at'), 100),
                    likes=number(row.get('likes'), minimum=-float('inf') if base['platform'] == 'reddit' else 0), comment_count=number(row.get('comment_count')))
    else:
        if not (row.get('product_id') or row.get('post_id')) or not row.get('body'):
            raise ValueError('评论必须包含 product_id 或 post_id，以及 body')
        if row.get('post_id') and row.get('review_type') != 'social':
            raise ValueError('社交内容评论的 review_type 必须为 social')
        base.update(product_id=string(row.get('product_id'), 100), post_id=string(row.get('post_id'), 100), body=string(row['body']),
                    translation=string(row.get('translation')), rating=number(row.get('rating'), 5),
                    like_count=number(row.get('like_count'), minimum=-float('inf') if base['platform'] == 'reddit' else 0),
                    date=string(row.get('date'), 100),
                    review_type='social' if row.get('review_type') == 'social' else 'product')
    return base


def new_project(name, keyword):
    return {'schema_version': 1, 'id': uid(), 'name': string(name, 120) or '未命名调研',
            'keyword': string(keyword, 300), 'market': '美国', 'platform': 'Amazon', 'language': '英文',
            'created_at': now(), 'updated_at': now(), 'revision': 0, 'data_version': 0,
            'keywords': [], 'products': [], 'posts': [], 'reviews': [], 'analyses': [], 'ai_reports': [],
            'watch_history': [], 'runs': [], 'demo': False, 'decision_workspace': normalize_workspace({})}


def demo_project():
    p = new_project('便携榨汁杯 · 产品体验', 'portable blender')
    p['demo'] = True
    keywords = [
        ('portable blender', '便携榨汁杯', '了解产品', '日常随行'),
        ('portable blender for smoothies', '便携果昔搅拌杯', '寻找商品', '早餐果昔'),
        ('portable blender easy to clean', '容易清洗的便携榨汁杯', '比较商品', '清洁维护'),
        ('portable blender leaking', '便携榨汁杯漏水', '解决使用问题', '通勤携带'),
        ('portable blender battery life', '便携榨汁杯续航', '比较商品', '出门使用'),
        ('portable blender lid stuck', '榨汁杯盖子打不开', '解决使用问题', '使用维护'),
        ('portable blender for office', '办公室便携榨汁杯', '寻找商品', '办公室'),
        ('portable blender not charging', '便携榨汁杯无法充电', '解决使用问题', '充电故障'),
        ('portable blender vs personal blender', '便携与个人搅拌机比较', '比较商品', '选购比较'),
        ('portable blender for travel', '旅行便携榨汁杯', '寻找商品', '旅行'),
        ('portable blender small bag', '适合小包携带的榨汁杯', '待验证', '通勤携带'),
        ('portable blender quiet office', '办公室安静使用的榨汁杯', '待验证', '办公室')]
    for i, (text, translation, intent, scene) in enumerate(keywords):
        p['keywords'].append(normalize('keywords', {'id': f'k{i+1}', 'text': text, 'translation': translation,
            'intent': intent, 'scene': scene, 'seed': 'portable blender', 'source': '虚构演示样本',
            'data_type': 'ai' if i > 9 else 'suggestion', 'favorite': i in (2, 3)}, 'demo'))
    for i, (name, price, size, feature) in enumerate([
        ('Daily Blend 随行杯', 39.99, '480 mL', '可拆卸杯体'),
        ('Go Mix 轻巧杯', 29.99, '350 mL', '随行提带'),
        ('Studio Blend 大容量杯', 54.99, '600 mL', '杯身刻度'),
        ('Pocket Juice 迷你杯', None, '300 mL', '紧凑杯身')]):
        p['products'].append(normalize('products', {'id': f'p{i+1}', 'title': name, 'price': price,
            'currency': 'USD', 'brand': name.split(' ')[0], 'source': '虚构演示样本',
            'features': [size, feature], 'candidate': i < 3}, 'demo'))
    reviews = [
        ('p1', 'I use it at the office for my morning smoothie. The cup comes apart for cleaning.', '我在办公室用它做早餐果昔，杯子可以拆开清洗。', 5),
        ('p1', 'Cleaning the lid takes longer than I expected.', '清洗杯盖比我预想的费时间。', 3),
        ('p1', 'It leaked inside my bag when I carried it to work.', '带去上班时，它在包里漏水了。', 2),
        ('p1', 'The battery needed charging after a few uses.', '用了几次就需要充电。', 3),
        ('p2', 'The small cup fits my bag and is easy to carry.', '小杯子能装进包里，携带方便。', 5),
        ('p2', 'I wish the cup held more of my breakfast smoothie.', '我希望它能装下更多早餐果昔。', 3),
        ('p2', 'The battery stopped charging after two weeks.', '两周后电池无法充电。', 1),
        ('p2', 'The lid is difficult to clean around the seal.', '杯盖密封圈附近不容易清洁。', 2),
        ('p3', 'The larger cup is useful for my morning smoothie.', '大杯子适合装我的早餐果昔。', 5),
        ('p3', 'It is too bulky for my office bag.', '它太大了，不适合放进我的通勤包。', 2),
        ('p3', 'The cup is easy to clean but the lid gets stuck.', '杯子容易清洗，但盖子会卡住。', 3),
        ('p3', 'I like the markings when adding ingredients.', '添加食材时，杯身刻度很有用。', 5)]
    for i, (product, body, translation, rating) in enumerate(reviews):
        p['reviews'].append(normalize('reviews', {'id': f'r{i+1}', 'product_id': product, 'body': body,
            'translation': translation, 'rating': rating, 'source': '虚构演示样本'}, 'demo'))
    p['data_version'] = 1
    return p


THEMES = [
    ('清洁与维护', 'clean|wash|清洗|清洁', '清洁步骤会影响日常使用。核对杯盖、密封圈是否可拆洗。'),
    ('携带与密封', 'leak|bag|carry|bulky|漏水|携带|通勤包', '携带需求与漏水、体积问题需要分别验证，不能直接承诺防漏。'),
    ('充电与续航', 'battery|charg|电池|充电|续航', '核对实际续航与充电稳定性，记录测试条件。'),
    ('早餐与容量', 'smoothie|breakfast|larger|held more|果昔|容量', '核对容量是否匹配一份早餐，以及携带时的体积。'),
    ('杯盖使用', 'lid.*stuck|盖子.*卡|打不开', '验证杯盖在使用后是否容易打开。')]


def analyze(p):
    insights = []
    for label, pattern, action in THEMES:
        for review_type, platform in [('product', '')] + [('social', x) for x in ['', *sources.LABELS]]:
            matches = [r for r in p['reviews'] if r['review_type'] == review_type and
                       (review_type == 'product' or r.get('platform', '') == platform) and
                       re.search(pattern, r['body'] + ' ' + r['translation'], re.I)]
            if matches:
                insights.append({'id': uid(), 'title': label + (' · ' + sources.LABELS[platform] if platform else ''), 'action': action, 'review_type': review_type,
                    'evidence_ids': [r['id'] for r in matches], 'count': len(matches),
                    'sample_size': sum(r['review_type'] == review_type and (review_type == 'product' or r.get('platform', '') == platform) for r in p['reviews'])})
    decisions = []
    for product in p['products']:
        if not product['candidate']:
            continue
        reviews = [r for r in p['reviews'] if r['product_id'] == product['id'] and r['review_type'] == 'product']
        decisions.append({'product_id': product['id'], 'status': '继续观察',
            'reason': f'已整理 {len(reviews)} 条商品评价样本；尚缺采购、物流、退货与实际性能验证，暂不足以确定优先级。',
            'evidence_ids': [r['id'] for r in reviews],
            'keyword_ids': [k['id'] for k in p['keywords'] if k['data_type'] != 'ai'][:10],
            'missing': ['采购与物流成本', '广告与退货数据', '真实使用测试'] + ([] if reviews else ['评论正文'])})
    return {'id': uid(), 'created_at': now(), 'data_version': p['data_version'], 'method': '规则整理',
            'scope': {'total': len(p['reviews']), 'analyzed': len(p['reviews']), 'unanalyzed': 0,
                      'selection': '全部已导入样本；按中英文词组匹配主题，同一评论可属于多个主题，不推断情绪或市场占比'},
            'insights': insights, 'decisions': decisions}


class Store:
    def __init__(self, path):
        self.path = Path(path)
        self.path.mkdir(parents=True, exist_ok=True)

    def folder(self, project_id):
        if not re.fullmatch(r'[a-f0-9]{16}', project_id):
            raise ValueError('项目编号无效')
        return self.path / project_id

    def load(self, project_id):
        folder = self.folder(project_id)
        manifest = json.loads((folder / 'current.json').read_text())
        target = manifest['file']
        if not re.fullmatch(r'v\d+-[a-f0-9]+\.json', target):
            raise ValueError('项目版本路径无效')
        payload = (folder / target).read_bytes()
        if hashlib.sha256(payload).hexdigest() != manifest['sha256']:
            raise ValueError('项目文件不完整，请等待同步完成后重试')
        project = json.loads(payload)
        project.setdefault('posts', [])
        project.setdefault('ai_reports', [])
        project.setdefault('watch_history', [])
        project.setdefault('decision_workspace', normalize_workspace({}))
        return project

    def save(self, p, expected=None):
        with LOCK:
            folder = self.folder(p['id'])
            folder.mkdir(exist_ok=True)
            if (folder / 'current.json').exists():
                current = self.load(p['id'])
                if expected != current['revision']:
                    raise Conflict('项目已被更新，请重新打开后再操作')
            p['revision'] += 1
            p['updated_at'] = now()
            payload = json.dumps(p, ensure_ascii=False, indent=2, allow_nan=False).encode()
            filename = f'v{p["revision"]:06d}-{uid()}.json'
            self.atomic(folder / filename, payload)
            manifest = {'file': filename, 'sha256': hashlib.sha256(payload).hexdigest()}
            self.atomic(folder / 'current.json', json.dumps(manifest).encode())
            return p

    @staticmethod
    def atomic(path, content):
        temp = path.with_name(path.name + '.' + uid() + '.tmp')
        with open(temp, 'wb') as file:
            file.write(content)
            file.flush()
            os.fsync(file.fileno())
        os.replace(temp, path)

    def listing(self):
        result = []
        for file in self.path.glob('*/current.json'):
            try:
                p = self.load(file.parent.name)
                result.append({key: p[key] for key in ('id', 'name', 'keyword', 'updated_at', 'demo', 'revision')} |
                    {'counts': {kind: len(p[kind]) for kind in KINDS}})
            except (OSError, ValueError, KeyError):
                result.append({'id': file.parent.name, 'name': '项目暂不可读取', 'error': '文件缺失或同步未完成'})
        return sorted(result, key=lambda p: p.get('updated_at', ''), reverse=True)


class Conflict(ValueError):
    pass


def import_rows(p, kind, rows, provenance=None, record_run=True):
    if kind not in KINDS or not isinstance(rows, list) or len(rows) > 5000:
        raise ValueError('每次请选择一种数据，最多导入 5000 行')
    provenance = 'demo' if p['demo'] else provenance or 'import'
    p.setdefault(kind, [])
    existing = {r['id'] for r in p[kind]}
    products = {r['id'] for r in p['products']}
    posts = {r['id'] for r in p.get('posts', [])}
    def signature(row):
        if kind == 'keywords':
            return (row['text'].casefold(), row['data_type'], row.get('platform', ''))
        if kind == 'reviews':
            return (row.get('post_id') or row['product_id'], row['body'].strip(), row['date'], row['review_type'])
        return (row['id'],)
    signatures = {signature(r) for r in p[kind]}
    errors, imported, duplicates = [], 0, 0
    for index, row in enumerate(rows):
        try:
            if not isinstance(row, dict):
                raise ValueError('记录必须是对象')
            data = normalize(kind, row, provenance)
            if kind == 'reviews':
                if data.get('post_id'):
                    if data['post_id'] not in posts:
                        raise ValueError('对应内容不存在，请先采集或导入内容')
                    parent = next(r for r in p['posts'] if r['id'] == data['post_id'])
                    if data['platform'] != parent['platform']:
                        raise ValueError('评论平台与内容不一致')
                elif data['product_id'] not in products:
                    raise ValueError('对应商品不存在，请先导入商品')
            sig = signature(data)
            if data['id'] in existing or sig in signatures:
                duplicates += 1
                continue
            p[kind].append(data)
            existing.add(data['id'])
            signatures.add(sig)
            imported += 1
        except (ValueError, TypeError, AttributeError) as error:
            errors.append({'row': index + 1, 'reason': str(error)[:160]})
    run = {'id': uid(), 'kind': kind, 'created_at': now(), 'requested': len(rows), 'imported': imported,
           'duplicates': duplicates, 'errors': errors, 'source': '文件导入', 'pages': None,
           'status': 'partial' if errors and imported else 'failed' if errors else 'success'}
    if record_run:
        p['runs'].append(run)
    if imported:
        p['data_version'] += 1
    return run


def restore_collection_details(original, restored, project):
    allowed = {'xhs', 'tiktok', 'reddit', 'amazon'}
    advanced = restored['kind'] == 'keywords' and original.get('keyword_mode') in ('az', 'intent')
    max_requests = 500 if advanced else 20
    if len(original.get('page_results', [])) > max_requests:
        raise ValueError('采集页面数量超出预算范围')
    def errors(rows):
        return [{**{'row': count_value(e.get('row', 0)), 'reason': string(e.get('reason'), 300)},
                 **{k: string(e[k], 300) if k != 'http' else e[k]
                    for k in ('platform', 'query', 'http') if k in e}} for e in rows[:max(200, max_requests)]]
    restored['errors'] = errors(original.get('errors', []))
    if 'platforms' in original:
        platforms = original['platforms']
        if not isinstance(platforms, list) or not platforms or len(platforms) > 4 or \
                any(x not in allowed for x in platforms) or len(set(platforms)) != len(platforms):
            raise ValueError('采集任务平台列表无效')
        restored['platforms'] = list(platforms)
    if 'budget' in original:
        b = original['budget']
        restored['budget'] = {k: count_value(b[k]) for k in ('tikhub_requests', 'mcp_queries')}
        restored['budget'].update(estimated_tikhub_usd=number(b.get('estimated_tikhub_usd')),
                                  note=string(b.get('note'), 500))
        if sum(restored['budget'][k] for k in ('tikhub_requests', 'mcp_queries')) != restored['request_limit']:
            raise ValueError('采集请求预算不一致')
        if 'translation_requests' in b:
            restored['budget']['translation_requests'] = count_value(b['translation_requests'])
            if restored['budget']['translation_requests'] > restored['budget']['tikhub_requests']:
                raise ValueError('翻译预留超过 TikHub 预算')
    if 'platform_results' in original:
        summaries = []
        for x in original['platform_results']:
            if x.get('platform') not in allowed:
                raise ValueError('采集摘要平台无效')
            summary = {k: count_value(x[k]) for k in ('pages', 'requests', 'imported', 'duplicates')}
            summary.update(platform=x['platform'], status=string(x.get('status'), 30),
                           errors=errors(x.get('errors', [])),
                           query_pairs=[{k: string(pair[k], 300) for k in ('original', 'query', 'post_id') if k in pair}
                                        for pair in x.get('query_pairs', [])[:max_requests]])
            if 'keyword_mode' in original:
                summary.update(query_limit=count_value(x.get('query_limit', 0)),
                               current_round=count_value(x.get('current_round', 0)),
                               capped=x.get('capped') is True, stop_reason=string(x.get('stop_reason'), 30))
            summaries.append(summary)
        if [x['platform'] for x in summaries] != restored.get('platforms'):
            raise ValueError('采集摘要与平台列表不一致')
        if any(sum(x[k] for x in summaries) != restored[k] for k in ('pages', 'requests', 'imported', 'duplicates')):
            raise ValueError('各平台采集计数不一致')
        restored['platform_results'] = summaries
    if not 0 <= restored['requests'] <= restored['request_limit'] <= max_requests:
        raise ValueError('采集请求数超出范围')
    if 'keyword_mode' in original:
        mode, rounds = original['keyword_mode'], count_value(original.get('rounds', 1))
        stop_reasons = ('', 'completed', 'budget', 'cancelled', 'source_blocked', 'error')
        if restored['kind'] != 'keywords' or mode not in ('quick', 'az', 'intent') or not 1 <= rounds <= 6 or mode == 'quick' and rounds != 1:
            raise ValueError('采词模式或轮数无效')
        restored.update(keyword_mode=mode, rounds=rounds, current_round=count_value(original.get('current_round', 0)),
                        capped=original.get('capped') is True, stop_reason=string(original.get('stop_reason'), 30), round_results=[])
        if restored['current_round'] > rounds or restored['stop_reason'] not in stop_reasons or not isinstance(original.get('capped'), bool):
            raise ValueError('采词停止状态或轮次无效')
        seen_rounds = set()
        for row in original.get('round_results', []):
            result = {k: count_value(row[k]) for k in ('round', 'queries', 'new_keywords', 'duplicates')}
            result.update(platform=row.get('platform'), status=row.get('status'))
            key = (result['platform'], result['round'])
            if result['platform'] not in restored.get('platforms', []) or not 1 <= result['round'] <= rounds or key in seen_rounds or result['status'] not in ('running', 'success', 'partial', 'failed', 'cancelled', 'capped', 'interrupted'):
                raise ValueError('分轮采集记录无效')
            seen_rounds.add(key)
            restored['round_results'].append(result)
        if sum(r['queries'] for r in restored['round_results']) != len(restored['page_results']) or \
           sum(r['new_keywords'] for r in restored['round_results']) != restored['imported'] or \
           sum(r['duplicates'] for r in restored['round_results']) != restored['duplicates']:
            raise ValueError('分轮采集计数不一致')
        for summary in restored.get('platform_results', []):
            if not 1 <= summary['query_limit'] <= restored['request_limit'] or summary['current_round'] > rounds or summary['stop_reason'] not in stop_reasons:
                raise ValueError('平台采词额度或状态无效')
    for page in restored['page_results']:
        if page.get('platform') and page['platform'] not in allowed:
            raise ValueError('采集页面平台无效')
        for field in ('query', 'original_query', 'post_id', 'error'):
            if field in page:
                page[field] = string(page[field], 500 if field == 'error' else 300)
        if 'round' in page:
            page['round'] = count_value(page['round'])
            page['parent_query'] = string(page.get('parent_query'), 300)
            if not 1 <= page['round'] <= restored.get('rounds', 1) or page.get('expansion') not in ('seed', 'az', 'prefix', 'suffix', 'suggestion'):
                raise ValueError('采集页面的扩词来源无效')
        if page.get('post_id') and not any(p['id'] == page['post_id'] and
                (not page.get('platform') or p['platform'] == page['platform']) for p in project['posts']):
            raise ValueError('采集页面引用了不存在的内容')
    if 'keyword_mode' in original:
        summaries = restored.get('platform_results', [])
        translation_limit = restored.get('budget', {}).get('translation_requests', 0)
        if not summaries or sum(s['query_limit'] for s in summaries) + translation_limit != restored['request_limit']:
            raise ValueError('平台查询额度与翻译预留不一致')
        pages = restored['page_results']
        for page in pages:
            if page.get('platform') not in restored.get('platforms', []) or page.get('kind') != 'keywords' or 'round' not in page:
                raise ValueError('采词页面缺少有效的平台或轮次')
            for key in ('page', 'returned', 'imported', 'duplicates', 'skipped'):
                page[key] = count_value(page.get(key))
            if page['page'] != 1 or page['imported'] + page['duplicates'] > page['returned']:
                raise ValueError('采词页面计数无效')
            http = page.get('http')
            if http is not None and (isinstance(http, bool) or not isinstance(http, int) or not 100 <= http <= 599):
                raise ValueError('采词页面 HTTP 状态无效')
            expansion = page['expansion']
            first_expansions = ('seed',) if mode == 'quick' else ('seed', 'az') if mode == 'az' else ('seed', 'prefix', 'suffix')
            if expansion not in (first_expansions if page['round'] == 1 else ('suggestion',)):
                raise ValueError('采词页面的轮次与扩词方式不一致')
        if sum(p['returned'] for p in pages) != restored['requested'] or \
           sum(p['imported'] for p in pages) != restored['imported'] or \
           sum(p['duplicates'] for p in pages) != restored['duplicates'] or \
           not len(pages) <= restored['requests'] <= len(pages) + translation_limit:
            raise ValueError('采词页面与任务计数不一致')
        if len(restored.get('translations', [])) > restored['requests'] - len(pages):
            raise ValueError('采词翻译记录超过已发出请求数')
        if restored['current_round'] != (pages[-1]['round'] if pages else 0):
            raise ValueError('当前轮次与最后查询不一致')
        grouped = {(r['platform'], r['round']): r for r in restored['round_results']}
        if set(grouped) != {(p['platform'], p['round']) for p in pages}:
            raise ValueError('分轮记录与查询页面不对应')
        for key, result in grouped.items():
            selected = [p for p in pages if (p['platform'], p['round']) == key]
            if result['queries'] != len(selected) or result['new_keywords'] != sum(p['imported'] for p in selected) or \
               result['duplicates'] != sum(p['duplicates'] for p in selected):
                raise ValueError('分轮采集与对应页面计数不一致')
        for summary in summaries:
            selected = [p for p in pages if p['platform'] == summary['platform']]
            if len(selected) > summary['query_limit'] or not len(selected) <= summary['requests'] <= len(selected) + translation_limit or \
               summary['pages'] != sum(p.get('http') == 200 and not p.get('error') for p in selected) or \
               summary['imported'] != sum(p['imported'] for p in selected) or \
               summary['duplicates'] != sum(p['duplicates'] for p in selected) or \
               summary['current_round'] != max((p['round'] for p in selected), default=0):
                raise ValueError('平台摘要与查询页面不一致')
    if restored['status'] == 'running':
        restored['status'] = 'interrupted'
        for row in restored.get('platform_results', []):
            if row['status'] in ('pending', 'running'):
                row['status'] = 'interrupted'
        for row in restored.get('round_results', []):
            if row['status'] == 'running':
                row['status'] = 'interrupted'


def restore_project(original):
    if not isinstance(original, dict) or original.get('schema_version') != 1:
        raise ValueError('不支持的项目文件版本')
    p = new_project(original.get('name'), original.get('keyword'))
    p['demo'] = boolean(original.get('demo'))
    for field in ('market', 'platform', 'language'):
        if field in original:
            p[field] = string(original[field], 100)
    for kind in KINDS:
        run = import_rows(p, kind, original.get(kind, []))
        if run['errors'] or run['duplicates']:
            raise ValueError('恢复失败：项目包含无效或重复记录')
        for row, old_row in zip(p[kind], original.get(kind, [])):
            row['provenance'] = 'demo' if p['demo'] else old_row.get('provenance') if old_row.get('provenance') in ('live', 'import') else 'import'
    version = original.get('data_version', 0)
    if not isinstance(version, int) or version < 0:
        raise ValueError('数据版本无效')
    p['data_version'] = version
    p['ai_reports'] = [normalize_ai_report(r, p) for r in original.get('ai_reports', [])[-100:]]
    p['watch_history'] = sellersprite.restore_watch_history(original.get('watch_history', []), p['products'])
    review_ids = {r['id'] for r in p['reviews']}
    product_ids = {r['id'] for r in p['products']}
    keyword_ids = {r['id'] for r in p['keywords']}
    for old in original.get('analyses', [])[-100:]:
        if old.get('method') != '规则整理':
            raise ValueError('该分析版本尚不支持恢复')
        a = {'id': string(old['id'], 100), 'created_at': string(old['created_at'], 100),
             'data_version': int(old['data_version']), 'method': '规则整理',
             'scope': {**{k: count_value(old['scope'][k]) for k in ('total', 'analyzed', 'unanalyzed')},
                       'selection': string(old['scope']['selection'])},
             'insights': [], 'decisions': []}
        for insight in old['insights']:
            if not set(insight['evidence_ids']) <= review_ids:
                raise ValueError('分析引用了不存在的评论证据')
            if count_value(insight['count']) != len(insight['evidence_ids']) or \
               count_value(insight['sample_size']) < insight['count']:
                raise ValueError('评论样本计数不一致')
            a['insights'].append({k: copy.deepcopy(insight[k]) for k in
                ('id', 'title', 'action', 'review_type', 'evidence_ids', 'count', 'sample_size')})
        for decision in old['decisions']:
            if decision['product_id'] not in product_ids or not set(decision['evidence_ids']) <= review_ids or \
               not set(decision['keyword_ids']) <= keyword_ids:
                raise ValueError('选品判断引用了不存在的证据')
            if any(r['product_id'] != decision['product_id'] for r in p['reviews'] if r['id'] in decision['evidence_ids']):
                raise ValueError('选品判断中的评论与商品不匹配')
            a['decisions'].append({k: copy.deepcopy(decision[k]) for k in
                ('product_id', 'status', 'reason', 'evidence_ids', 'keyword_ids', 'missing')})
        p['analyses'].append(a)
    # 恢复原始任务记录与分析版本，不以新数据重算旧结论。
    p['runs'] = []
    for run in original.get('runs', []):
        p['runs'].append({**{k: string(run[k], 200) for k in ('id', 'kind', 'created_at', 'source', 'status')},
            **{k: count_value(run[k]) for k in ('requested', 'imported', 'duplicates')},
            'pages': None if run.get('pages') is None else count_value(run['pages']), 'errors': [{'row': count_value(e['row']), 'reason': string(e['reason'], 160)}
                                      for e in run['errors']]})
        if run.get('mode') == 'collection':
            p['runs'][-1].update(mode='collection', platform=string(run.get('platform'), 30),
                request_limit=count_value(run.get('request_limit', 0)), requests=count_value(run.get('requests', 0)),
                note=string(run.get('note')), page_results=[{k: x.get(k) for k in ('page', 'query', 'post_id', 'http', 'returned', 'imported', 'duplicates', 'skipped', 'error', 'platform', 'kind', 'original_query', 'round', 'parent_query', 'expansion') if k in x} for x in run.get('page_results', [])[:500 if run.get('keyword_mode') in ('az', 'intent') and run['kind'] == 'keywords' else 20]])
            restored = p['runs'][-1]
            restored['translations'] = [{'original': string(x.get('original'), 300), 'translated': string(x.get('translated'), 300), 'method': string(x.get('method') or 'TikHub 机器翻译', 100)} for x in run.get('translations', [])[:20]]
            restore_collection_details(run, restored, p)
        elif run.get('mode') == 'seller':
            p['runs'][-1].update(mode='seller', query=string(run.get('query'), 300),
                original_query=string(run.get('original_query'), 300), tool=string(run.get('tool'), 100))
    p['decision_workspace'] = normalize_workspace(original.get('decision_workspace', {}))
    p['created_at'] = string(original.get('created_at'), 100) or p['created_at']
    return p


def handler_for(store):
    jobs = CollectionJobs(store, LOCK, import_rows, uid, now)
    ai = AIJobs(store, LOCK, uid, now)
    history_running = set()
    identity = server_identity(store)
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def respond(self, status, data, content_type='application/json; charset=utf-8'):
            payload = data if isinstance(data, bytes) else json.dumps(data, ensure_ascii=False, allow_nan=False).encode()
            self.send_response(status)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(len(payload)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('X-Frame-Options', 'DENY')
            self.end_headers()
            self.wfile.write(payload)

        def do_GET(self):
            try:
                path = urlparse(self.path).path
                if path == '/api/health':
                    return self.respond(200, identity)
                if path == '/':
                    return self.respond(200, (ROOT / 'web/index.html').read_bytes(), 'text/html; charset=utf-8')
                if path in ('/business.js', '/usage-flow.svg', '/collection.js', '/research.js', '/workflow.js', '/workflow.css', '/watch.js', '/keyword-controls.js', '/insight-report.css'):
                    return self.respond(200, (ROOT / 'web' / path[1:]).read_bytes(),
                        'image/svg+xml' if path.endswith('.svg') else 'text/css; charset=utf-8' if path.endswith('.css') else 'text/javascript; charset=utf-8')
                if path == '/api/ai':
                    return self.respond(200, ai.status())
                if path == '/api/ai/jobs':
                    project_id = parse_qs(urlparse(self.path).query).get('project', [None])[0]
                    return self.respond(200, ai.list(project_id))
                if path.startswith('/api/ai/jobs/'):
                    return self.respond(200, ai.get(path.split('/')[4]))
                if path == '/api/sources':
                    return self.respond(200, sources.connection_status())
                if path == '/api/device-setup':
                    return self.respond(200, device_setup.status())
                if path == '/api/sellersprite':
                    return self.respond(200, sellersprite.status())
                if path == '/api/sellersprite/tools':
                    return self.respond(200, {k: v for k, v in (sellersprite._client.tools if sellersprite._client else {}).items() if k in sellersprite.ALLOWED.values()})
                if path == '/api/active-jobs':
                    with LOCK:
                        return self.respond(200, [jobs.get(id_) for id_, job in jobs.jobs.items() if job['run']['status'] == 'running'])
                if path.startswith('/api/jobs/'):
                    return self.respond(200, jobs.get(path.split('/')[3]))
                if path == '/api/projects':
                    return self.respond(200, store.listing())
                if path.startswith('/api/projects/'):
                    return self.respond(200, store.load(path.split('/')[3]))
                return self.respond(404, {'error': '页面不存在'})
            except FileNotFoundError:
                self.respond(404, {'error': '项目文件不存在或尚未完成同步'})
            except (ValueError, KeyError):
                self.respond(400, {'error': '项目文件无效或同步未完成'})

        def do_POST(self):
            # 同源 JSON 请求，防止其他网页向本机服务提交写操作。
            host = self.headers.get('Host', '')
            origin = self.headers.get('Origin')
            if host not in (f'127.0.0.1:{self.server.server_port}', f'localhost:{self.server.server_port}') or \
               (origin and origin not in (f'http://{host}', f'http://127.0.0.1:{self.server.server_port}')):
                return self.respond(403, {'error': '只允许本机工作台访问'})
            if self.headers.get('Content-Type', '').split(';')[0] != 'application/json':
                return self.respond(415, {'error': '请使用 JSON 请求'})
            try:
                size = int(self.headers.get('Content-Length', 0))
                if not 0 < size <= 12_000_000:
                    raise ValueError('文件过大或请求为空，最大 12 MB')
                body = json.loads(self.rfile.read(size))
                if not isinstance(body, dict):
                    raise ValueError('请求格式无效')
                path = urlparse(self.path).path
                if path == '/api/sellersprite/connect':
                    return self.respond(200, sellersprite.connect(body.get('key'), persist=body.get('persist') is True))
                if path == '/api/sources/connect':
                    return self.respond(200, sources.connect(body.get('key'), body.get('base_url'), persist=body.get('persist') is True))
                if path.startswith('/api/jobs/') and path.endswith('/cancel'):
                    return self.respond(200, jobs.cancel(path.split('/')[3]))
                if path.startswith('/api/ai/jobs/') and path.endswith('/cancel'):
                    return self.respond(200, ai.cancel(path.split('/')[4]))
                if path.endswith('/ai'):
                    parts = path.strip('/').split('/')
                    if len(parts) != 4 or parts[:2] != ['api', 'projects']:
                        raise ValueError('操作地址无效')
                    with LOCK:
                        return self.respond(202, ai.start(store.load(parts[2]), body))
                if path.endswith('/product-history'):
                    parts = path.strip('/').split('/')
                    if len(parts) != 4 or parts[:2] != ['api', 'projects']:
                        raise ValueError('操作地址无效')
                    project_id = parts[2]
                    with LOCK:
                        p = store.load(project_id)
                        if body.get('revision') != p['revision']:
                            raise Conflict('项目已被更新，请重新打开后再查询商品历史')
                        asin = sellersprite.history_asin(body.get('product_id'))
                        if p['demo'] or not any(r['id'] == asin and r.get('platform') == 'amazon' for r in p['products']):
                            raise ValueError('请先采集或导入这个 Amazon 商品，再查询历史')
                        if project_id in history_running:
                            raise Conflict('这个项目正在查询商品历史，请等待完成')
                        if len(p['watch_history']) >= 500:
                            raise ValueError('本项目已保存 500 次商品历史，请在新项目继续调研')
                        for old in p['watch_history']:
                            if old.get('status') == 'running':
                                old['status'] = 'interrupted'
                        history = {'id': uid(), 'product_id': asin, 'marketplace': 'US', 'source': '卖家精灵 MCP',
                                   'mode': 'manual', 'status': 'running', 'created_at': now(), 'finished_at': '',
                                   'requests': 0, 'request_limit': 2, 'results': []}
                        p['watch_history'].append(copy.deepcopy(history))
                        store.save(p, p['revision'])
                        history_running.add(project_id)

                    def save_history():
                        with LOCK:
                            current = store.load(project_id)
                            for index, item in enumerate(current['watch_history']):
                                if item['id'] == history['id']:
                                    current['watch_history'][index] = copy.deepcopy(history)
                                    break
                            return store.save(current, current['revision'])

                    try:
                        for tool in sellersprite.HISTORY_TOOLS:
                            history['requests'] += 1
                            save_history()
                            result = {'tool': tool, 'status': 'failed', 'http': None, 'error': '', 'data': None}
                            try:
                                payload, result['http'] = sellersprite.query_history(tool, asin, history['created_at'])
                                result['data'] = sellersprite.parse_history(tool, payload, asin, history['created_at'])
                                result['status'] = 'success'
                            except sources.SourceError as error:
                                result['http'] = error.status or result['http']
                                result['error'] = sources.text(str(error), 300)
                            except Exception:
                                # Do not expose upstream payloads, signed URLs or credential errors.
                                result['error'] = '该项历史数据未能验证，请检查数据源连接；未自动重试，其他成功结果保留。'
                            history['results'].append(result)
                            if len(history['results']) == 2:
                                successes = sum(r['status'] == 'success' for r in history['results'])
                                history['status'] = 'success' if successes == 2 else 'partial' if successes else 'failed'
                                history['finished_at'] = now()
                            p = save_history()
                        return self.respond(200, p)
                    finally:
                        with LOCK:
                            history_running.discard(project_id)
                if path.endswith('/seller-collect'):
                    parts = path.strip('/').split('/')
                    if len(parts) != 4 or parts[:2] != ['api', 'projects']:
                        raise ValueError('操作地址无效')
                    with LOCK:
                        p = store.load(parts[2])
                        if p['demo'] or body.get('revision') != p['revision']:
                            raise ValueError('请重新打开真实项目后再采集')
                        kind = body.get('kind')
                        if kind not in sellersprite.ALLOWED:
                            raise ValueError('不支持的查询')
                        keyword = string(body.get('query'), 300)
                        asin = string(body.get('product_id'), 100)
                        if kind == 'reviews' and asin not in {r['id'] for r in p['products']}:
                            raise ValueError('请先采集对应商品')
                        if kind != 'reviews' and not keyword:
                            raise ValueError('请输入产品词')
                    original = keyword
                    if kind != 'reviews' and sources.needs_translation('amazon', keyword):
                        keyword = sources.translate_query(keyword)
                    payload = sellersprite.query(kind, keyword, asin)
                    rows = sellersprite.parse(kind, payload, keyword, now(), asin)
                    for row in rows:
                        row['original_query'] = original
                    with LOCK:
                        p = store.load(parts[2])
                        run = import_rows(p, kind, rows, provenance='live')
                        run.update(source='卖家精灵 MCP', mode='seller', pages=1, query=keyword,
                                   original_query=original, tool=sellersprite.ALLOWED[kind])
                        return self.respond(200, store.save(p, p['revision']))
                with LOCK:
                    if path == '/api/projects':
                        p = demo_project() if body.get('demo') else new_project(body.get('name'), body.get('keyword'))
                        return self.respond(201, store.save(p))
                    if path == '/api/restore':
                        p = restore_project(body.get('project'))
                        return self.respond(201, store.save(p))
                    parts = path.strip('/').split('/')
                    if len(parts) != 4 or parts[:2] != ['api', 'projects']:
                        return self.respond(404, {'error': '操作不存在'})
                    p = store.load(parts[2])
                    expected = body.get('revision')
                    if expected != p['revision']:
                        raise Conflict('项目已被更新，请重新打开后再操作')
                    action = parts[3]
                    if action == 'collect':
                        return self.respond(202, jobs.start(p, body))
                    if action == 'toggle':
                        kind = body.get('kind')
                        field = body.get('field', 'candidate') if kind == 'products' else 'favorite' if kind == 'keywords' else None
                        if kind == 'products' and field not in ('candidate', 'watched'):
                            raise ValueError('不支持的商品标记')
                        if not field:
                            raise ValueError('不支持的操作')
                        record = next((r for r in p[kind] if r['id'] == body.get('id')), None)
                        if not record:
                            raise ValueError('记录不存在')
                        record[field] = not record.get(field, False)
                        if kind == 'products' and field == 'candidate':
                            p['data_version'] += 1
                    elif action == 'import':
                        rows = body.get('rows')
                        if body.get('format') == 'csv':
                            rows = list(csv.DictReader(io.StringIO(body.get('text', '').lstrip('\ufeff'))))
                        import_rows(p, body.get('kind'), rows)
                    elif action == 'analyze':
                        if not p['reviews'] and not any(r['candidate'] for r in p['products']):
                            raise ValueError('请先导入评论或添加候选商品')
                        p['analyses'].append(analyze(p))
                    elif action == 'decision-workspace':
                        p['decision_workspace'] = normalize_workspace(body.get('workspace'))
                    elif action == 'rename':
                        p['name'] = string(body.get('name'), 120) or p['name']
                    else:
                        raise ValueError('不支持的操作')
                    self.respond(200, store.save(p, expected))
            except Conflict as error:
                self.respond(409, {'error': str(error)})
            except (ValueError, TypeError, KeyError, AttributeError) as error:
                self.respond(400, {'error': str(error)[:250]})
            except FileNotFoundError:
                self.respond(404, {'error': '项目文件不存在，请等待同步完成'})
    return Handler


def server_identity(store):
    return {'app': 'fieldwork', 'build': BUILD_ID,
            'workspace': hashlib.sha256(str(store.path.resolve()).encode()).hexdigest()}


def is_current_workbench(port, identity):
    try:
        # Never follow another local application's redirects or use system proxies.
        with build_opener(ProxyHandler({}), sources.NoRedirect()).open(
                f'http://127.0.0.1:{port}/api/health', timeout=0.5) as response:
            return response.status == 200 and json.loads(response.read(1024)) == identity
    except HTTPError as error:
        error.close()
        return False
    except (OSError, ValueError, HTTPException):
        return False


class LocalHTTPServer(ThreadingHTTPServer):
    allow_reuse_address = os.name != 'nt'

    def server_bind(self):
        if os.name == 'nt':
            # Windows SO_REUSEADDR can let two listeners bind the same port.
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()


def bind_or_reuse(port, store):
    ports = range(port, min(port + 10, 65536))
    identity = server_identity(store)
    # Check all candidate ports before binding: an earlier launch may have used
    # a fallback port even if the preferred port has since become available.
    for candidate in ports:
        if is_current_workbench(candidate, identity):
            return None, f'http://127.0.0.1:{candidate}'
    handler = handler_for(store)
    for candidate in ports:
        try:
            server = LocalHTTPServer(('127.0.0.1', candidate), handler)
            return server, f'http://127.0.0.1:{server.server_port}'
        except OSError as error:
            if error.errno != errno.EADDRINUSE:
                raise
            if is_current_workbench(candidate, identity):
                return None, f'http://127.0.0.1:{candidate}'
    raise OSError(errno.EADDRINUSE, '连续 10 个候选端口均被占用')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=8765)
    parser.add_argument('--data-dir', type=Path, default=ROOT / 'data/projects')
    parser.add_argument('--open', action='store_true', help='启动后打开浏览器')
    parser.add_argument('--project', default='', help='启动后打开指定项目的使用指南')
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error('端口必须在 1 到 65535 之间')
    if args.project and not re.fullmatch(r'[a-f0-9]{16}', args.project):
        parser.error('项目编号格式无效')
    try:
        server, url = bind_or_reuse(args.port, Store(args.data_dir))
    except OSError as error:
        print(f'无法启动本机工作台（系统错误 {error.errno}）：{error.strerror}', flush=True)
        raise SystemExit(1)
    print(f'{"工作台已启动" if server else "打开已运行的工作台"}：{url}', flush=True)
    if server:
        device_setup.start()
    if args.open:
        import webbrowser
        webbrowser.open(url + '/#guide?project=' + args.project if args.project else url)
    if server is None:
        return
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
