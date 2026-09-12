import copy
import json
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

import ai_jobs as ai
import codex_runner


def project():
    return {'id': 'a' * 16, 'keyword': '宠物饮水机', 'revision': 0, 'data_version': 1,
            'keywords': [{'id': 'k1', 'text': 'pet water fountain easy to clean', 'translation': '',
                          'platform': 'tiktok', 'source': 'TikHub', 'market_scope': '未限定地域', 'provenance': 'live'},
                         {'id': 'k2', 'text': '宠物饮水机漏水', 'translation': '', 'platform': 'xiaohongshu',
                          'source': 'TikHub', 'market_scope': '中文讨论', 'provenance': 'live'}],
            'posts': [], 'reviews': [], 'analyses': [{'method': '规则整理'}], 'ai_reports': []}


def keyword_result(evidence):
    return {'title': '关键词报告', 'summary': '清洗和漏水值得进一步查评论。',
            'items': [{'id': e['id'], 'valid': True, 'reason': '', 'w5h1': 'HOW',
                       'intent': '需求意图', 'stage': 'A4', 'emotion': '中性', 'theme': '维护体验'} for e in evidence],
            'findings': [{'text': '目前样本涉及维护问题。', 'evidence_ids': [evidence[0]['id']]}],
            'next_steps': [{'text': '采集维护相关评论。', 'evidence_ids': [evidence[0]['id']]}]}


class MemoryStore:
    def __init__(self, p):
        self.p = copy.deepcopy(p)

    def load(self, id_):
        return copy.deepcopy(self.p)

    def save(self, p, expected):
        if expected != self.p['revision']:
            raise ValueError('冲突')
        p['revision'] += 1
        self.p = copy.deepcopy(p)

    def listing(self):
        return [{'id': self.p['id']}]


