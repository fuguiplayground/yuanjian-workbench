"""Run text-only Codex jobs using the local login, without project or tool access."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import threading
import time
import re


CONFIG_PATH = Path(__file__).resolve().parent / 'codex.local.json'


class AIError(ValueError):
    pass


class Cancelled(AIError):
    pass


DISABLED = ('shell_tool', 'unified_exec', 'apps', 'multi_agent', 'plugins', 'hooks',
            'browser_use', 'browser_use_external', 'computer_use', 'image_generation',
            'view_image', 'in_app_browser', 'in_app_local_automation',
            'workspace_dependencies', 'skill_search', 'skill_mcp_dependency_install',
            'sleep_tool', 'goals', 'code_mode', 'code_mode_host')


def executable():
    override = os.environ.get('FIELDWORK_CODEX_PATH')
    if override is None and CONFIG_PATH.exists():
        try:
            override = json.loads(CONFIG_PATH.read_text(encoding='utf-8-sig'))['executable']
            if not isinstance(override, str):
                return ''
        except (OSError, UnicodeError, ValueError, KeyError, TypeError):
            return ''
    if override is not None:
        # Never fall back to another CLI when an explicit selection is invalid.
        path = Path(override).expanduser()
        return str(path) if path.is_absolute() and path.is_file() and os.access(path, os.X_OK) else ''
    candidates = (shutil.which('codex'), str(Path.home() / '.local/bin/codex'),
                  '/Applications/Codex.app/Contents/Resources/codex',
                  '/Applications/ChatGPT.app/Contents/Resources/codex')
    return next((p for p in candidates if p and Path(p).is_file() and os.access(p, os.X_OK)), '')


def status():
    binary = executable()
    return {'available': bool(binary), 'executable': binary, 'provider': '本机 Codex',
            'note': '使用本机 Codex 登录与额度，无需另填 AI 密钥；分析会发送至 Codex 模型服务。'}


def configured_model():
    # Read only the non-sensitive model preference. Never load auth or provider secrets.
    path = Path(os.environ.get('CODEX_HOME', str(Path.home() / '.codex'))) / 'config.toml'
    try:
        with path.open(encoding='utf-8') as config:
            for line in config:
                if line.lstrip().startswith('['):
                    break
                match = re.fullmatch(r'''\s*model\s*=\s*["']([A-Za-z0-9._-]{1,100})["']\s*(?:#.*)?''', line.strip())
                if match:
                    return match.group(1)
        return ''
    except (OSError, UnicodeError):
        return ''


def feature_options():
    options = ['-c', 'features.skip_host_skill_discovery=true']
    for feature in DISABLED:
        options.extend(('-c', f'features.{feature}=false'))
    return options


def mcp_server_names(binary, directory, env):
    try:
        result = subprocess.run([binary, *feature_options(), 'mcp', 'list', '--json'],
                                cwd=directory, env=env, capture_output=True,
                                text=True, encoding='utf-8', timeout=15)
        if result.returncode:
            raise ValueError('MCP discovery failed')
        servers = json.loads(result.stdout)
        if not isinstance(servers, list) or any(
                not isinstance(server, dict) or not isinstance(server.get('name'), str)
                or not re.fullmatch(r'[A-Za-z0-9_-]{1,100}', server['name']) for server in servers):
            raise ValueError('Unsupported MCP configuration')
        return sorted({server['name'] for server in servers})
    except (OSError, UnicodeError, ValueError, subprocess.TimeoutExpired):
        raise AIError('无法确认 Codex 工具隔离配置，分析尚未启动；请检查本机 MCP 配置') from None


def command(binary, directory, schema, instructions, mcp_servers=()):
    # Keep the user's provider/auth routing; disable tools separately.
    cmd = [binary, 'exec', '--ignore-rules', '--ephemeral', '--skip-git-repo-check',
           '--sandbox', 'read-only', '--color', 'never', '--json',
           '--cd', str(directory), '--output-schema', str(schema),
           '-c', 'approval_policy="never"', '-c', 'web_search="disabled"',
           '-c', 'project_doc_max_bytes=0', '-c', 'developer_instructions=""',
           '-c', 'model_instructions_file=' + json.dumps(str(instructions)),
           '-c', 'model_reasoning_effort="low"']
    cmd.extend(feature_options())
    for name in mcp_servers:
        if not isinstance(name, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,100}', name):
            raise AIError('Codex MCP 名称不支持安全隔离，分析尚未启动')
        cmd.extend(('-c', f'mcp_servers.{name}.enabled=false'))
    if model := configured_model():
        cmd.extend(('--model', model))
    return cmd + ['-']


def run(system, payload, schema, cancel=None, timeout=600):
    binary = executable()
    if not binary:
        raise AIError('未找到可用的 Codex 程序，请检查 codex.local.json 或 FIELDWORK_CODEX_PATH 的路径配置')
    cancel = cancel or threading.Event()
    # Only prompt/schema files are temporary. Neither credentials nor raw CLI logs are saved.
    with tempfile.TemporaryDirectory(prefix='fieldwork-ai-') as folder:
        folder = Path(folder)
        spec, instructions = folder / 'schema.json', folder / 'instructions.md'
        spec.write_text(json.dumps(schema, ensure_ascii=False), encoding='utf-8')
        # Some compatible providers do not enforce the response schema themselves.
        format_instruction = ('\n\n最终输出格式要求（优先于前述方法素材中的格式示例）：\n'
                              '只返回一个严格符合以下 JSON Schema 的对象，不要 Markdown 代码围栏。'
                              '每层对象都必须包含全部 required 字段；不得添加、重命名、包装或省略字段。'
                              '缺少证据时在对应文字字段说明待验证，不编造事实，不修改证据编号。\n')
        instructions.write_text(system + format_instruction + json.dumps(schema, ensure_ascii=False, indent=2),
                                encoding='utf-8')
        env = {k: v for k, v in os.environ.items()
               if not k.startswith(('CODEX_THREAD', 'CODEX_TURN', 'CODEX_SANDBOX'))}
        servers = mcp_server_names(binary, folder, env)
        cmd = command(binary, folder, spec, instructions, servers)
        try:
            process = subprocess.Popen(cmd, cwd=folder, stdin=subprocess.PIPE,
                                       stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                       text=True, encoding='utf-8', env=env)
        except OSError:
            raise AIError('本机 Codex 无法启动；请确认 Codex 安装完整') from None
        started, input_ = time.monotonic(), json.dumps(payload, ensure_ascii=False)
        try:
            while True:
                if cancel.is_set():
                    raise Cancelled('AI 任务已取消；原始数据保留')
                if time.monotonic() - started > timeout:
                    raise AIError('本机 Codex 本次响应超时；原始数据保留，可重新生成')
                try:
                    output, error = process.communicate(input=input_, timeout=0.3)
                    break
                except subprocess.TimeoutExpired:
                    input_ = None
            if process.returncode:
                # Provider messages can include session or account details; expose fixed errors only.
                if any(s in (error + output).lower() for s in ('unauthorized', 'not logged in', '401', 'authentication')):
                    raise AIError('模型服务拒绝 Codex 认证，请核对 Codex 的服务配置和登录凭据')
                if any(s in (error + output).lower() for s in ('usage limit', 'rate limit', 'quota', '429')):
                    raise AIError('本机 Codex 可用额度不足或限流，请稍后再试')
                raise AIError('本机 Codex 返回失败，未写入分析结果；请检查 Codex 是否能正常对话')
            messages = []
            usage = {}
            for line in output.splitlines():
                try:
                    event = json.loads(line)
                except ValueError:
                    continue
                item = event.get('item') or {}
                if item.get('type') in ('command_execution', 'mcp_tool_call', 'web_search', 'file_change'):
                    raise AIError('AI 尝试使用分析范围外的工具，结果已拒绝')
                if event.get('type') == 'item.completed' and item.get('type') == 'agent_message':
                    messages.append(item.get('text', ''))
                if event.get('type') == 'turn.completed':
                    usage = {k: v for k, v in (event.get('usage') or {}).items()
                             if k in ('input_tokens', 'output_tokens', 'cached_input_tokens') and isinstance(v, int)}
            if not messages:
                raise AIError('本机 Codex 未返回可读取的分析结果')
            try:
                data = json.loads(messages[-1])
            except ValueError:
                raise AIError('AI 返回的格式无效，未写入分析结果') from None
            if not isinstance(data, dict):
                raise AIError('AI 返回的格式无效，未写入分析结果')
            return data, {'provider': '本机 Codex', 'model': configured_model() or 'Codex 默认模型', 'usage': usage}
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.communicate(timeout=3)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.communicate()
