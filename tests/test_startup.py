import errno
import json
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.request import urlopen
from unittest.mock import Mock, patch

import server as app


class StartupTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.store = app.Store(temp.name)

    def run_server(self, handler=None, instance=None):
        instance = instance or ThreadingHTTPServer(
            ('127.0.0.1', 0), handler or app.handler_for(self.store))
        thread = threading.Thread(target=instance.serve_forever, daemon=True)
        thread.start()
        def stop():
            instance.shutdown()
            instance.server_close()
            thread.join()
        self.addCleanup(stop)
        return instance

    def test_repeat_launch_reuses_same_workspace_and_build(self):
        existing = self.run_server()
        result, url = app.bind_or_reuse(existing.server_port, self.store)
        self.assertIsNone(result)
        self.assertEqual(url, f'http://127.0.0.1:{existing.server_port}')
        with urlopen(url + '/api/health') as response:
            identity = json.load(response)
        self.assertEqual(identity, app.server_identity(self.store))
        self.assertNotIn(str(self.store.path), json.dumps(identity))

    def test_other_app_or_legacy_instance_is_left_running_and_new_port_works(self):
        class Other(BaseHTTPRequestHandler):
            def log_message(self, *_):
                pass
            def do_GET(self):
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b'{"other_app":true}')
        existing = self.run_server(Other)
        result, url = app.bind_or_reuse(existing.server_port, self.store)
        self.assertIsNotNone(result)
        self.run_server(instance=result)
        self.assertNotEqual(existing.server_port, result.server_port)
        with urlopen(url + '/') as response:
            self.assertEqual(response.status, 200)
            self.assertIn('远见'.encode(), response.read())
        with urlopen(f'http://127.0.0.1:{existing.server_port}/') as response:
            self.assertEqual(json.load(response), {'other_app': True})

    def test_different_workspace_is_not_reused(self):
        existing = self.run_server()
        with tempfile.TemporaryDirectory() as other:
            identity = app.server_identity(app.Store(other))
            self.assertFalse(app.is_current_workbench(existing.server_port, identity))

    def test_old_build_is_not_reused(self):
        existing = self.run_server()
        identity = {**app.server_identity(self.store), 'build': 'newer-build'}
        self.assertFalse(app.is_current_workbench(existing.server_port, identity))

    def test_reuses_fallback_before_binding_new_preferred_port(self):
        with patch.object(app, 'is_current_workbench', side_effect=lambda port, _: port == 8767), \
             patch.object(app, 'ThreadingHTTPServer') as bind:
            result, url = app.bind_or_reuse(8765, self.store)
            self.assertIsNone(result)
            self.assertEqual(url, 'http://127.0.0.1:8767')
            bind.assert_not_called()

    def test_permission_failure_is_not_treated_as_port_conflict(self):
        with patch.object(app, 'is_current_workbench', return_value=False), \
             patch.object(app, 'ThreadingHTTPServer', side_effect=PermissionError(errno.EACCES, 'denied')) as bind:
            with self.assertRaises(PermissionError):
                app.bind_or_reuse(8765, self.store)
            self.assertEqual(bind.call_count, 1)

    def test_double_click_opens_browser_for_reused_and_fallback_instances(self):
        for reused in (True, False):
            instance = None if reused else Mock()
            if instance:
                instance.serve_forever.side_effect = KeyboardInterrupt
            with self.subTest(reused=reused), \
                 patch.object(sys, 'argv', ['server.py', '--open']), \
                 patch.object(app, 'Store', return_value=self.store), \
                 patch.object(app, 'bind_or_reuse', return_value=(instance, 'http://127.0.0.1:8767')), \
                 patch.object(app.device_setup, 'start') as setup, \
                 patch('webbrowser.open') as browser, patch('builtins.print'):
                app.main()
                browser.assert_called_once_with('http://127.0.0.1:8767')
                self.assertEqual(setup.call_count, 0 if reused else 1)
                if instance:
                    instance.server_close.assert_called_once()


if __name__ == '__main__':
    unittest.main()
