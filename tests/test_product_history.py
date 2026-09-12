import copy
import json
import tempfile
import threading
import unittest
from datetime import datetime
from http.server import ThreadingHTTPServer
from types import SimpleNamespace
from unittest.mock import Mock, patch
from urllib.error import HTTPError
from urllib.request import Request, ProxyHandler, build_opener

import sellersprite as ss
import sources
from server import Store, handler_for, import_rows, new_project, restore_project


ASIN = 'B012345678'
PARENT = 'B087654321'


def keepa_payload(at):
    stamp = int(datetime.fromisoformat(at).timestamp() * 1000) - 1000
    return {'code': 'OK', 'data': {'asin': ASIN, 'dataAsin': PARENT, 'parentAsin': PARENT,
        'price': [{'timePoint': stamp, 'value': 19.95}], 'bsr': [{'timePoint': stamp, 'value': 123}],
        'reviews': [{'timePoint': stamp, 'value': 31}], 'rating': [{'timePoint': stamp, 'value': 4.3}],
        'sellerId': 'must-not-be-stored', 'buyBoxSellerIdHistory': 'private-field'}}


def sales_payload():
    return {'code': 'OK', 'data': {'asin': {'asin': ASIN, 'parent': PARENT, 'sellerId': 'must-not-be-stored'},
        'salesTrendPoints': [{'month': '2025-08', 'price': 20, 'averagePrice': 19.4,
                            'parentUnitSales': 600, 'childUnitSales': None,
                            'parentSalesRevenue': 11640, 'childSalesRevenue': None}]}}


class HistoryParseTests(unittest.TestCase):
    def test_exact_query_schema_and_read_only_tool_allowlist(self):
        client = SimpleNamespace(lock=threading.RLock(), call=Mock(return_value={}), last_http=200)
        at = '2026-09-12T00:00:00+00:00'
        with patch.object(ss, '_client', client):
            self.assertEqual(ss.query_history('keepa_info', ASIN, at), ({}, 200))
            args = client.call.call_args.args[1]
            self.assertEqual(args['marketplace'], 'US')
            self.assertTrue(args['dailyLatest'])
            self.assertEqual(args['endTimestamp'] - args['startTimestamp'], 90 * 86400000)
            self.assertNotIn('sellerId', args['returnFields'])
            ss.query_history('asin_sales_trend', ASIN, at)
            self.assertEqual(client.call.call_args.args, ('asin_sales_trend', {
                'marketplace': 'US', 'asin': ASIN, 'returnFields': 'asin,salesTrendPoints'}))
            with self.assertRaises(ValueError):
                ss.query_history('asin_prediction', ASIN, at)
            self.assertEqual(client.call.call_count, 2)

    def test_aliases_missing_values_time_ranges_and_privacy(self):
        at = '2026-09-12T00:00:00+00:00'
        payload = keepa_payload(at)
        stamp = payload['data']['price'][0]['timePoint']
        payload['data']['price'] += [{'timePoint': stamp, 'value': 21},
                                    {'timePoint': stamp - 86400000, 'value': -1},
                                    {'timePoint': stamp, 'value': True},
                                    {'timePoint': stamp + 2 * 86400000, 'value': 99}]
        parsed = ss.parse_history('keepa_info', payload, ASIN, at)
        self.assertEqual(parsed['data_asin'], PARENT)
        self.assertEqual(parsed['requested_asin'], ASIN)
        self.assertEqual([x['value'] for x in parsed['series']['price']], [None, 21])
        self.assertEqual(parsed['skipped_points'], 3)
        self.assertNotIn('sellerId', json.dumps(parsed))
        self.assertNotIn('must-not', json.dumps(parsed))
        monthly = ss.parse_history('asin_sales_trend', sales_payload(), ASIN, at)
        self.assertEqual(monthly['months'][0]['parent_units'], 600)
        self.assertIsNone(monthly['months'][0]['child_units'])
        self.assertNotIn('sales', parsed['series'])

    def test_invalid_envelopes_and_malformed_months(self):
        at = '2026-09-12T00:00:00+00:00'
        for payload in ({'code': 'FAIL'}, {'data': {}}, {'data': {'asin': ASIN}}):
            with self.assertRaises((ValueError, sources.SourceError)):
                ss.parse_history('keepa_info', payload, ASIN, at)
        bad = keepa_payload(at)
        bad['data']['price'] = {}
        with self.assertRaises(sources.SourceError):
            ss.parse_history('keepa_info', bad, ASIN, at)
        payload = sales_payload()
        payload['data']['salesTrendPoints'] += [{'month': '2025-99'}, {'month': '2026-11'},
            {'month': '2025-07', 'parentUnitSales': 1.5}]
        parsed = ss.parse_history('asin_sales_trend', payload, ASIN, at)
        self.assertEqual(len(parsed['months']), 1)
        self.assertEqual(parsed['skipped_points'], 3)


class HistoryHTTPTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = Store(self.temp.name)
        p = new_project('商品历史回归', 'blender')
        import_rows(p, 'products', [{'id': ASIN, 'platform': 'amazon', 'title': 'Blender', 'price': 9.9,
                                     'currency': 'USD', 'candidate': True}], provenance='live')
        self.project = self.store.save(p)
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), handler_for(self.store))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = 'http://127.0.0.1:' + str(self.server.server_port)
        self.path = '/api/projects/' + p['id'] + '/product-history'

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.temp.cleanup()

    def request(self, body=None):
        if body is None:
            body = {'revision': self.project['revision'], 'product_id': ASIN}
        req = Request(self.base + self.path, data=json.dumps(body).encode(), headers={'Content-Type': 'application/json'})
        try:
            response = build_opener(ProxyHandler({})).open(req, timeout=5)
        except HTTPError as error:
            response = error
        with response:
            return response.status, json.load(response)

    @staticmethod
    def supplier(tool, asin, at):
        return (keepa_payload(at) if tool == 'keepa_info' else sales_payload()), 200

    def test_manual_two_query_history_preserves_products_and_roundtrips(self):
        with patch('sellersprite.query_history', side_effect=self.supplier) as query:
            status, p = self.request()
        self.assertEqual(status, 200)
        self.assertEqual([c.args[0] for c in query.call_args_list], list(ss.HISTORY_TOOLS))
        self.assertEqual(p['products'], self.project['products'])
        self.assertEqual(p['data_version'], self.project['data_version'])
        history = p['watch_history'][0]
        self.assertEqual((history['status'], history['requests'], history['request_limit']), ('success', 2, 2))
        self.assertEqual([r['http'] for r in history['results']], [200, 200])
        self.assertEqual(history['results'][0]['data']['data_asin'], PARENT)
        self.assertNotIn('must-not-be-stored', json.dumps(p))
        self.assertEqual(restore_project(p)['watch_history'], p['watch_history'])
        self.assertEqual(self.store.load(p['id'])['watch_history'], p['watch_history'])

    def test_first_result_saved_before_second_failure_and_concurrent_edit_retained(self):
        first_was_saved = []
        def supplier(tool, asin, at):
            if tool == 'keepa_info':
                return keepa_payload(at), 200
            current = self.store.load(self.project['id'])
            first_was_saved.append(current['watch_history'][0]['results'][0]['status'])
            current['name'] = '用户在请求期间修改的项目名'
            self.store.save(current, current['revision'])
            raise sources.SourceError('卖家精灵 HTTP 429：额度限制', 429)
        with patch('sellersprite.query_history', side_effect=supplier) as query:
            status, p = self.request()
        self.assertEqual(status, 200)
        self.assertEqual(query.call_count, 2)
        self.assertEqual(first_was_saved, ['success'])
        self.assertEqual(p['name'], '用户在请求期间修改的项目名')
        history = p['watch_history'][0]
        self.assertEqual(history['status'], 'partial')
        self.assertEqual(history['results'][1]['http'], 429)
        self.assertIsNone(history['results'][1]['data'])
        self.assertEqual(restore_project(p)['watch_history'], p['watch_history'])

    def test_first_failure_does_not_prevent_second_and_exception_payload_hidden(self):
        with patch('sellersprite.query_history', side_effect=[ValueError('token=must-not-be-stored'), (sales_payload(), 200)]):
            status, p = self.request()
        self.assertEqual(status, 200)
        self.assertEqual(p['watch_history'][0]['status'], 'partial')
        self.assertNotIn('must-not-be-stored', json.dumps(p))

    def test_invalid_inputs_and_stale_revision_make_no_supplier_requests(self):
        with patch('sellersprite.query_history') as query:
            for body, expected in (({'revision': 0, 'product_id': ASIN}, 409),
                                   ({'revision': self.project['revision'], 'product_id': 'bad'}, 400),
                                   ({'revision': self.project['revision'], 'product_id': PARENT}, 400)):
                self.assertEqual(self.request(body)[0], expected)
            query.assert_not_called()
        self.assertEqual(self.store.load(self.project['id'])['watch_history'], [])

    def test_parallel_double_click_does_not_duplicate_paid_queries(self):
        entered, release = threading.Event(), threading.Event()
        completed = []
        def supplier(tool, asin, at):
            if tool == 'keepa_info':
                entered.set()
                release.wait(3)
            return self.supplier(tool, asin, at)
        with patch('sellersprite.query_history', side_effect=supplier) as query:
            pending = threading.Thread(target=lambda: completed.append(self.request()))
            pending.start()
            try:
                self.assertTrue(entered.wait(1))
                p = self.store.load(self.project['id'])
                status, error = self.request({'revision': p['revision'], 'product_id': ASIN})
                self.assertEqual(status, 409)
                self.assertIn('正在查询', error['error'])
            finally:
                release.set()
                pending.join(4)
        self.assertEqual(query.call_count, 2)
        self.assertEqual(completed[0][0], 200)
        self.assertEqual(len(completed[0][1]['watch_history']), 1)

    def test_restore_rejects_wrong_links_counts_points_and_strips_unknown_fields(self):
        with patch('sellersprite.query_history', side_effect=self.supplier):
            _, original = self.request()
        for alter in (
            lambda h: h.update(product_id=PARENT),
            lambda h: h.update(requests=1),
            lambda h: h['results'][0]['data'].update(requested_asin=PARENT),
            lambda h: h['results'][0]['data']['series']['price'][0].update(value=True),
            lambda h: h['results'][0].update(http=403),
            lambda h: h['results'][1]['data']['months'][0].update(month='2025-13'),
        ):
            p = copy.deepcopy(original)
            alter(p['watch_history'][0])
            with self.assertRaises((ValueError, KeyError, TypeError)):
                restore_project(p)
        p = copy.deepcopy(original)
        p['watch_history'][0]['Authorization'] = 'must-not-be-stored'
        p['watch_history'][0]['results'][0]['data']['sellerId'] = 'must-not-be-stored'
        restored = restore_project(p)
        self.assertNotIn('must-not-be-stored', json.dumps(restored))
        history = p['watch_history'][0]
        history.update(status='running', requests=1, results=history['results'][:1], finished_at='')
        self.assertEqual(restore_project(p)['watch_history'][0]['status'], 'interrupted')


if __name__ == '__main__':
    unittest.main()
