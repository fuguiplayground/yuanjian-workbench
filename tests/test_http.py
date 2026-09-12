import json
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from server import Store, handler_for


class HTTPTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), handler_for(Store(self.temp.name)))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f'http://127.0.0.1:{self.server.server_port}'

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.temp.cleanup()

    def request(self, path, body=None, origin=None):
        headers = {'Content-Type': 'application/json'}
        if origin:
            headers['Origin'] = origin
        req = Request(self.base + path, data=json.dumps(body).encode() if body is not None else None, headers=headers)
        try:
            response = urlopen(req, timeout=5)
        except HTTPError as error:
            response = error
        with response:
            data = response.read()
            return response.status, json.loads(data) if 'application/json' in response.headers['Content-Type'] else data

    def test_decision_workspace_roundtrip_and_conflict(self):
        status, p = self.request('/api/projects', {'name': '决策测试', 'keyword': '词'})
        self.assertEqual(status, 201)
        url = '/api/projects/' + p['id'] + '/decision-workspace'
        w = {'brief': {'goal': '找机会'}, 'selected_id': 'opp-1', 'cases': [{'id': 'opp-1', 'title': '场景机会', 'strategy': {'audience': '某类人'}}]}
        old = p['revision']
        status, saved = self.request(url, {'revision': old, 'workspace': w})
        self.assertEqual(status, 200)
        self.assertEqual(saved['data_version'], p['data_version'])
        self.assertEqual(self.request(url, {'revision': old, 'workspace': w})[0], 409)
        self.assertEqual(self.request('/api/projects/' + p['id'])[1]['decision_workspace'], saved['decision_workspace'])
        status, restored = self.request('/api/restore', {'project': saved})
        self.assertEqual(status, 201)
        self.assertEqual(restored['decision_workspace'], saved['decision_workspace'])
        w['selected_id'] = 'missing'
        self.assertEqual(self.request(url, {'revision': saved['revision'], 'workspace': w})[0], 400)
        self.assertEqual(self.request('/business.js')[0], 200)

    def test_http_create_import_analyze_restore_and_reopen(self):
        status, home = self.request('/')
        self.assertEqual(status, 200)
        self.assertIn('远见'.encode(), home)
        status, p = self.request('/api/projects', {'demo': True})
        self.assertEqual(status, 201)
        prefix = '/api/projects/' + p['id']
        status, p = self.request(prefix + '/analyze', {'revision': p['revision']})
        self.assertEqual(status, 200)
        old_revision = p['revision']
        status, p = self.request(prefix + '/import', {'revision': p['revision'], 'kind': 'keywords',
            'format': 'csv', 'text': 'id,text\nnew,portable blender clean seal\nbad,\n'})
        self.assertEqual(status, 200)
        self.assertEqual(p['runs'][-1]['status'], 'partial')
        self.assertEqual(p['runs'][-1]['imported'], 1)
        self.assertEqual(len(p['runs'][-1]['errors']), 1)
        self.assertNotEqual(p['data_version'], p['analyses'][-1]['data_version'])
        status, _ = self.request(prefix + '/rename', {'revision': old_revision, 'name': 'wrong'})
        self.assertEqual(status, 409)
        status, restored = self.request('/api/restore', {'project': p})
        self.assertEqual(status, 201)
        self.assertEqual(restored['analyses'], p['analyses'])
        self.assertEqual(restored['runs'], p['runs'])
        status, reopened = self.request('/api/projects/' + restored['id'])
        self.assertEqual(status, 200)
        self.assertEqual(len(reopened['keywords']), 13)

    def test_watch_and_candidate_are_independent_and_restored(self):
        _, p = self.request('/api/projects', {'demo': True})
        prefix = '/api/projects/' + p['id']
        item = p['products'][0]
        candidate, version = item['candidate'], p['data_version']
        status, watched = self.request(prefix + '/toggle', {'revision': p['revision'], 'kind': 'products', 'id': item['id'], 'field': 'watched'})
        self.assertEqual(status, 200)
        self.assertTrue(watched['products'][0].get('watched', False))
        self.assertEqual(watched['products'][0]['candidate'], candidate)
        self.assertEqual(watched['data_version'], version)
        status, stale = self.request(prefix + '/toggle', {'revision': p['revision'], 'kind': 'products', 'id': item['id'], 'field': 'watched'})
        self.assertEqual(status, 409)
        status, toggled = self.request(prefix + '/toggle', {'revision': watched['revision'], 'kind': 'products', 'id': item['id']})
        self.assertEqual(status, 200)
        self.assertTrue(toggled['products'][0]['watched'])
        self.assertEqual(toggled['products'][0]['candidate'], not candidate)
        self.assertEqual(toggled['data_version'], version + 1)
        status, restored = self.request('/api/restore', {'project': toggled})
        self.assertEqual(status, 201)
        self.assertTrue(restored['products'][0]['watched'])
        status, _ = self.request(prefix + '/toggle', {'revision': toggled['revision'], 'kind': 'products', 'id': item['id'], 'field': 'price'})
        self.assertEqual(status, 400)
        old = dict(toggled)
        old['products'] = [dict(x) for x in toggled['products']]
        for x in old['products']:
            x.pop('watched', None)
        status, legacy = self.request('/api/restore', {'project': old})
        self.assertEqual(status, 201)
        self.assertFalse(legacy['products'][0]['watched'])

    def test_http_blocks_cross_origin_and_bad_data(self):
        status, _ = self.request('/api/projects', {'demo': True}, 'https://untrusted.example')
        self.assertEqual(status, 403)
        status, _ = self.request('/api/restore', {'project': {'schema_version': 99}})
        self.assertEqual(status, 400)


if __name__ == '__main__':
    unittest.main()
