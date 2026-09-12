import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import codex_runner


class ExecutableSelectionTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='fieldwork-codex-test-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.config = self.root / 'codex.local.json'
        self.environment_binary = self.make_binary('environment.exe')
        self.config_binary = self.make_binary('configured.exe')
        self.path_binary = self.make_binary('path.exe')
        self.start_patch(patch.object(codex_runner, 'CONFIG_PATH', self.config))
        self.start_patch(patch.dict(os.environ))
        os.environ.pop('FIELDWORK_CODEX_PATH', None)
        self.which = self.start_patch(
            patch.object(codex_runner.shutil, 'which', return_value=str(self.path_binary)))
        self.start_patch(patch.object(codex_runner.Path, 'home', return_value=self.root))

    def start_patch(self, patcher):
        value = patcher.start()
        self.addCleanup(patcher.stop)
        return value

    def make_binary(self, name):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b'placeholder; never executed')
        path.chmod(0o700)
        return path

    def write_config(self, value):
        self.config.write_text(json.dumps(value), encoding='utf-8')

    def test_environment_overrides_local_configuration_and_path(self):
        self.write_config({'executable': str(self.config_binary)})
        os.environ['FIELDWORK_CODEX_PATH'] = str(self.environment_binary)

        self.assertEqual(codex_runner.executable(), str(self.environment_binary))
        self.which.assert_not_called()

    def test_environment_does_not_depend_on_valid_local_configuration(self):
        self.config.write_text('{invalid json', encoding='utf-8')
        os.environ['FIELDWORK_CODEX_PATH'] = str(self.environment_binary)

        self.assertEqual(codex_runner.executable(), str(self.environment_binary))
        self.which.assert_not_called()

    def test_local_configuration_overrides_path(self):
        self.write_config({'executable': str(self.config_binary)})

        self.assertEqual(codex_runner.executable(), str(self.config_binary))
        self.which.assert_not_called()

    def test_invalid_environment_selection_never_falls_back(self):
        self.write_config({'executable': str(self.config_binary)})
        for invalid in ('', 'relative.exe', str(self.root / 'missing.exe'), str(self.root)):
            with self.subTest(selection=invalid):
                os.environ['FIELDWORK_CODEX_PATH'] = invalid
                self.assertEqual(codex_runner.executable(), '')
                self.which.assert_not_called()

    def test_invalid_local_selection_never_falls_back(self):
        for invalid in ('', 'relative.exe', str(self.root / 'missing.exe'), str(self.root),
                        None, 42, [], {}):
            with self.subTest(selection=invalid):
                self.write_config({'executable': invalid})
                self.assertEqual(codex_runner.executable(), '')
                self.which.assert_not_called()

    def test_malformed_configuration_never_falls_back(self):
        for content in ('{invalid json', '{}', '[]', 'null', '"codex.exe"'):
            with self.subTest(content=content):
                self.config.write_text(content, encoding='utf-8')
                self.assertEqual(codex_runner.executable(), '')
                self.which.assert_not_called()

    def test_unconfigured_selection_uses_path(self):
        self.assertEqual(codex_runner.executable(), str(self.path_binary))
        self.which.assert_called_once_with('codex')

    def test_unconfigured_selection_retains_local_bin_fallback(self):
        self.which.return_value = None
        local_binary = self.make_binary('.local/bin/codex')

        self.assertEqual(codex_runner.executable(), str(local_binary))
        self.which.assert_called_once_with('codex')

    def test_status_exposes_selected_path_and_unavailable_selection(self):
        self.write_config({'executable': str(self.config_binary)})
        result = codex_runner.status()
        self.assertIs(result['available'], True)
        self.assertEqual(result['executable'], str(self.config_binary))

        self.write_config({'executable': str(self.root / 'missing.exe')})
        result = codex_runner.status()
        self.assertIs(result['available'], False)
        self.assertEqual(result['executable'], '')
        self.which.assert_not_called()


if __name__ == '__main__':
    unittest.main()
