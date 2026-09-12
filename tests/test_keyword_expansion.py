"""Expansion invariants and bounded jobs; isolated stores and fake suppliers only."""
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

import sources
from collection_jobs import CollectionJobs
from keyword_expansion import KeywordQueue, first_round
from server import Store, import_rows, new_project, now, uid


class ExpansionQueueTests(unittest.TestCase):
    def test_templates_match_chinese_workbench_and_use_english_word_boundaries(self):
        self.assertEqual(first_round('饮水机', 'az', 'xhs'), [('饮水机' + c, 'az') for c in 'abcdefghijklmnopqrstuvwxyz'])
        self.assertEqual(first_round('pet fountain', 'az', 'tiktok')[0], ('pet fountain a', 'az'))
        chinese = first_round('饮水机', 'intent', 'xhs')
        self.assertEqual(len(chinese), 26)
        self.assertIn(('怎么饮水机', 'prefix'), chinese)
        self.assertIn(('饮水机平替', 'suffix'), chinese)
        english = first_round('pet fountain', 'intent', 'amazon')
        self.assertEqual(len(english), 26)
        self.assertIn(('pet fountain review', 'suffix'), english)
        self.assertTrue(all(not sources.needs_translation('amazon', query) for query, _ in english))

    def test_breadth_first_dedup_and_returned_words_only_after_first_round(self):
        queue = KeywordQueue(['Seed', 'second'], 'az', 3, 100, 'tiktok')
        observed = []
        for target in queue:
            query = target['query']
            if not queue.prepare(target, query):
                continue
            queue.used += 1
            observed.append(target)
            rows = [{'text': 'Child'}, {'text': '  child '}, {'text': 'SEED'}] if target['round'] == 1 else \
                [{'text': 'Grandchild'}] if target['round'] == 2 else [{'text': 'No fourth round'}]
            queue.extend(target, query, rows)
        self.assertEqual([x['round'] for x in observed], [1] * 54 + [2, 3])
        self.assertEqual(observed[-2]['query'], 'Child')
        self.assertEqual(observed[-2]['parent_query'], 'Seed')
        self.assertEqual(observed[-2]['original_query'], 'Seed')
        self.assertEqual(observed[-1]['expansion'], 'suggestion')
        self.assertFalse(queue.capped)

    def test_queue_memory_is_bounded_and_quick_never_recurses(self):
        queue = KeywordQueue(['seed'], 'intent', 6, 500, 'xhs')
        target = next(queue)
        queue.prepare(target, 'seed')
        queue.extend(target, 'seed', [{'text': f'word {i}'} for i in range(5000)])
        self.assertEqual(len(queue.pending), 500)
        self.assertTrue(queue.capped)
        queue.used = 1
        for _ in queue:
            queue.used += 1
        self.assertEqual(queue.used, 500)
        self.assertTrue(queue.pending)
        quick = KeywordQueue(['seed'], 'quick', 1, 1, 'xhs')
        target = next(quick)
        quick.prepare(target, 'seed')
        quick.used += 1
        quick.extend(target, 'seed', [{'text': 'child'}])
        self.assertEqual(list(quick), [])
        self.assertFalse(quick.capped)


class ExpansionJobTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = Store(self.temp.name)
        self.project = self.store.save(new_project('扩词专项', 'fountain'))
        self.jobs = CollectionJobs(self.store, threading.RLock(), import_rows, uid, now)
        self.credential = patch('sources.credential', return_value='mock-only')
        self.credential.start()

    def tearDown(self):
        self.credential.stop()
        self.temp.cleanup()

    def start(self, **body):
        return self.jobs.start(self.store.load(self.project['id']), {
            'kind': 'keywords', 'platforms': ['xhs'], 'queries': ['fountain'], **body})

    def wait(self, job):
        deadline = time.monotonic() + 12
        while time.monotonic() < deadline:
            run = self.jobs.get(job['id'])['run']
            if run['status'] != 'running':
                return run
            time.sleep(.01)
        self.jobs.cancel(job['id'])
        self.fail('有限采词任务未及时结束')

    @staticmethod
    def rows(platform, kind, payload, query, collected_at, post=None):
        words = payload.get('words', [])
        return [{'id': platform + '-' + word, 'platform': platform, 'query': query,
                 'text': word, 'source': 'mock', 'collected_at': collected_at} for word in words], None, 0

    def test_default_is_compatible_quick_and_explicit_rounds_are_normalized(self):
        with patch('sources.request', return_value={'words': ['actual term']}) as request, \
             patch('sources.parse', side_effect=self.rows):
            run = self.wait(self.start(rounds=6))
        request.assert_called_once()
        self.assertEqual((run['keyword_mode'], run['rounds'], run['request_limit']), ('quick', 1, 1))
        self.assertEqual(run['round_results'], [{'platform': 'xhs', 'round': 1, 'queries': 1,
                                                 'new_keywords': 1, 'duplicates': 0, 'status': 'success'}])
        self.assertEqual(run['page_results'][0]['expansion'], 'seed')
        self.assertFalse(run['capped'])

    def test_az_real_queries_not_fake_keywords_and_round_counts_persist_atomically(self):
        original_save = self.store.save
        inconsistent = []
        def save(project, expected=None):
            for run in (r for r in project['runs'] if r.get('keyword_mode')):
                if sum(r['queries'] for r in run['round_results']) != len(run['page_results']):
                    inconsistent.append('query count')
                if sum(r['new_keywords'] for r in run['round_results']) != run['imported']:
                    inconsistent.append('new keyword count')
                if sum(r['duplicates'] for r in run['round_results']) != run['duplicates']:
                    inconsistent.append('duplicate count')
                if len(project['keywords']) != run['imported']:
                    inconsistent.append('persisted keywords')
            return original_save(project, expected)
        def request(platform, kind, params):
            return {'words': ['actual grandchild'] if params['keyword'] == 'actual child' else ['actual child']}
        with patch.object(self.store, 'save', side_effect=save), patch('sources.request', side_effect=request) as mocked, \
             patch('sources.parse', side_effect=self.rows):
            run = self.wait(self.start(keyword_mode='az', rounds=2, request_limit=60))
        self.assertEqual(mocked.call_count, 28)
        self.assertEqual([r['queries'] for r in run['round_results']], [27, 1])
        self.assertEqual([r['new_keywords'] for r in run['round_results']], [1, 1])
        self.assertEqual(run['duplicates'], 26)
        self.assertEqual(run['page_results'][-1]['parent_query'], 'fountain')
        self.assertEqual(run['page_results'][-1]['round'], 2)
        self.assertEqual(run['stop_reason'], 'completed')
        self.assertEqual(inconsistent, [])
        keywords = self.store.load(self.project['id'])['keywords']
        self.assertEqual([r['text'] for r in keywords], ['actual child', 'actual grandchild'])
        self.assertEqual((keywords[1]['round'], keywords[1]['parent_query'], keywords[1]['original_query'], keywords[1]['query']),
                         (2, 'fountain', 'fountain', 'actual child'))

    def test_shared_translation_and_equal_platform_budgets_never_starve_later_platforms(self):
        with patch('sources.translate_query', return_value='pet fountain') as translate, \
             patch('sources.request', return_value={'words': ['actual word']}) as request, \
             patch('sources.parse', side_effect=self.rows), \
             patch('sellersprite.query', return_value={'data': {'items': [{'keyword': 'actual word'}]}}) as seller:
            run = self.wait(self.start(platforms=['xhs', 'tiktok', 'reddit', 'amazon'], queries=['饮水机'],
                                       keyword_mode='intent', rounds=2, request_limit=9))
        translate.assert_called_once_with('饮水机')
        self.assertEqual(request.call_count, 6)
        self.assertEqual(seller.call_count, 2)
        self.assertEqual(run['requests'], 9)
        self.assertEqual(run['budget']['tikhub_requests'], 7)
        self.assertEqual(run['budget']['mcp_queries'], 2)
        self.assertEqual(run['budget']['translation_requests'], 1)
        self.assertTrue(all(s['query_limit'] == 2 and s['capped'] for s in run['platform_results']))
        self.assertTrue(all(s['pages'] == 2 for s in run['platform_results']))
        self.assertEqual(run['stop_reason'], 'budget')
        self.assertEqual(run['status'], 'success')
        self.assertEqual(run['errors'], [])
        self.assertTrue(all(e['original_query'] == '饮水机' for e in run['page_results']))
        self.assertIn('pet fountain', seller.call_args_list[0].args)

    def test_provider_failure_does_not_spend_reserved_other_provider_budget(self):
        with patch('sources.request', side_effect=sources.SourceError('限流', 429)) as request, \
             patch('sellersprite.query', return_value={'data': {'items': []}}) as seller:
            run = self.wait(self.start(platforms=['xhs', 'amazon'], keyword_mode='az', rounds=2, request_limit=6))
        request.assert_called_once()
        self.assertEqual(seller.call_count, 3)
        self.assertEqual(run['requests'], 4)
        self.assertEqual(run['platform_results'][0]['stop_reason'], 'source_blocked')
        self.assertEqual(run['platform_results'][1]['stop_reason'], 'budget')
        self.assertEqual(run['round_results'][0]['status'], 'failed')

    def test_cancel_during_request_preserves_page_and_never_issues_expansion(self):
        entered, release = threading.Event(), threading.Event()
        def request(*_):
            entered.set()
            release.wait(2)
            return {'words': ['preserved term']}
        with patch('sources.request', side_effect=request) as mocked, patch('sources.parse', side_effect=self.rows):
            job = self.start(keyword_mode='az', rounds=6, request_limit=200)
            self.assertTrue(entered.wait(1))
            self.jobs.cancel(job['id'])
            release.set()
            run = self.wait(job)
        mocked.assert_called_once()
        self.assertEqual(run['stop_reason'], 'cancelled')
        self.assertEqual(run['round_results'][0]['status'], 'cancelled')
        self.assertEqual(self.store.load(self.project['id'])['keywords'][0]['text'], 'preserved term')

    def test_invalid_mode_rounds_and_budget_fail_before_any_supplier_request(self):
        cases = [{'keyword_mode': 'invented'}, {'rounds': 7}, {'rounds': True}, {'rounds': '2'},
                 {'request_limit': 501}, {'request_limit': True}, {'request_limit': 0},
                 {'platforms': ['tiktok', 'amazon'], 'queries': ['饮水机'], 'request_limit': 2}]
        with patch('sources.request') as request, patch('sources.translate_query') as translate, patch('sellersprite.query') as seller:
            for case in cases:
                with self.subTest(case=case), self.assertRaises(ValueError):
                    self.start(**{'keyword_mode': 'intent', **case})
            request.assert_not_called()
            translate.assert_not_called()
            seller.assert_not_called()
        self.assertEqual(self.store.load(self.project['id'])['runs'], [])


if __name__ == '__main__':
    unittest.main()
