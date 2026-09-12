import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
from http.server import HTTPServer
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from unittest.mock import patch
import device_setup as setup


class DeviceSetupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.receipt = Path(self.temp.name) / 'receipt.json'
        self.config = {'source':'127.0.0.1', 'target':'127.0.0.1', 'expires_at':time.time()+60}
        self.server = HTTPServer(('127.0.0.1', 0), setup.make_handler(self.config, self.receipt))
        self.config['port'] = self.server.server_port
        self.thread = threading.Thread(target=self.server.serve_forever, name='setup-source', daemon=True)
        self.thread.start()
        self.addCleanup(self.stop)

    def stop(self):
        self.server.shutdown(); self.server.server_close(); self.thread.join()

    def request(self, path='/connections', headers=None):
        req = Request(f"http://127.0.0.1:{self.config['port']}"+path, headers=headers or {})
        try:
            response = urlopen(req, timeout=3)
        except HTTPError as e:
            response = e
        with response:
            return response.status, json.load(response)

    def test_browser_and_other_device_cannot_read_credentials(self):
        with patch.object(setup.credential_store, 'read') as read:
            self.assertEqual(self.request()[0],403)
            self.assertEqual(self.request(headers={'X-Fieldwork-Setup':'1','Origin':'https://other.example'})[0],403)
            self.config['target']='100.113.199.9'
            self.assertEqual(self.request(headers={'X-Fieldwork-Setup':'1'})[0],403)
            read.assert_not_called()

    def test_sender_readiness_checks_denial_without_reading_vault(self):
        self.config['target'] = '100.113.199.9'
        with patch.object(setup.credential_store, 'read') as read:
            self.assertTrue(setup.sender_ready(self.config))
            read.assert_not_called()
        self.config['target'] = '127.0.0.1'
        with patch.object(setup.credential_store, 'read', return_value=None):
            self.assertFalse(setup.sender_ready(self.config))

    def test_receiver_saves_each_provider_then_closes_handoff(self):
        source={'tikhub':{'key':'test-tikhub-key','base_url':'https://api.tikhub.dev'},
                'sellersprite':{'key':'test-seller-key'}}
        target={}
        def read(provider):
            return (source if threading.current_thread().name=='setup-source' else target).get(provider)
        def tik(key,base,persist):
            self.assertTrue(persist);target['tikhub']={'key':key,'base_url':base}
        def seller(key,persist):
            self.assertTrue(persist);target['sellersprite']={'key':key}
        with patch.object(setup.credential_store,'read',side_effect=read), patch.object(setup.sources,'connect',side_effect=tik), patch.object(setup.sellersprite,'connect',side_effect=seller):
            setup.receive(self.config)
            self.assertEqual(source,target)
            self.assertTrue(self.receipt.exists())
            self.assertEqual(self.request(headers={'X-Fieldwork-Setup':'1'})[0],410)
        self.assertNotIn('test-',self.receipt.read_text())

    def test_expired_or_unready_sender_does_not_return_keys(self):
        with patch.object(setup.credential_store,'read',return_value=None):
            self.assertEqual(self.request(headers={'X-Fieldwork-Setup':'1'})[0],503)
        self.config['expires_at']=time.time()-1
        with patch.object(setup.credential_store,'read') as read:
            self.assertEqual(self.request(headers={'X-Fieldwork-Setup':'1'})[0],403)
            read.assert_not_called()

    def test_failed_save_does_not_acknowledge_completion(self):
        source={'tikhub':{'key':'test-tikhub-key','base_url':'https://api.tikhub.dev'},
                'sellersprite':{'key':'test-seller-key'}}
        def read(provider):
            return source.get(provider) if threading.current_thread().name=='setup-source' else None
        with patch.object(setup.credential_store,'read',side_effect=read), patch.object(setup.sources,'connect',side_effect=ValueError('cannot save')):
            with self.assertRaises(ValueError): setup.receive(self.config)
        self.assertFalse(self.receipt.exists())
