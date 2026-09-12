"""Public clone and optional team package checks; temporary fixtures only."""
from contextlib import redirect_stdout
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

import server
import team_start


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('check_public_project', ROOT / 'scripts/check_project.py')
checker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(checker)


class PublicFixture(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / 'web').mkdir()
        (self.root / 'sample.py').write_text('value = 1\n', encoding='utf-8')
        for name in ('index.html', *checker.STATIC_ASSETS):
            (self.root / 'web' / name).write_text('fixture content', encoding='utf-8')

    def tearDown(self):
        self.temp.cleanup()

    def check(self, url=None):
        output = io.StringIO()
        with patch.object(checker, 'ROOT', self.root), patch.object(sys, 'argv', ['check_project.py'] + (['--url', url] if url else [])), redirect_stdout(output):
            checker.main()
        return output.getvalue()

    def project(self):
        store = server.Store(self.root / 'data/projects')
        return store, store.save(server.new_project('验收临时项目', 'test'))


class PublicInitializationTests(PublicFixture):
    def test_empty_public_clone_passes_without_creating_data_or_reading_credentials(self):
        with patch('sellersprite.connect', side_effect=AssertionError('must not connect')), \
             patch('sources.credential', side_effect=AssertionError('must not read credentials')):
            output = self.check()
        self.assertIn('0 个项目', output)
        self.assertIn('公开源码初始化通过', output)
        self.assertFalse((self.root / 'data').exists())

    def test_empty_existing_project_directory_also_passes(self):
        server.Store(self.root / 'data/projects')
        self.assertIn('0 个项目', self.check())

    def test_optional_manifest_remains_strict_and_extra_user_projects_are_allowed(self):
        store, project = self.project()
        second = store.save(server.new_project('后来新建的项目', 'second'))
        path = self.root / 'package-manifest.json'
        path.write_text(json.dumps({'projects': [{'id': project['id']}]}), encoding='utf-8')
        self.assertIn('2 个项目', self.check())
        for manifest in ({'projects': []}, {'projects': [{'id': 'f' * 16}]}, {'projects': [{'id': project['id']}] * 2},
                         {'projects': [{}]}, {'projects': 'invalid'}):
            with self.subTest(manifest=manifest), self.assertRaises(ValueError):
                path.write_text(json.dumps(manifest), encoding='utf-8')
                self.check()
        self.assertEqual(store.load(second['id'])['name'], '后来新建的项目')

    def test_manifest_cannot_turn_missing_data_into_an_empty_public_clone(self):
        (self.root / 'package-manifest.json').write_text(json.dumps({'projects': [{'id': 'a' * 16}]}), encoding='utf-8')
        with self.assertRaisesRegex(ValueError, '随包项目不完整'):
            self.check()
        self.assertFalse((self.root / 'data').exists())

    def test_project_sha_validation_is_preserved_without_a_package_manifest(self):
        store, project = self.project()
        self.assertIn('1 个项目', self.check())
        folder = store.folder(project['id'])
        pointer = json.loads((folder / 'current.json').read_text())
        version = folder / pointer['file']
        version.write_bytes(version.read_bytes() + b' ')
        with self.assertRaisesRegex(ValueError, '无法读取'):
            self.check()

    def test_new_frontend_assets_are_required_even_offline(self):
        for name in ('keyword-controls.js', 'insight-report.css'):
            path = self.root / 'web' / name
            path.write_text('', encoding='utf-8')
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, name.replace('.', r'\.')):
                self.check()
            path.write_text('fixture content', encoding='utf-8')

    def test_url_rejects_remote_credentials_paths_https_and_queries_before_network(self):
        server.Store(self.root / 'data/projects')
        with patch.object(checker, 'build_opener') as network:
            for url in ('http://example.com', 'https://127.0.0.1', 'http://127.0.0.1/path',
                        'http://localhost?query=1', 'http://user:password@localhost', 'http://localhost#part'):
                with self.subTest(url=url), self.assertRaisesRegex(ValueError, '仅支持本机'):
                    self.check(url)
            network.assert_not_called()

    def test_team_entry_without_private_connection_calls_normal_server_entry(self):
        with patch.object(team_start, '__file__', str(self.root / 'team_start.py')), \
             patch.object(team_start.sellersprite, 'set_team_connection') as connection, \
             patch.object(team_start.server, 'main') as launch:
            team_start.main()
        connection.assert_not_called()
        launch.assert_called_once_with()

    @unittest.skipUnless(os.name == 'posix' and shutil.which('bash'), '需要 POSIX 环境及 Bash 运行 macOS 启动脚本')
    def test_mac_entry_has_no_default_project_and_preserves_explicit_arguments(self):
        script = ROOT / '打开工作台.command'
        command = 'python3() { printf "%s\\n" "$@"; }; export -f python3; bash "$1" "${@:2}"'
        for args in ([], ['--project', 'a' * 16, '--port', '18765']):
            result = subprocess.run(['bash', '-c', command, 'fixture', str(script), *args], capture_output=True, text=True, timeout=5)
            self.assertEqual(result.returncode, 0, result.stderr)
            lines = result.stdout.splitlines()
            self.assertIn('team_start.py', lines)
            self.assertIn('--open', lines)
            self.assertEqual(lines.count('--project'), 1 if args else 0)
            if args:
                self.assertEqual(lines[-len(args):], args)

    def test_windows_entry_keeps_setup_and_optional_project_argument(self):
        script = (ROOT / 'start.ps1').read_text(encoding='utf-8-sig')
        self.assertIn("[string]$Project = ''", script)
        self.assertIn("if ($Project) { $launchArguments += @('--project', $Project) }", script)
        self.assertIn(".venv\\Scripts\\python.exe", script)
        self.assertIn("'setup.ps1'", script)
        self.assertIn("if (-not $NoBrowser)", script)


