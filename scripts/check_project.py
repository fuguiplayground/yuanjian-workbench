"""只读检查初始化、项目数据及可选的本机 HTTP 服务。"""
import argparse
import ast
import json
from pathlib import Path
import sys
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, build_opener


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def check(condition, message):
    if not condition:
        raise ValueError(message)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url', help='可选的本机服务地址，例如 http://127.0.0.1:8765')
    args = parser.parse_args()
    check(sys.version_info >= (3, 10), '需要 Python 3.10 或以上版本')
    sources = sorted(ROOT.glob('*.py')) + sorted((ROOT / 'scripts').glob('*.py'))
    for source in sources:
        ast.parse(source.read_text(encoding='utf-8'), filename=str(source))
    print(f'通过：{len(sources)} 个 Python 文件的语法检查')

    import server

    check((ROOT / 'data/projects').is_dir(), '本地项目目录不存在')
    store = server.Store(ROOT / 'data/projects')
    manifest = json.loads((ROOT / 'package-manifest.json').read_text(encoding='utf-8'))
    projects = store.listing()
    check(projects, '没有可读取的项目')
    check(all('error' not in project for project in projects), '存在无法读取的项目')
    project_ids = {project['id'] for project in projects}
    check({project['id'] for project in manifest['projects']} <= project_ids, '随包项目不完整')
    for project_id in project_ids:
        project = store.load(project_id)
        check(project['id'] == project_id, '项目编号与目录不一致')
    print(f'通过：{len(projects)} 个项目的版本校验和与读取检查')

    if args.url:
        url = args.url.rstrip('/')
        parsed = urlsplit(url)
        check(parsed.scheme == 'http' and parsed.hostname in ('127.0.0.1', 'localhost')
              and not parsed.username and not parsed.password and not parsed.path
              and not parsed.query and not parsed.fragment, '仅支持本机 HTTP 服务地址')
        opener = build_opener(ProxyHandler({}), NoRedirect())

        def get(path, expected_type):
            with opener.open(url + path, timeout=10) as response:
                check(response.status == 200, f'接口返回异常：{path}')
                check(response.headers.get_content_type() == expected_type, f'内容类型异常：{path}')
                payload = response.read()
                check(payload, f'接口返回为空：{path}')
                return json.loads(payload) if expected_type == 'application/json' else payload

        check(get('/api/health', 'application/json') == server.server_identity(store), '服务与当前工作目录或源码版本不一致')
        check(get('/api/projects', 'application/json') == projects, '服务项目列表与本地不一致')
        for project_id in project_ids:
            check(get('/api/projects/' + project_id, 'application/json') == store.load(project_id), '服务项目内容与本地不一致')
        get('/', 'text/html')
        for name in ('collection.js', 'research.js', 'workflow.js', 'watch.js'):
            get('/' + name, 'text/javascript')
        get('/workflow.css', 'text/css')
        get('/usage-flow.svg', 'image/svg+xml')
        print('通过：健康接口、全部项目读取、首页及全部静态资源')
    print('初始化验收完成；未调用第三方服务或修改业务数据。')


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, KeyError, SyntaxError) as error:
        print(f'验收失败：{error}', file=sys.stderr)
        raise SystemExit(1)