class AIJobsTests(unittest.TestCase):
    def test_source_prompts_and_adaptations(self):
        prompt = ai.system_prompt('insights')
        self.assertIn(ai.PROMPTS['prompts']['_AUDIENCE_SYSTEM'], prompt)
        self.assertIn(ai.PROMPTS['prompts']['_INSIGHT_SYSTEM'], prompt)
        self.assertIn('必须保留', ai.system_prompt('keywords'))
        self.assertNotIn('小红书 + 抖音（多平台汇总）', prompt)

    def test_bounded_coverage_is_explicit_and_platforms_preserved(self):
        p = project()
        p['keywords'] = [dict(p['keywords'][0], id='k' + str(i)) for i in range(180)]
        prepared = ai.prepare(p, {'kind': 'keywords'})
        self.assertEqual(prepared['scope']['total'], 180)
        self.assertEqual(prepared['scope']['processed'], 150)
        self.assertEqual(prepared['scope']['truncated'], 30)
        self.assertEqual(prepared['evidence_snapshot'][0]['platform'], 'tiktok')

    def test_translation_does_not_truncate_and_skips_existing(self):
        p = project()
        p['posts'] = [{'id': 'post1', 'title': 'Title', 'body': 'a' * 5000, 'translation': ''},
                      {'id': 'post2', 'title': 'Old', 'body': 'Text', 'translation': '已有译文'}]
        prepared = ai.prepare(p, {'kind': 'translate', 'target': 'posts'})
        self.assertEqual(prepared['scope']['processed'], 1)
        self.assertEqual(len(prepared['evidence_snapshot'][0]['text']), 5006)
        self.assertFalse(prepared['evidence_snapshot'][0]['text_truncated'])

    def test_invalid_selection_cannot_fall_back_to_all_data(self):
        with self.assertRaises(ValueError):
            ai.prepare(project(), {'kind': 'keywords', 'ids': ['absent']})
        with self.assertRaises(ValueError):
            ai.prepare(project(), {'kind': 'translate', 'target': 'files'})

    def test_report_rejects_missing_duplicate_and_invented_evidence(self):
        evidence = ai.prepare(project(), {'kind': 'keywords'})['evidence_snapshot']
        for modify in (lambda r: r['items'].pop(),
                       lambda r: r['items'].append(r['items'][0]),
                       lambda r: r['findings'][0].update(evidence_ids=['reviews:invented'])):
            result = keyword_result(evidence)
            modify(result)
            with self.assertRaises(ValueError):
                ai.validate_report('keywords', result, evidence)

    def test_statistics_are_computed_from_classifications(self):
        evidence = ai.prepare(project(), {'kind': 'keywords'})['evidence_snapshot']
        result = keyword_result(evidence)
        result['items'][1].update(valid=False, reason='测试无效原因')
        result['stats'] = {'valid': 9000}
        result = ai.validate_report('keywords', result, evidence)
        self.assertEqual(result['stats']['valid'], 1)
        self.assertEqual(result['stats']['total'], 2)
        self.assertEqual(result['topic_map'][0]['count'], 1)

    def test_report_restore_checks_source_hash_and_recomputes_stats(self):
        p = project()
        prepared = ai.prepare(p, {'kind': 'keywords'})
        record = dict(prepared, id='b' * 16, status='success', data_version=1,
                      report=keyword_result(prepared['evidence_snapshot']))
        restored = ai.normalize_ai_report(record, p)
        self.assertEqual(restored['report']['stats']['total'], 2)
        renamed = copy.deepcopy(p)
        renamed['id'] = 'c' * 16
        ai.normalize_ai_report(record, renamed)
        p['keywords'][0]['text'] = 'changed source'
        with self.assertRaises(ValueError):
            ai.normalize_ai_report(record, p)
        record['scope']['source_fingerprint'] = '0' * 64
        with self.assertRaises(ValueError):
            ai.normalize_ai_report(record, project())

    def test_restore_strips_extra_metadata_and_rejects_claim_type(self):
        p = project()
        prepared = ai.prepare(p, {'kind': 'keywords'})
        record = dict(prepared, id='b' * 16, status='success', data_version=1,
                      report=keyword_result(prepared['evidence_snapshot']),
                      usage={'input_tokens': 200, 'account': 'private', 'output_tokens': -1})
        record['scope']['extra'] = 'hidden metadata'
        restored = ai.normalize_ai_report(record, p)
        self.assertEqual(restored['usage'], {'input_tokens': 200})
        self.assertNotIn('extra', restored['scope'])
        record['report']['findings'][0]['text'] = {'html': '<script>'}
        with self.assertRaises(ValueError):
            ai.normalize_ai_report(record, p)

    def test_cross_collection_and_forged_scope_cannot_restore(self):
        p = project()
        prepared = ai.prepare(p, {'kind': 'keywords'})
        record = dict(prepared, id='b' * 16, status='success', data_version=1,
                      report=keyword_result(prepared['evidence_snapshot']))
        record['scope']['counts']['keywords']['processed'] = 100
        with self.assertRaises(ValueError):
            ai.normalize_ai_report(record, p)
        record['scope']['counts']['keywords']['processed'] = 2
        record['kind'], record['target'] = 'translate', 'reviews'
        with self.assertRaises(ValueError):
            ai.normalize_ai_report(record, p)

    def test_translation_job_keeps_original_and_rule_analyses(self):
        p = project()
        original = copy.deepcopy(p['keywords'])
        store = MemoryStore(p)
        def runner(system, payload, schema, cancel):
            return {'title': '翻译', 'summary': '翻译完成', 'target_language': 'zh-CN',
                    'translations': [{'id': e['id'], 'translation': '中文译文'} for e in payload['evidence']]}, {'model': 'test', 'usage': {}}
        jobs = ai.AIJobs(store, threading.RLock(), lambda: 'b' * 16, lambda: '2026-09-12', runner)
        with patch('ai_jobs.threading.Thread'):
            job = jobs.start(p, {'kind': 'translate', 'target': 'keywords'})
        jobs.work(jobs.jobs[job['id']])
        self.assertEqual(jobs.get(job['id'])['status'], 'success')
        self.assertEqual(store.p['keywords'][0]['text'], original[0]['text'])
        self.assertEqual(store.p['keywords'][0]['translation'], '中文译文')
        self.assertEqual(store.p['analyses'], [{'method': '规则整理'}])
        self.assertEqual(len(store.p['ai_reports']), 1)
        ai.normalize_ai_report(store.p['ai_reports'][0], store.p)

    def test_translation_rejects_source_changed_during_ai_work(self):
        p = project()
        store = MemoryStore(p)
        def runner(system, payload, schema, cancel):
            store.p['keywords'][0]['text'] = 'different original'
            return {'title': '翻译', 'summary': '', 'target_language': 'zh-CN',
                    'translations': [{'id': e['id'], 'translation': 'wrong version'} for e in payload['evidence']]}, {}
        jobs = ai.AIJobs(store, threading.RLock(), lambda: 'b' * 16, lambda: '2026-09-12', runner)
        with patch('ai_jobs.threading.Thread'):
            job = jobs.start(p, {'kind': 'translate', 'target': 'keywords'})
        jobs.work(jobs.jobs[job['id']])
        self.assertEqual(jobs.get(job['id'])['status'], 'failed')
        self.assertEqual(store.p['keywords'][0]['translation'], '')

    def test_honest_failed_insight_self_checks_save_for_review(self):
        p = project()
        store = MemoryStore(p)
        reference = 'keywords:k1'
        result = {'title': '有限需求假设', 'summary': '只有搜索词，付费需求待验证。',
                  'core_opportunity': {'text': '清洗便利可能是研究方向，尚不能判断购买意愿。', 'evidence_ids': [reference]},
                  'audiences': [{**{k: '待验证' for k in ('name', 'natural', 'social', 'consumption', 'scene',
                                    'lifestyle', 'emotion', 'deep_emotion', 'values', 'explicit_need', 'implicit_need', 'score', 'why')},
                                  'evidence_ids': [reference]}],
                  'topics': [{'title': '饮水机清洗怎么做', 'layer': 'A4', 'angle': '待验证', 'why': '需要更多评论',
                              'words': [p['keywords'][0]['text']], 'evidence_ids': [reference]}],
                  'cautions': [{'text': '不能将搜索词当作付费证据。', 'evidence_ids': [reference]}],
                  'self_check': {'no_anxiety': False, 'narrowest': False, 'has_contrast': False,
                                 'real_demand': False, 'note': '样本缺少付费证据，其他策略也需要复核。'}}
        jobs = ai.AIJobs(store, threading.RLock(), lambda: 'b' * 16, lambda: '2026-09-12',
                         lambda *args, **kwargs: (result, {}))
        with patch('ai_jobs.threading.Thread'):
            job = jobs.start(p, {'kind': 'insights'})
        jobs.work(jobs.jobs[job['id']])
        self.assertEqual(jobs.get(job['id'])['status'], 'success')
        self.assertIn('需复核', jobs.get(job['id'])['message'])
        saved = ai.normalize_ai_report(store.p['ai_reports'][0], store.p)
        self.assertEqual(saved['report']['self_check'], result['self_check'])
        result['core_opportunity']['evidence_ids'] = ['keywords:invented']
        with self.assertRaises(ValueError):
            ai.validate_report('insights', result, saved['evidence_snapshot'])

    def test_restart_reports_interrupted_and_cancel_never_persists_result(self):
        p = project()
        store = MemoryStore(p)
        jobs = ai.AIJobs(store, threading.RLock(), lambda: 'b' * 16, lambda: '2026-09-12',
                         lambda *args, **kwargs: (keyword_result(args[1]['evidence']), {}))
        with patch('ai_jobs.threading.Thread'):
            job = jobs.start(p, {'kind': 'keywords'})
        rebooted = ai.AIJobs(store, threading.RLock(), lambda: 'c' * 16, lambda: '')
        self.assertEqual(rebooted.get(job['id'])['status'], 'interrupted')
        jobs.cancel(job['id'])
        jobs.work(jobs.jobs[job['id']])
        self.assertEqual(jobs.get(job['id'])['status'], 'cancelled')
        self.assertIsNone(store.p['ai_reports'][0]['report'])

    def test_local_codex_preserves_provider_config_but_disables_tools_and_rules(self):
        with tempfile.TemporaryDirectory() as d, patch('codex_runner.configured_model', return_value='test-model'):
            args = codex_runner.command('/codex', Path(d), Path(d) / 'schema.json', Path(d) / 'system.md')
        self.assertNotIn('--ignore-user-config', args)
        self.assertIn('--ignore-rules', args)
        self.assertIn('--ephemeral', args)
        self.assertEqual(args[args.index('--sandbox') + 1], 'read-only')
        overrides = {args[i + 1] for i, value in enumerate(args) if value == '-c'}
        for feature in ('shell_tool', 'apps', 'plugins', 'hooks', 'multi_agent', 'computer_use'):
            self.assertIn(f'features.{feature}=false', overrides)
        self.assertIn('developer_instructions=""', overrides)
        self.assertFalse(any(value.startswith(('model_provider', 'model_providers')) for value in overrides))
        self.assertNotIn('--dangerously-bypass-approvals-and-sandbox', args)

    def test_codex_timeout_and_cancel_still_terminate_the_process(self):
        schema = {'type': 'object', 'properties': {}, 'required': [], 'additionalProperties': False}
        for cancelled in (False, True):
            event = threading.Event()
            if cancelled:
                event.set()
            with patch('codex_runner.executable', return_value='/codex'), \
                    patch('codex_runner.mcp_server_names', return_value=[]), \
                    patch('codex_runner.configured_model', return_value='test-model'), \
                    patch('codex_runner.subprocess.Popen') as popen, \
                    patch('codex_runner.time.monotonic', side_effect=[0, 601]):
                process = popen.return_value
                process.poll.return_value = None
                process.communicate.return_value = ('', '')
                with self.assertRaises(codex_runner.Cancelled if cancelled else codex_runner.AIError):
                    codex_runner.run('纯文本任务', {}, schema, cancel=event)
                process.terminate.assert_called_once()
                process.communicate.assert_called_once_with(timeout=3)


if __name__ == '__main__':
    unittest.main()
