"""Export/import round trips through the real versioned project store."""
import copy
import json
import tempfile
import unittest
from pathlib import Path

import ai_jobs as ai
from server import Store, import_rows, new_project, restore_project


STAMP = '2026-09-12T08:30:00+00:00'


def project_fixture():
    project = new_project('饮水机跨平台调研', '宠物饮水机')
    project.update(market='德国', platform='跨平台', language='中文和英文')
    common = {'source': 'TikHub', 'collected_at': STAMP, 'market_scope': '样本地域未确认'}
    import_rows(project, 'keywords', [
        dict(common, id='k1', text='pet water fountain easy to clean', platform='tiktok'),
        dict(common, id='k2', text='宠物饮水机漏水', platform='xhs'),
    ], provenance='live', record_run=False)
    import_rows(project, 'posts', [dict(common, id='p1', platform='reddit', external_id='post-1',
        title='Cleaning the fountain', body='The pump is difficult to clean.',
        source_url='https://www.reddit.com/r/cats/comments/post-1')], provenance='live', record_run=False)
    import_rows(project, 'reviews', [dict(common, id='r1', platform='reddit', post_id='p1',
        review_type='social', body='Can I remove the pump to clean it?')], provenance='live', record_run=False)
    return project


def partial_collection():
    error = {'row': 4, 'platform': 'reddit', 'query': '宠物饮水机',
             'reason': '该平台暂时不可用，其他平台的记录已保存。', 'http': 503}
    pairs = lambda query: [{'original': '宠物饮水机', 'query': query, 'post_id': ''}]
    return {'id': 'e' * 16, 'kind': 'keywords', 'created_at': STAMP,
        'source': '小红书 · TikHub、TikTok · TikHub、Reddit · TikHub',
        'mode': 'collection', 'platform': 'multi', 'platforms': ['xhs', 'tiktok', 'reddit'],
        'status': 'partial', 'requested': 2, 'imported': 2, 'duplicates': 0,
        'errors': [error], 'pages': 2, 'requests': 4, 'request_limit': 4,
        'budget': {'tikhub_requests': 4, 'mcp_queries': 0, 'estimated_tikhub_usd': 0.04,
                   'note': '包含一次查询词翻译，最多四次请求。'},
        'platform_results': [
            {'platform': 'xhs', 'status': 'success', 'pages': 1, 'requests': 1, 'imported': 1,
             'duplicates': 0, 'errors': [], 'query_pairs': pairs('宠物饮水机')},
            {'platform': 'tiktok', 'status': 'success', 'pages': 1, 'requests': 2, 'imported': 1,
             'duplicates': 0, 'errors': [], 'query_pairs': pairs('pet water fountain')},
            {'platform': 'reddit', 'status': 'failed', 'pages': 0, 'requests': 1, 'imported': 0,
             'duplicates': 0, 'errors': [copy.deepcopy(error)], 'query_pairs': pairs('pet water fountain')},
        ],
        'page_results': [
            {'platform': platform, 'kind': 'keywords', 'page': 1, 'query': query,
             'original_query': '宠物饮水机', 'post_id': '', 'http': http,
             'returned': count, 'imported': count, 'duplicates': 0, 'skipped': 0,
             **({'error': error['reason']} if http == 503 else {})}
            for platform, query, http, count in [('xhs', '宠物饮水机', 200, 1),
                ('tiktok', 'pet water fountain', 200, 1), ('reddit', 'pet water fountain', 503, 0)]
        ],
        'translations': [{'original': '宠物饮水机', 'translated': 'pet water fountain',
                          'method': '本地 Codex'}],
        'note': '默认综合排序，不限时间；此次只完成两个平台。'}


def keyword_result(evidence):
    return {'title': '关键词报告', 'summary': '样本涉及清洗和漏水问题。',
        'items': [{'id': row['id'], 'valid': True, 'reason': '使用问题可作为需求线索。',
                   'w5h1': 'HOW', 'intent': '需求意图', 'stage': 'A4', 'emotion': '中性',
                   'theme': '维护体验'} for row in evidence],
        'findings': [{'text': '清洗维护值得继续看评论。', 'evidence_ids': [evidence[0]['id']]}],
        'next_steps': [{'text': '继续采集清洗主题的内容。', 'evidence_ids': [evidence[0]['id']]}]}


