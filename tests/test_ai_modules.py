import copy
import json
import subprocess
import tempfile
import threading
import unittest
from unittest.mock import patch

import ai_jobs as ai
import ai_modules as modules
import codex_runner
from test_ai_jobs import MemoryStore, project


def sample_project():
    p = project()
    p['posts'] = [{'id': 'p1', 'title': 'How I clean the fountain', 'body': 'The narrow pump is hard to reach.',
                   'platform': 'reddit', 'source': 'TikHub', 'market_scope': '未限定地域', 'provenance': 'live',
                   'likes': -1, 'comment_count': None}]
    p['reviews'] = [{'id': 'r1', 'body': 'I bought this fountain but cleaning the pump takes too long.',
                     'platform': 'amazon', 'source': '卖家精灵', 'market_scope': '美国站', 'provenance': 'live',
                     'rating': 2}]
    return p


def point(ids, basis='inference'):
    return {'text': '清洗耗时可能增加维护负担。' if basis != 'unknown' else '资料不足，待验证。',
            'basis': basis, 'evidence_ids': list(ids), 'validation': '访谈实际清洗步骤和每次耗时。'}


def module_result(key, evidence):
    ids = [e['id'] for e in evidence]
    words = [e for e in evidence if e['kind'] == 'keywords']
    base = {'title': modules.MODULES[key]['label'], 'summary': '优先验证清洗维护是否构成购买阻碍。',
            'quality': 'limited', 'limitations': ['当前仅有少量样本，不能代表总体。']}
    if key == 'clean':
        return dict(base, items=[{'id': e['id'], 'valid': True, 'reason': '表达维护需求', 'w5h1': 'HOW',
                    'intent': '需求意图', 'stage': 'A4', 'emotion': '中性', 'theme': '清洗维护',
                    'content_suggestion': '展示泵体清洗步骤和耗时。'} for e in evidence],
                    theme_recommendations=[{'theme': '清洗维护', 'direction': point(ids), 'layer': 'A4'}],
                    high_value_terms=[{'text': words[0]['text'], 'evidence_id': words[0]['id'], 'why': point(ids)}],
                    brand_opportunities=[], findings=[point(ids)], next_steps=[point(ids)])
    if key == 'intent':
        return dict(base, items=[{'id': e['id'], 'stage': 'A4', 'emotion': '纠结'} for e in evidence],
                    stage_insights=[{'stage': 'A4', 'interpretation': point(ids), 'next_content': point(ids)}],
                    bottleneck=point(ids), demands=[{'need': '减少清洗耗时', 'urgency': '待验证',
                    'diagnosis': point(ids), 'action': point(ids)}],
                    emotions=[{'emotion': '纠结', 'interpretation': point(ids)}], next_steps=[point(ids)])
    if key == 'segments':
        result = module_result('audience', evidence)
        for person in result['audiences']:
            person.update(motives={k: point(ids) for k in modules.MOTIVE_KEYS}, buying_motivation=point(ids), life_stage=point([], 'unknown'),
                          marketing={k: point(ids) for k in ('product','channels','content','creators','promotion')})
        return result
    if key == 'audience':
        person = {'name': '被清洗步骤劝退的养宠者', 'one_line': '希望持续供水，又不愿增加泵体清洗负担。',
                  'layers': {k: point(ids) for k in ('natural', 'social', 'consumption', 'scene',
                                                   'lifestyle', 'emotion', 'deep_emotion', 'values')},
                  'day_in_life': [{'moment': moment, 'scene': '检查饮水机', 'task': '保持饮水清洁',
                      'friction': '泵体缝隙难清理', 'basis': 'inference', 'evidence_ids': ids,
                      'validation': '请用户复述真实清洗顺序。'} for moment in ('补水时', '清洗时')],
                  'needs': {k: point(ids) for k in ('explicit', 'implicit', 'deep')},
                  **{k: [point(ids)] for k in ('purchase_triggers', 'decision_factors', 'barriers', 'alternatives')},
                  'positioning': {k: point(ids) for k in ('target', 'promise', 'proof', 'avoid')},
                  'search_terms': [{'text': e['text'], 'evidence_id': e['id']} for e in words],
                  'scores': {k: {'score': None, 'reason': point([], 'unknown')} for k in ('pain', 'payment', 'fit', 'content')},
                  'priority': '待验证', 'priority_reason': point(ids),
                  'validation_questions': ['一次清洗需要哪些步骤？', '清洗时间是否影响再次购买？'], 'evidence_ids': ids}
        person['layers']['natural'] = point([], 'unknown')
        return dict(base, audiences=[person], audience_map=point(ids), next_steps=[point(ids)])
    if key == 'comments':
        quote = {'quote': evidence[0]['text'], 'evidence_id': ids[0]}
        return dict(base, pains=[{'point': point(ids), 'quotes': [quote]}], questions=[], loves=[],
                    golden_quotes=[quote], topics=[point(ids)], demand_priorities=[point(ids)], next_steps=[point(ids)])
    if key == 'notes':
        return dict(base, themes=[{'theme': '清洗演示', 'explanation': point(ids)}],
                    angles=[{'angle': '先展示最难清洗的部件', 'why': point(ids)}],
                    performance_note='社区分数不能解释购买意愿。',
                    patterns=[{'part': part, 'finding': point(ids)} for part in ('opening', 'body', 'closing')],
                    topics=[{'title': '泵体清洗步骤', 'angle': '展示内部缝隙', 'why': point(ids)}],
                    gaps=[point(ids)], next_steps=[point(ids)])
    if key == 'topics':
        return dict(base, topics=[{'title': '饮水机泵体到底要洗多久', 'target': '关注维护负担的养宠者',
                    'stage': 'A4', 'angle': '把日常清洗过程展示出来', 'format': '操作视频',
                    'opening': '从拆开泵体的第一步开始计时。', 'outline': ['拍摄拆洗步骤', '核对可见时间'],
                    'call_to_action': '收集其他使用者的清洗步骤。', 'why': point(ids),
                    'words': [e['text'] for e in words], 'evidence_ids': ids}],
                    priority_reason=point(ids), next_steps=[point(ids)])
    return dict(base, core_opportunity=point(ids), narrowest_entry=point(ids),
                priority_audiences=[{'name': '关注维护的养宠者', 'why': point(ids)}], positioning=point(ids),
                actions=[{'action': '做一次清洗记录', 'why': point(ids), 'deliverable': '连续清洗视频',
                          'verification': '记录完整步骤与计时，不剪掉难点'}], cautions=[point(ids)],
                self_check={'no_anxiety': True, 'narrowest': True, 'has_contrast': True, 'real_demand': False,
                            'note': '付费需求仍需验证。'})


