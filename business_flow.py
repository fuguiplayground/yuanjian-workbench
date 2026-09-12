"""人工决策记录：与模型报告分开保存，通过机会编号关联策略、内容及反馈。"""
import re

FIELDS = {
    'brief': ('product', 'market', 'goal', 'constraints', 'success'),
    'opportunity': ('title', 'scenario', 'task', 'obstacle', 'alternative', 'gap', 'evidence'),
    'strategy': ('audience', 'reason', 'promise', 'proof', 'avoid'),
    'content': ('title', 'angle', 'outline', 'proof', 'metric'),
    'feedback': ('observation', 'source', 'result', 'next', 'context'),
}

def fields(value, kind):
    if not isinstance(value, dict):
        raise ValueError('决策记录字段必须为对象')
    result = {}
    for key in FIELDS[kind]:
        text = value.get(key, '')
        if not isinstance(text, str) or len(text) > (45000 if key == 'context' else 4000):
            raise ValueError('决策记录字段类型或长度无效')
        result[key] = text.strip()
    return result

def normalize_workspace(value):
    if not isinstance(value, dict):
        raise ValueError('决策工作区格式无效')
    rows = value.get('cases', [])
    if not isinstance(rows, list) or len(rows) > 100:
        raise ValueError('最多保存 100 张机会卡')
    result = {'brief': fields(value.get('brief', {}), 'brief'), 'cases': [], 'selected_id': value.get('selected_id', '')}
    ids = set()
    for raw in rows:
        if not isinstance(raw, dict):
            raise ValueError('机会卡格式无效')
        id_ = raw.get('id')
        if not isinstance(id_, str) or not re.fullmatch(r'[a-zA-Z0-9_-]{1,80}', id_) or id_ in ids:
            raise ValueError('机会编号无效或重复')
        ids.add(id_)
        row = {'id': id_, **fields(raw, 'opportunity')}
        if not row['title']:
            raise ValueError('请填写需求机会名称')
        version = raw.get('source_version', 0)
        if isinstance(version, bool) or not isinstance(version, int) or version < 0:
            raise ValueError('机会卡资料版本无效')
        row['source_version'] = version
        for kind in ('strategy', 'content', 'feedback'):
            row[kind] = fields(raw.get(kind, {}), kind)
        if row['feedback']['result'] not in ('', '未验证', '支持当前假设', '不支持当前假设', '结果不明确'):
            raise ValueError('请选择有效的反馈结论')
        if row['feedback']['result'] not in ('', '未验证') and not (row['feedback']['observation'] and row['feedback']['source']):
            raise ValueError('验证结论需要实际观察及来源')
        result['cases'].append(row)
    if not isinstance(result['selected_id'], str) or (result['selected_id'] and result['selected_id'] not in ids):
        raise ValueError('当前选择的需求机会不存在')
    return result