def insight_result(evidence):
    refs = [row['id'] for row in evidence]
    audience = {key: '证据不足，待验证' for key in ('natural', 'social', 'consumption',
        'scene', 'lifestyle', 'emotion', 'deep_emotion', 'values', 'explicit_need', 'implicit_need', 'score')}
    audience.update(name='正在解决水泵清洗问题的用户', why='原文出现清洗问题，先验证维护成本。', evidence_ids=refs)
    return {'title': '千机塔营销洞察', 'summary': '先验证清洗维护这一个问题。',
        'core_opportunity': {'text': '提供可验证的清洗步骤，再判断产品改进需求。', 'evidence_ids': refs},
        'audiences': [audience],
        'topics': [{'title': '水泵能不能拆下来清洗', 'layer': 'A4', 'angle': '展示清洗步骤和限制。',
                    'why': '先回答原文中的使用问题。', 'words': [evidence[0]['text']], 'evidence_ids': refs}],
        'cautions': [{'text': '这些样本不代表用户比例或购买意愿。', 'evidence_ids': refs}],
        'self_check': {**{key: True for key in ('no_anxiety', 'narrowest', 'has_contrast', 'real_demand')},
                       'note': '只把有限样本作为进一步验证的线索。'}}


def report_fixture(project, kind, report_id, target=''):
    prepared = ai.prepare(project, {'kind': kind, 'target': target})
    evidence = prepared['evidence_snapshot']
    if kind == 'translate':
        result = {'title': '中文翻译', 'summary': '原文保留。', 'target_language': 'zh-CN',
                  'translations': [{'id': row['id'], 'translation': '中文译文：' + row['row_id']} for row in evidence]}
    else:
        result = keyword_result(evidence) if kind == 'keywords' else insight_result(evidence)
    record = dict(prepared, id=report_id, status='success', data_version=project['data_version'],
        created_at=STAMP, finished_at=STAMP, prompt_version=ai.PROMPT_VERSION,
        model='test-fixture', message='已完成', usage={'input_tokens': 40, 'output_tokens': 80}, report=result)
    return ai.normalize_ai_report(record, project)


