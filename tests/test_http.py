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

    def test_http_blocks_cross_origin_and_bad_data(self):
        status, _ = self.request('/api/projects', {'demo': True}, 'https://untrusted.example')
        self.assertEqual(status, 403)
        status, _ = self.request('/api/restore', {'project': {'schema_version': 99}})
        self.assertEqual(status, 400)


if __name__ == '__main__':
    unittest.main()
