import copy
import tempfile
import unittest
from server import new_project, Store, restore_project
from business_flow import normalize_workspace

class BusinessFlowTests(unittest.TestCase):
    def test_roundtrip_and_links(self):
        p = new_project('test', 'test')
        raw = {'brief': {'goal': '找人群'}, 'selected_id': 'case-1', 'cases': [
            {'id': 'case-1', 'title': '清洗不便', 'strategy': {'audience': '通勤使用者'},
             'content': {'title': '清洗演示'}, 'feedback': {'result': '未验证'}}]}
        p['decision_workspace'] = normalize_workspace(raw)
        with tempfile.TemporaryDirectory() as d:
            store = Store(d); store.save(p)
            loaded = store.load(p['id'])
            self.assertEqual(loaded['decision_workspace']['cases'][0]['content']['title'], '清洗演示')
            self.assertEqual(restore_project(loaded)['decision_workspace'], loaded['decision_workspace'])
    def test_invalid_links_and_limits(self):
        for value in [{'selected_id':'missing','cases':[]}, {'cases':[{'id':'x','title':'a'},{'id':'x','title':'b'}]}, {'brief':{'goal':['bad']}}, {'cases':[{'id':'x','title':'a','feedback':{'result':'成功已证明'}}]}]:
            with self.assertRaises(ValueError): normalize_workspace(value)
    def test_old_project(self):
        p=new_project('old','old');p.pop('decision_workspace',None)
        self.assertEqual(restore_project(p)['decision_workspace']['cases'],[])
