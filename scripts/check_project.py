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
STATIC_ASSETS = {**{name: 'text/javascript' for name in
                   ('business.js', 'collection.js', 'research.js', 'workflow.js', 'watch.js', 'keyword-controls.js')},
                 'workflow.css': 'text/css', 'insight-report.css': 'text/css',
                 'usage-flow.svg': 'image/svg+xml'}


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
    for name in ('index.html', *STATIC_ASSETS):
        path = ROOT / 'web' / name
        check(path.is_file() and path.stat().st_size > 0, f'前端资源缺失或为空：{name}')
    print('通过：首页及全部前端资源文件检查')

    import server

    data_path = ROOT / 'data/projects'
    check(not data_path.exists() or data_path.is_dir(), '本地项目路径不是目录')
    # A public clone has no bundled data. Read-only verification must not create it.
    store = server.Store(data_path) if data_path.is_dir() else None
    projects = store.listing() if store is not None else []
    check(all('error' not in project for project in projects), '存在无法读取的项目')
    project_ids = {project['id'] for project in projects}
    manifest_path = ROOT / 'package-manifest.json'
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
        check(isinstance(manifest, dict) and isinstance(manifest.get('projects'), list)
              and manifest['projects'], '随包项目清单格式无效或为空')
        check(all(isinstance(p, dict) and isinstance(p.get('id'), str) for p in manifest['projects']), '随包项目清单编号无效')
        required = [project['id'] for project in manifest['projects']]
        check(len(set(required)) == len(required) and set(required) <= project_ids, '随包项目不完整或编号重复')
    for project_id in project_ids:
        project = store.load(project_id)
        check(project['id'] == project_id, '项目编号与目录不一致')
    print(f'通过：{len(projects)} 个项目的版本校验和与读取检查')
    if not projects:
        print('公开源码初始化通过：当前没有项目，首次启动后可新建或导入。')

    if args.url:
        url = args.url.rstrip('/')
        parsed = urlsplit(url)
        check(parsed.scheme == 'http' and parsed.hostname in ('127.0.0.1', 'localhost')
              and not parsed.username and not parsed.password and not parsed.path
              and not parsed.query and not parsed.fragment, '仅支持本机 HTTP 服务地址')
        check(store is not None, '请先在当前目录启动工作台，再检查 HTTP 服务')
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
        for name, content_type in STATIC_ASSETS.items():
            get('/' + name, content_type)
        print('通过：健康接口、全部项目读取、首页及全部静态资源')
    print('初始化验收完成；未调用第三方服务或修改业务数据。')


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, KeyError, SyntaxError) as error:
        print(f'验收失败：{error}', file=sys.stderr)
        raise SystemExit(1)
