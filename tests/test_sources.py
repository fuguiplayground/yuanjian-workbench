import copy
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

import sources
from collection_jobs import CollectionJobs
from server import Store, LOCK, uid, now, new_project, import_rows, analyze, restore_project


def video_page(id_='1', more=False, cursor=20):
    return {'code': 200, 'data': {'status_code': 0, 'search_item_list': [
        {'aweme_info': {'aweme_id': id_, 'desc': 'portable blender', 'statistics': {'comment_count': 2},
                        'author': {'email': 'private@example.com'}}}], 'has_more': more, 'cursor': cursor}}


class SourceTests(unittest.TestCase):
    def test_tiktok_success_without_suggestions_is_empty(self):
        rows, _, _ = sources.parse('tiktok', 'keywords', {'data': {'status_code': 0}}, 'Portable Juicing Cup', now())
        self.assertEqual(rows, [])
        with self.assertRaises(KeyError):
            sources.parse('tiktok', 'keywords', {'data': {}}, 'blender', now())

    def test_missing_metrics_and_identity_redaction(self):
        rows, _, _ = sources.parse('tiktok', 'posts', video_page(), 'blender', now())
        self.assertIsNone(rows[0]['likes'])
        self.assertNotIn('author', rows[0])
        self.assertIn('地域未确认', rows[0]['market_scope'])
        self.assertNotIn('private', str(rows))
        self.assertEqual(sources.text('contact abc@example.com @somebody 13812345678'),
                         'contact [邮箱已脱敏] [用户提及] [手机号已脱敏]')
        self.assertEqual(sources.safe_url('https://example.com/post?token=secret'), 'https://example.com/post')

    def test_reddit_community_is_not_a_keyword(self):
        data = {'data': {'search': {'dynamic': {'components': {'main': [{'children': [
            {'presentation': {'query': 'blender', 'suggestion': '%query% cup'}},
            {'presentation': {'title': 'r/Blenders', 'subreddit': {'name': 'Blenders'}}}]}]}}}}}
        rows, _, _ = sources.parse('reddit', 'keywords', data, 'blender', now())
        self.assertEqual([r['text'] for r in rows], ['blender cup'])

    def test_platform_keywords_do_not_collapse(self):
        p = new_project('research', 'blender')
        for platform in sources.LABELS:
            import_rows(p, 'keywords', [{'text': 'blender', 'platform': platform}])
        self.assertEqual(len(p['keywords']), 3)

    def test_reddit_score_can_be_negative(self):
        p = new_project('research', 'blender')
        result = import_rows(p, 'posts', [{'id': 'r1', 'title': 'Blender', 'platform': 'reddit', 'likes': -3}])
        self.assertEqual(result['imported'], 1)
        self.assertEqual(p['posts'][0]['likes'], -3)
        self.assertEqual(sources.metric(-3, signed=True), -3)

    def test_social_parent_and_analysis_platform_separation(self):
        p = new_project('research', 'blender')
        for platform in ('tiktok', 'xhs'):
            import_rows(p, 'posts', [{'id': platform, 'title': 'Blender', 'platform': platform}])
            result = import_rows(p, 'reviews', [{'id': platform+'c', 'body': 'clean 清洗', 'post_id': platform,
                'review_type': 'social', 'platform': platform}], provenance='live')
            self.assertEqual(result['imported'], 1)
        bad = import_rows(p, 'reviews', [{'post_id': 'xhs', 'body': 'different', 'review_type': 'social', 'platform': 'tiktok'}])
        self.assertEqual(len(bad['errors']), 1)
        a = analyze(p)
        self.assertEqual(len(a['insights']), 2)
        self.assertEqual([i['sample_size'] for i in a['insights']], [1, 1])
        p['analyses'].append(a)
        restored = restore_project(p)
        self.assertEqual(restored['reviews'][0]['provenance'], 'live')
        self.assertEqual(len(restored['posts']), 2)

    def test_xhs_comment_pagination_context(self):
        data = {'data': {'data': {'comments': [], 'has_more': True, 'cursor': '{"index":20,"pageArea":"ALL"}'}}}
        _, cursor, _ = sources.parse('xhs', 'reviews', data, 'test', now(), {'id': 'xhs1'})
        params = sources.params_for('xhs', 'reviews', '', {'external_id': '1'}, cursor)
        self.assertEqual(params['index'], 20)
        self.assertEqual(params['pageArea'], 'ALL')


class JobTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = Store(self.temp.name)
        self.p = self.store.save(new_project('research', 'blender'))
        self.jobs = CollectionJobs(self.store, LOCK, import_rows, uid, now)
        self.cred = patch('sources.credential', return_value='test-only')
        self.cred.start()

    def tearDown(self):
        self.cred.stop()
        self.temp.cleanup()

    def start(self, **extra):
        return self.jobs.start(self.store.load(self.p['id']), {'platform': 'tiktok', 'kind': 'posts',
                            'queries': ['blender'], 'pages': 2, **extra})

    def wait(self, job):
        deadline = time.monotonic()+3
        while time.monotonic() < deadline:
            state = self.jobs.get(job['id'])
            if state['run']['status'] != 'running':
                return state['run']
            time.sleep(.01)
        self.fail('job did not finish')

    def test_partial_failure_keeps_first_page(self):
        with patch('sources.request', side_effect=[video_page(more=True), sources.SourceError('HTTP 500：失败', 500)]):
            run = self.wait(self.start())
        self.assertEqual(run['status'], 'partial')
        self.assertEqual(run['pages'], 1)
        self.assertEqual(len(self.store.load(self.p['id'])['posts']), 1)
        self.assertEqual(run['page_results'][1]['http'], 500)

    def test_existing_page_does_not_block_later_new_page(self):
        p = self.store.load(self.p['id'])
        rows, _, _ = sources.parse('tiktok', 'posts', video_page(), 'blender', now())
        import_rows(p, 'posts', rows, provenance='live')
        self.store.save(p, p['revision'])
        with patch('sources.request', side_effect=[video_page(more=True), video_page('2')]) as request:
            run = self.wait(self.start())
        self.assertEqual(run['imported'], 1)
        self.assertEqual(run['duplicates'], 1)
        self.assertEqual(request.call_args_list[1].args[2]['offset'], 20)

    def test_cancel_preserves_inflight_page_and_parallel_edit(self):
        entered, release = threading.Event(), threading.Event()
        def request(*args):
            entered.set(); release.wait(2)
            return video_page(more=True)
        with patch('sources.request', side_effect=request) as mocked:
            job = self.start()
            self.assertTrue(entered.wait(1))
            p = self.store.load(self.p['id']); p['name'] = 'edited during request'; self.store.save(p, p['revision'])
            self.jobs.cancel(job['id']); release.set()
            run = self.wait(job)
        self.assertEqual(run['status'], 'cancelled')
        self.assertEqual(mocked.call_count, 1)
        saved = self.store.load(self.p['id'])
        self.assertEqual(saved['name'], 'edited during request')
        self.assertEqual(len(saved['posts']), 1)

    def test_limit_and_demo_rejected_before_spend(self):
        with patch('sources.request') as request:
            with self.assertRaises(ValueError):
                self.start(queries=['a','b','c'], pages=10)
            self.p['demo'] = True
            with self.assertRaises(ValueError):
                self.jobs.start(self.p, {'platform':'tiktok', 'kind':'keywords','queries':['a']})
            request.assert_not_called()

    def test_repeated_page_stops_without_infinite_requests(self):
        with patch('sources.request', return_value=video_page(more=True)) as request:
            run = self.wait(self.start(pages=10))
        self.assertEqual(request.call_count, 2)
        self.assertEqual(run['imported'], 1)

    def test_chinese_translation_budget_and_evidence(self):
        with patch('sources.translate_query', return_value='portable blender'), patch('sources.request', return_value=video_page()) as request:
            run = self.wait(self.start(queries=['便携榨汁杯'], pages=1))
        self.assertEqual(run['requests'], 2)
        self.assertEqual(run['request_limit'], 2)
        self.assertEqual(run['translations'][0]['original'], '便携榨汁杯')
        self.assertEqual(request.call_args.args[2]['keyword'], 'portable blender')
        row = self.store.load(self.p['id'])['posts'][0]
        self.assertEqual(row['original_query'], '便携榨汁杯')
        self.assertEqual(row['query'], 'portable blender')

    def test_translation_failure_does_not_search(self):
        with patch('sources.translate_query', side_effect=sources.SourceError('翻译失败', 500)), patch('sources.request') as request:
            run = self.wait(self.start(queries=['榨汁杯'], pages=1))
        self.assertEqual(run['status'], 'failed')
        self.assertEqual(run['requests'], 1)
        request.assert_not_called()
        self.assertFalse(sources.needs_translation('xhs', '榨汁杯'))


if __name__ == '__main__':
    unittest.main()
