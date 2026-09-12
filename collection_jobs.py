"""Bounded collection jobs with incremental snapshots and cooperative cancellation."""
import copy
import json
import threading
import sources
import sellersprite
from keyword_expansion import KeywordQueue, MODES, MAX_REQUESTS


LABELS = {**sources.LABELS, 'amazon': 'Amazon'}


class CollectionJobs:
    def __init__(self, store, lock, importer, uid, now):
        self.store, self.lock, self.importer, self.uid, self.now = store, lock, importer, uid, now
        self.jobs = {}

    def get(self, id_):
        with self.lock:
            if id_ not in self.jobs:
                raise ValueError('任务不在当前服务中；已保存结果请在项目记录查看')
            return copy.deepcopy({k: v for k, v in self.jobs[id_].items() if k != 'cancel_event'})

    def cancel(self, id_):
        with self.lock:
            if id_ not in self.jobs:
                raise ValueError('任务不存在')
            self.jobs[id_]['cancel_event'].set()
            return self.get(id_)

    def start(self, project, body):
        kind = body.get('kind')
        if project['demo']:
            raise ValueError('请新建真实调研项目，避免与演示样本混用')
        if kind not in ('keywords', 'posts', 'reviews'):
            raise ValueError('采集平台或类型无效')
        pages = body.get('pages', 1)
        if isinstance(pages, bool) or not isinstance(pages, int) or not 1 <= pages <= 10:
            raise ValueError('页数须为 1 至 10 的整数')
        queries = body.get('queries', [])
        if not isinstance(queries, list) or any(not isinstance(q, str) for q in queries):
            raise ValueError('关键词格式无效')
        queries = list(dict.fromkeys(q.strip() for q in queries if q.strip()))
        if len(queries) > 20 or any(len(q) > 300 for q in queries):
            raise ValueError('每次最多 20 个关键词，每词最多 300 字符')
        if kind == 'reviews':
            ids = body.get('post_ids', [])
            if not isinstance(ids, list) or not ids or len(ids) > 20 or any(not isinstance(i, str) for i in ids):
                raise ValueError('请选择 1 至 20 条内容，可以跨平台选择')
            selected = set(ids)
            posts = [p for p in project['posts'] if p['id'] in selected]
            if len(posts) != len(selected) or any(p.get('platform') not in sources.LABELS or not p.get('external_id') for p in posts):
                raise ValueError('所选内容不存在或缺少有效的平台编号')
            platforms = list(dict.fromkeys(p['platform'] for p in posts))
            targets = [(p['platform'], p.get('original_query') or p.get('query', ''), p) for p in posts]
        else:
            platforms = body.get('platforms', [body.get('platform')])
            if not isinstance(platforms, list) or not 1 <= len(platforms) <= 4 or any(not isinstance(p, str) or p not in LABELS for p in platforms):
                raise ValueError('请选择 1 至 4 个有效平台')
            platforms = list(dict.fromkeys(platforms))
            if not queries:
                raise ValueError('请输入至少一个关键词')
            targets = [(platform, q, None) for platform in platforms for q in queries]
        if kind == 'keywords':
            pages = 1
        keyword_mode, rounds = body.get('keyword_mode', 'quick'), body.get('rounds', 1)
        if kind == 'keywords':
            if keyword_mode not in MODES:
                raise ValueError('关键词模式须为 quick、az 或 intent')
            rounds = body.get('rounds', 1 if keyword_mode == 'quick' else 2)
            if isinstance(rounds, bool) or not isinstance(rounds, int) or not 1 <= rounds <= 6:
                raise ValueError('采集轮数须为 1 至 6 的整数')
            if keyword_mode == 'quick':
                rounds = 1
        translation_queries = {q for platform, q, _ in targets if kind != 'reviews' and sources.needs_translation(platform, q)}
        tikhub_limit = sum(pages for p, _, _ in targets if p != 'amazon') + len(translation_queries)
        seller_limit = sum(p == 'amazon' for p, _, _ in targets)
        limit = tikhub_limit + seller_limit
        query_limits = {}
        if kind == 'keywords' and (keyword_mode != 'quick' or 'request_limit' in body):
            requested_limit = body.get('request_limit', 200)
            maximum = 20 if keyword_mode == 'quick' else MAX_REQUESTS
            if isinstance(requested_limit, bool) or not isinstance(requested_limit, int) or not 1 <= requested_limit <= maximum:
                raise ValueError(f'关键词请求预算须为 1 至 {maximum} 的整数')
            limit = min(requested_limit, limit) if keyword_mode == 'quick' else requested_limit
            available = limit - len(translation_queries)
            if available < len(platforms):
                raise ValueError('请求预算不足：需预留根词翻译，并让每个平台至少查询一次')
            share, remainder = divmod(available, len(platforms))
            query_limits = {p: share + (i < remainder) for i, p in enumerate(platforms)}
            seller_limit = query_limits.get('amazon', 0)
            tikhub_limit = limit - seller_limit
        elif limit > 20:
            raise ValueError('单次最多 20 个请求，请减少关键词、内容数量或页数')
        if kind == 'keywords' and not query_limits:
            query_limits = {p: len(queries) for p in platforms}
        with self.lock:
            if any(j['project_id'] == project['id'] and j['run']['status'] == 'running' for j in self.jobs.values()):
                raise ValueError('这个项目已有采集任务，请等待完成或取消')
            run = {'id': self.uid(), 'kind': kind, 'created_at': self.now(),
                   'source': '、'.join(LABELS[p] + (' · 卖家精灵 MCP' if p == 'amazon' else ' · TikHub') for p in platforms),
                   'mode': 'collection', 'platform': platforms[0] if len(platforms) == 1 else 'multi',
                   'platforms': platforms, 'status': 'running', 'requested': 0, 'imported': 0,
                   'duplicates': 0, 'errors': [], 'pages': 0, 'requests': 0, 'request_limit': limit,
                   'budget': {'tikhub_requests': tikhub_limit, 'mcp_queries': seller_limit,
                              'estimated_tikhub_usd': round(tikhub_limit * .01, 2),
                              'note': 'TikHub 按每次 US$0.01 保守估计；MCP 使用会员查询额度，初始化握手不计入数据查询页数。'},
                   'platform_results': [{'platform': p, 'status': 'pending', 'pages': 0, 'requests': 0,
                                         'imported': 0, 'duplicates': 0, 'errors': [], 'query_pairs': []} for p in platforms],
                   'page_results': [], 'note': '采集范围：默认综合排序，不限时间。评论只覆盖接口返回的层级。' +
                       (' Amazon 每个词只取 1 页、最多 10 条。' if 'amazon' in platforms else '')}
            if kind == 'keywords':
                run.update(keyword_mode=keyword_mode, rounds=rounds, current_round=0, capped=False,
                           stop_reason='', round_results=[])
                run['budget']['translation_requests'] = len(translation_queries)
                run['budget']['note'] += ' 先预留根词翻译，再平均分配平台查询额度；未用额度不自动转移。'
                run['note'] += ' 扩词模板仅用于发起查询，只有平台实际返回的词进入关键词库。'
                for summary in run['platform_results']:
                    summary.update(query_limit=query_limits[summary['platform']], current_round=0,
                                   capped=False, stop_reason='')
            project['runs'].append(copy.deepcopy(run))
            self.store.save(project, project['revision'])
            job = {'id': run['id'], 'project_id': project['id'], 'run': run, 'cancel_event': threading.Event()}
            self.jobs[job['id']] = job
            threading.Thread(target=self.work, args=(job, kind, targets, pages), daemon=True).start()
            return self.get(job['id'])

    def persist(self, job, rows=None, kind=None, platform_result=None, page_result=None, round_result=None):
        with self.lock:
            p = self.store.load(job['project_id'])
            imported = None
            if rows is not None:
                imported = self.importer(p, kind or job['run']['kind'], rows, provenance='live', record_run=False)
                if platform_result is not None:
                    for error in imported['errors']:
                        error['platform'] = platform_result['platform']
                job['run']['imported'] += imported['imported']
                job['run']['duplicates'] += imported['duplicates']
                job['run']['errors'].extend(imported['errors'])
                if platform_result is not None:
                    platform_result['imported'] += imported['imported']
                    platform_result['duplicates'] += imported['duplicates']
                    platform_result['errors'].extend(imported['errors'])
                if page_result is not None:
                    page_result.update(imported=imported['imported'], duplicates=imported['duplicates'])
                if round_result is not None:
                    round_result['new_keywords'] += imported['imported']
                    round_result['duplicates'] += imported['duplicates']
                    if imported['errors']:
                        round_result['status'] = 'partial'
            for i, run in enumerate(p['runs']):
                if run['id'] == job['id']:
                    p['runs'][i] = copy.deepcopy(job['run'])
                    break
            self.store.save(p, p['revision'])
            return imported

    def work(self, job, kind, targets, pages):
        run, stop = job['run'], job['cancel_event']
        translations, translation_errors, blocked_providers = {}, {}, {}

        def failure(summary, reason, query='', http=None):
            error = {'row': run['requests'], 'platform': summary['platform'],
                     'query': sources.text(query, 300), 'reason': reason, 'http': http}
            run['errors'].append(error)
            summary['errors'].append(error)

        def count_request(summary):
            if run['requests'] >= run['request_limit']:
                raise sources.SourceError('已达到本次请求预算，停止采集')
            run['requests'] += 1
            summary['requests'] += 1

        def finish_round(result, stop_reason=''):
            entries = [e for e in run['page_results'] if e['platform'] == result['platform'] and e.get('round') == result['round']]
            if any(e.get('error') for e in entries):
                result['status'] = 'partial' if any(not e.get('error') for e in entries) else 'failed'
            elif result['status'] != 'partial':
                result['status'] = 'cancelled' if stop_reason == 'cancelled' else 'capped' if stop_reason == 'budget' else 'success'

        try:
            for summary in run['platform_results']:
                if stop.is_set():
                    break
                platform = summary['platform']
                provider = 'seller' if platform == 'amazon' else 'tikhub'
                summary['status'] = 'running'
                self.persist(job)
                if provider in blocked_providers:
                    for _, query, _ in (t for t in targets if t[0] == platform):
                        failure(summary, blocked_providers[provider], query)
                    summary['status'] = 'failed'
                    if kind == 'keywords':
                        summary['stop_reason'] = 'source_blocked'
                    self.persist(job)
                    continue
                if provider == 'tikhub':
                    try:
                        sources.credential()
                    except (sources.SourceError, ValueError, OSError) as error:
                        reason = str(error) if isinstance(error, sources.SourceError) else '本机 TikHub 连接配置无法读取，请检查数据源设置。'
                        blocked_providers[provider] = reason
                        for _, query, _ in (t for t in targets if t[0] == platform):
                            failure(summary, reason, query)
                        summary['status'] = 'failed'
                        if kind == 'keywords':
                            summary['stop_reason'] = 'source_blocked'
                        self.persist(job)
                        continue
                platform_blocked = False
                platform_targets = [(q, post) for p, q, post in targets if p == platform]
                queue = KeywordQueue([q for q, _ in platform_targets], run['keyword_mode'], run['rounds'],
                                     summary['query_limit'], platform) if kind == 'keywords' else None
                tasks = queue if queue is not None else ({'original_query': q, 'query': q, 'post': post}
                                                        for q, post in platform_targets)
                for target in tasks:
                    original_query, post = target['original_query'], target['post']
                    if stop.is_set():
                        break
                    if platform_blocked:
                        if queue is not None and run['keyword_mode'] != 'quick':
                            break
                        failure(summary, '该平台前序请求已被拒绝；本目标未请求，其他平台继续。', original_query)
                        continue
                    query = post.get('query', original_query) if post else target['query']
                    if kind != 'reviews' and (queue is None or target['expansion'] == 'seed') and sources.needs_translation(platform, query):
                        if query not in translations and query not in translation_errors:
                            if 'tikhub' in blocked_providers:
                                translation_errors[query] = '英文查询词尚未生成；' + blocked_providers['tikhub']
                            else:
                                count_request(summary)
                                self.persist(job)
                                try:
                                    translations[query] = sources.translate_query(query)
                                    run.setdefault('translations', []).append({'original': sources.text(query, 300),
                                        'translated': translations[query], 'method': 'TikHub 机器翻译'})
                                except sources.SourceError as error:
                                    translation_errors[query] = '关键词翻译失败：' + str(error)
                                    if error.status in (401, 402, 429):
                                        blocked_providers['tikhub'] = 'TikHub 凭据、余额或频率受限；已停止该数据源，其他数据源继续。'
                                        platform_blocked = provider == 'tikhub'
                                except (ValueError, KeyError, TypeError, AttributeError, IndexError):
                                    translation_errors[query] = '关键词翻译返回格式无效；该词未搜索，其他目标继续。'
                                self.persist(job)
                        if query in translation_errors:
                            failure(summary, translation_errors[query], original_query)
                            self.persist(job)
                            continue
                        query = translations[query]
                    if queue is not None and not queue.prepare(target, query):
                        continue
                    summary['query_pairs'].append({'original': sources.text(original_query, 300),
                                                   'query': sources.text(query, 300), 'post_id': post['id'] if post else ''})
                    cursor, seen, seen_pages = None, set(), set()
                    row_kind = 'products' if platform == 'amazon' and kind == 'posts' else kind
                    for page in range(1, (1 if platform == 'amazon' else pages) + 1):
                        if stop.is_set():
                            break
                        mark = json.dumps(cursor, sort_keys=True)
                        if mark in seen:
                            run['note'] += ' 接口重复分页标记，已停止该目标的后续页。'
                            break
                        seen.add(mark)
                        count_request(summary)
                        round_result = None
                        if queue is not None:
                            queue.used += 1
                            summary['current_round'] = target['round']
                            run['current_round'] = target['round']
                            round_result = next((r for r in run['round_results'] if r['platform'] == platform and
                                                 r['round'] == target['round']), None)
                            if round_result is None:
                                for previous in (r for r in run['round_results'] if r['platform'] == platform):
                                    finish_round(previous)
                                round_result = {'platform': platform, 'round': target['round'], 'queries': 0,
                                                'new_keywords': 0, 'duplicates': 0, 'status': 'running'}
                                run['round_results'].append(round_result)
                            round_result['queries'] += 1
                        entry = {'platform': platform, 'kind': row_kind, 'page': page, 'query': sources.text(query, 300),
                                 'original_query': sources.text(original_query, 300), 'post_id': post['id'] if post else '',
                                 'http': None, 'returned': 0, 'imported': 0, 'duplicates': 0, 'skipped': 0}
                        if queue is not None:
                            entry.update({key: target[key] for key in ('round', 'parent_query', 'expansion')})
                        run['page_results'].append(entry)
                        self.persist(job)
                        try:
                            if platform == 'amazon':
                                payload = sellersprite.query(row_kind, query)
                                entry['http'] = 200
                                rows = sellersprite.parse(row_kind, payload, query, self.now())
                                cursor, skipped = None, 0
                            else:
                                payload = sources.request(platform, kind, sources.params_for(platform, kind, query, post, cursor))
                                entry['http'] = 200
                                rows, cursor, skipped = sources.parse(platform, kind, payload, query, self.now(), post)
                            for row in rows:
                                row['original_query'] = original_query
                                if queue is not None:
                                    row.update({key: target[key] for key in ('round', 'parent_query', 'expansion')})
                            if queue is not None:
                                queue.extend(target, query, rows)
                            entry.update(returned=len(rows), skipped=skipped)
                            run['requested'] += len(rows)
                            run['pages'] += 1
                            summary['pages'] += 1
                            self.persist(job, rows, row_kind, summary, entry, round_result)
                            fingerprint = tuple(sorted(r['id'] for r in rows))
                            if fingerprint in seen_pages:
                                run['note'] += ' 接口重复返回同一页内容，已停止该目标的后续页。'
                                break
                            seen_pages.add(fingerprint)
                            if not cursor or not rows:
                                break
                        except sources.SourceError as error:
                            entry.update(http=error.status, error=str(error))
                            failure(summary, str(error), original_query, error.status)
                            if error.status in (401, 402, 403, 429):
                                platform_blocked = True
                            if error.status in (401, 402, 429):
                                blocked_providers[provider] = ('TikHub' if provider == 'tikhub' else '卖家精灵') + \
                                    ' 凭据、余额或频率受限；已停止该数据源，其他数据源继续。'
                            self.persist(job)
                            break
                        except (ValueError, KeyError, TypeError, AttributeError, IndexError):
                            entry['error'] = ('卖家精灵连接未验证或结果字段无效，请检查 MCP 设置；其他平台继续。' if platform == 'amazon' else
                                              '返回字段与已验证结构不一致，停止本目标，已保存其他结果')
                            failure(summary, entry['error'], original_query)
                            self.persist(job)
                            break
                        stop.wait(0.15)
                    if queue is not None and queue.pending and queue.used < queue.limit and not platform_blocked:
                        stop.wait(0.15)
                if queue is not None:
                    summary['capped'] = queue.capped
                    summary['stop_reason'] = 'cancelled' if stop.is_set() else 'source_blocked' if platform_blocked else \
                        'budget' if queue.capped else 'error' if summary['errors'] else 'completed'
                    run['capped'] = run['capped'] or queue.capped
                    for result in (r for r in run['round_results'] if r['platform'] == platform):
                        finish_round(result, summary['stop_reason'] if result['round'] == summary['current_round'] else '')
                summary['status'] = ('partial' if summary['imported'] else 'failed') if summary['errors'] else \
                    'cancelled' if stop.is_set() else 'success'
                self.persist(job)
            with self.lock:
                for summary in run['platform_results']:
                    if summary['status'] in ('pending', 'running'):
                        summary['status'] = 'cancelled' if stop.is_set() else 'failed'
                        if kind == 'keywords':
                            summary['stop_reason'] = 'cancelled' if stop.is_set() else 'error'
                run['status'] = ('partial' if run['imported'] else 'failed') if run['errors'] else 'cancelled' if stop.is_set() else 'success'
                if kind == 'keywords':
                    run['stop_reason'] = 'cancelled' if stop.is_set() else 'budget' if run['capped'] else 'error' if run['errors'] else 'completed'
                    run['note'] += ' 已到请求预算，保留全部已采结果。' if run['capped'] else \
                        ' 已停止，保留全部已采结果。' if stop.is_set() else ' 已到所选轮数或没有待查新词；未自动重试。'
                else:
                    run['note'] += ' 已停止；已返回结果保留。' if stop.is_set() else ' 已到页数上限、结果末页或重复页面；未自动重试。'
                self.persist(job)
        except Exception:
            # Never include exception payloads: upstream errors can contain signed URLs.
            with self.lock:
                run['status'] = 'partial' if run['imported'] else 'failed'
                if kind == 'keywords':
                    run['stop_reason'] = 'error'
                    for result in run['round_results']:
                        if result['status'] == 'running':
                            result['status'] = 'failed'
                for summary in run['platform_results']:
                    if summary['status'] in ('pending', 'running'):
                        summary['status'] = 'failed'
                run['errors'].append({'row': run['requests'], 'reason': '任务保存或处理失败；此前保存的页面仍在项目中'})
                try:
                    self.persist(job)
                except Exception:
                    pass
