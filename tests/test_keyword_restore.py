"""Real collection/save/restore paths, using temporary projects and fake suppliers."""
import copy
import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

import sources
from collection_jobs import CollectionJobs
from server import Store, import_rows, new_project, normalize, now, restore_project, uid


class KeywordRestoreTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.store = Store(Path(cls.temp.name) / 'source')
        project = cls.store.save(new_project('跨设备扩词验收', 'fountain'))
        cls.jobs = CollectionJobs(cls.store, threading.RLock(), import_rows, uid, now)
        cls.inflight = None
        original_save = cls.store.save
        def save(p, expected=None):
            if p['runs']:
                run = p['runs'][-1]
                if len(run.get('page_results', [])) == 2 and run['page_results'][-1]['http'] is None:
                    cls.inflight = copy.deepcopy(p)
            return original_save(p, expected)
        def request(platform, kind, params):
            return {'words': ['grandchild'] if params.get('keyword') == 'child' else ['child']}
        def parse(platform, kind, payload, query, collected_at, post=None):
            return [{'id': platform + '-' + word, 'platform': platform, 'text': word, 'query': query,
                     'source': 'fake supplier', 'collected_at': collected_at} for word in payload['words']], None, 0
        with patch('sources.credential', return_value='mock-only'), patch('sources.request', side_effect=request), \
             patch('sources.parse', side_effect=parse), patch.object(cls.store, 'save', side_effect=save):
            job = cls.jobs.start(project, {'kind': 'keywords', 'platforms': ['xhs', 'tiktok'], 'queries': ['fountain'],
                                           'keyword_mode': 'az', 'rounds': 2, 'request_limit': 60})
            deadline = time.monotonic() + 20
            while cls.jobs.get(job['id'])['run']['status'] == 'running' and time.monotonic() < deadline:
                time.sleep(.02)
            if cls.jobs.get(job['id'])['run']['status'] == 'running':
                cls.jobs.cancel(job['id'])
                raise AssertionError('模拟供应商的有限任务未及时结束')
        cls.package = cls.store.load(project['id'])

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_more_than_twenty_pages_roundtrip_through_json_and_second_store(self):
        path = Path(self.temp.name) / 'project-export.json'
        path.write_text(json.dumps(self.package, ensure_ascii=False), encoding='utf-8')
        restored = restore_project(json.loads(path.read_text(encoding='utf-8')))
        destination = Store(Path(self.temp.name) / 'destination')
        restored = destination.save(restored)
        restored = destination.load(restored['id'])
        original_run, run = self.package['runs'][-1], restored['runs'][-1]
        self.assertEqual(len(run['page_results']), 56)
        self.assertEqual(run['pages'], 56)
        self.assertEqual([r['queries'] for r in run['round_results']], [27, 1, 27, 1])
        self.assertEqual(restored['keywords'], self.package['keywords'])
        for key, value in original_run.items():
            self.assertEqual(run[key], value, key)
        self.assertEqual([r['round'] for r in restored['keywords']], [1, 2, 1, 2])

    def test_inflight_snapshot_restores_as_interrupted_without_inventing_a_page(self):
        self.assertIsNotNone(self.inflight)
        p = restore_project(copy.deepcopy(self.inflight))
        run = p['runs'][-1]
        self.assertEqual(run['status'], 'interrupted')
        self.assertEqual([r['status'] for r in run['platform_results']], ['interrupted', 'interrupted'])
        self.assertEqual(run['round_results'][0]['status'], 'interrupted')
        self.assertEqual((run['pages'], run['requests'], run['imported']), (1, 2, 1))
        self.assertIsNone(run['page_results'][1]['http'])
        self.assertEqual(run['page_results'][1]['returned'], 0)

    def test_unknown_fields_do_not_enter_restored_project(self):
        p = copy.deepcopy(self.package)
        run = p['runs'][-1]
        for obj in (p['keywords'][0], run, run['budget'], run['platform_results'][0], run['round_results'][0], run['page_results'][0]):
            obj['private_account_payload'] = 'fake-private-marker'
        self.assertNotIn('fake-private-marker', json.dumps(restore_project(p), ensure_ascii=False))

    def test_invalid_modes_rounds_and_keyword_provenance_are_rejected(self):
        for changes in ({'keyword_mode': 'recursive'}, {'keyword_mode': 'quick'}, {'rounds': 0}, {'rounds': 7},
                        {'rounds': True}, {'current_round': 3}, {'stop_reason': 'forever'}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                p = copy.deepcopy(self.package)
                p['runs'][-1].update(changes)
                restore_project(p)
        for changes in ({'round': 0}, {'round': 7}, {'round': True}, {'expansion': 'invented'}):
            with self.subTest(keyword=changes), self.assertRaises(ValueError):
                normalize('keywords', {'text': 'term', 'round': 1, 'expansion': 'seed', **changes})

    def test_global_and_grouped_round_counts_are_checked_against_pages(self):
        def move_round_imports(run):
            run['round_results'][0]['new_keywords'] += 1
            run['round_results'][1]['new_keywords'] -= 1
        def move_platform_queries(run):
            run['round_results'][0]['queries'] -= 1
            run['round_results'][2]['queries'] += 1
        changes = [lambda r: r['round_results'][0].update(queries=28), move_round_imports, move_platform_queries,
                   lambda r: r['page_results'][0].update(returned=99),
                   lambda r: r['page_results'][0].update(imported=-1),
                   lambda r: r['page_results'][0].update(duplicates=True),
                   lambda r: r['page_results'][0].update(platform='reddit'),
                   lambda r: r['page_results'][0].update(round=2),
                   lambda r: r['page_results'][0].update(expansion='invented')]
        for i, change in enumerate(changes):
            with self.subTest(case=i), self.assertRaises(ValueError):
                p = copy.deepcopy(self.package)
                change(p['runs'][-1])
                restore_project(p)

    def test_allocated_budget_checks_use_quotas_not_actual_usage(self):
        run = restore_project(copy.deepcopy(self.package))['runs'][-1]
        self.assertEqual((run['requests'], run['request_limit']), (56, 60))
        for change in (lambda r: r['platform_results'][0].update(query_limit=29),
                       lambda r: r['budget'].update(translation_requests=1),
                       lambda r: r['platform_results'][0].update(query_limit=27),
                       lambda r: r.update(request_limit=501)):
            with self.subTest(change=change), self.assertRaises(ValueError):
                p = copy.deepcopy(self.package)
                change(p['runs'][-1])
                restore_project(p)

    def test_quick_start_cannot_produce_an_unrestorable_large_budget(self):
        with tempfile.TemporaryDirectory() as directory, patch('collection_jobs.threading.Thread.start') as start:
            store = Store(directory)
            p = store.save(new_project('quick budget', 'seed'))
            jobs = CollectionJobs(store, threading.RLock(), import_rows, uid, now)
            with self.assertRaises(ValueError):
                jobs.start(p, {'kind': 'keywords', 'platforms': ['xhs', 'tiktok'],
                               'queries': [f'seed {i}' for i in range(20)], 'keyword_mode': 'quick', 'request_limit': 40})
            start.assert_not_called()

    def collect_small(self, body):
        with tempfile.TemporaryDirectory() as directory, patch('sources.credential', return_value='mock-only'):
            store = Store(directory)
            p = store.save(new_project('small restore', 'seed'))
            jobs = CollectionJobs(store, threading.RLock(), import_rows, uid, now)
            job = jobs.start(p, {'kind': 'keywords', 'platforms': ['xhs'], 'queries': ['seed'], **body})
            deadline = time.monotonic() + 4
            while jobs.get(job['id'])['run']['status'] == 'running' and time.monotonic() < deadline:
                time.sleep(.01)
            self.assertNotEqual(jobs.get(job['id'])['run']['status'], 'running')
            return store.load(p['id'])

    def test_valid_quick_roundtrip_and_rejects_more_than_one_round(self):
        with patch('sources.request', return_value={'data': {'data': {'sug_items': [{'text': 'real-shaped term'}]}}}):
            p = self.collect_small({'request_limit': 20})
        restored = restore_project(p)
        run = restored['runs'][-1]
        self.assertEqual((run['keyword_mode'], run['rounds'], run['requests'], run['request_limit']), ('quick', 1, 1, 1))
        self.assertEqual(restored['keywords'], p['keywords'])
        p['runs'][-1]['rounds'] = 2
        with self.assertRaises(ValueError):
            restore_project(p)

    def test_failure_page_and_unused_provider_quota_remain_restorable(self):
        with patch('sources.request', side_effect=sources.SourceError('HTTP 429：mock rate limit', 429)), \
             patch('sellersprite.query', return_value={'data': {'items': [{'keyword': 'supplier term'}]}}):
            p = self.collect_small({'platforms': ['xhs', 'amazon'], 'keyword_mode': 'intent', 'rounds': 2, 'request_limit': 6})
        restored = restore_project(p)
        run = restored['runs'][-1]
        self.assertEqual((run['requests'], run['pages'], run['request_limit']), (4, 3, 6))
        self.assertEqual(run['page_results'][0]['http'], 429)
        self.assertEqual(run['platform_results'][0]['query_limit'], 3)
        self.assertEqual(run['round_results'][0]['status'], 'failed')
        self.assertEqual(restored['keywords'], p['keywords'])

    def test_legacy_collection_without_keyword_metadata_still_restores(self):
        p = copy.deepcopy(self.inflight)
        run = p['runs'][-1]
        for key in ('keyword_mode', 'rounds', 'current_round', 'capped', 'stop_reason', 'round_results'):
            run.pop(key, None)
        run['request_limit'] = 4
        run['budget'] = {'tikhub_requests': 4, 'mcp_queries': 0, 'estimated_tikhub_usd': .04, 'note': 'legacy'}
        for page in run['page_results']:
            for key in ('round', 'parent_query', 'expansion'):
                page.pop(key, None)
        for summary in run['platform_results']:
            for key in ('query_limit', 'current_round', 'capped', 'stop_reason'):
                summary.pop(key, None)
        restored = restore_project(p)['runs'][-1]
        self.assertEqual(restored['status'], 'interrupted')
        self.assertNotIn('keyword_mode', restored)
        self.assertEqual(restored['page_results'], run['page_results'])


if __name__ == '__main__':
    unittest.main()
