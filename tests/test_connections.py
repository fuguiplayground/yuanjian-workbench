import io
import json
import unittest
from unittest.mock import Mock, patch
from urllib.error import HTTPError
import credential_store as vault
import sources
import sellersprite as seller


class ConnectionTests(unittest.TestCase):
    def setUp(self):
        self.records = {}
        patches = [patch.object(vault, 'read', side_effect=lambda p:self.records.get(p)),
                   patch.object(vault, 'save', side_effect=lambda p,r:self.records.update({p:r.copy()})),
                   patch.object(sources, '_session_connection', None), patch.object(seller, '_client', None)]
        for p in patches:
            p.start(); self.addCleanup(p.stop)

    def test_official_url_is_extracted_not_used_as_destination(self):
        key = 'test-key-123456'
        self.assertEqual(seller.parse_connection('https://mcp.sellersprite.com/mcp?secret-key='+key), key)
        self.assertEqual(seller.parse_connection(key), key)
        for url in ['http://mcp.sellersprite.com/mcp?secret-key='+key,
                    'https://other.example/mcp?secret-key='+key,
                    'https://mcp.sellersprite.com.evil.example/mcp?secret-key='+key,
                    'https://user@mcp.sellersprite.com/mcp?secret-key='+key,
                    'https://mcp.sellersprite.com/mcp?secret-key='+key+'&secret-key=second',
                    'https://mcp.sellersprite.com/mcp?secret-key=abc%0Adef']:
            with self.assertRaises(ValueError): seller.parse_connection(url)

    def test_mcp_saved_only_after_verified_and_loaded_on_next_session(self):
        tools = {'product_research': {'inputSchema': {'properties': {'request': {}}}}}
        def initialize(client): client.tools = tools
        with patch.object(seller.Client, 'initialize', initialize):
            result = seller.connect('test-key-123456', persist=True)
            self.assertTrue(result['saved'])
            self.assertNotIn('test-key', json.dumps(result))
            seller._client = None
            with patch.object(seller.Client, 'call', return_value={'data': {'items': []}}):
                seller.query('products', 'blender')
                self.assertEqual(seller._client.key, 'test-key-123456')
        with patch.object(seller.Client, 'initialize', side_effect=sources.SourceError('denied')):
            with self.assertRaises(sources.SourceError): seller.connect('replacement-key', persist=True)
        self.assertEqual(self.records['sellersprite']['key'], 'test-key-123456')

    def test_tikhub_validation_redaction_and_restart(self):
        response = io.BytesIO(json.dumps({'code':200,'api_key_data':{'key':'private'},
                                         'user_data':{'email':'private@example.com'}}).encode())
        response.status = 200
        with patch.object(sources, 'build_opener') as opener:
            opener.return_value.open.return_value = response
            status = sources.connect('test-tikhub-key', 'https://api.tikhub.io', persist=True)
        self.assertTrue(status['verified']); self.assertTrue(status['saved'])
        self.assertNotIn('private', json.dumps(status))
        sources._session_connection = None
        self.assertEqual(sources.credential(), 'test-tikhub-key')
        self.assertEqual(sources.api_base(), 'https://api.tikhub.io')

    def test_bad_tikhub_key_or_host_does_not_replace_valid_record(self):
        self.records['tikhub']={'key':'previous-valid-key','base_url':'https://api.tikhub.dev'}
        with patch.object(sources, 'build_opener') as opener:
            opener.return_value.open.side_effect=HTTPError('https://api.tikhub.dev',401,'no',{},None)
            with self.assertRaises(sources.SourceError): sources.connect('test-bad-key',persist=True)
            with self.assertRaises(sources.SourceError): sources.connect('test-key-1234','https://evil.example',True)
        self.assertEqual(self.records['tikhub']['key'],'previous-valid-key')

    def test_redirect_never_forwards_credentials(self):
        with self.assertRaises(HTTPError) as caught:
            sources.NoRedirect().redirect_request(Mock(full_url='https://api.tikhub.dev'),None,302,'',{},'https://evil.example')
        caught.exception.close()


class VaultTests(unittest.TestCase):
    def test_mac_secret_uses_stdin_not_command_line_and_checks_readback(self):
        record={'key':'test-key-123456'}
        with patch.object(vault.sys,'platform','darwin'), patch.object(vault.subprocess,'run') as run, patch.object(vault,'read',return_value=record):
            vault.save('sellersprite',record)
            args=run.call_args
            self.assertEqual(args.args[0],['/usr/bin/security','-i'])
            self.assertNotIn(record['key'],str(args.args))
            self.assertIn(b'add-generic-password',args.kwargs['input'])
        with patch.object(vault.sys,'platform','darwin'), patch.object(vault.subprocess,'run'), patch.object(vault,'read',return_value=None):
            with self.assertRaises(ValueError): vault.save('sellersprite',record)

    def test_unsupported_os_does_not_fall_back_to_plaintext(self):
        with patch.object(vault.sys,'platform','linux'):
            with self.assertRaises(ValueError): vault.save('tikhub',{'key':'test-key-1234'})
            self.assertIsNone(vault.read('tikhub'))
