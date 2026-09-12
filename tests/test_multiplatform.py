"""Cross-platform collection uses isolated stores and mocked suppliers only."""
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

import sources
from collection_jobs import CollectionJobs
from server import Store, import_rows, new_project, now, uid


class MultiPlatformTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = Store(self.temp.name)
        self.project = self.store.save(new_project('多平台回归', 'blender'))
        self.jobs = CollectionJobs(self.store, threading.RLock(), import_rows, uid, now)
        self.credential = patch('sources.credential', return_value='test-only')
        self.credential.start()

    def tearDown(self):
        self.credential.stop()
        self.temp.cleanup()

    def start(self, **body):
        return self.jobs.start(self.store.load(self.project['id']), {
            'platforms': ['xhs', 'tiktok', 'reddit', 'amazon'], 'kind': 'keywords',
            'queries': ['榨汁杯'], **body})

    def wait(self, job):
        deadline = time.monotonic() + 4
        while time.monotonic() < deadline:
            result = self.jobs.get(job['id'])['run']
            if result['status'] != 'running':
                return result
            time.sleep(.01)
        self.fail('任务未在限定时间结束')

    @staticmethod
    def rows(platform, kind, payload, query, collected_at, post=None):
        common = {'id': platform + '-row', 'platform': platform, 'query': query,
                  'source': platform + ' · 测试', 'collected_at': collected_at}
        if kind == 'keywords':
            return [{**common, 'text': 'same term'}], None, 0
        if kind == 'reviews':
            return [{**common, 'id': post['id'] + '-comment', 'body': 'easy to clean',
                     'post_id': post['id'], 'review_type': 'social'}], None, 0
        return [{**common, 'title': 'Blender', 'external_id': platform + '-external'}], None, 0

    def test_same_word_keeps_four_sources_and_reuses_translation(self):
        with patch('sources.translate_query', return_value='blender') as translate, \
             patch('sources.request', return_value={}) as request, \
             patch('sources.parse', side_effect=self.rows), \
             patch('sellersprite.query', return_value={'data': {'items': [{'keyword': 'same term', 'searches': 12}]}}) as seller:
            run = self.wait(self.start())
        self.assertEqual(run['status'], 'success')
        self.assertEqual(run['platform'], 'multi')
        self.assertEqual(run['platforms'], ['xhs', 'tiktok', 'reddit', 'amazon'])
        self.assertEqual(run['request_limit'], 5)
        self.assertEqual(run['requests'], 5)
        self.assertEqual(run['budget']['tikhub_requests'], 4)
        self.assertEqual(run['budget']['mcp_queries'], 1)
        translate.assert_called_once_with('榨汁杯')
        seller.assert_called_once_with('keywords', 'blender')
        self.assertEqual(request.call_count, 3)
        rows = self.store.load(self.project['id'])['keywords']
        self.assertEqual({r['platform'] for r in rows}, {'xhs', 'tiktok', 'reddit', 'amazon'})
        self.assertTrue(all(r['original_query'] == '榨汁杯' for r in rows))
        self.assertEqual({r['query'] for r in rows if r['platform'] != 'xhs'}, {'blender'})
        self.assertTrue(all(r['status'] == 'success' for r in run['platform_results']))
        self.assertTrue(all(r['original_query'] == '榨汁杯' for r in run['page_results']))

    def test_platform_forbidden_does_not_cancel_other_platforms(self):
        def request(platform, *_):
            if platform == 'xhs':
                raise sources.SourceError('HTTP 403：该接口没有权限', 403)
            return {}
        with patch('sources.request', side_effect=request), patch('sources.parse', side_effect=self.rows):
            run = self.wait(self.start(platforms=['xhs', 'tiktok', 'reddit'], queries=['blender']))
        self.assertEqual(run['status'], 'partial')
        self.assertEqual(run['imported'], 2)
        self.assertEqual([p['status'] for p in run['platform_results']], ['failed', 'success', 'success'])
        self.assertEqual(run['errors'][0]['platform'], 'xhs')
        self.assertEqual(run['page_results'][0]['http'], 403)

    def test_tikhub_balance_failure_keeps_amazon_working(self):
        with patch('sources.request', side_effect=sources.SourceError('HTTP 402：余额不足', 402)) as request, \
             patch('sellersprite.query', return_value={'data': {'items': [{'keyword': 'blender'}]}}) as seller:
            run = self.wait(self.start(queries=['blender']))
        self.assertEqual(run['status'], 'partial')
        request.assert_called_once()
        seller.assert_called_once()
        self.assertEqual(run['requests'], 2)
        self.assertEqual(run['platform_results'][-1]['status'], 'success')
        self.assertEqual(len(self.store.load(self.project['id'])['keywords']), 1)

    def test_amazon_content_is_product_and_only_one_page(self):
        with patch('sources.request', return_value={}), patch('sources.parse', side_effect=self.rows), \
             patch('sellersprite.query', return_value={'data': {'items': [{'asin': 'B012345678', 'title': 'Blender'}]}}) as seller:
            run = self.wait(self.start(platforms=['xhs', 'amazon'], kind='posts', queries=['blender'], pages=3))
        self.assertEqual(run['request_limit'], 4)
        self.assertEqual(run['requests'], 2)
        seller.assert_called_once_with('products', 'blender')
        saved = self.store.load(self.project['id'])
        self.assertEqual(len(saved['posts']), 1)
        self.assertEqual(saved['products'][0]['id'], 'B012345678')
        self.assertEqual(run['page_results'][-1]['kind'], 'products')

    def test_mixed_comments_resolve_platform_from_parent(self):
        p = self.store.load(self.project['id'])
        for platform in ('reddit', 'xhs'):
            import_rows(p, 'posts', [{'id': platform, 'platform': platform, 'title': 'Blender', 'external_id': platform + '-external',
                                      'query': 'blender', 'original_query': '榨汁杯'}])
        self.store.save(p, p['revision'])
        with patch('sources.request', return_value={}) as request, patch('sources.parse', side_effect=self.rows):
            run = self.wait(self.start(kind='reviews', platform='tiktok', post_ids=['reddit', 'xhs'], queries=[]))
        self.assertEqual(run['platforms'], ['reddit', 'xhs'])
        self.assertEqual([call.args[0] for call in request.call_args_list], ['reddit', 'xhs'])
        saved = self.store.load(self.project['id'])
        self.assertEqual({(r['platform'], r['post_id']) for r in saved['reviews']}, {('reddit', 'reddit'), ('xhs', 'xhs')})
        self.assertTrue(all(r['original_query'] == '榨汁杯' and r['query'] == 'blender' for r in saved['reviews']))

    def test_missing_tikhub_does_not_prevent_amazon(self):
        with patch('sources.credential', side_effect=sources.SourceError('请连接 TikHub')), \
             patch('sources.request') as request, \
             patch('sellersprite.query', return_value={'data': {'items': [{'keyword': 'blender'}]}}) as seller:
            run = self.wait(self.start(queries=['blender']))
        request.assert_not_called()
        seller.assert_called_once()
        self.assertEqual(run['status'], 'partial')
        self.assertEqual(run['requests'], 1)
        self.assertEqual([r['status'] for r in run['platform_results']], ['failed', 'failed', 'failed', 'success'])

    def test_platform_refusal_marks_remaining_queries_without_retry(self):
        with patch('sources.request', side_effect=sources.SourceError('HTTP 403：拒绝访问', 403)) as request:
            run = self.wait(self.start(platforms=['xhs'], queries=['one', 'two']))
        request.assert_called_once()
        self.assertEqual(run['status'], 'failed')
        self.assertEqual([e['query'] for e in run['errors']], ['one', 'two'])
        self.assertEqual(run['requests'], 1)

    def test_cancel_stops_later_platforms_preserving_current_page(self):
        entered, release = threading.Event(), threading.Event()
        def request(*_):
            entered.set()
            release.wait(2)
            return {}
        with patch('sources.request', side_effect=request) as mocked, patch('sources.parse', side_effect=self.rows), patch('sellersprite.query') as seller:
            job = self.start(queries=['blender'])
            self.assertTrue(entered.wait(1))
            self.jobs.cancel(job['id'])
            release.set()
            run = self.wait(job)
        mocked.assert_called_once()
        seller.assert_not_called()
        self.assertEqual(run['status'], 'cancelled')
        self.assertEqual(len(self.store.load(self.project['id'])['keywords']), 1)
        self.assertTrue(all(p['status'] == 'cancelled' for p in run['platform_results']))

    def test_bad_platforms_and_combined_budget_rejected_before_requests(self):
        with patch('sources.request') as request, patch('sellersprite.query') as seller:
            for platforms in ([], 'xhs', ['bad'], ['xhs', {}]):
                with self.assertRaises(ValueError):
                    self.start(platforms=platforms)
            with self.assertRaises(ValueError):
                self.start(kind='posts', queries=['one', 'two'], pages=4)
            request.assert_not_called()
            seller.assert_not_called()
        self.assertEqual(len(self.store.load(self.project['id'])['runs']), 0)

    def test_shared_translation_failure_is_not_retried_or_empty_success(self):
        with patch('sources.translate_query', side_effect=sources.SourceError('翻译暂不可用', 500)) as translate, \
             patch('sources.request', return_value={}) as request, patch('sources.parse', side_effect=self.rows), patch('sellersprite.query') as seller:
            run = self.wait(self.start())
        translate.assert_called_once()
        request.assert_called_once()
        seller.assert_not_called()
        self.assertEqual(run['status'], 'partial')
        self.assertEqual(run['requests'], 2)
        self.assertEqual(run['imported'], 1)
        self.assertEqual(len(run['errors']), 3)

    def test_every_snapshot_commits_rows_page_counts_and_platform_counts_together(self):
        p = self.store.load(self.project['id'])
        import_rows(p, 'keywords', [{'id': 'existing', 'platform': 'tiktok', 'text': 'same term'}])
        self.store.save(p, p['revision'])
        rows = [{'id': 'duplicate', 'platform': 'tiktok', 'text': 'same term'},
                {'id': 'new', 'platform': 'tiktok', 'text': 'new term'},
                {'id': 'invalid', 'platform': 'tiktok', 'text': ''}]
        original_save = self.store.save
        observed, inconsistent = [], []

        def save_snapshot(project, expected=None):
            for run in (r for r in project['runs'] if r.get('mode') == 'collection'):
                observed.append((run['status'], run['imported']))
                for field in ('imported', 'duplicates'):
                    if run[field] != sum(page[field] for page in run['page_results']) or \
                       run[field] != sum(platform[field] for platform in run['platform_results']):
                        inconsistent.append(field)
                if run['requested'] != sum(page['returned'] for page in run['page_results']):
                    inconsistent.append('returned rows')
                if run['pages'] != sum(platform['pages'] for platform in run['platform_results']):
                    inconsistent.append('completed pages')
                if len(project['keywords']) != 1 + run['imported']:
                    inconsistent.append('persisted rows')
            return original_save(project, expected)

        with patch.object(self.store, 'save', side_effect=save_snapshot), \
             patch('sources.request', return_value={}), patch('sources.parse', return_value=(rows, None, 0)):
            run = self.wait(self.start(platforms=['tiktok'], queries=['blender']))
        self.assertEqual(run['status'], 'partial')
        self.assertEqual((run['requested'], run['imported'], run['duplicates']), (3, 1, 1))
        self.assertEqual(len(run['errors']), 1)
        self.assertGreater(len(observed), 3)
        self.assertEqual(inconsistent, [])


if __name__ == '__main__':
    unittest.main()
