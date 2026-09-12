"""Versioned, independently grounded analysis modules for the local AI report."""
import copy
import math
from pathlib import Path


def obj(properties):
    return {'type': 'object', 'properties': properties, 'required': list(properties), 'additionalProperties': False}


def arr(items):
    return {'type': 'array', 'items': items}


def enum(*values):
    return {'type': 'string', 'enum': list(values)}


S = {'type': 'string'}
IDS = arr(S)
STAGE = enum('A1', 'A2', 'A3', 'A4', 'A5')
POINT = obj({'text': S, 'basis': enum('evidence', 'inference', 'unknown'),
             'evidence_ids': IDS, 'validation': S})
QUOTE = obj({'quote': S, 'evidence_id': S})
SCORE = obj({'score': {'type': ['integer', 'null'], 'minimum': 1, 'maximum': 5}, 'reason': POINT})
BASE = {'title': S, 'summary': S, 'quality': enum('complete', 'limited'), 'limitations': arr(S)}
PROFILE = obj({
    'name': S, 'one_line': S,
    'layers': obj({k: POINT for k in ('natural', 'social', 'consumption', 'scene', 'lifestyle',
                                    'emotion', 'deep_emotion', 'values')}),
    'day_in_life': arr(obj({'moment': S, 'scene': S, 'task': S, 'friction': S,
                          'basis': enum('evidence', 'inference', 'unknown'), 'evidence_ids': IDS, 'validation': S})),
    'needs': obj({k: POINT for k in ('explicit', 'implicit', 'deep')}),
    'purchase_triggers': arr(POINT), 'decision_factors': arr(POINT),
    'barriers': arr(POINT), 'alternatives': arr(POINT),
    'positioning': obj({k: POINT for k in ('target', 'promise', 'proof', 'avoid')}),
    'search_terms': arr(obj({'text': S, 'evidence_id': S})),
    'scores': obj({k: SCORE for k in ('pain', 'payment', 'fit', 'content')}),
    'priority': enum('高', '中', '低', '待验证'), 'priority_reason': POINT,
    'validation_questions': arr(S), 'evidence_ids': IDS,
})

MODULE_ORDER = ('clean', 'audience', 'intent', 'comments', 'notes', 'topics', 'summary', 'segments')
MODULES = {
    'segments': {'label': '分人群营销策略', 'collections': ('keywords', 'posts', 'reviews'), 'prompt': '_AUDIENCE_SYSTEM', 'output': '同一行为下按动机与人生阶段拆人群，再逐人群制定产品、渠道、内容、达人及促销策略'},
    'clean': {'label': '关键词库', 'collections': ('keywords',), 'prompt': '_CLEAN_SYSTEM',
              'output': '逐词分类、内容建议、主题选题地图、高价值词与品牌机会'},
    'audience': {'label': '人群画像', 'collections': ('keywords', 'posts', 'reviews'), 'prompt': '_AUDIENCE_SYSTEM',
                 'output': '千机塔八层、日常场景、三层需求、购买决策与逐项优先级依据'},
    'intent': {'label': '搜索意图', 'collections': ('keywords',), 'prompt': '_INTENT_SYSTEM',
               'output': 'A1–A5 分布、最大决策卡点、需求迫切度与对应内容策略'},
    'comments': {'label': '评论需求', 'collections': ('reviews',), 'prompt': '_COMMENTS_SYSTEM',
                 'output': '痛点、提问、认可、原话及可继续验证的需求'},
    'notes': {'label': '内容规律', 'collections': ('posts',), 'prompt': '_NOTES_SYSTEM',
              'output': '内容主题、表现与角度、开头结构收尾、样本中的未覆盖角度'},
    'topics': {'label': '营销选题', 'collections': ('keywords', 'posts', 'reviews'), 'prompt': '_TOPICS_SYSTEM',
               'output': '具体标题、人群、切入角度、开头、提纲、行动引导与证据词'},
    'summary': {'label': '综合判断', 'collections': ('keywords', 'posts', 'reviews'), 'prompt': '_INSIGHT_SYSTEM',
                'output': '最窄切入点、先做什么、验证步骤及四项判断自检'},
}