class ModuleTests(unittest.TestCase):
    def job(self, selected, runner=None, p=None):
        p = p or sample_project()
        store = MemoryStore(p)
        counter = iter(('b' * 16, 'c' * 16, 'd' * 16))
        runner = runner or (lambda system, payload, schema, cancel: (module_result(payload['module'], payload['evidence']), {'model': 'test'}))
        jobs = ai.AIJobs(store, threading.RLock(), lambda: next(counter), lambda: '2026-09-12T12:00:00Z', runner)
        with patch('ai_jobs.threading.Thread'):
            public = jobs.start(store.load(p['id']), {'kind': 'insights', 'modules': selected})
        return jobs, store, public['id']

    def test_invalid_selected_codex_path_blocks_legacy_and_modules_before_save(self):
        p = sample_project()
        store = MemoryStore(p)
        jobs = ai.AIJobs(store, threading.RLock(), lambda: 'b' * 16, lambda: '2026-09-12')
        with patch('codex_runner.executable', return_value=''), patch('codex_runner.subprocess.Popen') as popen:
            for body in ({'kind': 'keywords'}, {'kind': 'insights', 'modules': ['audience']}):
                with self.subTest(body=body), self.assertRaisesRegex(ValueError, 'codex.local.json'):
                    jobs.start(store.load(p['id']), body)
            popen.assert_not_called()
        self.assertEqual(store.p['ai_reports'], [])
        self.assertEqual(store.p['revision'], 0)

    def test_default_runner_mcp_discovery_failure_is_saved_per_module_without_model_execution(self):
        p = sample_project()
        store = MemoryStore(p)
        jobs = ai.AIJobs(store, threading.RLock(), lambda: 'b' * 16, lambda: '2026-09-12')
        failure = subprocess.CompletedProcess(['/codex'], 1, '', 'private-provider-detail')
        with patch('codex_runner.executable', return_value='/codex'), \
                patch('codex_runner.configured_model', return_value='test-model'), \
                patch('codex_runner.subprocess.run', return_value=failure) as discovery, \
                patch('codex_runner.subprocess.Popen') as popen:
            with patch('ai_jobs.threading.Thread'):
                public = jobs.start(store.load(p['id']), {'kind': 'insights', 'modules': ['audience', 'comments']})
            jobs.work(jobs.jobs[public['id']])
            self.assertEqual(discovery.call_count, 2)
            popen.assert_not_called()
        saved = ai.normalize_ai_report(store.p['ai_reports'][0], store.p)
        self.assertEqual(saved['status'], 'failed')
        for module in saved['report']['modules'].values():
            self.assertEqual(module['status'], 'failed')
            self.assertIn('无法确认 Codex 工具隔离配置', module['message'])
            self.assertIsNone(module['report'])
        self.assertNotIn('private-provider-detail', json.dumps(saved))

    def test_all_modules_are_independent_and_completed_blocks_persist_before_next_call(self):
        calls = []
        def runner(system, payload, schema, cancel):
            key = payload['module']
            if calls:
                saved = store.p['ai_reports'][0]['report']['modules'][calls[-1]]
                self.assertEqual(saved['status'], 'success')
            calls.append(key)
            self.assertEqual({e['kind'] for e in payload['evidence']}, set(modules.MODULES[key]['collections']))
            return module_result(key, payload['evidence']), {'model': 'test', 'usage': {'input_tokens': 10, 'secret': 'discard'}}
        jobs, store, id_ = self.job(list(reversed(modules.MODULE_ORDER)), runner)
        jobs.work(jobs.jobs[id_])
        self.assertEqual(calls, list(modules.MODULE_ORDER))
        self.assertEqual(jobs.get(id_)['status'], 'success')
        self.assertEqual(jobs.get(id_)['completed_modules'], len(modules.MODULE_ORDER))
        saved = ai.normalize_ai_report(store.p['ai_reports'][0], store.p)
        self.assertEqual(saved['usage'], {'input_tokens': 10 * len(modules.MODULE_ORDER)})
        self.assertEqual(saved['report']['modules']['notes']['evidence_snapshot'][0]['metrics'], {'likes': -1, 'comment_count': None})
        self.assertFalse(saved['report']['modules']['summary']['report']['self_check']['real_demand'])

    def test_single_failure_keeps_successes_and_only_selected_block_is_rerun(self):
        calls = []
        def runner(system, payload, schema, cancel):
            calls.append(payload['module'])
            if payload['module'] == 'comments':
                raise codex_runner.AIError('评论模块本次超时')
            return module_result(payload['module'], payload['evidence']), {}
        jobs, store, id_ = self.job(['clean', 'comments', 'notes'], runner)
        jobs.work(jobs.jobs[id_])
        self.assertEqual(jobs.get(id_)['status'], 'partial')
        old = ai.normalize_ai_report(store.p['ai_reports'][0], store.p)
        jobs.runner = lambda system, payload, schema, cancel: (calls.append(payload['module']) or module_result(payload['module'], payload['evidence']), {})
        with patch('ai_jobs.threading.Thread'):
            new = jobs.start(store.load(store.p['id']), {'kind': 'insights', 'modules': ['comments'], 'base_report_id': id_})
        jobs.work(jobs.jobs[new['id']])
        self.assertEqual(calls, ['clean', 'comments', 'notes', 'comments'])
        self.assertEqual(jobs.get(new['id'])['status'], 'success')
        self.assertEqual(len(store.p['ai_reports']), 2)
        restored = ai.normalize_ai_report(store.p['ai_reports'][1], store.p)
        self.assertEqual(restored['report']['modules']['clean'], old['report']['modules']['clean'])

    def test_cancel_preserves_previous_block_and_interrupted_report_can_continue(self):
        def runner(system, payload, schema, cancel):
            if payload['module'] == 'audience':
                cancel.set()
            return module_result(payload['module'], payload['evidence']), {}
        jobs, store, id_ = self.job(['clean', 'audience', 'summary'], runner)
        jobs.work(jobs.jobs[id_])
        self.assertEqual(jobs.get(id_)['status'], 'cancelled')
        saved = ai.normalize_ai_report(store.p['ai_reports'][0], store.p)
        self.assertEqual(saved['report']['modules']['clean']['status'], 'success')
        self.assertEqual(saved['report']['modules']['summary']['status'], 'cancelled')
        interrupted = copy.deepcopy(saved)
        interrupted['status'] = 'running'
        interrupted['report']['modules']['summary']['status'] = 'pending'
        restored = ai.normalize_ai_report(interrupted, store.p)
        self.assertEqual(restored['status'], 'interrupted')
        self.assertEqual(restored['report']['modules']['summary']['status'], 'interrupted')
        jobs.runner = lambda system, payload, schema, cancel: (module_result(payload['module'], payload['evidence']), {})
        with patch('ai_jobs.threading.Thread'):
            new = jobs.start(store.load(store.p['id']), {'kind': 'insights', 'modules': ['audience', 'summary'], 'base_report_id': id_})
        jobs.work(jobs.jobs[new['id']])
        self.assertEqual(jobs.get(new['id'])['status'], 'success')

    def test_empty_module_is_skipped_without_calling_codex(self):
        p = sample_project(); p['reviews'] = []
        jobs, store, id_ = self.job(['comments'], lambda *a, **k: self.fail('empty module invoked model'), p)
        jobs.work(jobs.jobs[id_])
        saved = ai.normalize_ai_report(store.p['ai_reports'][0], store.p)
        self.assertEqual(saved['status'], 'failed')
        self.assertEqual(saved['report']['modules']['comments']['status'], 'skipped')

    def test_empty_personas_are_not_counted_as_a_completed_portrait(self):
        def runner(system, payload, schema, cancel):
            result = module_result('audience', payload['evidence'])
            result['audiences'] = []
            result['audience_map'] = point([], 'unknown')
            return result, {}
        jobs, store, id_ = self.job(['audience'], runner)
        jobs.work(jobs.jobs[id_])
        self.assertEqual(jobs.get(id_)['status'], 'failed')
        saved = ai.normalize_ai_report(store.p['ai_reports'][0], store.p)
        self.assertIn('已保存 0/1', saved['report']['summary'])
        self.assertIn('依据不足，未形成具体画像，请补充', saved['report']['modules']['audience']['message'])
        self.assertIsNone(saved['report']['modules']['audience']['report'])

    def test_upstream_rerun_invalidates_summary_without_extra_call_then_summary_uses_new_portrait(self):
        calls, contexts = [], []
        def runner(system, payload, schema, cancel):
            key = payload['module']; calls.append(key)
            result = module_result(key, payload['evidence'])
            if key == 'audience':
                result['audiences'][0]['name'] = '清洗耗时的养宠者' if calls.count('audience') == 1 else '被泵体缝隙劝退的养宠者'
            if key == 'summary':
                contexts.append(copy.deepcopy(payload['prior_modules']))
            return result, {}
        jobs, store, id_ = self.job(['audience', 'summary'], runner)
        jobs.work(jobs.jobs[id_])
        original = copy.deepcopy(store.p['ai_reports'][0])
        with patch('ai_jobs.threading.Thread'):
            rerun = jobs.start(store.load(store.p['id']), {'kind': 'insights', 'modules': ['audience'], 'base_report_id': id_})
        jobs.work(jobs.jobs[rerun['id']])
        self.assertEqual(calls, ['audience', 'summary', 'audience'])
        self.assertEqual(store.p['ai_reports'][0], original)
        changed = ai.normalize_ai_report(store.p['ai_reports'][1], store.p)
        self.assertEqual(changed['status'], 'partial')
        stale = changed['report']['modules']['summary']
        self.assertEqual(stale['status'], 'interrupted')
        self.assertIn('综合判断需要重新生成', stale['message'])
        self.assertIsNone(stale['report'])
        with patch('ai_jobs.threading.Thread'):
            summary = jobs.start(store.load(store.p['id']), {'kind': 'insights', 'modules': ['summary'], 'base_report_id': rerun['id']})
        jobs.work(jobs.jobs[summary['id']])
        self.assertEqual(jobs.get(summary['id'])['status'], 'success')
        self.assertEqual(calls, ['audience', 'summary', 'audience', 'summary'])
        self.assertEqual(contexts[-1][0]['audiences'][0]['name'], '被泵体缝隙劝退的养宠者')
        self.assertIn('one_line', contexts[-1][0]['audiences'][0])
        self.assertIn('priority', contexts[-1][0]['audiences'][0])
        self.assertEqual(set(contexts[-1][0]['audiences'][0]['needs']), {'explicit', 'implicit', 'deep'})
        large = copy.deepcopy(store.p['ai_reports'][-1]['report']['modules'])
        person = large['audience']['report']['audiences'][0]
        person['name'] = person['one_line'] = '长文本' * 10000
        for need in person['needs'].values():
            need['text'] = '长文本' * 10000
        large['audience']['report']['audiences'] = [person] * 5
        self.assertLessEqual(len(json.dumps(ai.prior_module_context(large), ensure_ascii=False)), 12000)

    def test_scope_limits_apply_per_module_and_counts_are_not_model_statistics(self):
        p = sample_project()
        p['keywords'] = [dict(p['keywords'][0], id='k'+str(i)) for i in range(180)]
        p['reviews'] = [dict(p['reviews'][0], id='r'+str(i)) for i in range(80)]
        jobs, store, id_ = self.job(['clean', 'comments'], p=p)
        jobs.work(jobs.jobs[id_])
        saved = ai.normalize_ai_report(store.p['ai_reports'][0], store.p)
        clean = saved['report']['modules']['clean']
        self.assertEqual(clean['scope']['processed'], 150)
        self.assertEqual(clean['scope']['truncated'], 30)
        self.assertEqual(clean['report']['stats']['total'], 150)
        self.assertEqual(saved['report']['modules']['comments']['scope']['processed'], 60)
        self.assertEqual(saved['scope']['processed'], 210)

    def test_forged_cross_module_quote_metrics_and_status_are_rejected_on_restore(self):
        jobs, store, id_ = self.job(['comments', 'notes'])
        jobs.work(jobs.jobs[id_])
        original = store.p['ai_reports'][0]
        mutations = [
            lambda r: r['report']['modules']['comments']['report']['pains'][0]['point'].update(evidence_ids=['posts:p1']),
            lambda r: r['report']['modules']['comments']['report']['golden_quotes'][0].update(quote='invented quote'),
            lambda r: r['report']['modules']['notes']['evidence_snapshot'][0]['metrics'].update(likes=100000),
            lambda r: r['report']['modules']['comments'].update(data_version=0),
            lambda r: r.update(status='failed'),
        ]
        for mutate in mutations:
            forged = copy.deepcopy(original); mutate(forged)
            with self.assertRaises(ValueError):
                ai.normalize_ai_report(forged, store.p)
        renamed = copy.deepcopy(store.p); renamed['id'] = 'e' * 16
        ai.normalize_ai_report(original, renamed)

    def test_cannot_reuse_stale_report_or_silently_fall_back_from_bad_modules(self):
        jobs, store, id_ = self.job(['clean'])
        jobs.work(jobs.jobs[id_])
        p = store.load(store.p['id']); p['data_version'] += 1
        with self.assertRaises(ValueError):
            jobs.start(p, {'kind': 'insights', 'modules': ['notes'], 'base_report_id': id_})
        for body in ({'kind': 'insights', 'modules': []}, {'kind': 'insights', 'modules': ['unknown']},
                     {'kind': 'keywords', 'modules': ['clean']}, {'kind': 'insights', 'modules': ['clean'], 'ids': ['k1']}):
            with self.assertRaises(ValueError):
                jobs.start(store.load(store.p['id']), body)

    def test_detailed_persona_requires_scenes_and_no_payment_score_from_keywords(self):
        evidence = ai.prepare(sample_project(), {'kind': 'keywords'})['evidence_snapshot']
        result = module_result('audience', evidence)
        modules.validate('audience', result, evidence)
        result['audiences'][0]['scores']['payment'] = {'score': 5, 'reason': point([evidence[0]['id']])}
        with self.assertRaises(ValueError):
            modules.validate('audience', result, evidence)
        result = module_result('audience', evidence)
        result['audiences'][0]['day_in_life'] = []
        with self.assertRaises(ValueError):
            modules.validate('audience', result, evidence)
        result = module_result('audience', evidence)
        result['audiences'][0]['layers']['natural']['validation'] = ''
        with self.assertRaises(ValueError):
            modules.validate('audience', result, evidence)

    def test_real_store_export_restore_preserves_all_module_snapshots(self):
        import server
        source = sample_project()
        p = server.new_project('模块恢复验证', source['keyword'])
        source['reviews'][0].update(review_type='social', post_id='p1', platform='reddit')
        for kind in ('keywords', 'posts', 'reviews'):
            p[kind] = [server.normalize(kind, row, row.get('provenance', 'live')) for row in source[kind]]
        p['data_version'] = 1
        with tempfile.TemporaryDirectory() as folder:
            store = server.Store(folder)
            store.save(p)
            jobs = ai.AIJobs(store, threading.RLock(), lambda: 'f' * 16, server.now,
                            lambda system, payload, schema, cancel: (module_result(payload['module'], payload['evidence']), {}))
            with patch('ai_jobs.threading.Thread'):
                public = jobs.start(store.load(p['id']), {'kind': 'insights', 'modules': list(modules.MODULE_ORDER)})
            jobs.work(jobs.jobs[public['id']])
            saved = store.load(p['id'])
            self.assertEqual(saved['ai_reports'][0]['status'], 'success')
            restored = server.restore_project(json.loads(json.dumps(saved)))
            record = restored['ai_reports'][0]
            self.assertNotEqual(restored['id'], saved['id'])
            self.assertEqual(record['schema_version'], 2)
            self.assertEqual(list(record['report']['modules']), list(modules.MODULE_ORDER))
            self.assertEqual(record['evidence_snapshot'], saved['ai_reports'][0]['evidence_snapshot'])
            self.assertEqual(record['report']['modules']['comments']['report']['golden_quotes'][0]['quote'], p['reviews'][0]['body'])
