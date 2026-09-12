"""Team package connections use fake keys and never access real credentials."""
import json
import os
import unittest
from unittest.mock import patch

import credential_store
import sellersprite
import sources


TEAM_KEY = 'fake-team-key-for-tests'
PERSONAL_KEY = 'fake-personal-key-for-tests'


class TeamConnectionTests(unittest.TestCase):
    def setUp(self):
        self.records = {}
        patches = [patch.object(sellersprite, '_client', None), patch.object(sellersprite, '_team_key', None),
                   patch.dict(os.environ, {}, clear=True),
                   patch.object(credential_store, 'read', side_effect=lambda provider: self.records.get(provider)),
                   patch.object(credential_store, 'save'),
                   patch.object(sellersprite, 'build_opener'), patch.object(sources, 'build_opener'),
                   patch.object(sources, '_session_connection', {'key': 'fake-tikhub-session', 'base_url': sources.BASE_URLS[0]})]
        self.mocks = [p.start() for p in patches]
        for p in patches:
            self.addCleanup(p.stop)

    @staticmethod
    def initialize(client):
        client.tools = {'product_research': {'inputSchema': {'properties': {'request': {}}}}}

    def test_package_load_only_parses_and_stays_offline(self):
        before_env = dict(os.environ)
        before_tikhub = dict(sources._session_connection)
        with patch.object(sellersprite.Client, 'initialize') as initialize:
            self.assertIsNone(sellersprite.set_team_connection('https://mcp.sellersprite.com/mcp?secret-key=' + TEAM_KEY))
            self.assertEqual(sellersprite._team_key, TEAM_KEY)
            self.assertIsNone(sellersprite._client)
            initialize.assert_not_called()
        credential_store.read.assert_not_called()
        credential_store.save.assert_not_called()
        sellersprite.build_opener.assert_not_called()
        sources.build_opener.assert_not_called()
        self.assertEqual(dict(os.environ), before_env)
        self.assertEqual(sources._session_connection, before_tikhub)

    def test_status_marks_shared_configuration_without_claiming_connection(self):
        sellersprite.set_team_connection(TEAM_KEY)
        status = sellersprite.status()
        self.assertTrue(status['configured'])
        self.assertTrue(status['team_connection'])
        self.assertTrue(status['shared_quota'])
        self.assertFalse(status['connected'])
        self.assertFalse(status['saved'])
        self.assertEqual(status['tool_count'], 0)
        self.assertEqual(status['supported'], {})
        self.assertIn('共用', status['storage'])
        self.assertNotIn(TEAM_KEY, json.dumps(status))
        credential_store.save.assert_not_called()
        sellersprite.build_opener.assert_not_called()

    def test_first_query_initializes_team_connection_only_once(self):
        sellersprite.set_team_connection(TEAM_KEY)
        with patch.object(sellersprite.Client, 'initialize', autospec=True, side_effect=self.initialize) as initialize, \
             patch.object(sellersprite.Client, 'call', return_value={'data': {'items': []}}) as call:
            sellersprite.query('products', 'blender')
            sellersprite.query('products', 'cup')
        initialize.assert_called_once()
        self.assertEqual(call.call_count, 2)
        self.assertEqual(sellersprite._client.key, TEAM_KEY)
        self.assertTrue(sellersprite.status()['connected'])
        self.assertTrue(sellersprite.status()['team_connection'])
        credential_store.save.assert_not_called()
        sources.build_opener.assert_not_called()

    def test_vault_then_environment_then_team_precedence(self):
        sellersprite.set_team_connection(TEAM_KEY)
        self.records['sellersprite'] = {'key': PERSONAL_KEY}
        with patch.dict(os.environ, {'SELLERSPRITE_SECRET_KEY': 'fake-environment-key'}), \
             patch.object(sellersprite.Client, 'initialize', self.initialize):
            self.assertFalse(sellersprite.status()['team_connection'])
            sellersprite.connect()
            self.assertEqual(sellersprite._client.key, PERSONAL_KEY)
            sellersprite._client = None
            self.records.clear()
            sellersprite.connect()
            self.assertEqual(sellersprite._client.key, 'fake-environment-key')
            self.assertFalse(sellersprite.status()['shared_quota'])

    def test_existing_client_and_explicit_replacement_take_precedence(self):
        with patch.object(sellersprite.Client, 'initialize', self.initialize):
            sellersprite.connect(PERSONAL_KEY)
            sellersprite.set_team_connection(TEAM_KEY)
            self.records['sellersprite'] = {'key': 'fake-other-vault-key'}
            sellersprite.connect()
            self.assertEqual(sellersprite._client.key, PERSONAL_KEY)
            self.assertFalse(sellersprite.status()['team_connection'])
            sellersprite.connect('fake-explicit-replacement')
            self.assertEqual(sellersprite._client.key, 'fake-explicit-replacement')
            sellersprite._client = None
            self.records.clear()
            sellersprite.connect()
            self.assertTrue(sellersprite.status()['team_connection'])
            sellersprite.connect(PERSONAL_KEY)
            self.assertEqual(sellersprite._client.key, PERSONAL_KEY)
            self.assertFalse(sellersprite.status()['shared_quota'])
        credential_store.save.assert_not_called()

    def test_bad_package_key_or_failed_initialization_preserves_valid_state(self):
        sellersprite.set_team_connection(TEAM_KEY)
        for bad in ('bad', '中文错误密钥', 'https://evil.example/mcp?secret-key=' + TEAM_KEY):
            with self.assertRaises(ValueError):
                sellersprite.set_team_connection(bad)
        self.assertEqual(sellersprite._team_key, TEAM_KEY)
        with patch.object(sellersprite.Client, 'initialize', side_effect=sources.SourceError('模拟连接失败')):
            with self.assertRaises(sources.SourceError):
                sellersprite.query('products', 'blender')
        self.assertIsNone(sellersprite._client)
        self.assertTrue(sellersprite.status()['configured'])
        self.assertFalse(sellersprite.status()['connected'])
        with patch.object(sellersprite.Client, 'initialize', self.initialize):
            sellersprite.connect(PERSONAL_KEY)
        with patch.object(sellersprite.Client, 'initialize', side_effect=sources.SourceError('模拟连接失败')):
            with self.assertRaises(sources.SourceError):
                sellersprite.connect('fake-invalid-replacement')
        self.assertEqual(sellersprite._client.key, PERSONAL_KEY)
        credential_store.save.assert_not_called()

    def test_without_team_package_retains_unconfigured_status(self):
        status = sellersprite.status()
        self.assertFalse(status['configured'])
        self.assertFalse(status['connected'])
        self.assertFalse(status['team_connection'])
        self.assertFalse(status['shared_quota'])
        self.assertEqual(status['storage'], '仅当前服务内存；停止服务后需重新连接')


if __name__ == '__main__':
    unittest.main()