SCHEMAS = {
    'clean': obj({**BASE, 'items': arr(obj({'id': S, 'valid': {'type': 'boolean'}, 'reason': S,
        'w5h1': enum('WHAT', 'WHO', 'WHERE', 'WHEN', 'WHY', 'HOW'), 'intent': S, 'stage': STAGE,
        'emotion': enum('正向', '负向', '中性'), 'theme': S, 'content_suggestion': S})),
        'theme_recommendations': arr(obj({'theme': S, 'direction': POINT, 'layer': STAGE})),
        'high_value_terms': arr(obj({'text': S, 'evidence_id': S, 'why': POINT})),
        'brand_opportunities': arr(POINT), 'findings': arr(POINT), 'next_steps': arr(POINT)}),
    'audience': obj({**BASE, 'audiences': arr(PROFILE), 'audience_map': POINT, 'next_steps': arr(POINT)}),
    'intent': obj({**BASE, 'items': arr(obj({'id': S, 'stage': STAGE, 'emotion': S})),
        'stage_insights': arr(obj({'stage': STAGE, 'interpretation': POINT, 'next_content': POINT})),
        'bottleneck': POINT, 'demands': arr(obj({'need': S, 'urgency': enum('高', '中', '低', '待验证'),
                                               'diagnosis': POINT, 'action': POINT})),
        'emotions': arr(obj({'emotion': S, 'interpretation': POINT})), 'next_steps': arr(POINT)}),
    'comments': obj({**BASE,
        **{k: arr(obj({'point': POINT, 'quotes': arr(QUOTE)})) for k in ('pains', 'questions', 'loves')},
        'golden_quotes': arr(QUOTE), 'topics': arr(POINT), 'demand_priorities': arr(POINT), 'next_steps': arr(POINT)}),
    'notes': obj({**BASE, 'themes': arr(obj({'theme': S, 'explanation': POINT})),
        'angles': arr(obj({'angle': S, 'why': POINT})), 'performance_note': S,
        'patterns': arr(obj({'part': enum('opening', 'body', 'closing'), 'finding': POINT})),
        'topics': arr(obj({'title': S, 'angle': S, 'why': POINT})), 'gaps': arr(POINT), 'next_steps': arr(POINT)}),
    'topics': obj({**BASE, 'topics': arr(obj({'title': S, 'target': S, 'stage': STAGE, 'angle': S,
        'format': S, 'opening': S, 'outline': arr(S), 'call_to_action': S, 'why': POINT,
        'words': arr(S), 'evidence_ids': IDS})), 'priority_reason': POINT, 'next_steps': arr(POINT)}),
    'summary': obj({**BASE, 'core_opportunity': POINT, 'narrowest_entry': POINT,
        'priority_audiences': arr(obj({'name': S, 'why': POINT})), 'positioning': POINT,
        'actions': arr(obj({'action': S, 'why': POINT, 'deliverable': S, 'verification': S})),
        'cautions': arr(POINT), 'self_check': obj({**{k: {'type': 'boolean'} for k in
                  ('no_anxiety', 'narrowest', 'has_contrast', 'real_demand')}, 'note': S})}),
}

MOTIVE_KEYS = ('environment', 'identity', 'attributes', 'functional_problem', 'emotion', 'social_friction', 'functional_expectation', 'emotional_expectation', 'social_expectation')

# 新模块保留旧画像 schema，不改变已保存历史报告的校验契约。
SCHEMAS['segments'] = obj({**BASE, 'audiences': arr(obj({**PROFILE['properties'],
    'buying_motivation': POINT, 'life_stage': POINT, 'motives': obj({k: POINT for k in MOTIVE_KEYS}),
    'marketing': obj({k: POINT for k in ('product', 'channels', 'content', 'creators', 'promotion')})})),
    'audience_map': POINT, 'next_steps': arr(POINT)})