if __name__ == '__main__':
    unittest.main()

class SegmentStrategyTests(unittest.TestCase):
    def test_person_strategy_is_grounded_and_old_schema_stays_valid(self):
        prepared = ai.prepare(sample_project(), {'kind':'insights'}, modules.MODULES['segments']['collections'], allow_empty=True, include_metrics=True)
        evidence = prepared['evidence_snapshot']
        result = module_result('segments', evidence)
        validated = modules.validate('segments', result, evidence)
        self.assertEqual(set(validated['audiences'][0]['marketing']), {'product','channels','content','creators','promotion'})
        modules.validate('audience', module_result('audience', evidence), evidence)
        result['audiences'][0]['marketing']['product']['evidence_ids'] = ['posts:not-provided']
        with self.assertRaises(ValueError):
            modules.validate('segments', result, evidence)


class ConsumerMotivationIntegrationTests(unittest.TestCase):
    def test_actual_prompt_loads_adapter_only_for_segments(self):
        prompt = ai.module_prompt('segments')
        for word in ('消费动机洞察', '物理环境', '社交困扰', '社交期望'):
            self.assertIn(word, prompt)
        self.assertNotIn('消费动机洞察', ai.module_prompt('clean'))
        self.assertIn('不是实时搜索', prompt)
        self.assertIn('segments 原有 JSON schema', prompt)