class WorkflowRestoreTests(unittest.TestCase):
    def round_trip(self, project):
        with tempfile.TemporaryDirectory() as directory:
            source = Store(Path(directory) / 'source')
            destination = Store(Path(directory) / 'destination')
            saved = source.save(copy.deepcopy(project))
            package = json.loads(json.dumps(source.load(saved['id']), ensure_ascii=False))
            recovered = destination.save(restore_project(package))
            # Reopen both stores to exercise manifests, content hashes and disk JSON.
            original = Store(Path(directory) / 'source').load(saved['id'])
            result = Store(Path(directory) / 'destination').load(recovered['id'])
            self.assertNotEqual(original['id'], result['id'])
            return original, result

    def test_partial_multi_platform_run_preserves_every_field(self):
        project = project_fixture()
        project['runs'].append(partial_collection())
        original, restored = self.round_trip(project)
        self.assertEqual(restored['runs'], original['runs'])
        self.assertEqual(restored['runs'][0]['status'], 'partial')
        self.assertEqual(restored['runs'][0]['page_results'][-1]['http'], 503)
        self.assertEqual(restored['runs'][0]['translations'][0]['method'], '本地 Codex')

    def test_translations_and_their_reports_keep_all_original_text(self):
        project = project_fixture()
        before = copy.deepcopy(project)
        for index, target in enumerate(('keywords', 'posts', 'reviews')):
            record = report_fixture(project, 'translate', format(index + 1, '016x'), target)
            for item in record['report']['translations']:
                row_id = item['id'].split(':', 1)[1]
                next(row for row in project[target] if row['id'] == row_id)['translation'] = item['translation']
            project['ai_reports'].append(record)
        original, restored = self.round_trip(project)
        for kind, raw_fields in (('keywords', ('text',)), ('posts', ('title', 'body')), ('reviews', ('body',))):
            self.assertEqual(restored[kind], original[kind])
            for old, row in zip(before[kind], restored[kind]):
                for field in raw_fields:
                    self.assertEqual(row[field], old[field])
                self.assertTrue(row['translation'].startswith('中文译文：'))
        self.assertEqual(restored['ai_reports'], original['ai_reports'])
        for report in restored['ai_reports']:
            self.assertEqual(report['report']['target_language'], 'zh-CN')
            ai.normalize_ai_report(report, restored)

    def test_successful_keyword_and_insight_reports_keep_readable_evidence(self):
        project = project_fixture()
        project['ai_reports'] = [report_fixture(project, 'keywords', 'b' * 16),
                                 report_fixture(project, 'insights', 'c' * 16)]
        original, restored = self.round_trip(project)
        self.assertEqual(restored['ai_reports'], original['ai_reports'])
        for record in restored['ai_reports']:
            self.assertEqual(ai.normalize_ai_report(record, restored), record)
            for evidence in record['evidence_snapshot']:
                row = next(row for row in restored[evidence['kind']] if row['id'] == evidence['row_id'])
                self.assertEqual(ai.raw_text(evidence['kind'], row), evidence['text'])
        self.assertEqual(restored['ai_reports'][0]['report']['stats']['total'], 2)
        self.assertIn('reviews:r1', restored['ai_reports'][1]['scope']['evidence_ids'])

    def test_forged_report_reference_is_rejected_even_when_snapshot_is_valid(self):
        for kind in ('keywords', 'insights'):
            with self.subTest(kind=kind):
                project = project_fixture()
                record = report_fixture(project, kind, 'b' * 16)
                claim = record['report']['findings'][0] if kind == 'keywords' else record['report']['core_opportunity']
                claim['evidence_ids'] = ['reviews:invented']
                project['ai_reports'] = [record]
                with self.assertRaisesRegex(ValueError, '证据|依据'):
                    self.round_trip(project)

    def test_running_jobs_restore_as_interrupted_without_fabricated_results(self):
        project = project_fixture()
        record = report_fixture(project, 'keywords', 'b' * 16)
        record.update(status='running', report=None, finished_at='', message='分析中')
        project['ai_reports'] = [record]
        run = partial_collection()
        # XHS finished; a translation request is in flight before TikTok;
        # Reddit has not started. The already returned page remains usable.
        run.update(status='running', requested=1, imported=1, pages=1, requests=2,
                   errors=[], translations=[], page_results=run['page_results'][:1])
        run['platform_results'][1].update(status='running', pages=0, requests=1,
                                         imported=0, errors=[], query_pairs=[])
        run['platform_results'][2].update(status='pending', pages=0, requests=0,
                                         imported=0, errors=[], query_pairs=[])
        project['runs'] = [run]
        original, restored = self.round_trip(project)
        self.assertEqual(restored['ai_reports'][0]['status'], 'interrupted')
        self.assertIsNone(restored['ai_reports'][0]['report'])
        self.assertEqual(restored['runs'][0]['status'], 'interrupted')
        self.assertEqual([row['status'] for row in restored['runs'][0]['platform_results']],
                         ['success', 'interrupted', 'interrupted'])
        self.assertEqual(restored['runs'][0]['page_results'], original['runs'][0]['page_results'])
        self.assertEqual(restored['keywords'], original['keywords'])

    def test_project_market_language_and_data_version_survive_import(self):
        original, restored = self.round_trip(project_fixture())
        for field in ('name', 'keyword', 'market', 'platform', 'language', 'created_at', 'data_version', 'demo'):
            self.assertEqual(restored[field], original[field], field)

    def test_inconsistent_collection_totals_and_missing_post_are_rejected(self):
        for failure in ('budget', 'platform_count', 'post_reference'):
            with self.subTest(failure=failure):
                project = project_fixture()
                run = partial_collection()
                if failure == 'budget':
                    run['budget']['tikhub_requests'] += 1
                elif failure == 'platform_count':
                    run['platform_results'][0]['imported'] += 1
                else:
                    run['page_results'][0]['post_id'] = 'missing-post'
                project['runs'] = [run]
                with self.assertRaises(ValueError):
                    self.round_trip(project)


if __name__ == '__main__':
    unittest.main()