COMMON = '''
本次只完成指定模块，不把所有分析压缩成一句话简报。严格按本模块 schema 输出。
字段 basis：evidence 仅指原文直接表达；inference 是基于原文的解释或建议；unknown 是资料缺失。
所有 basis 对象均须明确 evidence_ids；前两种必须有本模块证据，unknown 允许空引用且须写明如何验证。
存在引用不代表结论已证实：用户画像、因果、心理与营销判断通常属于 inference；不得靠附一个编号冒充事实。
无资料时明确待验证，不为了填满字段编造。缺少重要资料时 quality=limited，并在 limitations 集中说明。
search_terms/high_value_terms 中的 text 必须是本模块关键词原文，evidence_id 必须对应同一词。
quote 必须逐字摘自对应 evidence_id 的可见原文，保留语言，不用翻译伪装原话；不凭单条评论声称高频。
评论 evidence.review_type 为 social 时是社交评论，为 product 时是商品评价；二者都不保证已经核实购买身份。
只引用本模块输入编号。不能把其他模块的推断当新证据；已完成模块如作为上下文仅供衔接。
日常场景允许具体的假设示例，但 basis 必须标 inference，不能捏造真实年龄、职业、收入、家庭、销量或付费。
词数、评论数是样本记录数，不是人数、搜索量或人群占比；不同平台互动数不可直接横比。
原提示词的固定数量是上限；证据不足少给，不能凑数。单项必须具体说清原因及下一步产出，避免空泛的「加强营销」。
'''

ADAPTATIONS = {
    'clean': '''售后故障、清洗、漏水、维修都是需求证据，必须保留；英文词不因字母组成无效。
逐条返回全部输入词，跨平台同词分别保留编号。有效词的 reason 说明分类依据，content_suggestion 给具体内容做法。
每个有效归一主题必须有一个 theme_recommendations，direction 说明内容角度，layer 给 A 层。
高价值词只选有具体人群、场景或购买/需求线索的原词，说明理由；无品牌证据时 brand_opportunities 为空。
统计由程序计算，不生成统计字段。不要用 A 层词数少推断平台内容供给不足，只能列为待检查方向。''',
    'audience': '''这是完整人群深描，不是一键简报。依据身份状态、动机、触发场景区分 3–5 类为上限；有依据少给。
每类必须完整填写八层 layers，重点解释 emotion/deep_emotion/values 的递进，不把三层写成同一句话。
name 具体到状态，不取「年轻人」「宝妈」这类宽泛名；one_line 写谁在什么处境下卡在哪里。
day_in_life 给有依据的 2–4 个日常片段（时刻、场景、任务、阻碍），标明假设，不编虚构用户履历。
needs.explicit 是嘴上表达的问题；implicit 是要完成的任务或未直说的顾虑；deep 是情感/身份/价值追求，后两层标推断。
purchase_triggers/decision_factors/barriers/alternatives 逐项说清为什么买、比较什么、为何不买、现在用什么替代。
positioning 给该人群的定位、具体承诺、需要证明的材料、应避免的承诺。
四标准来自原工作台：[痛感强度·付费证据·产品承接·内容供给]。scores 分别为 pain/payment/fit/content，每项单独 1–5 分或 null，加判断理由和证据。
score=null 表示无法判断，不是零分。只有关键词不得给 payment 打分；询价/求链接最多是求购线索，不等于已付费。
payment 只有直接说明发生过购买或支付的原话才可评分；reason.text 说明哪句原话提供了该线索。
没有直接付费线索时必须给 null。单纯有评论、有使用困扰、有点赞、有询价或反复搜索都不足以评分，不能用维护痛点代替付费依据。
缺少本产品资料时 fit 不得声称产品已经满足需求；未调研内容供给时 content 只能待验证。
不能将没有依据的年龄/性别/收入写成事实。search_terms 只选输入原词，评论也可支撑画像。
每类给优先级理由和具体访谈/验证问题，不能只用笼统的「痛点明显、市场大」。''',
    'intent': '''逐词完整返回 items，程序计算 A1–A5 与情绪的样本分布。
stage_insights 按样本中实际出现的阶段给诊断和下一步内容；bottleneck 解释用户为什么卡住，不复述最大词数。
demands 写具体需求、迫切度依据、处理动作；没有反复行为或购买证据，不把词频当需求强度。
情绪给具体感受及由哪类原话推得，内容动作要能直接执行。''',
    'comments': '''只分析评论/评价原文，区分提问、使用经历和态度表达。
每个痛点、问题、认可点都给逐字原话及编号。未提供回复链时不能断言问题无人回答。
提出需求排序依据与需补采的问题，不把几句泛泛赞美推断成强需求；不把商品评价与社交围观当同一强度证据。''',
    'notes': '''仅分析本次内容样本。metrics.likes 在 Reddit 是社区分数，不是点赞人数；不同平台不可横比。
有真实指标才能描述本样本内的高低表现，无指标时 performance_note 明说不能判断爆款；互动不证明因果。
patterns 分开分析开头、正文、收尾，给实际写法；正文被截断时不能猜未见结尾。
gaps 只写本次样本没覆盖的角度，不宣称整个市场空白；选题服务当前产品，不夹带叁斤个人定位。''',
    'topics': '''依据充分时深化 8–12 个角度为上限；不照抄标题、不靠恐吓制造焦虑。
每个给目标人群、A 层、角度反差、适合的形式、具体开头、3–5 个提纲要点、行动引导和为什么。
words 只能选本模块输入的关键词原文，无关键词时为空，引用可来自内容/评论。
提纲中的产品性能、实验结论和卖点若尚无证据，只能列为需要测试/展示的内容，不写成既定事实。''',
    'summary': '''只做综合判断模块，详细画像和选题不在此重复堆砌。
明确核心机会、最窄切入点、优先人群、定位及 3–5 个行动，每个行动写具体交付物和验证标准。
如果提供已完成模块上下文，指出它们的共同结论与矛盾，但证据仍限本模块原文。
self_check 四项如实填 boolean；有 false 时 note 写未通过原因和需补验证，不强迫全部通过。''',
}