class EvidencePipelineTests(unittest.TestCase):
    def test_cleaning_controls_exact_runner_payload_and_roundtrip(self):
        p=sample_project()
        p['keywords'].append({**p['keywords'][0], 'id':'pending', 'text':'待确认词'})
        evidence=ai.prepare(p, {'kind':'insights'}, ('keywords',), allow_empty=True, include_metrics=True)['evidence_snapshot']
        items=[{'id':evidence[0]['id'],'valid':True},{'id':evidence[1]['id'],'valid':False}]
        clean={'status':'success','evidence_snapshot':evidence,'report':{'items':items}}
        p['ai_reports']=[{'id':'clean-fixture','data_version':p['data_version'],'report':{'modules':{'clean':clean}}}]
        selected,note=ai.strategy_input(p)
        self.assertEqual([x['id'] for x in selected['keywords']], [p['keywords'][0]['id']])
        self.assertEqual(len(p['keywords']),3)
        self.assertIn('排除 1',note); self.assertIn('复核 1',note)
        received=[]
        def runner(system,payload,schema,cancel):
            received.extend(e['id'] for e in payload['evidence'])
            return module_result('segments',payload['evidence']),{'model':'offline-test'}
        store=MemoryStore(p); jobs=ai.AIJobs(store,threading.RLock(),lambda:'f'*16,lambda:'2026-09-12',runner)
        with patch('ai_jobs.threading.Thread'):
            public=jobs.start(store.load(p['id']),{'kind':'insights','modules':['segments']})
        jobs.work(jobs.jobs[public['id']])
        self.assertEqual(jobs.get(public['id'])['status'],'success')
        self.assertIn(evidence[0]['id'],received);self.assertNotIn(evidence[1]['id'],received);self.assertNotIn('keywords:pending',received)
        record=ai.normalize_ai_report(store.p['ai_reports'][-1],store.p)
        self.assertIn('排除 1',record['report']['modules']['segments']['scope']['selection'])
        self.assertEqual(set(record['report']['modules']['segments']['report']['audiences'][0]['motives']),set(modules.MOTIVE_KEYS))

    def test_stale_or_mismatched_cleaning_does_not_admit_words(self):
        p=sample_project(); evidence=ai.prepare(p,{'kind':'insights'},('keywords',),allow_empty=True)['evidence_snapshot']
        clean={'status':'success','evidence_snapshot':evidence,'report':{'items':[{'id':evidence[0]['id'],'valid':True}]}}
        p['ai_reports']=[{'id':'clean-fixture','data_version':p['data_version']-1,'report':{'modules':{'clean':clean}}}]
        self.assertFalse(ai.strategy_input(p)[0]['keywords'])
        p['ai_reports'][0]['data_version']=p['data_version']; p['keywords'][0]['text']='已改动'
        self.assertFalse(ai.strategy_input(p)[0]['keywords'])

    def test_old_report_missing_motives_is_unknown_not_inferred(self):
        evidence=ai.prepare(sample_project(),{'kind':'insights'},allow_empty=True)['evidence_snapshot']
        report=module_result('segments',evidence);del report['audiences'][0]['motives']
        with self.assertRaises(ValueError):modules.validate('segments',report,evidence)
        restored=modules.validate('segments',report,evidence,allow_legacy=True)
        self.assertTrue(all(v['basis']=='unknown' and not v['evidence_ids'] for v in restored['audiences'][0]['motives'].values()))
