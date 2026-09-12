"""Device-local OS credential storage; no secrets in project files or argv."""
import ctypes
import json
import subprocess
import sys

SERVICE = 'fieldwork.sources'
PROVIDERS = ('tikhub', 'sellersprite')


def backend():
    return {'darwin': 'macOS 钥匙串', 'win32': 'Windows 凭据管理器'}.get(sys.platform, '')


def _windows(provider, data=None):
    from ctypes import wintypes as w
    class Credential(ctypes.Structure):
        _fields_ = [('Flags', w.DWORD), ('Type', w.DWORD), ('TargetName', w.LPWSTR),
                    ('Comment', w.LPWSTR), ('LastWritten', w.FILETIME),
                    ('CredentialBlobSize', w.DWORD), ('CredentialBlob', ctypes.POINTER(w.BYTE)),
                    ('Persist', w.DWORD), ('AttributeCount', w.DWORD), ('Attributes', ctypes.c_void_p),
                    ('TargetAlias', w.LPWSTR), ('UserName', w.LPWSTR)]
    dll = ctypes.WinDLL('Advapi32.dll', use_last_error=True)
    pointer = ctypes.POINTER(Credential)
    dll.CredReadW.argtypes = [w.LPCWSTR, w.DWORD, w.DWORD, ctypes.POINTER(pointer)]
    dll.CredReadW.restype = w.BOOL
    dll.CredWriteW.argtypes = [pointer, w.DWORD]
    dll.CredWriteW.restype = w.BOOL
    dll.CredFree.argtypes = [ctypes.c_void_p]
    dll.CredFree.restype = None
    target = SERVICE + ':' + provider
    if data is not None:
        blob = (w.BYTE * len(data)).from_buffer_copy(data)
        credential = Credential(Type=1, TargetName=target, CredentialBlobSize=len(data),
                                CredentialBlob=blob, Persist=2, UserName=provider)
        if not dll.CredWriteW(ctypes.byref(credential), 0):
            raise ValueError('Windows 凭据保存失败，请检查当前用户权限')
        return None
    result = pointer()
    if not dll.CredReadW(target, 1, 0, ctypes.byref(result)):
        if ctypes.get_last_error() == 1168:
            return None
        raise ValueError('Windows 凭据暂不可读取，请检查当前用户会话')
    try:
        return ctypes.string_at(result.contents.CredentialBlob, result.contents.CredentialBlobSize)
    finally:
        dll.CredFree(result)


def read(provider):
    if provider not in PROVIDERS:
        raise ValueError('未知数据源')
    try:
        if sys.platform == 'darwin':
            result = subprocess.run(['/usr/bin/security', 'find-generic-password', '-s', SERVICE,
                                     '-a', provider, '-w'], capture_output=True, timeout=15)
            if result.returncode != 0:
                return None
            raw = result.stdout.strip()
        elif sys.platform == 'win32':
            raw = _windows(provider)
        else:
            return None
        value = json.loads(raw) if raw else None
        return value if isinstance(value, dict) and isinstance(value.get('key'), str) else None
    except (OSError, subprocess.TimeoutExpired, ValueError):
        return None


def save(provider, record):
    if provider not in PROVIDERS or not isinstance(record, dict) or not record.get('key'):
        raise ValueError('凭据格式无效')
    data = json.dumps(record, ensure_ascii=True, separators=(',', ':')).encode()
    if len(data) > 2500:
        raise ValueError('凭据过长，未保存')
    try:
        if sys.platform == 'darwin':
            # Hex data travels over stdin, never through process arguments or a shell.
            command = f'add-generic-password -U -s {SERVICE} -a {provider} -X {data.hex()}\n'
            subprocess.run(['/usr/bin/security', '-i'], input=command.encode(),
                           capture_output=True, timeout=30)
        elif sys.platform == 'win32':
            _windows(provider, data)
        else:
            raise ValueError('本系统暂不支持安全保存，请使用仅本次连接')
    except (OSError, subprocess.TimeoutExpired):
        raise ValueError('系统凭据库保存失败，请解锁后重试') from None
    if read(provider) != record:
        raise ValueError('凭据保存未通过回读校验，未标记为已保存')
