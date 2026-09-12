"""One-time provisioning between the user's two verified Tailscale devices.

Only public routing metadata and a completion receipt are synchronized.
Provider keys travel inside the existing WireGuard network, then enter the
recipient's OS credential store. No public/LAN listener or arbitrary peers.
"""
import ipaddress
import json
from pathlib import Path
import shutil
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.request import Request, ProxyHandler, build_opener
from urllib.error import HTTPError
import credential_store
import sources
import sellersprite

ROOT = Path(__file__).resolve().parent
CONFIG = ROOT / '.device-setup.json'
RECEIPT = ROOT / '.device-setup-complete.json'
STATE = {'state': 'idle', 'note': ''}


def settings():
    if not CONFIG.exists():
        return None
    value = json.loads(CONFIG.read_text())
    net = ipaddress.ip_network('100.64.0.0/10')
    if any(ipaddress.ip_address(value[k]) not in net for k in ('source', 'target')) or \
       value['source'] == value['target'] or value.get('port') != 18765:
        raise ValueError('自动配置的设备地址无效')
    if not isinstance(value.get('expires_at'), (int, float)):
        raise ValueError('自动配置的有效期无效')
    return value


def own_ips():
    cli = shutil.which('tailscale') or '/Applications/Tailscale.app/Contents/MacOS/Tailscale'
    result = subprocess.run([cli, 'status', '--json'], capture_output=True, timeout=10)
    if result.returncode:
        return []
    return json.loads(result.stdout).get('Self', {}).get('TailscaleIPs', [])


def make_handler(config, receipt=RECEIPT):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def reply(self, code, value):
            data = json.dumps(value, ensure_ascii=False).encode()
            self.send_response(code)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(data)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.end_headers()
            self.wfile.write(data)

        def permitted(self):
            return (self.client_address[0] == config['target'] and not self.headers.get('Origin')
                    and self.headers.get('X-Fieldwork-Setup') == '1'
                    and self.headers.get('Host') == f"{config['source']}:{config['port']}"
                    and time.time() < config['expires_at'])

        def do_GET(self):
            if not self.permitted():
                return self.reply(403, {'error': 'device not allowed'})
            if self.path != '/connections':
                return self.reply(404, {})
            if receipt.exists():
                return self.reply(410, {'error': 'setup already completed'})
            records = {p: credential_store.read(p) for p in ('tikhub', 'sellersprite')}
            if not all(records.values()):
                return self.reply(503, {'error': 'source not ready'})
            self.reply(200, records)

        def do_POST(self):
            if not self.permitted():
                return self.reply(403, {'error': 'device not allowed'})
            if self.path != '/complete':
                return self.reply(404, {})
            # Acknowledgement contains no provider data. A later request is refused.
            receipt.write_text(json.dumps({'completed_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
                                           'providers': ['tikhub', 'sellersprite'], 'verified_on_target': True}))
            self.reply(200, {'complete': True})
    return Handler


def receive(config):
    if time.time() >= config['expires_at']:
        raise ValueError('本次自动配置窗口已到期')
    base = f"http://{config['source']}:{config['port']}"
    opener = build_opener(ProxyHandler({}), sources.NoRedirect())
    header = {'X-Fieldwork-Setup': '1'}
    missing = [p for p in ('tikhub', 'sellersprite') if not credential_store.read(p)]
    if missing:
        with opener.open(Request(base + '/connections', headers=header), timeout=12) as response:
            records = json.loads(response.read(8000))
        if not isinstance(records, dict) or set(records) != {'tikhub', 'sellersprite'} or \
           any(not isinstance(r, dict) or not isinstance(r.get('key'), str) or not r['key'] for r in records.values()):
            raise ValueError('自动配置数据格式无效')
        for provider in missing:
            record = records[provider]
            if provider == 'tikhub':
                sources.connect(record.get('key'), record.get('base_url'), persist=True)
            else:
                sellersprite.connect(record.get('key'), persist=True)
    if not all(credential_store.read(p) for p in ('tikhub', 'sellersprite')):
        raise ValueError('本机凭据尚未保存完整')
    with opener.open(Request(base + '/complete', data=b'', headers=header), timeout=12) as response:
        if response.status != 200:
            raise ValueError('自动配置确认未完成')


def serve():
    config = settings()
    if not config or RECEIPT.exists() or time.time() >= config['expires_at'] or config['source'] not in own_ips():
        return
    try:
        class Server(HTTPServer):
            def get_request(self):
                conn, addr = super().get_request()
                conn.settimeout(5)
                return conn, addr
        server = Server((config['source'], config['port']), make_handler(config))
    except OSError:
        return
    server.timeout = 2
    try:
        while not RECEIPT.exists() and time.time() < config['expires_at']:
            server.handle_request()
    finally:
        server.server_close()


def sender_ready(config):
    # The sender itself is deliberately denied. Check that the expected service
    # is listening without reading any credentials or trusting an occupied port.
    request = Request(f"http://{config['source']}:{config['port']}/connections",
                      headers={'X-Fieldwork-Setup': '1'})
    try:
        with build_opener(ProxyHandler({}), sources.NoRedirect()).open(request, timeout=2):
            return False
    except HTTPError as error:
        with error:
            return error.code == 403 and error.read(1000) == b'{"error": "device not allowed"}'
    except OSError:
        return False


def start():
    def worker():
        try:
            config = settings()
            if not config:
                return
            ips = own_ips()
            if config['source'] in ips:
                if not RECEIPT.exists() and time.time() < config['expires_at']:
                    # Independent lifetime: the first-use handoff survives closing the workbench.
                    subprocess.Popen([sys.executable, str(Path(__file__).resolve()), '--serve'],
                                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                     stderr=subprocess.DEVNULL, start_new_session=True)
                    for attempt in range(6):
                        if sender_ready(config):
                            STATE.update(state='waiting', note='接收设备首次打开会自动接入；本机已准备好连接。')
                            return
                        time.sleep(0.5)
                    STATE.update(state='failed', note='本机自动配置服务未就绪，已保存的本机数据源仍可使用。')
                return
            if config['target'] not in ips:
                return
            if all(credential_store.read(p) for p in ('tikhub', 'sellersprite')):
                STATE.update(state='ready', note='两项数据源已在本机配置，重启可自动读取。')
                return
            STATE.update(state='receiving', note='正在从来源设备自动配置数据源，请稍候…')
            for attempt in range(3):
                try:
                    receive(config)
                    STATE.update(state='ready', note='TikHub 与卖家精灵已自动接入并保存在本机。')
                    return
                except (OSError, ValueError, KeyError):
                    if attempt < 2:
                        time.sleep(8)
            STATE.update(state='failed', note='自动接入未完成，请确认两台设备的 Tailscale 在线，稍后重新打开工作台。')
        except (OSError, ValueError, subprocess.TimeoutExpired):
            STATE.update(state='failed', note='暂时无法确认设备私网连接，已保存的本机凭据仍可使用。')
    threading.Thread(target=worker, daemon=True).start()


def status():
    if RECEIPT.exists():
        return {'state': 'complete', 'note': '接收设备已完成两项数据源验证与本机保存。'}
    return dict(STATE)


if __name__ == '__main__' and '--serve' in sys.argv:
    serve()
