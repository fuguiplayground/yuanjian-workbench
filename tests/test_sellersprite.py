import io
import json
import unittest
from unittest.mock import Mock, patch
import sellersprite as ss
import sources
from server import new_project, import_rows, restore_project, now


class SellerTests(unittest.TestCase):
    def test_schema_arguments_and_missing_permission(self):
        client = Mock()
        client.tools = {name: {'inputSchema': {'properties': {'request': {}}}}
                        for name in ('product_research', 'keyword_miner')}
        with patch.object(ss, '_client', client):
            ss.query('products', 'portable blender')
            args = client.call.call_args.args[1]['request']
            self.assertEqual(args['matchType'], 1)
            self.assertEqual(args['size'], 10)
            ss.query('keywords', 'portable blender')
            args = client.call.call_args.args[1]['request']
            self.assertNotIn('matchType', args)
            self.assertEqual(args['includeKeywords'], ['portable blender'])
            with self.assertRaises(sources.SourceError):
                ss.query('reviews', asin='B012345678')

    def test_sse_notification_before_result(self):
        response = io.BytesIO(b'event: message\ndata: {"method":"notifications/progress"}\n\n'
                             b'data: {"jsonrpc":"2.0","id":1,"result":{"tools":[]}}\n\n')
        response.headers = {'Content-Type': 'text/event-stream', 'Mcp-Session-Id': 'test-session'}
        with patch.object(ss, 'build_opener') as opener:
            opener.return_value.open.return_value = response
            client = ss.Client('test-only-key')
            self.assertEqual(client.rpc('tools/list', {}), {'tools': []})
            request = opener.return_value.open.call_args.args[0]
            self.assertEqual(request.get_header('Accept'), 'application/json, text/event-stream')
            self.assertEqual(client.session, 'test-session')

    def test_provider_metrics_privacy_and_restore(self):
        p = new_project('research', 'blender')
        products = ss.parse('products', {'data': {'items': [{'asin':'B012345678', 'title':'Blender',
             'units':123, 'ratings':25, 'rating':4.5, 'price':19.9, 'authorEmail':'private@example.com'}]}}, 'blender', now())
        self.assertIn('父体', products[0]['sales_kind'])
        self.assertIn('未注明', products[0]['sales_period'])
        self.assertNotIn('private', str(products))
        import_rows(p, 'products', products, provenance='live')
        keywords = ss.parse('keywords', {'data': {'items': [{'keyword':'blender','searches':1234,'month':'2026.08'}]}}, 'blender', now())
        run = import_rows(p, 'keywords', keywords, provenance='live')
        run.update(mode='seller', query='blender', original_query='榨汁杯', tool='keyword_miner', pages=1)
        restored = restore_project(p)
        self.assertEqual(restored['keywords'][0]['search_volume'], 1234)
        self.assertEqual(restored['keywords'][0]['data_type'], 'market')
        self.assertEqual(restored['runs'][-1]['original_query'], '榨汁杯')

    def test_failures_are_not_empty_success(self):
        for payload in ({'code': 'FAIL'}, {'data': {}}, {'data': {'items':[{}]}}):
            with self.assertRaises(sources.SourceError):
                ss.parse('products', payload, 'blender', now())
        self.assertEqual(ss.parse('products', {'data': {'items': []}}, 'blender', now()), [])
        with patch.object(ss.Client, 'initialize') as initialize:
            with self.assertRaises(ValueError):
                ss.connect('不小心粘贴了中文产品关键词')
            initialize.assert_not_called()