class LocalHttpChecks(PublicFixture):
    def serve(self, redirect=False, wrong_css=False):
        store = server.Store(self.root / 'data/projects')
        requests = []
        assets = checker.STATIC_ASSETS
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_):
                pass

            def do_GET(self):
                requests.append(self.path)
                if redirect:
                    self.send_response(302)
                    self.send_header('Location', '/redirect-target')
                    self.end_headers()
                    return
                if self.path == '/api/health':
                    payload, mime = json.dumps(server.server_identity(store)).encode(), 'application/json'
                elif self.path == '/api/projects':
                    payload, mime = b'[]', 'application/json'
                else:
                    payload = b'local fixture'
                    mime = 'text/html' if self.path == '/' else assets.get(self.path[1:], 'text/plain')
                    if wrong_css and self.path == '/insight-report.css':
                        mime = 'text/plain'
                self.send_response(200)
                self.send_header('Content-Type', mime)
                self.end_headers()
                self.wfile.write(payload)
        http = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        thread = threading.Thread(target=http.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(http.server_close)
        self.addCleanup(http.shutdown)
        return 'http://127.0.0.1:' + str(http.server_port), requests

    def test_empty_http_service_checks_new_js_and_css(self):
        url, requests = self.serve()
        self.assertIn('全部静态资源', self.check(url))
        self.assertIn('/keyword-controls.js', requests)
        self.assertIn('/insight-report.css', requests)
        self.assertNotIn('/api/sources', requests)

    def test_redirect_is_refused_instead_of_followed(self):
        url, requests = self.serve(redirect=True)
        with self.assertRaises(HTTPError) as caught:
            self.check(url)
        caught.exception.close()
        self.assertEqual(requests, ['/api/health'])

    def test_new_css_mime_is_checked(self):
        url, _ = self.serve(wrong_css=True)
        with self.assertRaisesRegex(ValueError, '内容类型异常：/insight-report.css'):
            self.check(url)


if __name__ == '__main__':
    unittest.main()