ADAPTATIONS['segments'] = ADAPTATIONS['audience'] + """
本模块同时输出拆分人群与每类人的完整营销方案，两页读取同一个人群对象，禁止名称猜配或拼接其他报告。
先分析原始词、帖子与评论的场景、要完成的任务、阻碍、期待，再按购买动机 × 人生阶段拆分。
同一标签不等于同一动机，同一身份也可能有两种购买目的。没有原文支持的划分只能标为假设；不要虚构姓名。
buying_motivation 解释为什么买；life_stage 只写资料支持的状态，未知则明确待验证。
marketing.product 写产品特性建议、设计要点、价值主张以及需验证的证明；不编造现有规格。
marketing.channels 写这类人在哪个具体场景被触达、选该渠道的理由与试点动作。
marketing.content 写痛点共鸣、场景演示、情感表达三个具体方向，各给一个标题和证明材料。
marketing.creators 写达人类型、适配原因及筛选条件，不虚构真实达人和报价。
marketing.promotion 写适配的组合或促销机制、需要确认的成本及测试指标，价格折扣仅为待测建议。
所有 marketing 项是策略建议，basis 为 inference 或 unknown，不作为已证实效果。
缺少产品信息、原帖或评论必须在 limitations 明确列出。不得照抄参考案例的12小时持妆等承诺。
"""

def system_prompt(key, prompts, guard):
    result = guard + prompts[MODULES[key]['prompt']] + COMMON + ADAPTATIONS[key]
    if key == 'segments':
        result += '\n' + (Path(__file__).resolve().parent / 'skills/consumer-motivation-insight/analysis.md').read_text(encoding='utf-8')
    return result


def check_schema(value, schema):
    type_ = schema['type']
    if isinstance(type_, list):
        if value is None and 'null' in type_:
            return
        type_ = next(t for t in type_ if t != 'null')
    if type_ == 'object':
        if not isinstance(value, dict) or set(value) != set(schema['properties']):
            raise ValueError('AI 返回的报告字段不完整或包含未知字段')
        for key, spec in schema['properties'].items():
            check_schema(value[key], spec)
    elif type_ == 'array':
        if not isinstance(value, list) or len(value) > 500:
            raise ValueError('AI 返回的列表格式无效')
        for item in value:
            check_schema(item, schema['items'])
    elif type_ == 'string':
        if not isinstance(value, str) or len(value) > 20000:
            raise ValueError('AI 返回的文字格式无效')
    elif type_ == 'boolean' and type(value) is not bool:
        raise ValueError('AI 返回的判断格式无效')
    elif type_ == 'integer':
        if type(value) is not int or not schema.get('minimum', -math.inf) <= value <= schema.get('maximum', math.inf):
            raise ValueError('AI 返回的评分格式无效')
    if 'enum' in schema and value not in schema['enum']:
        raise ValueError('AI 返回的分类标签无效')


