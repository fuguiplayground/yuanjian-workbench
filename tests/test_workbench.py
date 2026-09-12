import copy
import json
from pathlib import Path
import shutil
import tempfile
import unittest

from server import Store, Conflict, analyze, demo_project, import_rows, new_project, normalize, restore_project


class WorkbenchTests(unittest.TestCase):
    def test_project_save_reopen_and_versions(self):
        with tempfile.TemporaryDirectory() as folder:
            store = Store(folder)
            p = store.save(new_project('便携杯', 'portable blender'))
            first = copy.deepcopy(p)
            p['name'] = '新的项目名称'
            store.save(p, first['revision'])
            self.assertEqual(store.load(p['id'])['name'], '新的项目名称')
            self.assertEqual(len(list(Path(folder).glob('*/v*.json'))), 2)
            self.assertEqual(store.listing()[0]['counts']['products'], 0)

    def test_stale_window_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            store = Store(folder)
            p = store.save(new_project('A', 'a'))
            old = copy.deepcopy(p)
            store.save(p, p['revision'])
            with self.assertRaises(Conflict):
                store.save(old, old['revision'])

    def test_incomplete_sync_detected(self):
        with tempfile.TemporaryDirectory() as folder:
            store = Store(folder)
            p = store.save(new_project('A', 'a'))
            manifest = json.loads((Path(folder) / p['id'] / 'current.json').read_text())
            (Path(folder) / p['id'] / manifest['file']).write_text('{}')
            with self.assertRaisesRegex(ValueError, '不完整'):
                store.load(p['id'])
            self.assertIn('error', store.listing()[0])

    def test_partial_import_preserves_good_rows(self):
        p = new_project('A', 'a')
        run = import_rows(p, 'products', [
            {'id': 'a', 'title': 'Cup', 'price': 19.9, 'currency': 'USD'},
            {'id': 'b', 'price': 20}, {'id': 'c', 'title': 'Invalid', 'rating': 6},
            {'id': 'd', 'title': 'Missing metrics'}])
        self.assertEqual((run['imported'], len(run['errors']), run['status']), (2, 2, 'partial'))
        self.assertIsNone(p['products'][1]['price'])
        self.assertIsNone(p['products'][1]['review_count'])

    def test_orphan_comments_rejected(self):
        p = new_project('A', 'a')
        run = import_rows(p, 'reviews', [{'product_id': 'missing', 'body': 'Great'}])
        self.assertEqual(run['status'], 'failed')
        self.assertEqual(p['reviews'], [])
        self.assertEqual(p['data_version'], 0)

    def test_comment_deduplication_keeps_product_relationship(self):
        p = new_project('A', 'a')
        import_rows(p, 'products', [{'id': 'a', 'title': 'A'}, {'id': 'b', 'title': 'B'}])
        run = import_rows(p, 'reviews', [
            {'product_id': 'a', 'body': 'Easy to clean'},
            {'product_id': 'a', 'body': 'Easy to clean'},
            {'product_id': 'b', 'body': 'Easy to clean'}])
        self.assertEqual((run['imported'], run['duplicates']), (2, 1))

    def test_ai_terms_are_separate_from_imported_terms(self):
        p = new_project('A', 'a')
        run = import_rows(p, 'keywords', [{'text': 'cup'}, {'text': 'CUP'}, {'text': 'cup', 'data_type': 'ai'}])
        self.assertEqual((run['imported'], run['duplicates']), (2, 1))
        self.assertEqual({k['data_type'] for k in p['keywords']}, {'ai', 'suggestion'})

    def test_social_reviews_separate_and_evidence_valid(self):
        p = demo_project()
        import_rows(p, 'reviews', [{'id': 'social', 'product_id': 'p1', 'body': 'easy to clean', 'review_type': 'social'}])
        a = analyze(p)
        ids = {r['id'] for r in p['reviews']}
        for i in a['insights']:
            self.assertTrue(set(i['evidence_ids']) <= ids)
            self.assertEqual(i['count'], len(i['evidence_ids']))
        social = [i for i in a['insights'] if i['review_type'] == 'social']
        self.assertEqual(social[0]['evidence_ids'], ['social'])
        self.assertEqual(social[0]['sample_size'], 1)
        for d in a['decisions']:
            self.assertTrue(all(r['product_id'] == d['product_id'] and r['review_type'] == 'product'
                for r in p['reviews'] if r['id'] in d['evidence_ids']))

    def test_new_data_keeps_old_analysis_stale(self):
        p = demo_project()
        p['analyses'].append(analyze(p))
        old = copy.deepcopy(p['analyses'][0])
        import_rows(p, 'reviews', [{'product_id': 'p1', 'body': 'This lid is difficult to clean'}])
        self.assertEqual(p['analyses'][0], old)
        self.assertLess(old['data_version'], p['data_version'])

    def test_restore_preserves_old_analysis_and_settings(self):
        p = demo_project()
        p['analyses'].append(analyze(p))
        import_rows(p, 'reviews', [{'product_id': 'p1', 'body': 'This lid is difficult to clean'}])
        restored = restore_project(json.loads(json.dumps(p)))
        self.assertNotEqual(restored['id'], p['id'])
        for field in ('keywords', 'products', 'reviews', 'analyses', 'data_version', 'runs', 'demo', 'keyword'):
            self.assertEqual(restored[field], p[field], field)

    def test_restore_rejects_invented_evidence(self):
        p = demo_project()
        p['analyses'].append(analyze(p))
        p['analyses'][0]['insights'][0]['evidence_ids'].append('invented')
        with self.assertRaisesRegex(ValueError, '不存在'):
            restore_project(p)

    def test_two_independent_directories_round_trip(self):
        with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
            store_a, store_b = Store(a), Store(b)
            p = store_a.save(demo_project())
            shutil.copytree(Path(a) / p['id'], Path(b) / p['id'])
            on_b = store_b.load(p['id'])
            import_rows(on_b, 'keywords', [{'id': 'new-on-b', 'text': 'test independent directory'}])
            store_b.save(on_b, on_b['revision'])
            shutil.copytree(Path(b) / p['id'], Path(a) / p['id'], dirs_exist_ok=True)
            self.assertEqual(store_a.load(p['id'])['keywords'][-1]['id'], 'new-on-b')

    def test_metrics_and_csv_booleans(self):
        p = normalize('products', {'id': 'a', 'title': 'A', 'candidate': 'false',
            'sales_raw': '10K+ bought in past month', 'sales_period': 'past month', 'sales_kind': '购买量下限'})
        self.assertFalse(p['candidate'])
        self.assertEqual(p['sales_raw'], '10K+ bought in past month')
        for value in ('NaN', '-1', 'Infinity'):
            with self.assertRaises(ValueError):
                normalize('products', {'id': 'a', 'title': 'A', 'price': value})

    def test_urls_drop_signatures_and_unknown_fields(self):
        p = normalize('products', {'id': 'a', 'title': 'A', 'api_key': 'do-not-save',
            'source_url': 'https://example.com/product?token=do-not-save#fragment'})
        self.assertNotIn('api_key', p)
        self.assertEqual(p['source_url'], 'https://example.com/product')
        self.assertEqual(normalize('keywords', {'text': 'test', 'source_url': 'javascript:alert(1)'})['source_url'], '')


if __name__ == '__main__':
    unittest.main()
