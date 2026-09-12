import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, patch

import codex_runner


class CodexAuthenticationIsolationTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='fieldwork-auth-test-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.binary = str(self.root / 'codex.exe')
        self.system = '\u4ec5\u8fd4\u56de JSON \u7ed3\u679c\u3002'
        self.payload = {'text': 'private-payload-stdin-only'}
        self.schema = {'type': 'object', 'properties': {'ok': {'type': 'boolean'}}}
        self.start_patch(patch.dict(os.environ, {
            'CODEX_HOME': str(self.root / 'codex-home'),
            'CODEX_THREAD_ID': 'parent-thread',
            'CODEX_TURN_ID': 'parent-turn',
            'CODEX_SANDBOX': 'parent-sandbox',
        }, clear=True))
        self.start_patch(patch.object(codex_runner, 'executable', return_value=self.binary))
        self.start_patch(patch.object(codex_runner, 'configured_model', return_value='test-model'))
        self.discovery = self.start_patch(patch.object(
            codex_runner.subprocess, 'run', return_value=self.result('[]')))
        self.process = Mock()
        self.process.returncode = 0
        self.process.poll.return_value = 0
        self.process.communicate.return_value = (json.dumps({
            'type': 'item.completed',
            'item': {'type': 'agent_message', 'text': '{"ok": true}'},
        }), '')
        self.popen = self.start_patch(patch.object(
            codex_runner.subprocess, 'Popen', return_value=self.process))

    def start_patch(self, patcher):
        value = patcher.start()
        self.addCleanup(patcher.stop)
        return value

    def result(self, stdout, returncode=0):
        return subprocess.CompletedProcess([self.binary], returncode, stdout, 'private-error-detail')

    def command(self, servers=()):
        return codex_runner.command(self.binary, self.root, self.root / 'schema.json',
                                    self.root / 'instructions.md', servers)

    def overrides(self, arguments):
        return {arguments[index + 1] for index, value in enumerate(arguments) if value == '-c'}

    def assert_tools_disabled(self, arguments):
        required = {
            'shell_tool', 'unified_exec', 'apps', 'multi_agent', 'plugins', 'hooks',
            'browser_use', 'browser_use_external', 'computer_use', 'image_generation',
            'view_image', 'in_app_browser', 'in_app_local_automation',
            'workspace_dependencies', 'skill_search', 'skill_mcp_dependency_install',
            'sleep_tool', 'goals', 'code_mode', 'code_mode_host',
        }
        values = self.overrides(arguments)
        self.assertTrue({f'features.{name}=false' for name in required}.issubset(values))
        self.assertIn('features.skip_host_skill_discovery=true', values)

    def test_command_preserves_user_provider_configuration_and_isolates_tools(self):
        arguments = self.command(('server_a', 'server-b'))
        values = self.overrides(arguments)

        self.assertNotIn('--ignore-user-config', arguments)
        self.assertFalse(any(value.startswith('model_provider') for value in values))
        self.assertIn('--ignore-rules', arguments)
        self.assertIn('--ephemeral', arguments)
        self.assertEqual(arguments[arguments.index('--sandbox') + 1], 'read-only')
        for value in ('approval_policy="never"', 'web_search="disabled"',
                      'developer_instructions=""', 'project_doc_max_bytes=0',
                      'mcp_servers.server_a.enabled=false', 'mcp_servers.server-b.enabled=false'):
            self.assertIn(value, values)
        self.assert_tools_disabled(arguments)

    def test_command_rejects_mcp_names_that_cannot_be_isolated(self):
        for name in ('server.tools', '', 'server name', 'server"name', 'server\nname',
                     'a' * 101, None, 42):
            with self.subTest(name=name), self.assertRaises(codex_runner.AIError):
                self.command((name,))

    def test_discovery_uses_same_directory_environment_and_feature_isolation(self):
        self.discovery.return_value = self.result(json.dumps([
            {'name': 'server_b', 'enabled': False}, {'name': 'server-a', 'enabled': True},
            {'name': 'server_b'},
        ]))
        environment = {'CODEX_HOME': str(self.root / 'isolated-home')}

        self.assertEqual(codex_runner.mcp_server_names(self.binary, self.root, environment),
                         ['server-a', 'server_b'])
        args, kwargs = self.discovery.call_args
        self.assertEqual(args[0][0], self.binary)
        self.assertEqual(args[0][-3:], ['mcp', 'list', '--json'])
        self.assertNotIn('--ignore-user-config', args[0])
        self.assert_tools_disabled(args[0])
        self.assertEqual(kwargs['cwd'], self.root)
        self.assertEqual(kwargs['env'], environment)
        self.assertTrue(kwargs['capture_output'])
        self.assertGreater(kwargs['timeout'], 0)
        self.popen.assert_not_called()

    def test_empty_mcp_configuration_is_allowed(self):
        self.assertEqual(codex_runner.mcp_server_names(self.binary, self.root, {}), [])

    def test_discovery_failure_blocks_model_and_hides_raw_errors(self):
        failures = [
            self.result('private-error-detail', returncode=1),
            self.result('private-error-detail'),
            self.result('{}'), self.result('null'), self.result('[{}]'), self.result('[42]'),
            self.result('[{"name": null}]'), self.result('[{"name": "server.tools"}]'),
            self.result('[{"name": ""}]'), self.result('[{"name": "server name"}]'),
            subprocess.TimeoutExpired('codex', 15, output='private-error-detail'),
            OSError('private-error-detail'), UnicodeError('private-error-detail'),
        ]
        for failure in failures:
            with self.subTest(failure=type(failure).__name__, output=getattr(failure, 'stdout', None)):
                self.discovery.side_effect = failure if isinstance(failure, Exception) else None
                self.discovery.return_value = failure
                with self.assertRaises(codex_runner.AIError) as caught:
                    codex_runner.run(self.system, self.payload, self.schema)
                self.assertNotIn('private-error-detail', str(caught.exception))
                self.popen.assert_not_called()

    def test_run_sends_payload_only_via_stdin_and_disables_discovered_servers(self):
        self.discovery.return_value = self.result('[{"name":"server_a"},{"name":"server-b"}]')
        self.schema['properties']['claims'] = {
            'type': 'array', 'items': {
                'type': 'object', 'properties': {
                    'text': {'type': 'string'},
                    'evidence_ids': {'type': 'array', 'items': {'type': 'string'}},
                },
                'required': ['text', 'evidence_ids'], 'additionalProperties': False,
            },
        }
        self.schema.update(required=['ok', 'claims'], additionalProperties=False)

        def inspect_inputs(arguments, **kwargs):
            spec = Path(arguments[arguments.index('--output-schema') + 1])
            instruction_option = next(value for value in self.overrides(arguments)
                                      if value.startswith('model_instructions_file='))
            instructions = Path(json.loads(instruction_option.split('=', 1)[1]))
            self.assertEqual(spec.parent, kwargs['cwd'])
            self.assertEqual(instructions.parent, kwargs['cwd'])
            schema_text = spec.read_text(encoding='utf-8')
            instruction_text = instructions.read_text(encoding='utf-8')
            self.assertEqual(json.loads(schema_text), self.schema)
            self.assertTrue(instruction_text.startswith(self.system))
            schema_start = instruction_text.index('\n{', len(self.system)) + 1
            self.assertEqual(json.loads(instruction_text[schema_start:]), self.schema)
            format_constraints = instruction_text[len(self.system):schema_start]
            self.assertIn('required', format_constraints)
            self.assertIn('\u4e0d\u5f97\u6dfb\u52a0', format_constraints)
            for text in (instruction_text, schema_text, ' '.join(arguments)):
                self.assertNotIn(self.payload['text'], text)
            return self.process

        self.popen.side_effect = inspect_inputs

        data, metadata = codex_runner.run(self.system, self.payload, self.schema)

        self.assertEqual(data, {'ok': True})
        self.assertEqual(metadata['model'], 'test-model')
        self.popen.assert_called_once()
        arguments = self.popen.call_args.args[0]
        kwargs = self.popen.call_args.kwargs
        self.assertEqual(arguments[0], self.binary)
        self.assertEqual(arguments[-1], '-')
        self.assertNotIn(self.payload['text'], ' '.join(arguments))
        self.assertEqual(json.loads(self.process.communicate.call_args.kwargs['input']), self.payload)
        self.assertEqual(kwargs['stdin'], subprocess.PIPE)
        self.assertIn('mcp_servers.server_a.enabled=false', self.overrides(arguments))
        self.assertIn('mcp_servers.server-b.enabled=false', self.overrides(arguments))
        self.assert_tools_disabled(arguments)
        self.assertEqual(kwargs['cwd'], self.discovery.call_args.kwargs['cwd'])
        self.assertEqual(kwargs['env'], self.discovery.call_args.kwargs['env'])
        self.assertEqual(kwargs['env']['CODEX_HOME'], os.environ['CODEX_HOME'])
        for name in ('CODEX_THREAD_ID', 'CODEX_TURN_ID', 'CODEX_SANDBOX'):
            self.assertNotIn(name, kwargs['env'])

    def test_authentication_error_hides_provider_error_details(self):
        self.process.returncode = 1
        self.process.poll.return_value = 1
        self.process.communicate.return_value = ('', '401 unauthorized private-error-detail')

        with self.assertRaises(codex_runner.AIError) as caught:
            codex_runner.run(self.system, self.payload, self.schema)

        self.assertNotIn('private-error-detail', str(caught.exception))
        self.assertIn('\u670d\u52a1\u914d\u7f6e', str(caught.exception))


if __name__ == '__main__':
    unittest.main()