def metrics(kind, row):
    keys = ('likes', 'comment_count') if kind == 'posts' else ('rating',) if kind == 'reviews' else ()
    return {key: row.get(key) if type(row.get(key)) in (int, float) and math.isfinite(row[key]) else None for key in keys}


def validate(key, report, evidence, allow_legacy=False):
    report = copy.deepcopy(report)
    if not isinstance(report, dict):
        raise ValueError('AI 模块必须返回结构化报告')
    for derived in ('stats', 'topic_map', 'journey'):
        report.pop(derived, None)
    if key == 'segments' and allow_legacy:
        for person in report.get('audiences', []):
            if 'motives' not in person:
                person['motives'] = {k: {'text': '旧报告未独立分析此项', 'basis': 'unknown', 'evidence_ids': [], 'validation': '补充原文并重新生成消费动机分析。'} for k in MOTIVE_KEYS}
    check_schema(report, SCHEMAS[key])
    allowed = {e['id']: e for e in evidence}
    if any(e['kind'] not in MODULES[key]['collections'] for e in evidence):
        raise ValueError('模块引用了不属于本模块的数据类型')

    def check(value):
        if isinstance(value, dict):
            if 'evidence_ids' in value:
                ids = value['evidence_ids']
                if len(ids) != len(set(ids)) or any(i not in allowed for i in ids):
                    raise ValueError('模块引用了未提供或重复的证据')
                if not ids and value.get('basis') != 'unknown':
                    raise ValueError('模块结论缺少本块证据')
            if 'basis' in value:
                if value['basis'] == 'unknown' and not value['validation'].strip():
                    raise ValueError('待验证结论缺少验证方法')
                if 'text' in value and not value['text'].strip():
                    raise ValueError('模块结论不能为空')
            if 'evidence_id' in value:
                source = allowed.get(value['evidence_id'])
                if not source:
                    raise ValueError('模块原话引用了未提供的证据')
                if 'quote' in value and (not value['quote'].strip() or value['quote'] not in source['text']):
                    raise ValueError('模块原话不是对应证据的可见原文')
                if 'text' in value and (source['kind'] != 'keywords' or value['text'] != source['text']):
                    raise ValueError('模块搜索词与引用原词不一致')
            for child in value.values():
                check(child)
        elif isinstance(value, list):
            for child in value:
                check(child)
    check(report)
    if not report['title'].strip() or not report['summary'].strip():
        raise ValueError('模块报告缺少标题或结论')
    if report['quality'] == 'limited' and not any(s.strip() for s in report['limitations']):
        raise ValueError('有限结论必须说明资料缺口')
    if key in ('clean', 'intent'):
        ids = [i['id'] for i in report['items']]
        if len(ids) != len(set(ids)) or set(ids) != set(allowed):
            raise ValueError('模块未完整覆盖本次关键词，或返回多余编号')
    if key == 'clean':
        valid = [i for i in report['items'] if i['valid']]
        themes = {}
        for item in valid:
            if not item['theme'].strip() or not item['content_suggestion'].strip():
                raise ValueError('有效关键词缺少主题或内容建议')
            themes.setdefault(item['theme'], []).append(item['id'])
        recs = report['theme_recommendations']
        if len(recs) != len(themes) or {r['theme'] for r in recs} != set(themes):
            raise ValueError('主题内容方向未完整对应有效关键词主题')
        for recommendation in recs:
            if any(i not in themes[recommendation['theme']] for i in recommendation['direction']['evidence_ids']):
                raise ValueError('主题内容方向引用了其他主题的关键词')
        high_value_ids = [r['evidence_id'] for r in report['high_value_terms']]
        if len(high_value_ids) != len(set(high_value_ids)) or set(high_value_ids) - {i['id'] for i in valid}:
            raise ValueError('高价值词包含无效词或重复记录')
        report['stats'] = {'total': len(report['items']), 'valid': len(valid),
            'invalid': len(report['items']) - len(valid), 'topic_count': len(themes),
            'longtail_count': len({r['evidence_id'] for r in report['high_value_terms']}),
            'how_pct': round(100 * sum(i['w5h1'] == 'HOW' for i in valid) / len(valid)) if valid else 0}
        for name, field, labels in (('w5h1', 'w5h1', ('WHAT','WHO','WHERE','WHEN','WHY','HOW')),
                                    ('journey', 'stage', ('A1','A2','A3','A4','A5')),
                                    ('emotion', 'emotion', ('正向','负向','中性'))):
            report['stats'][name] = [{'name': label, 'count': sum(i[field] == label for i in valid)} for label in labels]
        report['topic_map'] = sorted([dict(r, count=len(themes[r['theme']]), evidence_ids=themes[r['theme']]) for r in recs],
                                     key=lambda r: -r['count'])
    elif key == 'intent':
        stages = [r['stage'] for r in report['stage_insights']]
        present = {i['stage'] for i in report['items']}
        if len(stages) != len(set(stages)) or set(stages) != present:
            raise ValueError('决策阶段诊断未对应本次关键词分类')
        report['journey'] = [{'stage': stage, 'count': sum(i['stage'] == stage for i in report['items']),
                              'evidence_ids': [i['id'] for i in report['items'] if i['stage'] == stage]}
                             for stage in ('A1', 'A2', 'A3', 'A4', 'A5')]
    elif key in ('audience', 'segments'):
        if len(report['audiences']) > 5:
            raise ValueError('人群深描最多五类，不得用数量冒充深度')
        if not report['audiences']:
            raise ValueError('依据不足，未形成具体画像，请补充相关搜索词、使用场景或评论资料后重试')
        for person in report['audiences']:
            if not person['name'].strip() or not person['one_line'].strip() or not person['validation_questions']:
                raise ValueError('人群画像缺少具体描述或验证问题')
            if not 2 <= len(person['day_in_life']) <= 4 or any(not person[k] for k in
                    ('purchase_triggers', 'decision_factors', 'barriers', 'alternatives')):
                raise ValueError('人群深描缺少日常片段或购买决策分析；未知项请明确写待验证')
            for score in person['scores'].values():
                if score['reason']['basis'] == 'unknown' and score['score'] is not None:
                    raise ValueError('无证据评分必须留空，不能填零或猜分')
            payment = person['scores']['payment']
            if payment['score'] is not None and not any(allowed[i]['kind'] != 'keywords' for i in payment['reason']['evidence_ids']):
                raise ValueError('只有关键词不能给付费证据打分')
    elif key == 'comments':
        for item in report['pains'] + report['questions'] + report['loves']:
            if not item['quotes'] or any(q['evidence_id'] not in item['point']['evidence_ids'] for q in item['quotes']):
                raise ValueError('评论需求缺少与本项依据对应的原话')
    elif key == 'notes':
        parts = [p['part'] for p in report['patterns']]
        if len(parts) != 3 or set(parts) != {'opening', 'body', 'closing'}:
            raise ValueError('内容拆解须分别说明开头、正文、收尾；未见部分写待验证')
    elif key == 'topics':
        if len(report['topics']) > 12:
            raise ValueError('单次最多深化十二个选题')
        for topic in report['topics']:
            if len(topic['outline']) < 2 or not topic['opening'].strip():
                raise ValueError('选题深化缺少具体开头或提纲')
            if any(not topic[field].strip() for field in ('title', 'target', 'angle', 'format', 'call_to_action')):
                raise ValueError('选题深化缺少人群、角度、形式或行动引导')
            words = {allowed[i]['text'] for i in topic['evidence_ids'] if allowed[i]['kind'] == 'keywords'}
            if any(w not in words for w in topic['words']):
                raise ValueError('选题词未对应本选题所引用的真实关键词')
    elif key == 'summary':
        if not report['actions'] and report['quality'] != 'limited':
            raise ValueError('综合判断缺少下一步行动')
        for action in report['actions']:
            if any(not action[field].strip() for field in ('action', 'deliverable', 'verification')):
                raise ValueError('综合行动缺少具体交付物或验证标准')
    return report
