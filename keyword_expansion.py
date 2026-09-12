"""Finite breadth-first keyword expansion; templates are queries, never evidence."""
import heapq
import re


MODES = ('quick', 'az', 'intent')
MAX_REQUESTS = 500
# The Chinese intent templates match the original Sanjin workbench.
ZH_PREFIXES = ('怎么', '哪个', '怎么样', '好不好', '值不值', 'vs', '还是', '新手', '学生党', '自学', '入门', '在家')
ZH_SUFFIXES = ('推荐', '测评', '避雷', '攻略', '教程', '怎么做', '怎么开始', '赚钱吗', '好做吗', '靠谱吗', '收费', '接单', '兼职', '平替')
EN_PREFIXES = ('how to use', 'which', 'how does', 'is it worth buying', 'best', 'compare', 'alternatives to',
               'beginner', 'budget', 'learn about', 'getting started with', 'home')
EN_SUFFIXES = ('recommendations', 'review', 'problems', 'guide', 'tutorial', 'how to', 'getting started',
               'worth it', 'easy to use', 'reliable', 'cost', 'maintenance', 'small business', 'alternatives')


def normalized(value):
    return ' '.join(value.split()).casefold()


def first_round(query, mode, platform):
    chinese = platform == 'xhs' and bool(re.search(r'[\u3400-\u9fff]', query))
    join = '' if chinese else ' '
    if mode == 'az':
        return [(query + join + letter, 'az') for letter in 'abcdefghijklmnopqrstuvwxyz']
    if mode == 'intent':
        prefixes, suffixes = (ZH_PREFIXES, ZH_SUFFIXES) if chinese else (EN_PREFIXES, EN_SUFFIXES)
        return [(prefix + join + query, 'prefix') for prefix in prefixes] + \
               [(query + join + suffix, 'suffix') for suffix in suffixes]
    return []


class KeywordQueue:
    def __init__(self, seeds, mode, rounds, limit, platform):
        self.mode, self.rounds, self.limit, self.platform = mode, rounds, limit, platform
        self.pending, self.seen, self.executed = [], set(), set()
        self.sequence, self.used, self.capped = 0, 0, False
        for seed in seeds:
            self.add(seed, seed, 1, '', 'seed')

    def add(self, query, original, round_, parent, expansion):
        if not isinstance(query, str):
            return
        query = ' '.join(query.split())
        mark = normalized(query)
        if not query or len(query) > 300 or mark in self.seen or mark in self.executed:
            return
        # Keep the queue finite even if a supplier returns thousands of suggestions.
        if len(self.pending) >= MAX_REQUESTS:
            self.capped = True
            return
        self.seen.add(mark)
        self.sequence += 1
        target = {'query': query, 'original_query': original, 'round': round_,
                  'parent_query': parent, 'expansion': expansion, 'post': None}
        heapq.heappush(self.pending, (round_, self.sequence, target))

    def __iter__(self):
        return self

    def __next__(self):
        if self.used >= self.limit:
            self.capped = self.capped or bool(self.pending)
            raise StopIteration
        if not self.pending:
            raise StopIteration
        return heapq.heappop(self.pending)[2]

    def prepare(self, target, actual_query):
        mark = normalized(actual_query)
        if mark in self.executed:
            return False
        self.executed.add(mark)
        if target['expansion'] == 'seed':
            for query, expansion in first_round(actual_query, self.mode, self.platform):
                self.add(query, target['original_query'], 1, actual_query, expansion)
        return True

    def extend(self, target, actual_query, rows):
        if self.mode == 'quick' or target['round'] >= self.rounds:
            return
        for row in rows:
            self.add(row.get('text'), target['original_query'], target['round'] + 1, actual_query, 'suggestion')
